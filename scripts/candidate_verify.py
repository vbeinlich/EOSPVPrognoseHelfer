"""Verify private OCI, loaded local image and source material; never pull or push."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

from source_bundle import verify as verify_sources

MAX_ARCHIVE = 2_000_000_000
MAX_JSON = 4_000_000


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_oci(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Unsafe or oversized private OCI archive")
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if len(members) > 1000 or len({m.name for m in members}) != len(members):
            raise ValueError("Ambiguous OCI archive entries")
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError("Unsafe OCI archive entry")

        def read_json(name):
            member = archive.getmember(name)
            if member.size > MAX_JSON:
                raise ValueError("Oversized OCI metadata")
            return json.load(archive.extractfile(member))

        def blob(descriptor):
            digest = descriptor["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError("Full SHA256 OCI descriptor required")
            name = "blobs/sha256/" + digest.split(":")[1]
            member = archive.getmember(name)
            if member.size != descriptor["size"]:
                raise ValueError("OCI descriptor size differs")
            hashed = hashlib.sha256()
            with archive.extractfile(member) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    hashed.update(block)
            if "sha256:" + hashed.hexdigest() != digest:
                raise ValueError("OCI blob hash differs")
            return name

        index = read_json("index.json")
        if len(index["manifests"]) != 1:
            raise ValueError("Use a single-platform candidate without attestations")
        descriptor = index["manifests"][0]
        if descriptor["mediaType"] != "application/vnd.oci.image.manifest.v1+json":
            raise ValueError("Expected canonical OCI image manifest")
        manifest = read_json(blob(descriptor))
        config = read_json(blob(manifest["config"]))
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("Release candidate must be linux/amd64")
        for layer in manifest["layers"]:
            blob(layer)
        return {"oci_image_digest": descriptor["digest"], "config_digest": manifest["config"]["digest"],
                "config": config, "oci_archive_sha256": digest_file(path),
                "oci_archive_bytes": path.stat().st_size, "all_oci_blobs_verified": True}


def bind_local_image(proof, inspect, revision):
    config_digest = inspect.get("Descriptor", {}).get("annotations", {}).get("config.digest", inspect["Id"])
    if (config_digest != proof["config_digest"]
            or inspect["RootFS"]["Layers"] != proof["config"]["rootfs"]["diff_ids"]
            or inspect["Config"]["Labels"] != proof["config"]["config"]["Labels"]):
        raise ValueError("Loaded Docker image differs from the private OCI candidate")
    labels = proof["config"]["config"]["Labels"]
    if (labels.get("org.opencontainers.image.revision") != revision
            or labels.get("org.opencontainers.image.version") != "v0.1.0"
            or labels.get("org.opencontainers.image.source") != "https://github.com/vbeinlich/EOSPVPrognoseHelfer"):
        raise ValueError("Candidate source/version/repository labels differ")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oci", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--docker-context", required=True, help="Explicit local development context")
    args = parser.parse_args()

    def docker(*command):
        return subprocess.check_output(["docker", "--context", args.docker_context, *command], timeout=300)

    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
            raise ValueError("Full source revision required")
        context = json.loads(subprocess.check_output(
            ["docker", "context", "inspect", args.docker_context], timeout=30))[0]
        if not context["Endpoints"]["docker"]["Host"].startswith(("unix://", "npipe://")):
            raise ValueError("Remote production Docker endpoints are forbidden")
        proof = verify_oci(args.oci)
        bind_local_image(proof, json.loads(docker("image", "inspect", args.image))[0], args.source_revision)
        inventory = docker("run", "--rm", "--network", "none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=10001:10001", "--entrypoint", "cat", args.image,
            "/usr/share/eos-pv-helper/licenses/inventory.json")
        source_manifest = verify_sources(args.sources, inventory)
        del proof["config"]
        proof.update(source_revision=args.source_revision, inventory_sha256=hashlib.sha256(inventory).hexdigest(),
            source_material_sha256=digest_file(args.sources), source_material_bytes=args.sources.stat().st_size,
            source_material_payloads=len(source_manifest["files"]), source_coverage_verified=True,
            config_and_rootfs_match_local_image=True, published=False, approved=False)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError):
        raise SystemExit("Private candidate verification failed; no publication performed") from None
    print(json.dumps(proof, indent=2))


if __name__ == "__main__":
    main()
