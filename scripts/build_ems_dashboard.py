"""Build deterministic standalone stdlib dashboard code; never include private data."""

import argparse
import hashlib
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "replay_contract",
    "dashboard",
    "dashboard_view",
    "plan_inspector",
    "economics",
    "economics_native",
    "historical",
)


def build():
    stream = io.BytesIO()
    files = {
        "__main__.py": b"from eos_pv_helper.dashboard import main\nraise SystemExit(main())\n",
        "eos_pv_helper/__init__.py": b"",
    }
    for name in MODULES:
        files["eos_pv_helper/" + name + ".py"] = (
            (ROOT / "src/eos_pv_helper" / f"{name}.py")
            .read_text(encoding="utf-8-sig")
            .replace("\r\n", "\n")
            .encode()
        )
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, raw)
    return stream.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New code-only zipapp path")
    args = parser.parse_args()
    raw = build()
    with Path(args.output).open("xb") as handle:
        handle.write(raw)
    print(hashlib.sha256(raw).hexdigest())
