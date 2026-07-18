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
        # `ollama pull <model>` (e.g. "mistral", "llama3", "phi3", "qwen2.5:0.5b").
        self.model = "qwen2.5:0.5b"
        # How many of the most recent turns to feed back into the prompt.
        # Sending the FULL transcript every turn (unbounded) means the
        # prompt keeps growing round after round, and Ollama has to
        # re-process all of it before it can even start generating --
        # capping this keeps response time roughly constant across a long
        # debate instead of getting slower turn by turn. Kept short (4) on
        # top of that because very small models (e.g. qwen2.5:0.5b) start
        # losing track of who's who and drifting off-topic with too much
        # context crammed in.
        self.max_history_turns = 4
        # Labels used in the transcript fed back to the model. Small models
        # tend to just continue the "Speaker: text" pattern they see in
        # their own input rather than stopping after their own turn, so we
        # pass these to Ollama's "stop" option to force generation to halt
        # the instant the model starts hallucinating the other side's line,
        # and also use them below to hard-trim anything that slips through.
        self.speaker_labels = ["Advocate (Agent A):", "Challenger (Agent B):"]

    def _clean_response(self, raw_text, own_label, other_label):
        """
        Small/fast local models (like qwen2.5:0.5b) frequently keep
        generating past their own turn and start impersonating the other
        speaker, because that's the pattern they just saw in the prompt's
        transcript. This:
          1. Strips a leading self-label if the model echoed its own name
             (e.g. "Advocate (Agent A): ...") instead of discarding it.
          2. Cuts off everything from the OTHER speaker's label onward.
          3. Drops a trailing sentence fragment if num_predict cut the
             reply off mid-sentence.
        """
        text = raw_text.strip()

        # Strip a leading self-label ("Advocate (Agent A): ...") -- this is
        # just the model echoing its own name, the content after it is
        # still the model's genuine argument and should be kept.
        if text.lower().startswith(own_label.lower()):
            text = text[len(own_label):].strip()

        # Cut off everything from the OTHER speaker's label onward -- this
        # is the actual hallucinated turn that needs to be discarded.
        idx = text.lower().find(other_label.lower())
        if idx != -1:
            text = text[:idx].strip()

        if not text:
            return raw_text.strip()  # nothing usable left, fall back to raw

        # If the response was truncated mid-sentence (no trailing
        # punctuation), trim back to the last complete sentence so we don't
        # show a dangling fragment like "...I believe".
        if text and text[-1] not in ".!?":
            last_punct = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
            if last_punct != -1:
                text = text[:last_punct + 1].strip()

        return text or raw_text.strip()

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
    def _call_ollama(self, system_prompt, user_prompt, own_label, other_label, fallback_line, _is_retry=False):
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                # num_predict caps how many tokens the model is allowed to
                # generate. 90 gives small/fast models (e.g. qwen2.5:0.5b)
                # enough room to actually finish a sentence instead of
                # getting cut off mid-thought, while still keeping turns
                # quick enough to fit several exchanges in a short debate.
                "num_predict": 90,
                # Force generation to stop the moment the model starts
                # writing the OTHER speaker's line -- this is the main fix
                # for small models that "continue the transcript" instead
                # of stopping after their own turn.
                "stop": self.speaker_labels,
            },
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
        raw_reply = data.get("response", "").strip()

        # An empty raw_reply almost always means the model's very FIRST
        # tokens were the other speaker's label -- our "stop" sequence cut
        # generation before returning anything at all. This is the same
        # "model wrote nothing of its own" failure as below, just
        # discovered earlier (at the raw-response stage instead of after
        # cleaning), so it gets routed through the same retry/fallback path
        # rather than surfacing a raw error string in the debate feed.
        if not raw_reply:
            if not _is_retry:
                nudged_prompt = user_prompt + (
                    "\n\nRespond now, starting immediately with YOUR OWN argument "
                    "(do not repeat or restate the other speaker's line first)."
                )
                return self._call_ollama(
                    system_prompt, nudged_prompt, own_label, other_label,
                    fallback_line, _is_retry=True
                )
            return fallback_line  # retry also came back empty -- use the canned line

        cleaned = self._clean_response(raw_reply, own_label, other_label)

        # Occasionally a very small model skips its own argument entirely
        # and just opens by echoing the OTHER speaker's line -- there's no
        # genuine content left to salvage by trimming in that case. Retry
        # once with a more forceful nudge before giving up.
        if cleaned.lower().startswith(other_label.lower()) and not _is_retry:
            nudged_prompt = user_prompt + (
                "\n\nRespond now, starting immediately with YOUR OWN argument "
                "(do not repeat or restate the other speaker's line first)."
            )
            return self._call_ollama(
                system_prompt, nudged_prompt, own_label, other_label,
                fallback_line, _is_retry=True
            )

        if cleaned.lower().startswith(other_label.lower()):
            return fallback_line  # retry also failed -- use a graceful canned line

        return cleaned

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
            "Keep your response to 1-2 short, punchy sentences -- brevity wins here. "
            "IMPORTANT: Output ONLY your own argument as plain text. Do NOT write "
            "'Advocate:' or 'Challenger:' labels, do NOT write the other speaker's "
            "line, and do NOT continue the conversation beyond your own turn."
        )

        history_block = self._format_history()
        user_prompt = (
            f"Debate topic: \"{topic}\"\n\n"
            f"Transcript so far:\n{history_block}\n\n"
            "Give your next argument as the Advocate. If the Challenger has already "
            "spoken, directly rebut their strongest point before adding a new one.\n\n"
            # Priming the prompt with the agent's own label (instead of only
            # relying on instructions) nudges small/fast models to continue
            # generation directly in the right voice, rather than pattern-
            # matching the transcript and drifting into the other speaker's
            # turn from the very first token.
            "Advocate (Agent A):"
        )

        reply = self._call_ollama(
            system_prompt, user_prompt,
            own_label="Advocate (Agent A):", other_label="Challenger (Agent B):",
            fallback_line="The evidence in favor of this position remains compelling, "
                          "and I'd urge us not to dismiss it too quickly."
        )
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
            "punchy sentences -- brevity wins here. "
            "IMPORTANT: Output ONLY your own argument as plain text. Do NOT write "
            "'Advocate:' or 'Challenger:' labels, do NOT write the other speaker's "
            "line, and do NOT continue the conversation beyond your own turn."
        )

        history_block = self._format_history()
        user_prompt = (
            f"Debate topic: \"{topic}\"\n\n"
            f"Transcript so far:\n{history_block}\n\n"
            "Give your next argument as the Challenger. Directly rebut the "
            "Advocate's strongest point before adding a new one.\n\n"
            # See matching comment in generate_agent_a_response -- priming
            # with the agent's own label nudges the model to continue
            # directly in the right voice from the first generated token.
            "Challenger (Agent B):"
        )

        reply = self._call_ollama(
            system_prompt, user_prompt,
            own_label="Challenger (Agent B):", other_label="Advocate (Agent A):",
            fallback_line="That argument doesn't hold up under scrutiny -- the "
                          "evidence is far shakier than it's being presented."
        )
        self.add_to_history("B", reply)
        return reply
