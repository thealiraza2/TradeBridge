"""Shared test fixtures.

The MetaTrader5 package is Windows-only. When it is not installed (Linux /
macOS), install a minimal stub module so the server code can be imported and
the test-suite can run with unittest.mock. The stub raises if any real MT5
call is attempted — every test that needs MT5 behaviour patches it with a
mock, so the stub is never actually called.
"""
import sys
import types

try:
    import MetaTrader5  # noqa: F401
except ImportError:
    _stub = types.ModuleType("MetaTrader5")
    _stub.TRADE_RETCODE_DONE = 10009
    _stub.TRADE_RETCODE_PLACED = 10008
    _stub.TRADE_RETCODE_REQUOTE = 10004
    _stub.TRADE_RETCODE_PRICE_OFF = 10021
    _stub.TRADE_RETCODE_PRICE_CHANGED = 10020
    _stub.TRADE_ACTION_DEAL = 1
    _stub.ORDER_TYPE_BUY = 0
    _stub.ORDER_TYPE_SELL = 1
    _stub.ORDER_TIME_GTC = 0
    _stub.ORDER_FILLING_FOK = 0
    _stub.ORDER_FILLING_IOC = 1
    _stub.ORDER_FILLING_RETURN = 2
    _stub.POSITION_TYPE_BUY = 0
    _stub.POSITION_TYPE_SELL = 1
    _stub.DEAL_ENTRY_OUT = 1

    def _unavailable(*args, **kwargs):
        raise NotImplementedError(
            "MetaTrader5 is not installed (Windows-only package). "
            "Tests replace it with mocks; a real terminal is required to run the server."
        )

    for _name in (
        "initialize",
        "shutdown",
        "terminal_info",
        "account_info",
        "last_error",
        "symbol_select",
        "symbol_info",
        "symbol_info_tick",
        "order_send",
        "positions_get",
        "history_deals_get",
    ):
        setattr(_stub, _name, _unavailable)

    sys.modules["MetaTrader5"] = _stub
