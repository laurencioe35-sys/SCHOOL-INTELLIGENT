from app.modules.whiteboard.collaboration.document import (
    CollaborativeCanvas,
    StrokeOperation,
    measure_append_latency,
)
from app.modules.whiteboard.sketch_engine.vectorizer import (
    StrokePoint,
    classify_shape,
    extract_geometric_features,
)


def test_sketch_fallback_classifies_closed_shape_with_confirmation_confidence():
    points = [StrokePoint(0, 0, 1, 0), StrokePoint(10, 0, 1, 10), StrokePoint(10, 10, 1, 20), StrokePoint(0, 10, 1, 30), StrokePoint(0, 0, 1, 40)]
    candidate = classify_shape(extract_geometric_features(points))
    assert candidate.shape_type == "cube"
    assert candidate.confidence >= 0.75
    assert candidate.editable_handles


def test_canvas_is_tenant_and_room_scoped_and_deduplicates_operations():
    canvas = CollaborativeCanvas("tenant-1", "room-1")
    operation = StrokeOperation("tenant-1", "room-1", "user-1", "op-1", ((0, 0), (1, 1)))
    canvas.append(operation)
    canvas.append(operation)
    assert len(canvas.snapshot()) == 1


def test_thirty_writer_simulation_records_latency_samples():
    canvas = CollaborativeCanvas("tenant-1", "room-1")
    operations = [StrokeOperation("tenant-1", "room-1", f"user-{i}", f"op-{i}", ((i, i),)) for i in range(30)]
    latencies = measure_append_latency(canvas, operations)
    assert len(latencies) == 30
    assert sorted(latencies)[28] >= 0