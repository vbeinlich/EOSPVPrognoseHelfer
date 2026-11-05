"""Read-only preflight inside the EXISTING helper. stdout is a PRIVATE backup TAR.

No application imports, network, Docker socket, dispatch or changes to originals.
The host redirects stdout into its new mode-0600 backup before extracting it.
"""

import copy
import hashlib
import io
import json
import re
import sys
import tarfile
import tomllib
from pathlib import Path, PurePosixPath


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def safe_path(value):
    require(isinstance(value, str) and value.startswith("/") and
            not any(c in value for c in ("\n", "\r", "\0", ",")) and
            ".." not in PurePosixPath(value).parts, "unsupported_file_path")
    return value


def host_path(mounts, path):
    path = safe_path(path)
    matches = [m for m in mounts if path == m["Destination"] or
               path.startswith(m["Destination"].rstrip("/")+"/")]
    require(matches, "required_file_not_in_persistent_mount")
    mount = max(matches, key=lambda m: len(m["Destination"]))
    require(mount["Type"] in ("bind", "volume"), "unsupported_persistent_mount")
    source = safe_path(mount["Source"])
    suffix = path[len(mount["Destination"]):].lstrip("/")
    return str(PurePosixPath(source) / suffix) if suffix else source


def enable_evidence(raw):
    text = raw.decode("utf-8")
    parsed = tomllib.loads(text)
    expected = copy.deepcopy(parsed)
    require(isinstance(expected.get("evidence", {}), dict), "invalid_evidence_table")
    expected.setdefault("evidence", {})["enabled"] = True
    if parsed == expected:
        return raw
    headers = list(re.finditer(r"(?m)^\s*\[evidence\]\s*(?:#[^\n]*)?$", text))
    require(len(headers) <= 1, "unsupported_evidence_syntax")
    if headers:
        header = headers[0]
        rest = text[header.end():]
        next_table = re.search(r"(?m)^\s*\[", rest)
        end = header.end()+(next_table.start() if next_table else len(rest))
        body = text[header.end():end]
        pattern = r"(?m)^(\s*enabled\s*=\s*)(true|false)(\s*(?:#[^\n]*)?)$"
        matches = list(re.finditer(pattern, body))
        require(len(matches) <= 1, "unsupported_evidence_syntax")
        if matches:
            body = re.sub(pattern, lambda m: m[1]+"true"+m[3], body, count=1)
        else:
            body = "\nenabled = true\n"+body
        text = text[:header.end()]+body+text[end:]
    else:
        text = text.rstrip()+"\n\n[evidence]\nenabled = true\n"
    require(tomllib.loads(text) == expected, "config_semantics_would_change")
    return text.encode("utf-8")


def clone_payload(info, new_image):
    cfg, host = copy.deepcopy(info["Config"]), copy.deepcopy(info["HostConfig"])
    require(cfg["User"] == "10001:10001" and host["ReadonlyRootfs"], "unexpected_helper_identity")
    require(cfg["Entrypoint"] == ["python", "-m", "eos_pv_helper"], "unexpected_helper_entrypoint")
    cmd = cfg["Cmd"]
    require(cmd == ["sync", "--config", "/app/config.toml", "--refresh-source", "--write-eos"],
            "unexpected_sync_command_review_required")
    require(host.get("RestartPolicy", {}).get("Name") == "no" and not host.get("AutoRemove"),
            "unexpected_restart_or_auto_remove")
    require(not host.get("Privileged") and not host.get("CapAdd") and
            not host.get("Devices") and not host.get("DeviceRequests"), "unexpected_privileges")
    require(not host.get("VolumesFrom") and not host.get("ContainerIDFile"), "unsupported_host_dependency")
    require(not host.get("NetworkMode", "").startswith("container:"), "container_network_dependency")
    require(re.fullmatch(r"ghcr\.io/vbeinlich/eospvprognosehelfer:ems-v1\.1-test-[0-9a-f]{8}", new_image),
            "unexpected_candidate_tag")
    # Explicitly bind any formerly anonymous image volumes to their EXISTING names.
    # Keep original Binds/Mounts and their mount options otherwise byte-for-byte.
    destinations = {m["Target"] for m in host.get("Mounts") or []}
    kept_binds = []
    for bind in host.get("Binds") or []:
        fields = bind.split(":")
        require(len(fields) in (1, 2, 3), "unsupported_bind_syntax")
        if len(fields) == 1:
            safe_path(fields[0])  # Former anonymous volume is rebound below.
            continue
        kept_binds.append(bind)
        destinations.add(fields[1])
    if host.get("Binds") is not None:
        host["Binds"] = kept_binds
    for mount in info["Mounts"]:
        if mount["Destination"] in destinations or mount["Type"] == "tmpfs":
            continue
        require(mount["Type"] == "volume" and mount.get("Name"), "unrepresented_mount")
        host.setdefault("Binds", [])
        if host["Binds"] is None:
            host["Binds"] = []
        host["Binds"].append(mount["Name"]+":"+mount["Destination"]+":"+("rw" if mount["RW"] else "ro"))
    cfg["Image"] = new_image
    cfg["Labels"] = {**(cfg.get("Labels") or {}), "org.eos.test.original-container": info["Id"]}
    result = {**cfg, "HostConfig": host}
    networks = {}
    for name, endpoint in info.get("NetworkSettings", {}).get("Networks", {}).items():
        if name in ("host", "none"):
            continue
        networks[name] = {k: endpoint[k] for k in ("IPAMConfig", "Links", "Aliases", "DriverOpts")
                          if endpoint.get(k) is not None}
        if cfg.get("MacAddress"):
            networks[name]["MacAddress"] = cfg["MacAddress"]
    if networks:
        result["NetworkingConfig"] = {"EndpointsConfig": networks}
    return result


