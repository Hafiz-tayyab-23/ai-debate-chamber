# Autonomous AI Debate Chamber

Welcome to your Machine Learning Engineering sprint! In this project, you will construct a robust Python backend that pits two Generative AI models against each other in a logical debate, which is then mathematically evaluated by a Predictive Regression Model.

IMPORTANT FIRST STEP: Open "frontend/demo.html" in your browser right now and click "Run Mockup Simulation". This will show you exactly what the final product is supposed to look like!


The Objective
-------------
We have provided the complete Frontend Web UI and the foundational Python API Routing Gateway (app.py). 
Your task is to implement the missing Generative AI and Machine Learning logic in the backend to bring the system to life.

1. Local LLM Integration: You must use any local LLM runner of your choice (e.g., Ollama, LM Studio, GPT4All) to run a lightweight model locally on your machine.
2. Context Memory: Program the Python API to remember previous debate turns so the agents can logically attack each other's points.
3. The ML Judge (Scikit-Learn Regression): Analyze the text output mathematically (e.g., word counts, sentiment, complexity) and pass it through a trained Regression model to crown a victor based on real-world training data.


Step-by-Step Implementation Guide
---------------------------------

Step 1: Initialize the Environment
- Download this repository.
- Install Python 3.10+ and set up a virtual environment: "python -m venv venv"
- Activate the environment and install dependencies: "pip install flask flask-cors requests pandas scikit-learn numpy"
- Download and set up your preferred local LLM runner and pull any model you like.

Step 2: Implement the Agents (services/aiService.py)
- Open aiService.py. You will see empty functions for Agent A and Agent B.
- Write Python logic using the requests library (or an SDK) to send payloads to your local LLM server.
- Design aggressive, persona-driven System Prompts for each agent.

Step 3: Train the Regression Model (services/mlJudge.py)
- Create a mock CSV dataset (historical_debates.csv) holding columns like: word_count, complexity_score, and human_persuasiveness_score.
- Load this using pandas, split the data using train_test_split, and fit a RandomForestRegressor.
- In predict_score(), extract mathematical features from the LLMs' underlying text and generate a final 1-10 predictive rating.

Step 4: Final Sandbox Testing
- Run "python app.py".
- Open "frontend/index.html" in your browser. 
- Type a topic and click Initialize Nodes.


Evaluation & Grading Rubric (100 Points + Bonus)
------------------------------------------------

Because this architecture relies on Local AI Execution, we cannot simply blindly run your code on our end. You must explicitly prove your execution environment works by providing a physical demonstration, alongside submitting your code for structural review.

1. Task Completion & Logic Execution (50 Points)
We will review the ZIP file containing your source code to verify the following mechanics:
- Generative Integration: Your API successfully hits your local model endpoint and returns formatted JSON text correctly.
- Memory Loop: Your Python logic references previously stated arguments in the prompt, rather than wiping the context window blank every turn.
- Regression Math: Your Scikit-Learn script successfully loads a dataset, fits a model, and returns a mathematical prediction.

2. Video Demonstration (40 Points) (CRITICAL FOR VERIFICATION)
Because the debate lasts 5 minutes, there is no strict time limit on the video. You must record your screen demonstrating the fully functioning system from start to finish.
- Show your terminal running the Flask server and your local LLM engine.
- Showcase the index.html UI in action as the debate organically unfolds.
- CRITICAL: You must show the very end of the debate where the ML Judge overlay appears, displaying the final ML Verdict and calculating the exact scores for each model.
- Submission Details: Upload this video to LinkedIn (tagging Zenvyro Labs) or upload it to YouTube/Google Drive and submit the public URL alongside your code. 
- Bonus Points: Posting the video publicly to LinkedIn will earn you explicit bonus points!

3. Code Cleanliness & Structure (10 Points)
- Heavy documentation blocking (comments detailing why you chose specific regression features).
- Code must be formatted professionally with no massive unhandled exceptions or excessively messy scripts.
