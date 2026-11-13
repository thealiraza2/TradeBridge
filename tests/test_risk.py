"""Unit tests for the risk management and lot-size calculation module."""

import pytest
from server.risk import calculate_lot


def test_xauusd_10k_risk_1pct_sl_2dollars():
    """XAUUSD, balance $10,000, risk 1% = $100, SL $2.00 away -> 0.50 lot."""
    lot = calculate_lot(
        balance=10000.0,
        risk_pct=1.0,
        entry=3902.0,
        sl=3900.0,
        tick_value_per_unit=100.0,
        min_lot=0.01,
        max_lot=2.0,
        step=0.01,
        pip_size=0.01,
    )
    assert lot == 0.50

    # Also verify with unit pip_size=1.0 and default pip_size
    assert calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01, 1.0) == 0.50
    assert calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01) == 0.50


def test_eurusd_10k_risk_1pct_sl_20pips():
    """EURUSD, balance $10,000, risk 1% = $100, SL 20 pips -> 0.50 lot."""
    lot = calculate_lot(
        balance=10000.0,
        risk_pct=1.0,
        entry=1.0820,
        sl=1.0800,
        tick_value_per_unit=10.0,
        min_lot=0.01,
        max_lot=2.0,
        step=0.01,
        pip_size=0.0001,
    )
    assert lot == 0.50


def test_xauusd_5k_risk_half_pct_sl_5dollars():
    """XAUUSD, balance $5,000, risk 0.5% = $25, SL $5.00 away -> 0.05 lot."""
    lot = calculate_lot(
        balance=5000.0,
        risk_pct=0.5,
        entry=3905.0,
        sl=3900.0,
        tick_value_per_unit=100.0,
        min_lot=0.01,
        max_lot=2.0,
        step=0.01,
        pip_size=0.01,
    )
    assert lot == 0.05


def test_round_down_never_round_up():
    """Round DOWN: raw 0.579, step 0.01 -> 0.57 (NOT 0.58)."""
    # balance $5,790, risk 1% = $57.90. entry-sl $1.00 away on Gold = $100 loss/lot.
    # raw_lot = 57.90 / 100.0 = 0.579.
    lot = calculate_lot(
        balance=5790.0,
        risk_pct=1.0,
        entry=3901.0,
        sl=3900.0,
        tick_value_per_unit=100.0,
        min_lot=0.01,
        max_lot=2.0,
        step=0.01,
        pip_size=0.01,
    )
    assert lot == 0.57
    assert lot != 0.58


def test_ceiling_max_lot():
    """Ceiling: raw 5.0, max_lot 2.0 -> 2.0."""
    # balance $50,000, risk 1% = $500. entry-sl $1.00 away on Gold = $100 loss/lot.
    # raw_lot = 500 / 100.0 = 5.0.
    lot = calculate_lot(
        balance=50000.0,
        risk_pct=1.0,
        entry=3901.0,
        sl=3900.0,
        tick_value_per_unit=100.0,
        min_lot=0.01,
        max_lot=2.0,
        step=0.01,
        pip_size=0.01,
    )
    assert lot == 2.0


def test_below_minimum_lot_raises_value_error():
    """Below minimum: calculated 0.005, min_lot 0.01 -> ValueError."""
    # balance $100, risk 1% = $1.00. entry-sl $2.00 away on Gold = $200 loss/lot.
    # raw_lot = 1.0 / 200.0 = 0.005.
    with pytest.raises(ValueError, match="calculated lot below broker minimum"):
        calculate_lot(
            balance=100.0,
            risk_pct=1.0,
            entry=3902.0,
            sl=3900.0,
            tick_value_per_unit=100.0,
            min_lot=0.01,
            max_lot=2.0,
            step=0.01,
            pip_size=0.01,
        )


def test_invalid_inputs_raise_value_error():
    """Invalid inputs: balance 0, risk_pct 0, entry == sl -> ValueError."""
    # Balance 0
    with pytest.raises(ValueError, match="balance must be greater than 0"):
        calculate_lot(0.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01)

    # Negative balance
    with pytest.raises(ValueError, match="balance must be greater than 0"):
        calculate_lot(-1000.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01)

    # Risk pct 0
    with pytest.raises(ValueError, match="risk_pct must be greater than 0"):
        calculate_lot(10000.0, 0.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01)

    # Negative risk pct
    with pytest.raises(ValueError, match="risk_pct must be greater than 0"):
        calculate_lot(10000.0, -1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01)

    # Entry == SL
    with pytest.raises(ValueError, match="entry and sl cannot be equal"):
        calculate_lot(10000.0, 1.0, 3900.0, 3900.0, 100.0, 0.01, 2.0, 0.01)

    # tick_value_per_unit <= 0
    with pytest.raises(ValueError, match="tick_value_per_unit must be greater than 0"):
        calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 0.0, 0.01, 2.0, 0.01)

    # min_lot > max_lot
    with pytest.raises(ValueError, match="min_lot cannot be greater than max_lot"):
        calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 100.0, 2.0, 1.0, 0.01)

    # step <= 0
    with pytest.raises(ValueError, match="lot limits and step must be greater than 0"):
        calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.0)

    # pip_size <= 0
    with pytest.raises(ValueError, match="pip_size must be greater than 0"):
        calculate_lot(10000.0, 1.0, 3902.0, 3900.0, 100.0, 0.01, 2.0, 0.01, pip_size=0.0)
