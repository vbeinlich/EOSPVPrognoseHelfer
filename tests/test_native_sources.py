import hashlib

import pytest
from native_sources import collect, fetch


@pytest.fixture
def native_case(tmp_path):
    site, output = tmp_path / "site", tmp_path / "sources"
    payload, archive = b"synthetic-ELF-payload", b"synthetic-source-rpm"
    digest = hashlib.sha256(payload).hexdigest()
    for package in ("numpy.libs", "scipy.libs"):
        folder = site / package
        folder.mkdir(parents=True)
        (folder / "libquadmath-test.so.0").write_bytes(payload)
    source = {"filename": "gcc-synthetic.src.rpm", "url": "https://vault.centos.org/synthetic.src.rpm",
              "sha256": hashlib.sha256(archive).hexdigest()}
    manifest = {"libraries": [{"bundled_sha256": digest, "build_id": "synthetic", "source_id": "gcc"}],
                "sources": {"gcc": source}}
    return site, output, manifest, archive


def test_duplicate_bundled_library_gets_one_verified_source_archive(native_case):
    site, output, manifest, archive = native_case
    calls = []
    result = collect(site, output, manifest, download=lambda url: calls.append(url) or archive)
    assert len(calls) == 1 and len(result["libraries"]) == 2 and len(result["sources"]) == 1
    assert result["binary_replacements"] is False
    assert (output / "gcc-synthetic.src.rpm").read_bytes() == archive
    collect(site, output, manifest, download=lambda url: pytest.fail("Duplicate source download"))


def test_unknown_payload_fails_before_network_or_output_creation(native_case):
    site, output, manifest, _ = native_case
    (site / "scipy.libs/libquadmath-new.so.0").write_bytes(b"unreviewed binary")
    with pytest.raises(ValueError, match="Unknown"):
        collect(site, output, manifest, download=lambda url: pytest.fail("Guessing source"))
    assert not output.exists()


def test_source_hash_mismatch_or_corrupted_cache_fails_closed(native_case):
    site, output, manifest, archive = native_case
    with pytest.raises(ValueError, match="hash differs"):
        collect(site, output, manifest, download=lambda url: b"wrong source")
    collect(site, output, manifest, download=lambda url: archive)
    (output / "gcc-synthetic.src.rpm").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="hash differs"):
        collect(site, output, manifest, download=lambda url: pytest.fail("Silently refreshing a corrupt cache"))


@pytest.mark.parametrize("url", ["http://vault.centos.org/file", "https://example.org/file",
                                 "https://user@repo.almalinux.org/file"])
def test_unreviewed_source_origins_rejected_before_http(url):
    with pytest.raises(ValueError, match="origin"):
        fetch(url)
