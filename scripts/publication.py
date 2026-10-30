"""Plan or explicitly promote an already reviewed immutable registry image.

No build or upload path. CI never invokes --apply. A manual, globally serialized
workflow is the sole managed publisher; out-of-band registry writers must be
disabled by the operator. Registry V2 does not provide a portable atomic tag CAS.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from release_gate import validate
from source_bundle import MAX_TOTAL
from source_bundle import verify as verify_source_bundle

IMAGE = "ghcr.io/vbeinlich/eospvprognosehelfer"


def semver(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value
    ):
        raise ValueError("Only canonical stable vMAJOR.MINOR.PATCH versions are allowed")
    return tuple(int(v) for v in value[1:].split("."))


def validate_ci(runs, revision):
    matching = [run for run in runs if run.get("head_sha") == revision
                and run.get("event") == "push" and run.get("path") == ".github/workflows/test.yaml"]
    latest = max(matching, key=lambda run: (run.get("run_number", 0), run.get("run_attempt", 0)), default=None)
    if not latest or latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("Candidate source has no successful current build/test CI")
    return latest["id"]


class DockerRegistry:
    """All references are built from a fixed repository and validated input."""

    def _run(self, args, *, missing_ref=None):
        result = subprocess.run(["docker", *args], capture_output=True, timeout=300)
        if result.returncode:
            # Network/permission errors are not absence. Never print raw stderr,
            # credentials or response bodies, and never automatically retry writes.
            if missing_ref and (missing_ref + ": not found").encode() in result.stderr:
                return None
            raise ValueError("Registry command failed; inspect state before any manual retry")
        return result.stdout

    def digest(self, tag):
        ref = IMAGE + ":" + tag
        value = self._run(["buildx", "imagetools", "inspect", ref,
                           "--format", "{{.Manifest.Digest}}"], missing_ref=ref)
        if value is None:
            return None
        digest = value.decode().strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("Invalid registry digest")
        return digest

    def candidate(self, digest):
        ref = IMAGE + "@" + digest
        self._run(["pull", ref])
        labels = json.loads(self._run(["image", "inspect", ref, "--format",
                                      "{{json .Config.Labels}}"] ))
        inventory = self._run(["run", "--rm", "--network", "none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=10001:10001",
            "--entrypoint", "cat", ref, "/usr/share/eos-pv-helper/licenses/inventory.json"])
        return {"revision": labels.get("org.opencontainers.image.revision"),
                "version": labels.get("org.opencontainers.image.version"),
                "source": labels.get("org.opencontainers.image.source"), "inventory": inventory}

    def latest(self):
        digest = self.digest("latest")
        if digest is None:
            return None
        ref = IMAGE + "@" + digest
        self._run(["pull", ref])
        labels = json.loads(self._run(["image", "inspect", ref, "--format",
                                      "{{json .Config.Labels}}"] ))
        return {"digest": digest, "version": labels.get("org.opencontainers.image.version")}

    def assign(self, tag, digest):
        # Preserve the exact source manifest/index format and digest.
        self._run(["buildx", "imagetools", "create", "--prefer-index=false",
                   "--tag", IMAGE + ":" + tag, IMAGE + "@" + digest])
        if self.digest(tag) != digest:
            raise ValueError("Promoted digest differs; manual review required")

    def smoke(self, digest, revision):
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("unraid_smoke.py")),
            "--image", IMAGE + "@" + digest, "--revision", revision],
            capture_output=True, timeout=300)
        if result.returncode:
            raise ValueError("Exact candidate failed offline smoke test")

    def source_material(self, review, inventory):
        # Reviewed sources must be available anonymously *before* public image
        # promotion, not promised for a later release. Never upload here.
        with tempfile.TemporaryDirectory(prefix="eos-source-verification-") as folder:
            path = Path(folder) / "sources.tar.gz"
            digest, total = hashlib.sha256(), 0
            with urlopen(review["source_material_url"], timeout=180) as response, path.open("wb") as output:
                target = urlsplit(response.geturl())
                if target.scheme != "https" or target.hostname not in {
                    "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"
                }:
                    raise ValueError("Unexpected corresponding-source redirect")
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(block)
                    if total > MAX_TOTAL:
                        raise ValueError("Oversized corresponding-source material")
                    digest.update(block)
                    output.write(block)
            if digest.hexdigest() != review["source_material_sha256"]:
                raise ValueError("Published corresponding-source archive differs")
            verify_source_bundle(path, inventory)


def decision(version, digest, version_digest, latest, *, allow_initial=False):
    incoming = semver(version)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Full immutable candidate digest required")
    if version_digest is not None and version_digest != digest:
        raise ValueError("Version tag already points to another digest")
    if latest is None:
        if not allow_initial:
            raise ValueError("First latest assignment needs explicit approval")
    else:
        observed = semver(latest.get("version"))
        if incoming < observed:
            raise ValueError("An older release must never replace latest")
        if incoming == observed and latest.get("digest") != digest:
            raise ValueError("Same version has another latest digest")
    return {"version": version, "image_digest": digest,
            "assign_version": version_digest is None,
            "assign_latest": latest is None or latest["digest"] != digest}


def promote(record, version, digest, registry, *, apply=False):
    """Read-only by default. Callers serialize *all* versions, not each ref."""
    semver(version)
    # Missing/unreviewed approvals fail before registry access.
    validate(record, image_digest=digest, version=version)
    candidate = registry.candidate(digest)
    if candidate.get("source") != "https://github.com/vbeinlich/EOSPVPrognoseHelfer":
        raise ValueError("Candidate has unexpected source repository")
    if candidate.get("version") != version:
        raise ValueError("Candidate version label differs from requested stable version")
    validate(record, inventory=candidate["inventory"], image_digest=digest,
             source_revision=candidate["revision"], version=version)
    registry.source_material(record["license_review"], candidate["inventory"])
    registry.smoke(digest, candidate["revision"])
    options = record.get("publication", {})
    initial = options.get("allow_initial_latest") is True
    before_version, before_latest = registry.digest(version), registry.latest()
    plan = decision(version, digest, before_version, before_latest, allow_initial=initial)
    if not apply:
        return {**plan, "mode": "dry-run", "writes": 0}
    if options.get("enabled") is not True:
        raise ValueError("Public publication is not enabled in the reviewed approval")
    # Recheck live state after queued work/slow inspection, immediately before
    # the first write. The workflow holds its global concurrency slot throughout.
    if registry.digest(version) != before_version or registry.latest() != before_latest:
        raise ValueError("Registry changed after planning; revalidate without writing")
    writes = 0
    if plan["assign_version"]:
        registry.assign(version, digest)
        writes += 1
    # Do not move latest after a failed or concurrently replaced version tag.
    if registry.digest(version) != digest:
        raise ValueError("Version tag verification failed; latest left alone")
    latest = registry.latest()
    if latest != before_latest:
        raise ValueError("Latest changed during publication; manual review required")
    decision(version, digest, digest, latest, allow_initial=initial)
    if plan["assign_latest"]:
        registry.assign("latest", digest)
        writes += 1
    return {**plan, "mode": "applied", "writes": writes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="docs/GENETIC_ACCEPTANCE.json")
    parser.add_argument("--version", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply and os.environ.get("PUBLICATION_ENABLED") != "true":
        raise SystemExit("Public publication is disabled")
    try:
        result = promote(json.loads(Path(args.evidence).read_text()), args.version, args.digest,
                         DockerRegistry(), apply=args.apply)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        raise SystemExit("Publication blocked; approvals, candidate or registry require review") from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
