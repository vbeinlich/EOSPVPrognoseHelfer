"""Build deterministic code-only zipapp; no solution files or configurations read."""

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    files = {"__main__.py": b"from plan_inspector import main\nraise SystemExit(main())\n"}
    for target, source in (("plan_inspector.py", "plan_inspector.py"), ("plan_view.py", "plan_view.py"),
                           ("economics.py", "economics.py"), ("economics_native.py", "economics_native.py"),
                           ("historical_validator.py", "historical.py")):
        files[target] = (ROOT / "src/eos_pv_helper" / source).read_text(encoding="utf-8").encode("utf-8")
    manifest = {"schema_version": 1, "purpose": "code-only read-only plan inspector",
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    files["bundle.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # Same header on Windows and Linux; no zlib version dependence.
            info.external_attr = 0o600 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="NEW private zipapp file; absent means binary stdout")
    args = parser.parse_args()
    raw = build()
    if args.output:
        with Path(args.output).open("xb") as handle:
            handle.write(raw)
        print(json.dumps({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "contains_measurements": False}))
    else:
        sys.stdout.buffer.write(raw)
