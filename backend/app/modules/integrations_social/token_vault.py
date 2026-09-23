from __future__ import annotations

from cryptography.fernet import Fernet


class EncryptedToken:
    def __init__(self, ciphertext: bytes) -> None:
        self._ciphertext = ciphertext

    def reveal(self, master_key: bytes) -> str:
        return Fernet(master_key).decrypt(self._ciphertext).decode()

    def __repr__(self) -> str:
        return "EncryptedToken(<redacted>)"


class TokenVault:
    def __init__(self, master_key: bytes) -> None:
        self._fernet = Fernet(master_key)

    def seal(self, token: str) -> EncryptedToken:
        if not token:
            raise ValueError("Token cannot be empty")
        return EncryptedToken(self._fernet.encrypt(token.encode()))