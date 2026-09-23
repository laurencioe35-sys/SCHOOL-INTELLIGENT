from __future__ import annotations

MIN_ACCEPTABLE_KAPPA = 0.75


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        raise ValueError("Annotator label sets must have equal non-zero length")
    agreement = sum(a == b for a, b in zip(labels_a, labels_b)) / len(labels_a)
    categories = set(labels_a) | set(labels_b)
    expected = sum(
        (labels_a.count(category) / len(labels_a)) * (labels_b.count(category) / len(labels_b))
        for category in categories
    )
    if expected == 1:
        return 1.0
    return (agreement - expected) / (1 - expected)


def mark_training_ready(sample_state: str, labels_a: list[str], labels_b: list[str]) -> bool:
    return sample_state == "quarantine" and cohens_kappa(labels_a, labels_b) >= MIN_ACCEPTABLE_KAPPA