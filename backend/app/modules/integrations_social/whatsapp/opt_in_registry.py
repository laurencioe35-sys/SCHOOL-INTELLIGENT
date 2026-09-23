from __future__ import annotations


class OptInRequiredError(PermissionError):
    pass


class OptInRegistry:
    def __init__(self) -> None:
        self._numbers: set[str] = set()

    def register(self, phone_number: str) -> None:
        self._numbers.add(phone_number)

    def require(self, phone_number: str) -> None:
        if phone_number not in self._numbers:
            raise OptInRequiredError("WhatsApp opt-in is required before sending")