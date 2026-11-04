import hashlib
import json

import pytest
from dashboard_archive_hash_probe import recover

from eos_pv_helper.storage import atomic_json


def test_probe_matches_actual_writer_bytes_without_changing_original(tmp_path):
    value = {"original": "Unverändert", "result": [1.2, None, True]}
    saved = tmp_path / "get.json"
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    saved.write_bytes(raw)
    archived = tmp_path / "actual-writer.json"
    atomic_json(archived, value)
    expected = hashlib.sha256(archived.read_bytes()).hexdigest()
    restored = tmp_path / "private-copy.json"
    report = recover(saved, expected, restored)
    assert restored.read_bytes() == archived.read_bytes()
    assert restored.stat().st_mode & 0o777 == 0o600
    assert saved.read_bytes() == raw
    assert report["matches_independently_supplied_hash"] is True
    assert "not a direct NAS download" in report["provenance"]
    with pytest.raises(FileExistsError):
        recover(saved, expected, restored)
    assert recover(saved, expected) == report


def test_probe_does_not_create_anything_on_hash_mismatch(tmp_path):
    saved = tmp_path / "get.json"
    saved.write_text('{"result":1}')
    target = tmp_path / "must-not-exist.json"
    with pytest.raises(ValueError, match="no file or sidecar written"):
        recover(saved, "f" * 64, target)
    assert not target.exists()
    assert saved.read_text() == '{"result":1}'
