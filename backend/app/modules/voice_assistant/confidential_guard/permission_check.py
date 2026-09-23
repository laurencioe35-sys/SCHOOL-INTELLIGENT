from __future__ import annotations


class VoiceAccessDenied(PermissionError):
    pass


def check_screen_permission(*, role: str, resource: str, action: str = "read") -> None:
    restricted_resources = {"payroll", "salary", "account_balance", "account_number"}
    if resource in restricted_resources and role not in {"admin", "finance_manager"}:
        raise VoiceAccessDenied(f"Role '{role}' cannot {action} resource '{resource}'")