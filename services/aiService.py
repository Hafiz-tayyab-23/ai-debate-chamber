import requests


class DebateConductor:
    """
    Wraps calls to a locally-running Ollama server and keeps a running
    transcript of the debate so each agent can reference (and attack)
    what the other side already said.
    """

    def __init__(self):
        # We enforce local Ollama default port for maximum data privacy
        self.ollama_url = "http://localhost:11434/api/generate"
        # Each entry: {"speaker": "A" | "B", "text": "..."}
        self.debate_history = []
        # Lightweight local model -- swap for whatever you pulled via
        # `ollama pull <model>` (e.g. "mistral", "llama3", "phi3").
        self.model = "phi3"
        # How many of the most recent turns to feed back into the prompt.
        # Sending the FULL transcript every turn (unbounded) means the
        # prompt keeps growing round after round, and Ollama has to
        # re-process all of it before it can even start generating --
        # capping this keeps response time roughly constant across a long
        # debate instead of getting slower turn by turn. 6 turns (~3 full
        # back-and-forth exchanges) is enough for agents to still directly
        # rebut what was just said.
        self.max_history_turns = 6

    # ------------------------------------------------------------
    # MEMORY HELPERS
    # ------------------------------------------------------------
    def reset_history(self):
        self.debate_history = []

    def add_to_history(self, speaker, text):
        self.debate_history.append({"speaker": speaker, "text": text})

    def _format_history(self):
        """
        Turns the stored transcript into readable context the LLM can
        quote/attack in its next turn. Without this, every prompt would
        start from a blank context window and the agents would just
        restate opening arguments forever instead of engaging with each
        other's points.
        """
        if not self.debate_history:
            return "No arguments have been made yet. This is the opening statement."

        recent_turns = self.debate_history[-self.max_history_turns:]
        lines = []
        for turn in recent_turns:
            label = "Advocate (Agent A)" if turn["speaker"] == "A" else "Challenger (Agent B)"
            lines.append(f"{label}: {turn['text']}")
        return "\n".join(lines)

    # ------------------------------------------------------------
    # OLLAMA CALL
    # ------------------------------------------------------------
    def _call_ollama(self, system_prompt, user_prompt):
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            # num_predict caps how many tokens the model is allowed to
            # generate. Kept intentionally tight (60 tokens ~= 2-3 short
            # sentences) so each turn finishes quickly enough to fit several
            # full exchanges inside a short 2-3 minute debate window --
            # this is usually the single biggest speed lever available.
            "options": {"num_predict": 60},
        }
        try:
            response = requests.post(self.ollama_url, json=payload, timeout=300)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            # Surfaced to the frontend as the agent's "message" so the UI
            # still shows something instead of crashing the Flask route.
            return f"[Ollama connection error: {e}. Is `ollama serve` running on port 11434?]"

        data = response.json()
        # Ollama's non-streaming /api/generate response puts the full text
        # under the "response" key.
        return data.get("response", "").strip() or "[Ollama returned an empty response]"

    # ------------------------------------------------------------
    # AGENT A -- THE ADVOCATE
    # ------------------------------------------------------------
    def generate_agent_a_response(self, topic):
        """
        Agent A fiercely DEFENDS the topic.
        """
        system_prompt = (
            "You are Agent A, 'The Advocate', in a formal AI debate chamber. "
            "You passionately and confidently ARGUE IN FAVOR of the given topic. "
            "You are persuasive, cite plausible-sounding evidence and reasoning, "
            "and directly rebut the Challenger's previous point when one exists. "
            "Keep your response to 1-2 short, punchy sentences -- brevity wins here."
        )

        history_block = self._format_history()
        user_prompt = (
            f"Debate topic: \"{topic}\"\n\n"
            f"Transcript so far:\n{history_block}\n\n"
            "Give your next argument as the Advocate. If the Challenger has already "
            "spoken, directly rebut their strongest point before adding a new one."
        )

        reply = self._call_ollama(system_prompt, user_prompt)
        self.add_to_history("A", reply)
        return reply

    # ------------------------------------------------------------
    # AGENT B -- THE CHALLENGER
    # ------------------------------------------------------------
    def generate_agent_b_response(self, topic):
        """
        Agent B fiercely CHALLENGES the topic.
        """
        system_prompt = (
            "You are Agent B, 'The Challenger', in a formal AI debate chamber. "
            "You passionately and confidently ARGUE AGAINST the given topic. "
            "You are skeptical, poke holes in the Advocate's reasoning, and cite "
            "plausible-sounding counter-evidence. Directly rebut the Advocate's "
            "previous point when one exists. Keep your response to 1-2 short, "
            "punchy sentences -- brevity wins here."
        )

        history_block = self._format_history()
        user_prompt = (
            f"Debate topic: \"{topic}\"\n\n"
            f"Transcript so far:\n{history_block}\n\n"
            "Give your next argument as the Challenger. Directly rebut the "
            "Advocate's strongest point before adding a new one."
        )

        reply = self._call_ollama(system_prompt, user_prompt)
        self.add_to_history("B", reply)
        return reply
