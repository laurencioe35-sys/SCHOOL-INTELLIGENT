from __future__ import annotations

import base64
import os
import time
from typing import Any

class GeminiTranscriber:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.environ["GEMINI_API_KEY"]
        self.model = model or os.getenv("GEMINI_TRANSCRIPTION_MODEL", "gemini-3.5-transcribe")

    def transcribe(self, audio_b64: str, mime_type: str) -> str:
        import requests

        audio = base64.b64decode(audio_b64, validate=True)
        response = None
        for attempt in range(3):
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                params={"key": self.api_key},
                headers={"content-type": "application/json"},
                json={
                    "contents": [{"role": "user", "parts": [
                        {"text": "Transcribe exactamente el audio en español colombiano (es-CO). Conserva nombres, expresiones matemáticas y vocabulario local; devuelve solo el texto hablado, sin resumen ni traducción."},
                        {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(audio).decode("ascii")}},
                    ]}],
                    "generationConfig": {"temperature": 0, "maxOutputTokens": 2000},
                },
                timeout=60,
            )
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                break
            time.sleep(2 ** attempt)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        text = "".join(
            part.get("text") or part.get("audioTranscription", {}).get("text", "")
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        ).strip()
        if not text:
            raise RuntimeError("Gemini returned an empty transcription")
        return text
