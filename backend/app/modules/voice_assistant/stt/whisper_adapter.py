from __future__ import annotations


class WhisperSpeechToText:
    provider = "whisper-self-hosted"

    def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            raise ValueError("Audio input is empty")
        raise NotImplementedError("Whisper runtime is not configured in this environment")