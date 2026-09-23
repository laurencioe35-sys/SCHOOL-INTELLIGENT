from app.db import engine
from app.migrations import current_version, upgrade


def test_schema_upgrade_is_recorded_and_repeatable():
    version = upgrade(engine)

    assert version == 11
    assert current_version(engine) == 11
    assert upgrade(engine) == 11