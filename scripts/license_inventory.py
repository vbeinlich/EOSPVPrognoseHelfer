"""Build-time notices and exact installed-component inventory, not legal certification.

Preserve wheel/vendor notices, Debian copyright files and native EOS attribution.
For LGPL distributions and wheels missing license texts, preserve the matching
hash-verified PyPI source archive as well. No runtime network or device access.
"""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from urllib.request import urlopen

MAX_SOURCE_BYTES = 100_000_000


def validate_debian_coverage(status, index):
    installed = set()
    for paragraph in status.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in paragraph.splitlines()
                      if line and not line.startswith(" ") and ": " in line)
        if fields.get("Status") == "install ok installed":
            installed.add((fields["Package"], fields["Version"], fields.get("Source", fields["Package"])))
    expected = {(p["name"], p["version"], p["source"]) for p in index["binary_packages"]}
    sources = set()
    for _, version, source in installed:
        match = re.fullmatch(r"([^ ]+)(?: \((.+)\))?", source)
        if not match:
            raise ValueError("Invalid Debian source identity")
        sources.add((match[1], match[2] or version))
    indexed = {(p["name"], p["version"]) for p in index["source_packages"]}
    if installed != expected or sources != indexed or index.get("dsc_checksums_verified") is not True:
        raise ValueError("Base OS/source coverage changed; review its exact source index")


def notice_file(name):
    base = PurePosixPath(str(name).replace("\\", "/")).name.lower()
    return base.startswith(("license", "licence", "notice", "copying", "copyright", "authors")) and (
        not base.endswith((".py", ".pyc", ".so")))


def source_archive(name, version, directory):
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", name + version):
        raise ValueError("Invalid package identifier")
    with urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as response:
        metadata = json.load(response)
    sources = [row for row in metadata["urls"] if row["packagetype"] == "sdist"]
    if len(sources) != 1:
        raise ValueError("Exactly one source archive required for " + name)
    row = sources[0]
    url = urlsplit(row["url"])
    if url.scheme != "https" or url.hostname != "files.pythonhosted.org":
        raise ValueError("Untrusted source archive origin")
    with urlopen(row["url"], timeout=60) as response:
        raw = response.read(MAX_SOURCE_BYTES + 1)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_SOURCE_BYTES or digest != row["digests"]["sha256"]:
        raise ValueError("Source archive size/hash verification failed")
    filename = PurePosixPath(row["filename"]).name
    if filename != row["filename"] or not filename.endswith(".tar.gz"):
        raise ValueError("Unsupported source archive format")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_bytes(raw)
    # Never extract an archive tree or follow archive symlinks.
    notices = []
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            if member.isfile() and notice_file(member.name):
                if member.size > MAX_SOURCE_BYTES:
                    raise ValueError("Oversized source notice")
                target = directory / ("notice-" + hashlib.sha256(member.name.encode()).hexdigest()[:16]
                                      + "-" + PurePosixPath(member.name).name)
                target.write_bytes(archive.extractfile(member).read())
                notices.append(target.name)
    return {"filename": filename, "sha256": digest, "url": row["url"], "notices": notices}


