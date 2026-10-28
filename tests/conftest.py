from datetime import UTC, datetime

import pytest

from eos_pv_helper.normalize import STEP, SolarNight


@pytest.fixture
def forecast_case():
    start = datetime(2026, 6, 20, tzinfo=UTC)
    night = SolarNight(52.52, 13.405, "Europe/Berlin")
    # Synthetic daytime inputs. No model, API or installation data.
    values = {start + i * STEP: (0 if i % 9 == 0 else 3210.12345)
              for i in range(192) if not night(start + i * STEP, start + (i + 1) * STEP)}
    return start, night, values


@pytest.fixture
def config(tmp_path):
    return {
        "source": {"kind": "file", "path": "unused.json"},
        "location": {"latitude": 52.52, "longitude": 13.405, "timezone": "Europe/Berlin"},
        "horizon": {"start": "2026-06-20T00:00:00Z", "hours": 48},
        "output": {"directory": str(tmp_path)},
        "eos": {"write_enabled": False},
    }


@pytest.fixture
def schema():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures/eos-import-contract.json").read_text())
