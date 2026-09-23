from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ConsentRecord:
    pseudonym: str
    legal_guardian_id: str
    purpose: str
    granted_at: datetime
    revoked_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.revoked_at is None


@dataclass
class CorpusSample:
    pseudonym: str
    points: tuple[tuple[float, float, float], ...]
    state: str = "quarantine"


def _pseudonymize(student_id: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{student_id}".encode()).hexdigest()


class ConsentDataset:
    def __init__(self, salt: str) -> None:
        self._salt = salt
        self.consents: dict[str, ConsentRecord] = {}
        self.samples: list[CorpusSample] = []

    def grant_consent(self, student_id: str, legal_guardian_id: str, purpose: str) -> ConsentRecord:
        pseudonym = _pseudonymize(student_id, self._salt)
        record = ConsentRecord(pseudonym, legal_guardian_id, purpose, datetime.now(UTC))
        self.consents[pseudonym] = record
        return record

    def submit_for_training_corpus(self, student_id: str, points: tuple[tuple[float, float, float], ...]) -> CorpusSample:
        pseudonym = _pseudonymize(student_id, self._salt)
        consent = self.consents.get(pseudonym)
        if consent is None or not consent.active:
            raise PermissionError("Active legal guardian consent is required")
        sample = CorpusSample(pseudonym, tuple(points))
        self.samples.append(sample)
        return sample

    def revoke_consent_and_purge(self, student_id: str) -> int:
        pseudonym = _pseudonymize(student_id, self._salt)
        consent = self.consents.get(pseudonym)
        if consent is None:
            return 0
        self.consents[pseudonym] = ConsentRecord(
            consent.pseudonym, consent.legal_guardian_id, consent.purpose, consent.granted_at, datetime.now(UTC)
        )
        before = len(self.samples)
        self.samples[:] = [sample for sample in self.samples if sample.pseudonym != pseudonym]
        return before - len(self.samples)