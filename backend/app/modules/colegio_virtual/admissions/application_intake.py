from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4


@dataclass(frozen=True)
class RequiredDocument:
    code: str
    name: str


@dataclass(frozen=True)
class AdmissionApplication:
    id: UUID
    tenant_id: UUID
    applicant_name: str
    birth_date: date
    grade_level_code: str
    submitted_document_codes: frozenset[str] = field(default_factory=frozenset)


def create_application(
    *,
    tenant_id: UUID,
    applicant_name: str,
    birth_date: date,
    grade_level_code: str,
    submitted_document_codes: set[str] | None = None,
) -> AdmissionApplication:
    if not applicant_name.strip():
        raise ValueError("Applicant name is required")
    if not grade_level_code.strip():
        raise ValueError("Grade level code is required")
    return AdmissionApplication(
        id=uuid4(),
        tenant_id=tenant_id,
        applicant_name=applicant_name.strip(),
        birth_date=birth_date,
        grade_level_code=grade_level_code.strip(),
        submitted_document_codes=frozenset(submitted_document_codes or set()),
    )


def missing_documents(
    application: AdmissionApplication, required_documents: list[RequiredDocument]
) -> list[RequiredDocument]:
    return [
        document
        for document in required_documents
        if document.code not in application.submitted_document_codes
    ]