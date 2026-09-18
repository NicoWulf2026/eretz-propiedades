from pathlib import Path

import pytest

from scripts.api_snapshot import publish_snapshot


def test_snapshot_rejects_destination_created_after_initial_validation(tmp_path: Path):
    temporary = tmp_path / 'candidate.building'
    output = tmp_path / 'served.sqlite3'
    temporary.write_bytes(b'complete candidate')
    output.write_bytes(b'other writer completed')
    with pytest.raises(FileExistsError):
        publish_snapshot(temporary, output)
    assert output.read_bytes() == b'other writer completed'
    assert temporary.read_bytes() == b'complete candidate'


def test_explicit_snapshot_replacement_remains_supported(tmp_path: Path):
    temporary = tmp_path / 'candidate.building'
    output = tmp_path / 'served.sqlite3'
    temporary.write_bytes(b'complete candidate')
    output.write_bytes(b'previous derived artifact')
    publish_snapshot(temporary, output, replace=True)
    assert output.read_bytes() == b'complete candidate'
    assert not temporary.exists()
