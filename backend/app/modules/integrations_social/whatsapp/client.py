from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .opt_in_registry import OptInRegistry
from .session_window import is_within_24_hour_window
from .templates_registry import TemplateRegistry


@dataclass(frozen=True)
class WhatsAppSendResult:
    sent: bool
    reason: str


class WhatsAppClient:
    def __init__(self, opt_ins: OptInRegistry, templates: TemplateRegistry) -> None:
        self.opt_ins, self.templates = opt_ins, templates

    def send_template(self, phone: str, template_name: str, last_user_message_at: datetime) -> WhatsAppSendResult:
        self.opt_ins.require(phone)
        template = self.templates.get(template_name)
        if template is None or not template.approved:
            return WhatsAppSendResult(False, "Template is not approved; notification intent logged only")
        if not is_within_24_hour_window(last_user_message_at):
            return WhatsAppSendResult(False, "Outside 24-hour window; approved template required")
        return WhatsAppSendResult(True, "Message sent")