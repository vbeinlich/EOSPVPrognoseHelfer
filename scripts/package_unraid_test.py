"""Package already built, frozen test images. No registry push or remote Docker."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path

COMMIT = "546baa63ade70cab20c67a7410575c8d2b8dc667"
IMAGES = {
    "helper": ("ghcr.io/vbeinlich/eospvprognosehelfer:ems-v1.1-test-546baa63",
               "images/eos-helper-ems-v1.1-test-546baa63-linux-amd64.tar"),
    "worker": ("ems-native-replay:ems-v1.1-test-546baa63",
               "images/ems-replay-ems-v1.1-test-546baa63-linux-amd64.tar"),
}


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+"\n", encoding="utf-8")


def package(destination, source, tooling):
    def docker(*args):
        return subprocess.check_output(["docker", "--context", "desktop-linux", *args], text=True).strip()

    endpoint = docker("context", "inspect", "desktop-linux", "--format", '{{.Endpoints.docker.Host}}')
    assert endpoint == "npipe:////./pipe/dockerDesktopLinuxEngine"
    result = {"source_commit": COMMIT, "platform": "linux/amd64", "registry_push": False,
              "production_activation_approved": False, "images": {}}
    source_archive = destination / "source-546baa63.tar"
    with tarfile.open(source_archive) as archive:
        assert archive.pax_headers["comment"] == COMMIT
        archived_modules = {m.name.removeprefix("src/eos_pv_helper/"):
            hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            for m in archive.getmembers() if m.isfile() and m.name.startswith("src/eos_pv_helper/")
            and m.name.endswith(".py")}
    result["source_archive"] = {"file": source_archive.name, "sha256": sha(source_archive),
                                "git_archive_commit": COMMIT}
    environment = json.loads(docker("version", "--format", "{{json .}}"))
    write(destination / "reports/build-environment.json", environment)
    probe = r'''
import hashlib,importlib.metadata,importlib.util,json,os,sys,tarfile
from pathlib import Path
from eos_pv_helper import evidence
from eos_pv_helper.economics_native import fingerprint
import akkudoktoreos
fingerprint(Path(akkudoktoreos.__path__[0]))
archive_sha=hashlib.sha256(Path('/tmp/eos.tar.gz').read_bytes()).hexdigest()
assert archive_sha=='500975e7ba614db6481e8762b51649dd9e0ad8f226753b7b9fa5cb980f51472e'
source_files=0
with tarfile.open('/tmp/eos.tar.gz') as archive:
 for entry in archive.getmembers():
  if entry.isfile():
   relative=Path(entry.name).parts[1:]
   expected=archive.extractfile(entry).read()
   assert Path('/opt/eos',*relative).read_bytes()==expected
   source_files+=1
root=Path(importlib.util.find_spec('eos_pv_helper').origin).parent
modules={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
         for p in root.rglob('*.py')}
assert all(k in modules for k in ('evidence.py','historical.py','doctor.py','sync.py'))
assert os.getuid()==os.getgid()==10001 and not evidence.enabled({})
versions={d.metadata['Name']:d.version for d in importlib.metadata.distributions()}
licenses=json.loads(Path('/usr/share/eos-pv-helper/licenses/inventory.json').read_bytes())
assert licenses['python'] and licenses['system'] and licenses['native_sources']
print(json.dumps({'python':sys.version,'uid':os.getuid(),'gid':os.getgid(),
  'modules':modules,'dependencies':versions,'native_source_fingerprint_verified':True,
  'eos_source_archive_sha256':archive_sha,'eos_source_files_byte_verified':source_files,
  'evidence_default_enabled':False,'license_inventory':licenses}))
'''
    env_lines = []
    for name, (tag, relative_tar) in IMAGES.items():
        path = destination / relative_tar
        with tarfile.open(path) as archive:
            manifest = json.load(archive.extractfile("manifest.json"))
            assert len(manifest) == 1 and tag in manifest[0]["RepoTags"]
            raw = archive.extractfile(manifest[0]["Config"]).read()
            config_id = "sha256:"+hashlib.sha256(raw).hexdigest()
            config = json.loads(raw)
        inspected = json.loads(docker("image", "inspect", tag))[0]
        assert inspected["Os"] == "linux" and inspected["Architecture"] == "amd64"
        assert inspected["Config"]["User"] == "10001:10001"
        if name == "helper":
            assert inspected["Config"]["Entrypoint"] == ["python", "-m", "eos_pv_helper"]
            assert inspected["Config"]["Cmd"] == ["run"] and "DRY_RUN=true" in inspected["Config"]["Env"]
        inventory = json.loads(docker("run", "--rm", "--pull=never", "--network", "none", "--read-only",
            "--user", "10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--entrypoint", "python", tag, "-c", probe))
        expected = {p.relative_to(source / "src/eos_pv_helper").as_posix(): sha(p)
                    for p in (source / "src/eos_pv_helper").rglob("*.py")}
        assert inventory["modules"] == expected == archived_modules
        assert config["rootfs"]["diff_ids"] == inspected["RootFS"]["Layers"]
        write(destination / ("reports/"+name+"-installed-inventory.json"), inventory)
        write(destination / ("reports/"+name+"-image-inspect.json"), inspected)
        image = {"tag": tag, "tar": relative_tar, "tar_sha256": sha(path), "tar_bytes": path.stat().st_size,
                 "docker_config_image_id": config_id, "local_engine_image_id": inspected["Id"],
                 "local_manifest_digest": inspected.get("Descriptor", {}).get("digest"),
                 "registry_manifest_digest": None, "source_modules_match_frozen_commit": True}
        result["images"][name] = image
        prefix = name.upper()
        env_lines += [prefix+"_TAG="+tag, prefix+"_TAR="+relative_tar,
                      prefix+"_CONFIG_ID="+config_id, prefix+"_LOCAL_ID="+inspected["Id"]]
        # Copy only image-bundled public license/source inventory, never container data.
        temporary = "ems-package-licenses-"+uuid.uuid4().hex
        try:
            docker("create", "--name", temporary, "--network", "none", "--read-only", "--entrypoint", "python", tag, "--version")
            folder = destination / "licenses" / name
            folder.mkdir(parents=True, exist_ok=True)
            docker("cp", temporary+":/usr/share/eos-pv-helper/licenses/.", str(folder))
        finally:
            docker("rm", temporary)
    env_lines.append("ROLLBACK_SHA256=e7f988ab5dbf6807fbb9072b5d66cd0b0b88fcf73b898c0e983f8c2a2e7321a3")
    (destination / "images.env").write_text("\n".join(env_lines)+"\n", encoding="utf-8")
    for path in (tooling / "deploy/unraid-test").iterdir():
        if path.is_file():
            shutil.copyfile(path, destination / "tools" / path.name)
    for name in ("unraid-dashboard-publish.sh", "unraid-dashboard-replay-catalog.sh", "unraid-ems-dashboard.sh"):
        shutil.copyfile(source / "scripts" / name, destination / "tools" / name)
    bundle = destination / "tools/ems-dashboard-final.pyz"
    if not bundle.exists():
        subprocess.run(["python", str(source / "scripts/build_ems_dashboard.py"), "--output", str(bundle)], check=True)
    assert sha(bundle) == json.loads((source / "docs/DASHBOARD_CODE_HASHES.json").read_text())["dashboard_bundle_sha256"]
    write(destination / "manifest.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.destination, args.source, Path(__file__).resolve().parents[1]), indent=2))
