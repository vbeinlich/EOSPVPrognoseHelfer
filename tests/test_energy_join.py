import csv
import hashlib
import io
import json

import pytest
from test_energy_data import at

from eos_pv_helper.energy_data import EnergyDataError
from eos_pv_helper.energy_join import join_csv, main


def encode(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def inputs():
    left = [{"start_utc": at(h), "end_utc": at(h + 1), "load_wh": "300"} for h in range(2)]
    right = [{"start_utc": at(h), "end_utc": at(h + 1), "heatpump_wh": "500",
              "vehicle_barn_wh": "200", "vehicle_barn_5min_coverage": "12/12"} for h in range(2)]
    return left, right


def test_exact_join_reorders_supplement_without_overwriting_house_load_or_calculating():
    left, right = inputs()
    a, b = encode(left), encode(list(reversed(right)))
    joined, audit = join_csv(a, b, start=at(), end=at(2))
    rows = list(csv.DictReader(io.StringIO(joined.decode())))
    assert len(rows) == 2 and rows[0]["load_wh"] == "300"
    assert rows[0]["heatpump_wh"] == "500" and rows[0]["vehicle_barn_wh"] == "200"
    assert rows[0]["vehicle_barn_5min_coverage"] == "12/12"
    assert audit["columns_recalculated"] is False
    assert audit["source_sha256"] == [hashlib.sha256(raw).hexdigest() for raw in (a, b)]


@pytest.mark.parametrize("failure", ["duplicate", "missing", "end", "collision", "overlap", "gap"])
def test_bad_joins_fail_without_partial_or_positional_matching(failure):
    left, right = inputs()
    if failure == "duplicate":
        right[1] = right[0]
    elif failure == "missing":
        right.pop()
    elif failure == "end":
        right[0]["end_utc"] = at(1, 1)
    elif failure == "collision":
        for r in right:
            r["load_wh"] = "wrong"
    elif failure == "overlap":
        for rows in (left, right):
            rows[1]["start_utc"], rows[1]["end_utc"] = at(seconds=1800), at(1, 1800)
    else:
        for rows in (left, right):
            rows[1]["start_utc"], rows[1]["end_utc"] = at(2), at(3)
    with pytest.raises(EnergyDataError):
        join_csv(encode(left), encode(right), start=at(), end=at(2))


def test_join_cli_keeps_exact_original_bytes_and_refuses_overwrite(tmp_path):
    left, right = inputs()
    a, b, out = tmp_path / "base.csv", tmp_path / "supplement.csv", tmp_path / "joined"
    a.write_bytes(encode(left))
    b.write_bytes(encode(right))
    before = a.read_bytes(), b.read_bytes()
    args = ["--base", str(a), "--supplement", str(b), "--start", at(), "--end", at(2), "--output", str(out)]
    assert main(args) == 0
    assert (a.read_bytes(), b.read_bytes()) == before
    assert (out / "base-original.csv").read_bytes() == before[0]
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert all(hashlib.sha256((out / name).read_bytes()).hexdigest() == sha
               for name, sha in manifest["artifacts_sha256"].items())
    assert main(args) == 2
