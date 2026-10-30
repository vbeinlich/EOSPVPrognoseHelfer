import hashlib
import io
import json
import tarfile

import pytest
from source_bundle import fetch, prepare, verify


@pytest.fixture
def source_case(tmp_path):
    contents = {"native": b"gcc-source-and-patches", "debian": b"debian-exact-source",
                "data": b"complete-unchanged-ODbL-data-and-reader", "eos": b"eos-source",
                "python": b"lgpl-python-source", "project": b"application-source",
                "embedded": b"libiconv-and-relinkable-lxml-source"}
    def digest(key):
        return hashlib.sha256(contents[key]).hexdigest()
    debian = {"source_packages": [{"name": "synthetic-os", "version": "1.0", "files": [
        {"name": "source.tar.xz", "sha256": digest("debian"), "url": "https://snapshot.debian.org/file/synthetic"}]}]}
    debian_raw = json.dumps(debian).encode()
    inventory = {"debian_source_index_sha256": hashlib.sha256(debian_raw).hexdigest(),
        "native_eos_source_archive_sha256": digest("eos"), "python": [{
            "directory": "python/lgpl", "source": {"filename": "source.tar.gz", "sha256": digest("python")}}],
        "native_sources": {"sources": {"gcc": {"filename": "gcc.src.rpm", "sha256": digest("native"),
            "url": "https://vault.centos.org/synthetic"}}},
        "data_sources": {"sources": [{"filename": "data.crate", "sha256": digest("data"),
            "url": "https://static.crates.io/synthetic"}]},
        "embedded_sources": {"sources": [{"filename": "libiconv.tar.gz", "sha256": digest("embedded"),
            "url": "https://ftp.gnu.org/synthetic"}]}}
    raw = json.dumps(inventory).encode()
    notices = {"inventory.json": raw, "python/lgpl/source.tar.gz": contents["python"]}
    lookup = {hashlib.sha256(value).hexdigest(): value for value in contents.values()}
    return {"output": tmp_path / "private-sources.tar.gz", "inventory_raw": raw,
        "notice_files": notices, "eos_raw": contents["eos"], "project_raw": contents["project"],
        "debian_raw": debian_raw, "cache": tmp_path / "cache",
        "downloader": lambda entry, cache: lookup[entry["sha256"]]}


def test_source_bundle_covers_actual_inventory_without_any_registry_activity(source_case):
    manifest = prepare(**source_case)
    assert verify(source_case["output"], source_case["inventory_raw"]) == manifest
    assert source_case["output"].stat().st_mode & 0o077 == 0
    assert any(name.startswith("native/") for name in manifest["files"])
    assert any(name.startswith("data/") for name in manifest["files"])
    assert any(name.startswith("debian/") for name in manifest["files"])
    assert any(name.startswith("embedded/") for name in manifest["files"])


def rewrite(path, modify):
    with tarfile.open(path) as archive:
        files = {m.name: archive.extractfile(m).read() for m in archive.getmembers()}
    modify(files)
    with tarfile.open(path, "w:gz") as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))


@pytest.mark.parametrize("failure", ["changed-file", "missing-source", "another-inventory", "traversal"])
def test_source_bundle_tampering_or_incomplete_coverage_is_rejected(source_case, failure):
    prepare(**source_case)

    def mutate(files):
        if failure == "changed-file":
            files["native/gcc.src.rpm"] += b"changed"
        elif failure == "missing-source":
            del files["data/data.crate"]
        elif failure == "traversal":
            files["../escape"] = b"must not extract"
        else:
            manifest = json.loads(files["source-bundle.json"])
            manifest["inventory_sha256"] = "f" * 64
            files["source-bundle.json"] = json.dumps(manifest).encode()
    rewrite(source_case["output"], mutate)
    with pytest.raises(ValueError):
        verify(source_case["output"], source_case["inventory_raw"])


def test_no_replacement_of_existing_bundle(source_case):
    prepare(**source_case)
    before = source_case["output"].read_bytes()
    with pytest.raises(ValueError, match="replace"):
        prepare(**source_case)
    assert source_case["output"].read_bytes() == before


def test_source_cache_cannot_escape_its_directory(tmp_path):
    with pytest.raises(ValueError, match="SHA256"):
        fetch({"sha256": "../escape", "url": "https://snapshot.debian.org/file/x"}, tmp_path)


def test_source_archive_is_reproducible(source_case, tmp_path):
    prepare(**source_case)
    original = source_case["output"].read_bytes()
    source_case["output"] = tmp_path / "second.tar.gz"
    prepare(**source_case)
    assert source_case["output"].read_bytes() == original
