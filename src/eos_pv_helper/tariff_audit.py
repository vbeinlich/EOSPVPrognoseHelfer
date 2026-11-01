"""Offline reconciliation only; never another tariff source or an import transformation."""

import math
from decimal import Decimal, DecimalException


def luox_end_price_audit(*, net_market_eur_kwh=None, fixed_net_eur_kwh=None,
                         absolute_market_surcharge_fraction=None, vat_fraction=None,
                         evcc_end_eur_kwh=None, tolerance_eur_kwh="0.000001"):
    values = (net_market_eur_kwh, fixed_net_eur_kwh, absolute_market_surcharge_fraction,
              vat_fraction, evcc_end_eur_kwh, tolerance_eur_kwh)
    if any(v is None for v in values):
        return {"status": "not_verifiable", "reason": "Missing evidenced tariff components; no defaults or second price API"}
    try:
        if any(isinstance(v, bool) for v in values):
            raise ValueError()
        market, charges, surcharge, vat, observed, tolerance = [Decimal(str(v)) for v in values]
        if any(not v.is_finite() for v in (market, charges, surcharge, vat, observed, tolerance)):
            raise ValueError()
        if charges < 0 or not 0 <= surcharge <= 1 or not 0 <= vat <= 1 or not 0 <= tolerance <= Decimal("0.001"):
            raise ValueError()
        expected = (market + abs(market)*surcharge + charges)*(1+vat)
        difference = observed-expected
        if any(not math.isfinite(float(v)) for v in (expected, observed, difference)):
            raise ValueError()
        return {"status": "matched" if abs(difference) <= tolerance else "mismatch",
                "expected_eur_kwh": float(expected), "evcc_end_eur_kwh": float(observed),
                "difference_eur_kwh": float(difference), "scope": "provided_operator_contract_only",
                "import_price_modified": False}
    except (ValueError, DecimalException, OverflowError):
        return {"status": "not_verifiable", "reason": "Invalid provided tariff components"}
