from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WhatsAppTemplate:
    name: str
    approved: bool = False
    body: str = ""


class TemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, WhatsAppTemplate] = {}

    def register_placeholder(self, name: str) -> WhatsAppTemplate:
        template = WhatsAppTemplate(name)
        self._templates[name] = template
        return template

    def get(self, name: str) -> WhatsAppTemplate | None:
        return self._templates.get(name)