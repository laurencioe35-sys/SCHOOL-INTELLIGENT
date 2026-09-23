import pytest

from app.modules.whiteboard.dataset_pipeline.dataset_collection import ConsentDataset
from app.modules.whiteboard.dataset_pipeline.labeling_quality import mark_training_ready
from app.modules.whiteboard.dataset_pipeline.synthetic_augmentation import augment_stroke


def test_consent_pseudonymization_and_right_to_be_forgotten():
    dataset = ConsentDataset("test-salt")
    dataset.grant_consent("student-1", "guardian-1", "shape_training")
    for _ in range(3):
        dataset.submit_for_training_corpus("student-1", ((0.0, 0.0, 1.0),))
    removed = dataset.revoke_consent_and_purge("student-1")
    assert removed == 3
    assert dataset.samples == []
    assert "student-1" not in repr(dataset.samples)


def test_consent_is_required_and_quarantine_needs_two_annotators():
    dataset = ConsentDataset("test-salt")
    with pytest.raises(PermissionError):
        dataset.submit_for_training_corpus("student-2", ((0.0, 0.0, 1.0),))
    dataset.grant_consent("student-2", "guardian-2", "shape_training")
    sample = dataset.submit_for_training_corpus("student-2", ((0.0, 0.0, 1.0),))
    assert sample.state == "quarantine"
    assert mark_training_ready(sample.state, ["cube", "cube"], ["cube", "cube"]) is True


def test_each_real_sample_gets_five_variants_including_motor_tremor():
    variants = augment_stroke(((0.0, 0.0, 1.0), (1.0, 1.0, 0.8)), count=5)
    assert len(variants) == 5
    assert any(variant.simulate_motor_tremor for variant in variants)