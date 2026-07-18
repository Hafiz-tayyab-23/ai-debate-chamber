import re
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

# --------------------------------------------------------------------------
# WHY RandomForestRegressor?
# Debate "persuasiveness" is not a simple linear function of word count or
# sentiment alone -- a very long, purely positive argument is not
# automatically the most persuasive one. A tree-based ensemble can capture
# these non-linear interactions between features (e.g. "medium length +
# high complexity" scoring higher than "very long + low complexity")
# without us having to hand-engineer interaction terms the way plain
# LinearRegression would require.
# --------------------------------------------------------------------------

# A tiny hand-built polarity lexicon so we don't need to download external
# NLTK/VADER corpora at runtime (keeps the intern setup to just
# pandas/numpy/scikit-learn, per the README's pip install line).
_POSITIVE_WORDS = {
    "great", "strong", "clearly", "proven", "benefit", "benefits", "improve",
    "improves", "innovation", "opportunity", "opportunities", "growth",
    "efficient", "effective", "advantage", "advantages", "success",
    "successful", "gain", "gains", "positive", "progress", "solution",
    "solutions", "reliable", "trust", "trusted", "empower", "empowers"
}
_NEGATIVE_WORDS = {
    "fail", "fails", "failure", "risk", "risks", "risky", "danger",
    "dangerous", "flawed", "weak", "wrong", "problem", "problems", "worse",
    "harm", "harms", "harmful", "collapse", "crisis", "loss", "losses",
    "negative", "threat", "threats", "unsafe", "broken", "unrealistic"
}


