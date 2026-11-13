"""Risk management and lot-size calculation module for TradeBridge.

Pure functions only — no MetaTrader 5 dependencies, no server framework dependencies.
Calculates position size strictly respecting risk percentage and broker specifications.
"""

from decimal import Decimal, ROUND_FLOOR


def calculate_lot(
    balance: float,
    risk_pct: float,
    entry: float,
    sl: float,
    tick_value_per_unit: float,
    min_lot: float,
    max_lot: float,
    step: float,
    pip_size: float = 0.01,
) -> float:
    """Calculate the lot size based on account balance, risk percentage, entry, and stop loss.

    Formula:
        risk_amount  = balance * (risk_pct / 100)
        sl_distance  = |entry - sl|
        sl_in_units  = sl_distance / pip_size (pips for forex, dollars for gold)
        loss_per_lot = sl_in_units * tick_value_per_unit
        raw_lot      = risk_amount / loss_per_lot
        lot          = round DOWN to the nearest step (NEVER round up)
        lot          = min(lot, max_lot)
        if lot < min_lot: raise ValueError("calculated lot below broker minimum")

    Args:
        balance: Account balance in account currency.
        risk_pct: Percentage of account balance to risk (e.g. 1.0 for 1%).
        entry: Entry price.
        sl: Stop loss price.
        tick_value_per_unit: Dollar profit/loss of 1 lot when price moves by 1.00 unit
            ($100/lot for gold per $1.00 move; $10/lot per pip for EURUSD).
        min_lot: Broker minimum lot size (e.g. 0.01).
        max_lot: Maximum allowed lot ceiling (e.g. 2.0).
        step: Broker lot step increment (e.g. 0.01).
        pip_size: Size of 1 pip (e.g. 0.0001 for EURUSD, 0.01 for USDJPY, 0.01/1.0 for Gold).

    Returns:
        float: Calculated lot size rounded down to the nearest lot step.

    Raises:
        ValueError: If inputs are invalid (zero or negative balance/risk, entry == sl, etc.)
                    or if the calculated lot size is below min_lot.
    """
    if balance <= 0:
        raise ValueError("balance must be greater than 0")
    if risk_pct <= 0:
        raise ValueError("risk_pct must be greater than 0")
    if entry == sl:
        raise ValueError("entry and sl cannot be equal")
    if tick_value_per_unit <= 0:
        raise ValueError("tick_value_per_unit must be greater than 0")
    if min_lot <= 0 or max_lot <= 0 or step <= 0:
        raise ValueError("lot limits and step must be greater than 0")
    if min_lot > max_lot:
        raise ValueError("min_lot cannot be greater than max_lot")
    if pip_size <= 0:
        raise ValueError("pip_size must be greater than 0")

    # Use Decimal for all calculations to prevent floating point inaccuracies
    bal_dec = Decimal(str(balance))
    risk_pct_dec = Decimal(str(risk_pct))
    entry_dec = Decimal(str(entry))
    sl_dec = Decimal(str(sl))
    tick_val_dec = Decimal(str(tick_value_per_unit))
    min_lot_dec = Decimal(str(min_lot))
    max_lot_dec = Decimal(str(max_lot))
    step_dec = Decimal(str(step))
    pip_size_dec = Decimal(str(pip_size))

    # Calculate cash risk amount
    risk_amount = bal_dec * (risk_pct_dec / Decimal("100"))

    # Calculate stop loss distance in price points
    sl_distance = abs(entry_dec - sl_dec)

    # Conversion to units:
    # 1. Gold (XAUUSD): tick_value_per_unit is 100.0 ($1.00 move = $100/lot).
    #    The stop loss distance is already in dollars ($1.00 unit).
    # 2. Forex / Pip-based symbols: tick_value_per_unit is 10.0 (per PIP).
    #    The stop loss distance must be converted to pips using pip_size.
    if tick_val_dec == Decimal("100.0") and pip_size_dec in (Decimal("0.01"), Decimal("1.0")):
        sl_in_units = sl_distance  # dollars for gold
    else:
        sl_in_units = sl_distance / pip_size_dec  # pips for forex

    loss_per_lot = sl_in_units * tick_val_dec
    if loss_per_lot <= Decimal("0"):
        raise ValueError("loss_per_lot must be greater than 0")

    raw_lot = risk_amount / loss_per_lot

    # Round DOWN to the nearest step (never round up)
    step_multiplier = (raw_lot / step_dec).to_integral_value(rounding=ROUND_FLOOR)
    lot = step_multiplier * step_dec

    # Apply lot ceiling
    if lot > max_lot_dec:
        lot = max_lot_dec

    # Verify minimum lot threshold
    if lot < min_lot_dec:
        raise ValueError("calculated lot below broker minimum")

    return float(lot)
