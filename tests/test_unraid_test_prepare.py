"""Pure synthetic preflight and config preservation. Never contacts Docker or Unraid."""

import copy
import importlib.util
import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("unraid_prepare", ROOT / "deploy/unraid-test/prepare.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
TAG = "ghcr.io/vbeinlich/eospvprognosehelfer:ems-v1.1-test-546baa63"


def synthetic():
    info = {"Id": "1"*64, "Image": "sha256:"+"e"*64,
            "Config": {"Image": "old:private", "User": "10001:10001",
                "Entrypoint": ["python", "-m", "eos_pv_helper"],
                "Cmd": ["sync", "--config", "/app/config.toml", "--refresh-source", "--write-eos"],
                "Env": ["DRY_RUN=false", "EVCC_TOKEN=SYNTHETIC-CANARY"],
                "Labels": {"net.unraid.docker.icon": "preserve"}, "Volumes": {"/extra": {}}},
            "HostConfig": {"ReadonlyRootfs": True, "RestartPolicy": {"Name": "no"}, "AutoRemove": False,
                "Binds": ["/private/config.toml:/app/config.toml:ro", "/private/output:/output:rw",
                          "/private/keys:/run/secrets:ro"], "Mounts": [], "CapDrop": ["ALL"],
                "Memory": 512*1024**2, "NanoCpus": 250000000, "PidsLimit": 128,
                "SecurityOpt": ["no-new-privileges"], "NetworkMode": "bridge"},
            "Mounts": [
                {"Type": "bind", "Source": "/private/config.toml", "Destination": "/app/config.toml", "RW": False},
                {"Type": "bind", "Source": "/private/output", "Destination": "/output", "RW": True},
                {"Type": "bind", "Source": "/private/keys", "Destination": "/run/secrets", "RW": False},
                {"Type": "volume", "Name": "existing-volume", "Source": "/docker/volume/_data",
                 "Destination": "/extra", "RW": True}],
            "NetworkSettings": {"Networks": {"bridge": {"IPAMConfig": None, "EndpointID": "do-not-copy"}}}}
    files = {"/app/config.toml": b'''[output]\ndirectory="/output"\n[prices]\nenabled=true\n[evcc]\ntoken_file="/run/secrets/evcc"\n[trigger]\nenabled=true\nrun_enabled=true\n''',
             "/run/secrets/evcc": b"PRIVATE-SYNTHETIC-KEY",
             "/output/sync-state.json": b'{"events":{"old":{"status":"succeeded"}}}'}
    return info, files


def test_backup_actual_referenced_secrets_and_preserve_original_container_parameters():
    info, files = synthetic()
    before = copy.deepcopy(info)
    packet = module.prepare(info, TAG, files.__getitem__, lambda p: p in files)
    assert info == before
    clone = json.loads(packet["container-create.json"])
    for field in ("Env", "Cmd", "Entrypoint", "User"):
        assert clone[field] == info["Config"][field]
    for key in ("Memory", "NanoCpus", "SecurityOpt", "PidsLimit", "RestartPolicy"):
        assert clone["HostConfig"][key] == info["HostConfig"][key]
    assert clone["HostConfig"]["Binds"][-1] == "existing-volume:/extra:rw"
    assert clone["Image"] == TAG and "EndpointID" not in json.dumps(clone)
    assert packet["config-original.toml"] == files["/app/config.toml"]
    assert b"PRIVATE-SYNTHETIC-KEY" in packet.values()
    assert packet["claims-before.json"] == files["/output/sync-state.json"]
    expected = tomllib.loads(files["/app/config.toml"].decode())
    expected["evidence"] = {"enabled": True}
    assert tomllib.loads(packet["config-enabled.toml"].decode()) == expected


@pytest.mark.parametrize("raw", [b'key="unchanged"\n', b'[evidence]\nenabled=false # keep comment\n',
                                b'[evidence]\nother=3\n[trigger]\nrun_enabled=false\n',
                                b'[evidence]\nenabled=true\n', b'[evidence]\r\nenabled=false\r\n'])
def test_toml_patch_changes_exactly_one_permission(raw):
    expected = tomllib.loads(raw.decode())
    expected.setdefault("evidence", {})["enabled"] = True
    assert tomllib.loads(module.enable_evidence(raw).decode()) == expected


@pytest.mark.parametrize("raw", [b'evidence={enabled=false}\n', b'evidence.enabled=false\n',
                                b'notes="""\n[evidence]\n"""\n'])
def test_ambiguous_text_patches_fail_closed_without_rewriting_originals(raw):
    with pytest.raises((ValueError, tomllib.TOMLDecodeError)):
        module.enable_evidence(raw)


@pytest.mark.parametrize("change", ["root", "writable-root", "privileged", "device", "restart", "auto-remove", "command"])
def test_unexpected_runtime_is_refused_before_any_change(change):
    info, _ = synthetic()
    if change == "root":
        info["Config"]["User"] = "0:0"
    elif change == "command":
        info["Config"]["Cmd"] = ["run"]
    else:
        key, value = {"writable-root": ("ReadonlyRootfs", False), "privileged": ("Privileged", True),
                      "device": ("Devices", [{"PathOnHost": "/dev/example"}]),
                      "restart": ("RestartPolicy", {"Name": "always"}),
                      "auto-remove": ("AutoRemove", True)}[change]
        info["HostConfig"][key] = value
    with pytest.raises(ValueError):
        module.clone_payload(info, TAG)


def test_missing_required_config_file_does_not_invent_a_backup():
    info, files = synthetic()
    del files["/run/secrets/evcc"]
    with pytest.raises(KeyError):
        module.prepare(info, TAG, files.__getitem__, lambda p: p in files)


def test_mount_path_traversal_and_nonpersistent_configs_are_rejected():
    info, _ = synthetic()
    for name in ("/app/../secret", "/not-mounted/config.toml"):
        with pytest.raises(ValueError):
            module.host_path(info["Mounts"], name)