class DebateRegressionJudge:
    def __init__(self):
        self.model = None  # Populated by train_model()
        self.feature_names = [
            "word_count",
            "complexity_score",
            "sentiment_score",
            "exclamation_count",
        ]
        self.last_metrics = None

    # ----------------------------------------------------------------
    # FEATURE ENGINEERING
    # ----------------------------------------------------------------
    def extract_NLP_features(self, text):
        """
        Machine Learning models require NUMBERS, not text.
        Convert the raw text argument into mathematical features.

        - word_count: raw length signal (very short arguments rarely
          persuade a judge, very long ones can ramble).
        - complexity_score: vocabulary richness = unique_words / total_words.
          A higher ratio means the speaker isn't just repeating the same
          few words, which historically correlates with more sophisticated
          argumentation.
        - sentiment_score: naive lexicon-based polarity in [-1, 1]. Debates
          that lean too negative/whiny tend to score lower with human
          judges than confidently-framed (but not necessarily "happy")
          arguments, so we keep this as a signed signal rather than a
          strict positive/negative classifier.
        - exclamation_count: proxy for rhetorical emphasis / emotional
          appeals, which the mock training data treats as a mild positive
          signal up to a point (it's capped implicitly since it's rare in
          our historical set to have more than 2-3).
        """
        words = re.findall(r"[A-Za-z']+", text.lower())
        word_count = len(words)

        if word_count == 0:
            return {
                "word_count": 0,
                "complexity_score": 0.0,
                "sentiment_score": 0.0,
                "exclamation_count": 0,
            }

        unique_words = set(words)
        complexity_score = round(len(unique_words) / word_count, 4)

        pos_hits = sum(1 for w in words if w in _POSITIVE_WORDS)
        neg_hits = sum(1 for w in words if w in _NEGATIVE_WORDS)
        polarity_denom = pos_hits + neg_hits
        sentiment_score = round((pos_hits - neg_hits) / polarity_denom, 4) if polarity_denom else 0.0

        exclamation_count = text.count("!")

        return {
            "word_count": word_count,
            "complexity_score": complexity_score,
            "sentiment_score": sentiment_score,
            "exclamation_count": exclamation_count,
        }

    def _features_to_row(self, features_dict):
        """Order a features dict into the exact column order the model expects."""
        return [features_dict[name] for name in self.feature_names]

    # ----------------------------------------------------------------
    # TRAINING
    # ----------------------------------------------------------------
    def train_model(self, dataset_path):
        """
        Trains the Regression Model to score debates based on historical
        (mock) human-judged data.
        """
        print(f"Loading dataset from {dataset_path}...")
        df = pd.read_csv(dataset_path)

        required_cols = self.feature_names + ["human_persuasiveness_score"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Dataset is missing required columns: {missing}")

        X = df[self.feature_names].values
        y = df["human_persuasiveness_score"].values

        # Hold back 20% of the historical debates purely for evaluating how
        # well the model generalizes -- never trained on this slice.
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # n_estimators=200 gives the forest enough trees to stabilize
        # variance on a fairly small mock dataset; max_depth caps
        # overfitting since we only have ~40 historical rows.
        self.model = RandomForestRegressor(
            n_estimators=200, max_depth=6, random_state=42
        )
        self.model.fit(X_train, y_train)

        predictions = self.model.predict(X_test)
        mse = float(mean_squared_error(y_test, predictions))
        r2 = float(r2_score(y_test, predictions))

        self.last_metrics = {"mse": round(mse, 4), "r2_score": round(r2, 4)}
        print(f"Model Trained! MSE={self.last_metrics['mse']} R2={self.last_metrics['r2_score']}")

        return self.last_metrics

    # ----------------------------------------------------------------
    # LIVE INFERENCE
    # ----------------------------------------------------------------
    def predict_score(self, text):
        """
        Called live during the AI debate to judge one side's argument text.
        Returns a 1-10 predictive persuasiveness rating.
        """
        if self.model is None:
            raise Exception("Model is not trained yet! Call train_model() first.")

        features = self.extract_NLP_features(text)
        row = np.array(self._features_to_row(features)).reshape(1, -1)

        raw_score = float(self.model.predict(row)[0])
        # Clamp to the 1-10 scale the UI expects, since the RandomForest's
        # output range is bounded by the training labels but small
        # extrapolations on live (unseen) text can nudge slightly outside it.
        bounded_score = max(1.0, min(10.0, raw_score))
        return round(bounded_score, 2)

    # ----------------------------------------------------------------
    # HUMAN-READABLE ANALYSIS
    # ----------------------------------------------------------------
    def generate_analysis(self, features_a, features_b, score_a, score_b):
        """
        Raw regression internals (MSE, R^2) are useful for US to sanity-check
        the model during development, but they mean nothing to someone
        watching the debate. This turns the same underlying features the
        model actually used into a plain-English explanation of WHY one
        side scored higher -- comparing word count, vocabulary richness,
        tone, and rhetorical emphasis side by side.
        """
        insights = []

        # Word count comparison
        wc_diff = features_a["word_count"] - features_b["word_count"]
        if abs(wc_diff) >= 5:
            longer = "Agent A" if wc_diff > 0 else "Agent B"
            insights.append(
                f"{longer} built a substantially longer overall case "
                f"({features_a['word_count']} vs {features_b['word_count']} words), "
                "giving the model more material to work with."
            )
        else:
            insights.append(
                f"Both sides argued at a similar length "
                f"({features_a['word_count']} vs {features_b['word_count']} words)."
            )

        # Vocabulary complexity comparison
        cx_diff = features_a["complexity_score"] - features_b["complexity_score"]
        if abs(cx_diff) >= 0.05:
            richer = "Agent A" if cx_diff > 0 else "Agent B"
            insights.append(
                f"{richer} used richer, less repetitive vocabulary "
                f"({features_a['complexity_score']*100:.0f}% vs {features_b['complexity_score']*100:.0f}% unique words), "
                "a signal the model associates with more sophisticated argumentation."
            )

        # Sentiment / tone comparison
        sent_diff = features_a["sentiment_score"] - features_b["sentiment_score"]
        if abs(sent_diff) >= 0.1:
            more_positive = "Agent A" if sent_diff > 0 else "Agent B"
            insights.append(
                f"{more_positive} framed its argument more confidently and positively, "
                "which the historical training data links to slightly higher persuasiveness."
            )
        else:
            insights.append("Both sides struck a similarly confident tone.")

        # Rhetorical emphasis
        if features_a["exclamation_count"] != features_b["exclamation_count"]:
            emphatic = "Agent A" if features_a["exclamation_count"] > features_b["exclamation_count"] else "Agent B"
            insights.append(f"{emphatic} leaned more on emphatic, exclamatory delivery.")

        # Final verdict line
        score_gap = round(abs(score_a - score_b), 2)
        if score_gap < 0.3:
            insights.append(
                f"The final scores came out nearly tied ({score_a} vs {score_b}) -- "
                "this was a close, evenly matched debate."
            )
        else:
            winner = "Agent A (The Advocate)" if score_a > score_b else "Agent B (The Challenger)"
            insights.append(
                f"Overall, {winner} came out ahead ({max(score_a, score_b)} vs {min(score_a, score_b)}) "
                "based on this combination of factors."
            )

        return insights
