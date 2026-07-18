import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from services.aiService import DebateConductor
from services.mlJudge import DebateRegressionJudge

app = Flask(__name__)
CORS(app)  # Allow Cross-Origin Requests from the UI

# System Modules
conductor = DebateConductor()
ml_judge = DebateRegressionJudge()

# Absolute path so `python app.py` works regardless of the current working
# directory the intern launches it from.
DATASET_PATH = os.path.join(os.path.dirname(__file__), "historical_debates.csv")


def _ensure_judge_trained():
    """Lazily trains the regression judge the first time it's needed."""
    if ml_judge.model is None:
        ml_judge.train_model(DATASET_PATH)


@app.route('/api/debate/start', methods=['POST'])
def start_debate():
    """Initializes the debate: resets memory and generates Agent A's opening statement."""
    data = request.json
    topic = data.get('topic')

    if not topic:
        return jsonify({"error": "A debate topic is required."}), 400

    conductor.reset_history()
    message = conductor.generate_agent_a_response(topic)

    return jsonify({"status": "active", "topic": topic, "agent": "A", "message": message})


@app.route('/api/debate/next-turn', methods=['POST'])
def next_turn():
    """Triggers the next LLM agent to generate a rebuttal via local Ollama."""
    data = request.json
    topic = data.get('topic')
    last_speaker = data.get('last_speaker')

    if not topic:
        return jsonify({"error": "A debate topic is required."}), 400

    # Whoever didn't speak last goes next.
    next_agent = 'B' if last_speaker == 'A' else 'A'

    if next_agent == 'A':
        message = conductor.generate_agent_a_response(topic)
    else:
        message = conductor.generate_agent_b_response(topic)

    return jsonify({"agent": next_agent, "message": message})


@app.route('/api/machine-learning/train', methods=['POST'])
def trigger_training():
    """Triggers the SciKit-Learn Regression Model Training Loop."""
    try:
        accuracy_metrics = ml_judge.train_model(DATASET_PATH)
        return jsonify({"status": "Training Completed", "metrics": accuracy_metrics})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/machine-learning/evaluate', methods=['POST'])
def evaluate_debate():
    """Uses the Trained ML model to score each agent's cumulative arguments."""
    data = request.json
    advocate_text = data.get('advocate_text', '')
    challenger_text = data.get('challenger_text', '')

    if not advocate_text and not challenger_text:
        return jsonify({"error": "advocate_text and/or challenger_text is required."}), 400

    try:
        _ensure_judge_trained()

        advocate_score = ml_judge.predict_score(advocate_text)
        challenger_score = ml_judge.predict_score(challenger_text)

        if advocate_score > challenger_score:
            winner = "A"
        elif challenger_score > advocate_score:
            winner = "B"
        else:
            winner = "Tie"

        return jsonify({
            "winner": winner,
            "advocate_score": advocate_score,
            "challenger_score": challenger_score,
            "metrics": ml_judge.last_metrics,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("🚀 AI Server running on http://127.0.0.1:5000")
    print("Ensure Ollama is running locally on port 11434!")
    app.run(debug=True, port=5000)
