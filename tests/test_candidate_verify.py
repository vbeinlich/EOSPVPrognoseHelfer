import copy
import hashlib
import io
import json
import tarfile

import pytest
from candidate_verify import bind_local_image, verify_oci

REVISION = "a" * 40


def fixture(path, failure=None):
    files = {}

    def blob(raw, kind):
        raw = json.dumps(raw).encode() if isinstance(raw, dict) else raw
        digest = hashlib.sha256(raw).hexdigest()
        files["blobs/sha256/" + digest] = raw
        return {"mediaType": kind, "digest": "sha256:" + digest, "size": len(raw)}

    labels = {"org.opencontainers.image.revision": REVISION, "org.opencontainers.image.version": "v0.1.0",
              "org.opencontainers.image.source": "https://github.com/vbeinlich/EOSPVPrognoseHelfer"}
    config = {"architecture": "amd64", "os": "linux", "config": {"Labels": labels},
              "rootfs": {"diff_ids": ["sha256:" + "b" * 64]}}
    descriptor = blob(config, "application/vnd.oci.image.config.v1+json")
    layer = blob(b"synthetic-layer", "application/vnd.oci.image.layer.v1.tar")
    manifest = blob({"config": descriptor, "layers": [layer]}, "application/vnd.oci.image.manifest.v1+json")
    files["index.json"] = json.dumps({"manifests": [manifest]}).encode()
    if failure == "tampered":
        files["blobs/sha256/" + layer["digest"].split(":")[1]] = b"changed"
    elif failure == "missing":
        del files["blobs/sha256/" + layer["digest"].split(":")[1]]
    elif failure == "traversal":
        files["../secret"] = b"invalid"
    with tarfile.open(path, "w") as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    return {"Id": descriptor["digest"], "Config": {"Labels": labels},
            "RootFS": {"Layers": config["rootfs"]["diff_ids"]}}


def test_exact_private_oci_and_local_runtime_are_bound_without_registry(tmp_path):
    path = tmp_path / "private.oci.tar"
    image = fixture(path)
    proof = verify_oci(path)
    assert proof["all_oci_blobs_verified"]
    assert bind_local_image(proof, image, REVISION)
    modern = {**image, "Id": proof["oci_image_digest"],
              "Descriptor": {"annotations": {"config.digest": proof["config_digest"]}}}
    assert bind_local_image(proof, modern, REVISION)
    for field in ("config", "rootfs", "revision"):
        wrong = copy.deepcopy(image)
        if field == "config":
            wrong["Id"] = "sha256:" + "c" * 64
        elif field == "rootfs":
            wrong["RootFS"]["Layers"] = []
        else:
            wrong["Config"]["Labels"]["org.opencontainers.image.revision"] = "c" * 40
        with pytest.raises(ValueError):
            bind_local_image(proof, wrong, REVISION)


@pytest.mark.parametrize("failure", ["tampered", "missing", "traversal"])
def test_invalid_oci_is_rejected_without_extracting(tmp_path, failure):
    path = tmp_path / "private.oci.tar"
    fixture(path, failure)
    with pytest.raises((ValueError, KeyError)):
        verify_oci(path)
    assert not (tmp_path.parent / "secret").exists()
