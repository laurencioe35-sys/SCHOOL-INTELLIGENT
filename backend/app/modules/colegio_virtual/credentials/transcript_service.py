from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEntry:
    course_id: str
    final_grade: str
    report_card_hash: str


def build_transcript(report_cards: list[dict[str, object]]) -> list[TranscriptEntry]:
    return [
        TranscriptEntry(str(card["course_id"]), str(card["final_grade"]), str(card["document_hash"]))
        for card in report_cards
        if card.get("signed") is True and card.get("document_hash")
    ]