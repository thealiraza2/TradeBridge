"""MetaTrader 5 Real Order Executor for TradeBridge.

Connects directly to the MetaTrader 5 terminal to execute market orders
with simultaneous Stop Loss and Take Profit, slippage deviation limits,
stale-alert detection, and intelligent requote retry logic.
"""

from typing import Any, Dict
import MetaTrader5 as mt5

from server.logger import logger

REQUOTE_RETCODES = (
    getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004),
    getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021),
    getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", 10020),
)


def _get_filling_type(symbol_info: Any) -> int:
    """Determine best supported order filling type for symbol."""
    filling_mode = getattr(symbol_info, "filling_mode", 0)
    # Check bitmask: 1 = FOK, 2 = IOC
    if filling_mode & 2:
        return mt5.ORDER_FILLING_IOC
    if filling_mode & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def execute_order(validated_alert: Dict[str, Any], lot: float, settings: Any) -> Dict[str, Any]:
    """Execute a market order on MetaTrader 5 demo account.

    Args:
        validated_alert: Validated TradingView alert payload dictionary.
        lot: Calculated position lot size.
        settings: Settings instance.

    Returns:
        dict: Execution confirmation with ticket number and executed price.

    Raises:
        ValueError: If symbol unavailable, alert is stale, or order execution fails.
    """
    symbol = validated_alert["symbol"]
    action = validated_alert["action"]
    alert_entry = float(validated_alert["entry"])
    sl = float(validated_alert["sl"])
    tp = float(validated_alert["tp"])
    magic = int(getattr(settings, "magic", 20261113))
    max_entry_dev = float(getattr(settings, "max_entry_deviation", 50.0))
    comment = str(validated_alert.get("comment", "TradeBridge"))

    # 1. Ensure MT5 connection is active
    if not mt5.terminal_info():
        logger.error("MetaTrader 5 terminal not connected")
        raise ValueError("MT5 terminal not connected")

    # 2. Select symbol in Market Watch
    if not mt5.symbol_select(symbol, True):
        err = mt5.last_error()
        logger.error(f"Failed to select symbol {symbol} in MT5: {err}")
        raise ValueError(f"symbol {symbol} not available in MT5")

    info = mt5.symbol_info(symbol)
    if info is None:
        err = mt5.last_error()
        logger.error(f"Cannot get symbol info for {symbol}: {err}")
        raise ValueError(f"symbol {symbol} info unavailable in MT5")

    # 3. Fetch latest market price
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        err = mt5.last_error()
        logger.error(f"Failed to fetch market tick for {symbol}: {err}")
        raise ValueError(f"unable to get current market price for {symbol}")

    if action == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        market_price = float(tick.ask)
    elif action == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        market_price = float(tick.bid)
    else:
        raise ValueError(f"invalid action: {action}")

    # 4. Check for stale alert (entry deviation)
    point = float(info.point) if info.point and info.point > 0 else 0.00001
    deviation_in_points = abs(market_price - alert_entry) / point
    if deviation_in_points > max_entry_dev:
        msg = (
            f"Stale alert rejected: price deviation of {deviation_in_points:.1f} points "
            f"exceeds max allowed deviation of {max_entry_dev:.1f} points "
            f"(alert entry: {alert_entry}, current market: {market_price})"
        )
        logger.warning(msg)
        raise ValueError(msg)

    # 5. Build MT5 trade request
    filling_type = _get_filling_type(info)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": market_price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_type,
    }

    logger.info(
        f"Sending order attempt: {action} {lot:.2f} {symbol} @ {market_price:.5f} "
        f"SL {sl:.5f} TP {tp:.5f} (magic={magic}, dev=20)"
    )

    # 6. Send order to MT5
    result = mt5.order_send(request)

    # 7. Check for requote and retry exactly once
    if result is not None and result.retcode in REQUOTE_RETCODES:
        logger.warning(
            f"Requote / price-off received (retcode={result.retcode}: {result.comment}). "
            f"Retrying exactly once with refreshed price..."
        )
        # Refresh tick
        new_tick = mt5.symbol_info_tick(symbol)
        if new_tick:
            new_price = float(new_tick.ask if action == "BUY" else new_tick.bid)
            request["price"] = new_price
            logger.info(f"Retry order send: {action} {lot:.2f} {symbol} @ {new_price:.5f}")
            result = mt5.order_send(request)

    # 8. Evaluate final result
    if result is None:
        last_err = mt5.last_error()
        msg = f"mt5.order_send returned None. last_error: {last_err}"
        logger.error(msg)
        raise ValueError(msg)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        last_err = mt5.last_error()
        msg = (
            f"Order failed: retcode={result.retcode} ({result.comment}), "
            f"last_error={last_err}"
        )
        logger.error(msg)
        raise ValueError(msg)

    # 9. Success
    ticket = result.order
    executed_price = float(result.price) if result.price else market_price
    logger.info(
        f"Order executed successfully: ticket={ticket}, {action} {lot:.2f} {symbol} "
        f"@ {executed_price:.5f} SL {sl:.5f} TP {tp:.5f}"
    )

    return {
        "status": "executed",
        "ticket": ticket,
        "symbol": symbol,
        "action": action,
        "lot": lot,
        "entry": executed_price,
        "sl": sl,
        "tp": tp,
    }