def prepare(info, new_image, read_file=None, is_file=None):
    mounts = info["Mounts"]
    payload = clone_payload(info, new_image)

    def read(path):
        if read_file:
            return read_file(path)
        item = Path(path)
        require(not item.is_symlink() and item.is_file() and item.stat().st_size <= 32_000_000,
                "required_backup_file_missing_unsafe_or_large")
        raw = item.read_bytes()
        require(len(raw) <= 32_000_000, "required_backup_file_large")
        return raw

    config_path = "/app/config.toml"
    original = read(config_path)
    config = tomllib.loads(original.decode())
    require(config.get("output", {}).get("directory", "/output") == "/output", "unexpected_output_path")
    cfg_host, output_host = host_path(mounts, config_path), host_path(mounts, "/output")
    require(not cfg_host.startswith(output_host.rstrip("/")+"/"), "config_inside_original_output")
    files = {config_path: original}
    # File mounts can contain extra private configuration even when not named in TOML.
    for mount in mounts:
        path = mount["Destination"]
        if mount["Type"] == "bind" and (is_file(path) if is_file else Path(path).is_file()):
            if path != "/output" and not path.startswith("/output/"):
                files[path] = read(path)
    soc, source = config.get("soc", {}), config.get("source", {})
    sections = []
    if config.get("prices", {}).get("enabled") or (soc.get("enabled") and soc.get("source", "evcc") == "evcc"):
        sections.append(config.get("evcc", {}))
    if soc.get("enabled") and soc.get("source") == "homeassistant":
        sections.append(soc)
    if soc.get("ha", {}).get("enabled"):
        sections.append(soc["ha"])
    if source.get("kind") == "http":
        sections.append(source)
    for section in sections:
        for key in ("token_file", "bearer_token_file"):
            if section.get(key):
                files[section[key]] = read(safe_path(section[key]))
    if source.get("kind") == "file":
        files[source["path"]] = read(safe_path(source["path"]))
    records = []
    entries = {"config-original.toml": original, "config-enabled.toml": enable_evidence(original),
               "container-inspect.json": (json.dumps([info], indent=2)+"\n").encode(),
               "container-create.json": (json.dumps(payload, indent=2)+"\n").encode()}
    for index, (name, raw) in enumerate(sorted(files.items())):
        target = "files/"+str(index).zfill(3)+".bin"
        entries[target] = raw
        records.append({"container_path": name, "host_path": host_path(mounts, name),
                        "backup": target, "sha256": hashlib.sha256(raw).hexdigest()})
    entries["files.json"] = (json.dumps(records, indent=2)+"\n").encode()
    timeout = config.get("trigger", {}).get("request_timeout_seconds", 300)
    require(type(timeout) is int and 10 <= timeout <= 1800, "invalid_existing_dispatch_timeout")
    lines = [info["Id"], info["Image"], cfg_host, output_host,
             hashlib.sha256(original).hexdigest(), str(timeout+300)]
    require(all(isinstance(v, str) and "\n" not in v for v in lines), "unsafe_plan_line")
    entries["plan-lines"] = ("\n".join(lines)+"\n").encode()
    # This is only a reference snapshot. Rollback NEVER restores it.
    entries["claims-before.json"] = read("/output/sync-state.json")
    return entries


def main():
    try:
        info = json.load(sys.stdin)[0]
        entries = prepare(info, sys.argv[1])
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
            for name, raw in entries.items():
                item = tarfile.TarInfo(name)
                item.size, item.mode = len(raw), 0o600
                archive.addfile(item, io.BytesIO(raw))
    except Exception:
        raise SystemExit("Preflight/backup failed; no originals or configuration changed") from None


if __name__ == "__main__":
    main()
