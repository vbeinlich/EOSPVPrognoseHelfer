import importlib.util
import json
import shlex
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from eos_pv_helper.app import main, request_json
from eos_pv_helper.normalize import ForecastError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("image_metadata", ROOT / "scripts/image_metadata.py")
metadata_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata_module)


def test_template_volumes_security_and_command():
    root = ET.parse(ROOT / "templates/eos-pv-helper.xml").getroot()
    assert root.tag == "Container" and root.attrib["version"] == "2"
    assert root.findtext("Network") == "bridge"
    assert root.findtext("Privileged") == "false"
    assert not root.findtext("WebUI")
    assert root.findtext("Repository").startswith("ghcr.io/vbeinlich/eospvprognosehelfer")
    command = shlex.split(root.findtext("PostArgs"))
    assert command == ["run", "--config", "/app/config.toml"]
    flags = shlex.split(root.findtext("ExtraParams"))
    for expected in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                     "--user=10001:10001", "--memory=512m", "--cpus=0.25"):
        assert expected in flags
    assert "--pids-limit" in flags
    assert not any(flag.startswith(("--privileged", "--device", "--publish", "--network",
                                    "--restart", "--entrypoint")) for flag in flags)
    entries = {entry.attrib["Target"]: entry for entry in root.findall("Config")}
    for target, mode in [("/app/config.toml", "ro"), ("/input", "ro"), ("/output", "rw")]:
        entry = entries[target]
        assert entry.attrib["Mode"] == mode and entry.attrib["Type"] == "Path"
        assert entry.text.startswith("/mnt/user/appdata/eos-pv-helper/")
    assert entries["DRY_RUN"].text == "true"
    assert entries["HA_TOKEN"].attrib["Mask"] == "true" and not entries["HA_TOKEN"].text
    assert not entries["/run/secrets/ha_token"].text
    assert entries["/run/secrets/ha_token"].attrib["Default"] == ""
    assert entries["/run/secrets/ha_token"].attrib["Mode"] == "ro"
    assert not {"EOS_URL", "PUID", "PGID"} & set(entries)
    assert not any(entry.attrib["Type"] in ("Device", "Port") for entry in entries.values())


def test_stock_toml_is_cache_only_with_every_write_and_extension_disabled():
    config = tomllib.loads((ROOT / "config.example.toml").read_text())
    assert config["source"]["refresh_enabled"] is False
    assert all(config[section]["write_enabled"] is False for section in ("eos", "soc", "prices"))
    assert all(config[section]["enabled"] is False for section in ("soc", "prices", "trigger"))
    assert config["trigger"]["run_enabled"] is False


def test_preview_and_main_have_no_invented_release_or_latest_tag():
    for branch in ("feat/issue-1-pv-normalization", "main"):
        result = metadata_module.metadata("a" * 40, "refs/heads/" + branch, "0.1.0")
        assert result["tags"][0].endswith(":sha-" + "a" * 40)
        assert not any(tag.endswith((":latest", ":v0.1.0")) for tag in result["tags"])
        assert all(tag == tag.lower() for tag in result["tags"])


def test_release_tag_matches_code_version():
    result = metadata_module.metadata("a" * 40, "refs/tags/v0.1.0", "0.1.0")
    assert result["tags"] == [metadata_module.IMAGE + ":sha-" + "a" * 40]
    assert result["promotion_tags"] == [metadata_module.IMAGE + ":v0.1.0", metadata_module.IMAGE + ":latest"]


@pytest.mark.parametrize("sha,ref", [("a" * 7, "refs/heads/main"),
                                    ("A" * 40, "refs/heads/main"),
                                    ("a" * 40, "refs/pull/3/merge"),
                                    ("a" * 40, "refs/heads/other"),
                                    ("a" * 40, "refs/tags/v9.0.0"),
                                    ("a" * 40, "refs/tags/v0.1.0-rc.1")])
def test_invalid_or_unapproved_publishing_ref(sha, ref):
    with pytest.raises(ValueError):
        metadata_module.metadata(sha, ref, "0.1.0")


@pytest.mark.parametrize("kind", ["absent", "directory"])
def test_first_start_missing_config_is_actionable(tmp_path, monkeypatch, caplog, kind):
    config = tmp_path / "config.toml"
    if kind == "directory":
        config.mkdir()
    monkeypatch.setattr(sys, "argv", ["eos-pv-helper", "run", "--once", "--config", str(config)])
    assert main() == 1
    assert "Private config.toml missing or a directory" in caplog.text
    assert "mount it read-only" in caplog.text


def test_secret_file_auth_reads_only_file_and_does_not_log_it(tmp_path, monkeypatch, caplog):
    secret = tmp_path / "token"
    secret.write_text("synthetic.test.token\n")
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return json.dumps({"state": "55"}).encode()

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response()

    monkeypatch.setattr("eos_pv_helper.app.build_opener", lambda *args: Opener())
    assert request_json("http://127.0.0.1/state", token_file=secret)["state"] == "55"
    assert requests[0].get_header("Authorization") == "Bearer synthetic.test.token"
    assert "synthetic.test.token" not in caplog.text


@pytest.mark.parametrize("content", [None, "", "bad token", "x" * 8193])
def test_invalid_secret_file_never_makes_http_request(tmp_path, monkeypatch, content):
    secret = tmp_path / "token"
    if content is not None:
        secret.write_text(content)
    monkeypatch.setattr("eos_pv_helper.app.build_opener", lambda *args: pytest.fail("HTTP forbidden"))
    with pytest.raises(ForecastError):
        request_json("http://127.0.0.1/state", token_file=secret)


def test_ambiguous_secret_source_rejected_before_http():
    with pytest.raises(ForecastError, match="either"):
        request_json("http://127.0.0.1/state", token_env="HA_TOKEN", token_file="/unused")


def test_cached_http_reply_is_never_a_device_read_proof(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Cache-control") == "no-cache, no-store"
            return nullcontext(SimpleNamespace(headers={"Age": "0"}))
    monkeypatch.setattr("eos_pv_helper.app.build_opener", lambda *args: Opener())
    with pytest.raises(ForecastError, match="Cached HTTP response"):
        request_json("http://127.0.0.1/status", uncached=True)
