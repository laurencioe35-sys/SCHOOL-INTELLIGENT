from __future__ import annotations


class TextToSpeechAdapter:
    provider = "unconfigured"

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            raise ValueError("Text input is empty")
        raise NotImplementedError("TTS runtime is not configured in this environment")