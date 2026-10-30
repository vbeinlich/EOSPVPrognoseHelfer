import hashlib
import io
import tarfile
from urllib.error import URLError

import pytest
import test_source_bundle as source_fixtures
from publication import DockerRegistry, promote
from source_bundle import prepare
from test_publication import DIGEST, Registry
from test_publication import approval as approval_fixture


@pytest.fixture
def approval():
    return approval_fixture.__wrapped__()


class Download(io.BytesIO):
    def geturl(self):
        return "https://release-assets.githubusercontent.com/approved/sources.tar.gz"


@pytest.mark.parametrize("failure", [None, "unavailable", "corrupted", "incomplete", "redirect", "oversized"])
def test_real_source_download_and_archive_verification_precede_any_tag_write(tmp_path, monkeypatch, approval, failure):
    case = source_fixtures.source_case.__wrapped__(tmp_path)
    prepare(**case)
    raw = case["output"].read_bytes()
    registry = Registry()
    registry.labels[DIGEST]["inventory"] = case["inventory_raw"]
    approval["license_review"]["inventory_sha256"] = hashlib.sha256(case["inventory_raw"]).hexdigest()
    approval["license_review"]["source_material_sha256"] = hashlib.sha256(raw).hexdigest()
    if failure == "corrupted":
        raw += b"changed"
    if failure == "incomplete":
        raw = b"not a corresponding-source archive"
        approval["license_review"]["source_material_sha256"] = hashlib.sha256(raw).hexdigest()
    if failure == "oversized":
        monkeypatch.setattr("publication.MAX_TOTAL", 10)

    def download(url, **kwargs):
        assert url == approval["license_review"]["source_material_url"]
        if failure == "unavailable":
            raise URLError("Synthetic unavailable source asset")
        response = Download(raw)
        if failure == "redirect":
            response.geturl = lambda: "https://unreviewed.invalid/source"
        return response

    monkeypatch.setattr("publication.urlopen", download)
    registry.source_material = DockerRegistry().source_material
    if failure:
        with pytest.raises((OSError, ValueError, tarfile.TarError)):
            promote(approval, "v0.1.0", DIGEST, registry, apply=True)
        assert registry.writes == []
    else:
        assert promote(approval, "v0.1.0", DIGEST, registry, apply=True)["writes"] == 2
        assert promote(approval, "v0.1.0", DIGEST, registry, apply=True)["writes"] == 0
