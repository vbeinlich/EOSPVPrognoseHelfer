import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_complete_local_originals_are_preserved_without_private_payloads():
    expected = {
        "DOCTOR_OPERATOR_STEPS.md": "98111e0abbbe95260b7f63e567d68117b7fe5e00c7be8fff45f64bca739e24a9",
        "unraid-doctor-export.sh": "5749ecd60abb1fc627ad1126bdafd1c21b41138ba2054565bfb2d5a256029fb6",
    }
    directory = ROOT / "docs/doctor-export-review/local-originals"
    assert {p.name for p in directory.iterdir()} == set(expected)
    for name, digest in expected.items():
        raw = (directory / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        text = raw.decode()
        assert not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        assert not re.search(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}", text)


def test_snapshot_producer_remains_the_original_pinned_read_only_implementation():
    assert hashlib.sha256((ROOT / "scripts/doctor_snapshot.py").read_bytes()).hexdigest() == (
        "56a950467d27482bf3361c0739f6cccab394dcbe04d3c0238255119d6bbc8ca5"
    )
