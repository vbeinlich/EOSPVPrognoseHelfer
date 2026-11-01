import json

import pytest
from test_economics import saved
from test_evidence import archive, build_case, tick

from eos_pv_helper.event_context import (
    ContextError,
    observed_options,
    solution_inputs,
    verify_producer,
)
from eos_pv_helper.historical import unpack, validate
from eos_pv_helper.tariff_audit import luox_end_price_audit


def test_context_is_whitelisted_and_does_not_claim_observed_options_were_used():
    options = {"load": {"provider": "LoadAkkudoktor", "loadakkudoktor": {
        "loadakkudoktor_year_energy_kwh": 11251}, "token": "DO-NOT-EXPORT"},
        "optimization": {"genetic": {"generations": 400, "password": "DO-NOT-EXPORT"}}}
    out = observed_options(options)
    assert out["annual_load_kwh"] == 11251
    assert "not_atomic" in out["scope"] and "DO-NOT-EXPORT" not in json.dumps(out)
    used = solution_inputs(saved())
    assert used["selected_model_inputs_present"]
    assert used["annual_load_exact_binding"] == used["optimizer_options_exact_binding"] == "not_reported_by_solution"
    assert "PRIVATE" not in json.dumps(used)


def test_missing_context_is_not_backfilled_with_annual_defaults():
    assert observed_options({})["annual_load_kwh"] is None
    used = solution_inputs({})
    assert used["series"] == {} and used["selected_model_inputs_present"] is False


def test_existing_archive_adds_context_but_still_has_seven_unchanged_originals(config, monkeypatch):
    case = build_case(config, monkeypatch)
    case["settings"]["load"] = {"provider": "LoadAkkudoktor", "loadakkudoktor": {
        "loadakkudoktor_year_energy_kwh": 11251}, "secret": "DO-NOT-EXPORT"}
    monkeypatch.setenv("DRY_RUN", "false")
    assert tick(case)["evidence"]["status"] == "archived"
    manifest, files = unpack(archive(case).read_bytes())
    assert len(files) == 7
    assert manifest["producer"]["observed_options"]["annual_load_kwh"] == 11251
    assert manifest["producer"]["solution_inputs"]["selected_model_inputs_present"] is False
    assert len(manifest["producer"]["dispatched_request_sha256"]) == 64
    assert "DO-NOT-EXPORT" not in json.dumps(manifest)
    assert validate(manifest, files, now=case["now"])["accepted"]
    solution = json.loads(files["solution-"+manifest["event_version"]+".json"])
    assert not verify_producer(manifest["producer"], solution)["exact_solver_options_proven"]
    manifest["producer"]["observed_options"]["annual_load_kwh"] = 8000
    with pytest.raises(ContextError):
        verify_producer(manifest["producer"], solution)


@pytest.mark.parametrize("market", ["0.1", "-0.1", "0"])
def test_luox_reconciliation_uses_absolute_net_market_surcharge(market):
    from decimal import Decimal
    p = Decimal(market)
    expected = (p + abs(p)*Decimal("0.03") + Decimal("0.12"))*Decimal("1.19")
    result = luox_end_price_audit(net_market_eur_kwh=market, fixed_net_eur_kwh="0.12",
        absolute_market_surcharge_fraction="0.03", vat_fraction="0.19", evcc_end_eur_kwh=str(expected))
    assert result["status"] == "matched" and not result["import_price_modified"]


def test_missing_tariff_contract_and_double_markup_are_not_accepted():
    assert luox_end_price_audit(evcc_end_eur_kwh=.3)["status"] == "not_verifiable"
    result = luox_end_price_audit(net_market_eur_kwh=.1, fixed_net_eur_kwh=.12,
        absolute_market_surcharge_fraction=.03, vat_fraction=.19, evcc_end_eur_kwh=.5)
    assert result["status"] == "mismatch"


@pytest.mark.parametrize("market", [True, "NaN", "Infinity", "1e9999"])
def test_invalid_or_overflowing_tariff_values_never_become_prices(market):
    result = luox_end_price_audit(net_market_eur_kwh=market, fixed_net_eur_kwh=.12,
        absolute_market_surcharge_fraction=.03, vat_fraction=.19, evcc_end_eur_kwh=.3)
    assert result["status"] == "not_verifiable"
