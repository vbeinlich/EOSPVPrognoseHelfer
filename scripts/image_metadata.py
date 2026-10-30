"""Commit-addressed GHCR names. Preview publication never pretends to be a release."""

import json
import os
import re
import tomllib
from pathlib import Path

IMAGE = "ghcr.io/vbeinlich/eospvprognosehelfer"
PREVIEW_REF = "refs/heads/feat/issue-1-pv-normalization"


def metadata(sha, ref, version):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("A full lowercase commit SHA is required")
    tags = [f"{IMAGE}:sha-{sha}"]
    promotion_tags = []
    if ref == PREVIEW_REF:
        tags.append(f"{IMAGE}:pr-3")
    elif ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or tag[1:] != version:
            raise ValueError("Release tag must be vMAJOR.MINOR.PATCH and match pyproject.toml")
        promotion_tags = [f"{IMAGE}:{tag}", f"{IMAGE}:latest"]
    elif ref != "refs/heads/main":
        raise ValueError("Publishing from this branch is disabled")
    return {"image": IMAGE, "tags": tags, "promotion_tags": promotion_tags, "revision": sha,
            "version": ref.removeprefix("refs/tags/") if ref.startswith("refs/tags/") else "preview"}


def main():
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    result = metadata(os.environ["GITHUB_SHA"], os.environ["GITHUB_REF"], version)
    Path("image-metadata.json").write_text(json.dumps(result, indent=2) + "\n")
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        handle.write("tags<<TAGS\n" + "\n".join(result["tags"]) + "\nTAGS\n")
        handle.write("version=" + result["version"] + "\n")
        handle.write("promotion_tags=" + " ".join(result["promotion_tags"]) + "\n")


if __name__ == "__main__":
    main()