def collect(output, *, eos=None, distributions=None, system=Path("/usr/share/doc"),
            fetch_source=source_archive):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[1]
    entries = []
    for dist in distributions if distributions is not None else importlib.metadata.distributions():
        name, version = dist.metadata["Name"], dist.version
        safe = re.sub(r"[^A-Za-z0-9_.+-]", "_", name + "-" + version)
        folder = output / "python" / safe
        folder.mkdir(parents=True, exist_ok=True)
        notices = []
        for file in dist.files or []:
            if notice_file(file):
                path = Path(dist.locate_file(file))
                if path.is_file():
                    raw = path.read_bytes()
                    # Preserve the original relative name in the manifest; flatten
                    # the destination so RECORD paths cannot traverse our bundle.
                    target = hashlib.sha256(str(file).encode()).hexdigest()[:16] + "-" + path.name
                    (folder / target).write_bytes(raw)
                    notices.append({"original": str(file), "file": target,
                                    "sha256": hashlib.sha256(raw).hexdigest()})
        expression = dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        classifiers = dist.metadata.get_all("Classifier") or []
        entry = {"name": name, "version": version, "license_metadata": expression,
                 "license_classifiers": [c for c in classifiers if c.startswith("License ::")],
                 "project_urls": dist.metadata.get_all("Project-URL") or [],
                 "directory": "python/" + safe, "notices": notices}
        if (not notices or "lgpl" in (expression + " ".join(classifiers)).lower()
                or name.lower() in ("certifi", "tzfpy", "lxml")):
            entry["source"] = fetch_source(name, version, folder)
            if not notices and not entry["source"]["notices"]:
                fallback = project / "licenses" / "upstream-notices.json"
                known = json.loads(fallback.read_text()).get(name + "==" + version)
                if not known:
                    raise ValueError("Reviewed upstream notice required: " + name + "==" + version)
                original = project / "licenses" / known["file"]
                if hashlib.sha256(original.read_bytes()).hexdigest() != known["sha256"]:
                    raise ValueError("Reviewed upstream notice hash differs")
                shutil.copyfile(original, folder / known["file"])
                entry["reviewed_upstream_notice"] = known
        entries.append(entry)
    if eos:
        folder = output / "upstream-eos"
        folder.mkdir(exist_ok=True)
        for name in ("LICENSE", "NOTICE", "pyproject.toml"):
            shutil.copyfile(Path(eos) / name, folder / name)
    # Debian's installed copyright files cover OS libraries independently of
    # Python metadata. Keep their complete texts, including bundled exceptions.
    system_entries = []
    if system.exists():
        for path in sorted(system.glob("*/copyright*")):
            if not path.is_file():
                continue
            relative = path.relative_to(system)
            target = output / "system" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
            target.write_bytes(raw)
            system_entries.append({"file": str(relative), "sha256": hashlib.sha256(raw).hexdigest()})
        status = Path("/var/lib/dpkg/status")
        if status.is_file():
            shutil.copyfile(status, output / "system" / "dpkg-status")
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(project / name, output / name)
    if (project / "licenses").exists():
        shutil.copytree(project / "licenses", output / "texts", dirs_exist_ok=True)
    result = {"schema_version": 1, "scope": "installed Python distributions and Debian copyright texts",
              "legal_review_required": True, "python": sorted(entries, key=lambda r: r["name"].lower()),
              "system": system_entries, "native_eos_source": "/opt/eos" if eos else None}
    native = output / "native" / "sources.json"
    if native.is_file():
        result["native_sources"] = json.loads(native.read_text())
        result["native_sources_manifest_sha256"] = hashlib.sha256(native.read_bytes()).hexdigest()
    debian = project / "licenses/debian-sources.json"
    if system.exists() and debian.is_file():
        index = json.loads(debian.read_text())
        validate_debian_coverage(Path("/var/lib/dpkg/status").read_text(), index)
        result["debian_source_index_sha256"] = hashlib.sha256(debian.read_bytes()).hexdigest()
        result["debian_source_packages"] = len(index["source_packages"])
    eos_tar = Path("/tmp/eos.tar.gz")
    if eos and eos_tar.is_file():
        result["native_eos_source_archive_sha256"] = hashlib.sha256(eos_tar.read_bytes()).hexdigest()
    data = project / "licenses/data-sources.json"
    if eos and data.is_file():
        mapping = json.loads(data.read_text())
        dist = next(d for d in importlib.metadata.distributions()
                    if d.metadata["Name"].lower() == mapping["distribution"])
        binary = Path(dist.locate_file(mapping["binary"]))
        if dist.version != mapping["version"] or hashlib.sha256(binary.read_bytes()).hexdigest() != mapping["binary_sha256"]:
            raise ValueError("Timezone data artifact changed; source/license mapping needs review")
        result["data_sources"] = mapping
    embedded = project / "licenses/embedded-sources.json"
    if eos and embedded.is_file():
        mapping = json.loads(embedded.read_text())
        dist = next(d for d in importlib.metadata.distributions()
                    if d.metadata["Name"].lower() == mapping["distribution"])
        if dist.version != mapping["version"] or any(
            hashlib.sha256(Path(dist.locate_file("lxml/" + name)).read_bytes()).hexdigest() != digest
            for name, digest in mapping["binaries"].items()
        ):
            raise ValueError("Embedded libiconv artifact changed; review its matching sources")
        result["embedded_sources"] = mapping
    (output / "inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--eos", type=Path)
    args = parser.parse_args()
    result = collect(args.output, eos=args.eos)
    print("Preserved notices for", len(result["python"]), "Python distributions and",
          len(result["system"]), "OS packages; release review remains required")
