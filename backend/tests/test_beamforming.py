from app.modules.whiteboard.audio_beamforming.beamformer import (
    apply_beamforming,
    estimate_direction_of_arrival,
    signal_to_noise_ratio,
)


def test_delay_and_sum_combines_channels_without_dropping_samples():
    output = apply_beamforming([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]], [0, 0])
    assert output == [1.0, 2.0, 3.0]


def test_direction_estimate_returns_confidence_for_strongest_channel():
    estimate = estimate_direction_of_arrival([[0.1, 0.1], [1.0, 1.0], [0.1, 0.1]])
    assert estimate.confidence > 0.9


def test_snr_metric_is_explicit():
    assert signal_to_noise_ratio([1.0, 1.0], [0.1, 0.1]) > 0