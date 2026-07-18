# Autonomous AI Debate Chamber

Two locally-run LLM agents — an **Advocate** and a **Challenger** — debate any topic you give them in real time, with full memory of the transcript so they actually rebut each other instead of repeating themselves. When the debate ends, a **scikit-learn regression model** scores both sides' arguments and declares a winner.

Everything runs locally: the LLM inference (via Ollama) and the ML scoring both happen on your own machine, with no external API keys required.

## How it works

```
frontend/index.html  ──fetch──▶  app.py (Flask)  ──┬──▶ services/aiService.py ──▶ Ollama (local LLM)
                                                     └──▶ services/mlJudge.py  ──▶ scikit-learn
```

1. **You start a debate** with a topic. Flask calls `DebateConductor.generate_agent_a_response()`, which sends a persona system prompt + the topic to your local Ollama model.
2. **Each "Pass Turn"** alternates agents. Every prompt sent to Ollama includes the full transcript so far (`_format_history()`), so Agent B can directly attack what Agent A just said, and vice versa — this is the "memory loop."
3. **"End Debate & Judge"** sends each agent's full combined transcript to `/api/machine-learning/evaluate`. This:
   - Trains (or re-trains) a `RandomForestRegressor` on `historical_debates.csv`, a mock dataset of past debates rated by human judges.
   - Extracts numeric features from both agents' text (word count, vocabulary complexity, sentiment, rhetorical emphasis).
   - Predicts a 1–10 persuasiveness score for each side and declares a winner.

## Project structure

```
aiDebateChamber/
├── app.py                    # Flask routes wiring the UI to both services
├── services/
│   ├── aiService.py          # Ollama integration + debate memory (DebateConductor)
│   └── mlJudge.py            # Feature extraction + RandomForestRegressor (DebateRegressionJudge)
├── historical_debates.csv    # Mock training data for the ML judge
├── frontend/
│   ├── index.html            # Main UI
│   ├── demo.html              # Static mockup of the intended end state
│   ├── css/, js/
├── requirements.txt
└── ASSIGNMENT_BRIEF.md        # Original task brief this project was built against
```

## Setup

**1. Python environment**
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Local LLM (Ollama)**
```bash
# install from https://ollama.com, then:
ollama pull mistral
ollama serve
```
`services/aiService.py` targets `mistral` by default — change `self.model` there if you pull a different model.

**3. Run the backend**
```bash
python app.py
```
Runs on `http://127.0.0.1:5000`.

**4. Open the frontend**
Open `frontend/index.html` directly in a browser. If your browser blocks `fetch` calls from a `file://` page, instead run:
```bash
cd frontend && python -m http.server 8000
```
and visit `http://localhost:8000`.

## Using the app

1. Enter a debate topic and click **Initialize Nodes** — Agent A (Advocate) gives its opening statement.
2. Click **Pass Turn** repeatedly to let Agent A and Agent B alternate rebuttals.
3. Click **End Debate & Judge** to train/run the ML model and reveal the verdict overlay with both agents' scores.

## The ML model

`DebateRegressionJudge` extracts four features per argument:

| Feature | What it captures |
|---|---|
| `word_count` | Raw length |
| `complexity_score` | Vocabulary richness (unique words / total words) |
| `sentiment_score` | Lexicon-based polarity in [-1, 1] |
| `exclamation_count` | Rhetorical emphasis |

A `RandomForestRegressor` (200 trees, max depth 6) is trained on `historical_debates.csv` with an 80/20 train/test split, chosen over a linear model because persuasiveness isn't a simple additive function of these features — the forest can pick up interactions (e.g., medium length + high complexity outperforming very long + low complexity) without manual feature-crossing.

## Notes

- The model retrains from scratch every time `/api/machine-learning/train` is called (or lazily on first `/evaluate` call) — there's no persisted model file, since the dataset is small enough that retraining is instant.
- `historical_debates.csv` is synthetic mock data, not real debate transcripts, per the assignment brief.
