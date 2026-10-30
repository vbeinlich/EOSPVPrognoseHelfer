"""Prepare/verify private corresponding-source material; never upload or publish.

The later stable promotion requires these exact bytes to be publicly available
as an approved release asset first. All payloads and their origin remain indexed.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import urlopen

MAX_FILE = 200_000_000
MAX_TOTAL = 1_000_000_000
SOURCE_ORIGINS = {"snapshot.debian.org", "vault.centos.org", "repo.almalinux.org", "static.crates.io",
                  "ftp.gnu.org", "download.gnome.org", "zlib.net", "www.zlib.net"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fetch(source, cache):
    if not isinstance(source.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ValueError("Full source SHA256 required")
    if source.get("sha1") and not re.fullmatch(r"[0-9a-f]{40}", source["sha1"]):
        raise ValueError("Invalid source-cache identifier")
    parts = urlsplit(source["url"])
    if parts.scheme != "https" or parts.hostname not in SOURCE_ORIGINS or parts.username:
        raise ValueError("Unapproved corresponding-source origin")
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / source["sha256"]
    # Allow reuse of the already hash-verified private Snapshot Debian cache.
    old = cache / source.get("sha1", source["sha256"])
    if target.exists() or old.exists():
        raw = (target if target.exists() else old).read_bytes()
    else:
        with urlopen(source["url"], timeout=180) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in SOURCE_ORIGINS:
                raise ValueError("Unapproved corresponding-source redirect")
            raw = response.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE or sha(raw) != source["sha256"]:
        raise ValueError("Corresponding source size/hash differs")
    if not target.exists():
        target.write_bytes(raw)
    return raw


def source_requirements(inventory, debian_index):
    result = {}
    for package in debian_index["source_packages"]:
        for file in package["files"]:
            result["debian/" + file["sha256"] + "/" + file["name"]] = file
    for file in inventory["native_sources"]["sources"].values():
        result["native/" + file["filename"]] = file
    for file in inventory["data_sources"]["sources"]:
        result["data/" + file["filename"]] = file
    for file in inventory.get("embedded_sources", {}).get("sources", []):
        result["embedded/" + file["filename"]] = file
    return result


def verify(path, inventory_raw):
    """Read without extracting; validate coverage as well as the outer hash."""
    inventory = json.loads(inventory_raw)
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if (len(members) > 5000 or any(not m.isfile() or m.size > MAX_FILE for m in members)
                or sum(m.size for m in members) > MAX_TOTAL
                or len({m.name for m in members}) != len(members)):
            raise ValueError("Unsafe corresponding-source bundle")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe source-bundle member name")
        manifest = json.load(archive.extractfile("source-bundle.json"))
        if manifest["inventory_sha256"] != sha(inventory_raw):
            raise ValueError("Source material belongs to another image inventory")
        expected = manifest["files"]
        if {m.name for m in members} != set(expected) | {"source-bundle.json"}:
            raise ValueError("Source material index is incomplete")
        index_raw = archive.extractfile("metadata/debian-sources.json").read()
        if sha(index_raw) != inventory["debian_source_index_sha256"]:
            raise ValueError("Debian source index differs from the image")
        required = source_requirements(inventory, json.loads(index_raw))
        for entry in inventory["python"]:
            for notice in entry.get("notices", []):
                required["image-notices/" + entry["directory"] + "/" + notice["file"]] = notice
            if entry.get("source"):
                source = entry["source"]
                required["image-notices/" + entry["directory"] + "/" + source["filename"]] = source
        for notice in inventory.get("system", []):
            required["image-notices/system/" + notice["file"]] = notice
        required["eos/upstream-eos.tar.gz"] = {"sha256": inventory["native_eos_source_archive_sha256"]}
        for name, source in required.items():
            if expected.get(name) != source["sha256"]:
                raise ValueError("Required corresponding-source payload is absent")
        if "project/source.tar" not in expected:
            raise ValueError("Application source/rebuild instructions are absent")
        for member in members:
            if member.name == "source-bundle.json":
                continue
            digest = hashlib.sha256()
            with archive.extractfile(member) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected[member.name]:
                raise ValueError("Source-bundle payload hash differs")
    return manifest


def prepare(output, inventory_raw, notice_files, eos_raw, project_raw, debian_raw, cache,
            *, downloader=fetch):
    inventory, debian = json.loads(inventory_raw), json.loads(debian_raw)
    if sha(debian_raw) != inventory["debian_source_index_sha256"]:
        raise ValueError("Matching Debian source index required")
    if sha(eos_raw) != inventory["native_eos_source_archive_sha256"]:
        raise ValueError("EOS source archive differs")
    output = Path(output)
    if output.exists():
        raise ValueError("Refusing to replace an existing private source bundle")
    files = {"image-notices/" + name: raw for name, raw in notice_files.items()}
    files.update({"metadata/debian-sources.json": debian_raw, "eos/upstream-eos.tar.gz": eos_raw,
                  "project/source.tar": project_raw})
    for name, entry in source_requirements(inventory, debian).items():
        files[name] = downloader(entry, cache)
    manifest = {"schema_version": 1, "inventory_sha256": sha(inventory_raw),
                "files": {name: sha(raw) for name, raw in sorted(files.items())},
                "scope": "complete corresponding source coverage; not a publication approval"}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            with gzip.GzipFile(fileobj=handle, mode="wb", filename="", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w|") as archive:
                    for name, raw in sorted({**files, "source-bundle.json": json.dumps(manifest, sort_keys=True).encode()}.items()):
                        member = tarfile.TarInfo(name)
                        member.size, member.mode, member.mtime = len(raw), 0o644, 0
                        archive.addfile(member, io.BytesIO(raw))
        verify(temporary, inventory_raw)
        os.replace(temporary, output)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return manifest


def docker(*args):
    return subprocess.check_output(["docker", *args], timeout=300)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(docker("image", "inspect", args.image))[0]["Config"]
        revision = config.get("Labels", {}).get("org.opencontainers.image.revision", "")
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision != actual:
            raise ValueError("Image source must match the checked out source revision")
        if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
            raise ValueError("Use a clean checkout for the corresponding-source archive")
        raw = docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
                     "--entrypoint", "tar", args.image, "-C", "/usr/share/eos-pv-helper/licenses", "-cf", "-", ".")
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            notices = {m.name.removeprefix("./"): archive.extractfile(m).read()
                       for m in archive.getmembers() if m.isfile()}
        eos = docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
                     "--entrypoint", "cat", args.image, "/tmp/eos.tar.gz")
        project = subprocess.check_output(["git", "archive", "--format=tar", revision])
        result = prepare(args.output, notices["inventory.json"], notices, eos, project,
                         Path("licenses/debian-sources.json").read_bytes(), args.cache)
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError):
        raise SystemExit("Private source preparation failed; no publication performed") from None
    print(json.dumps({"private_bundle": str(args.output), "inventory_sha256": result["inventory_sha256"],
                      "payloads": len(result["files"])}))


if __name__ == "__main__":
    main()
