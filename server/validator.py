"""TradingView webhook alert validation module for TradeBridge.

Performs strict, ordered verification of incoming alert payloads.
Enforces security, mapping, price logic, and duplicate prevention.
No server framework dependencies and no MT5 connection.
"""

from typing import Any, Dict, Set


def validate_alert(data: Dict[str, Any], settings: Any, seen_ids: Set[str]) -> Dict[str, Any]:
    """Validate an incoming TradingView alert payload against settings and risk rules.

    Checks are performed in the following strict order:
      1. Secret verification (matches settings.webhook_secret; never logged)
      2. Action verification (must be BUY or SELL)
      3. Symbol mapping & whitelist check
      4. Entry, SL, TP numerical & non-zero check
      5. Side check (BUY: sl < entry < tp; SELL: tp < entry < sl)
      6. Risk percentage check (0 < risk_pct <= 5; defaults to settings if missing)
      7. Max lot check (max_lot > 0; defaults to settings if missing)
      8. Alert ID uniqueness check (duplicate protection; retains up to 1000 seen IDs)

    Args:
        data: Raw dictionary payload received from TradingView alert webhook.
        settings: Settings instance containing credentials, defaults, and symbols mapping.
        seen_ids: Set of recently seen alert_id strings for deduplication.

    Returns:
        dict: Validated alert payload with MT5 mapped symbol and filled defaults.

    Raises:
        ValueError: If any validation check fails.
    """
    if not isinstance(data, dict):
        raise ValueError("alert data must be a dictionary")

    # 1. Secret verification (NEVER log the secret)
    if "secret" not in data or data["secret"] != settings.webhook_secret:
        raise ValueError("invalid secret")

    # 2. Action verification
    action = data.get("action")
    if action not in ("BUY", "SELL"):
        raise ValueError("invalid action, must be BUY or SELL")

    # 3. Symbol mapping & whitelist verification
    raw_symbol = data.get("symbol")
    if not raw_symbol or not isinstance(raw_symbol, str):
        raise ValueError("missing or invalid symbol")

    mt5_symbol = settings.tv_to_mt5.get(raw_symbol, raw_symbol)
    if mt5_symbol not in settings.whitelist:
        raise ValueError("symbol not whitelisted")

    # 4. Entry, SL, TP numerical and non-zero verification
    for field in ("entry", "sl", "tp"):
        if field not in data:
            raise ValueError(f"missing {field}")
        val = data[field]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(f"{field} must be a number")
        if val == 0:
            raise ValueError(f"{field} cannot be zero")

    entry = float(data["entry"])
    sl = float(data["sl"])
    tp = float(data["tp"])

    # 5. Side check
    if action == "BUY":
        if not (sl < entry < tp):
            raise ValueError("BUY requires sl < entry < tp")
    elif action == "SELL":
        if not (tp < entry < sl):
            raise ValueError("SELL requires tp < entry < sl")

    # 6. Risk percentage check (0 < risk_pct <= 5, fill from default if missing)
    if "risk_pct" in data and data["risk_pct"] is not None:
        risk_val = data["risk_pct"]
        if isinstance(risk_val, bool) or not isinstance(risk_val, (int, float)):
            raise ValueError("risk_pct must be a number")
        if not (0 < risk_val <= 5):
            raise ValueError("risk_pct must be greater than 0 and less than or equal to 5")
        risk_pct = float(risk_val)
    else:
        risk_pct = float(settings.default_risk_pct)

    # 7. Max lot check (max_lot > 0, fill from default if missing)
    if "max_lot" in data and data["max_lot"] is not None:
        lot_val = data["max_lot"]
        if isinstance(lot_val, bool) or not isinstance(lot_val, (int, float)):
            raise ValueError("max_lot must be a number")
        if lot_val <= 0:
            raise ValueError("max_lot must be greater than 0")
        max_lot = float(lot_val)
    else:
        max_lot = float(settings.default_max_lot)

    # 8. Alert ID verification & duplicate protection
    alert_id = data.get("alert_id")
    if not alert_id or not isinstance(alert_id, str) or not alert_id.strip():
        raise ValueError("missing alert_id")

    if alert_id in seen_ids:
        raise ValueError(f"duplicate alert_id: {alert_id}")

    seen_ids.add(alert_id)
    if len(seen_ids) > 1000:
        # A set has no order, so the oldest id cannot be evicted precisely.
        # Clearing is the safe documented behaviour: after 1000 alerts the
        # dedup window resets instead of silently dropping an arbitrary id.
        seen_ids.clear()
        seen_ids.add(alert_id)

    return {
        "action": action,
        "symbol": mt5_symbol,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "risk_pct": risk_pct,
        "max_lot": max_lot,
        "alert_id": alert_id,
        "comment": str(data.get("comment", "")),
    }
