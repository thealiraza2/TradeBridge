"""FastAPI server and webhook endpoint for TradeBridge.

Receives TradingView alerts, validates them, enforces safety checks
(kill switch, max daily loss, max open positions), calculates lot sizes
using MT5 runtime specs, and executes orders via MetaTrader 5 (Phase 6).
"""

from collections import deque
from contextlib import asynccontextmanager
import datetime
import json
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
import MetaTrader5 as mt5

from server.config import Settings, load_settings
from server.executor import execute_order
from server.logger import BASE_DIR, LOG_FILE, logger, sanitize_payload
from server.risk import calculate_lot
from server.validator import validate_alert

# In-memory states
seen_ids: Set[str] = set()
kill_switch_active: bool = False
recent_alerts: Deque[Dict[str, Any]] = deque(maxlen=50)

RUNTIME_SETTINGS_FILE = BASE_DIR / "config" / "runtime_settings.json"


def _record_alert(
    validated_alert: Optional[Dict[str, Any]],
    lot: Optional[float],
    status: str,
    reason_or_ticket: str,
) -> None:
    """Record an alert in the in-memory history for dashboard visibility."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time": now_str,
        "symbol": validated_alert.get("symbol", "N/A") if validated_alert else "N/A",
        "action": validated_alert.get("action", "N/A") if validated_alert else "N/A",
        "lot": lot,
        "status": status,
        "reason": reason_or_ticket if status != "executed" else "",
        "ticket": reason_or_ticket if status == "executed" else None,
    }
    recent_alerts.append(entry)


def _calculate_daily_realized_loss() -> float:
    """Calculate net realized profit/loss from MT5 deals history for today (UTC)."""
    try:
        if not mt5.terminal_info():
            return 0.0
        now = datetime.datetime.now(datetime.timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(today_start, now)
        if not deals:
            return 0.0
        realized = 0.0
        for deal in deals:
            # Only count closed position deals (DEAL_ENTRY_OUT)
            if getattr(deal, "entry", None) == getattr(mt5, "DEAL_ENTRY_OUT", 1):
                realized += (deal.profit + deal.commission + deal.swap)
        return realized
    except Exception as exc:
        logger.warning(f"Could not calculate daily realized loss from MT5: {exc}")
        return 0.0


def _count_open_positions() -> int:
    """Count active open positions in MT5."""
    try:
        if not mt5.terminal_info():
            return 0
        positions = mt5.positions_get()
        return len(positions) if positions is not None else 0
    except Exception as exc:
        logger.warning(f"Could not count open positions in MT5: {exc}")
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for loading configuration and initializing MetaTrader 5."""
    # 1. Load configuration
    try:
        app.state.settings = load_settings()
        # Overlay any saved runtime settings if present
        if RUNTIME_SETTINGS_FILE.exists():
            try:
                with open(RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if "default_risk_pct" in saved:
                    app.state.settings.default_risk_pct = float(saved["default_risk_pct"])
                if "default_max_lot" in saved:
                    app.state.settings.default_max_lot = float(saved["default_max_lot"])
                if "max_positions" in saved:
                    app.state.settings.max_positions = int(saved["max_positions"])
                if "max_daily_loss_pct" in saved:
                    app.state.settings.max_daily_loss_pct = float(saved["max_daily_loss_pct"])
                logger.info("Applied saved runtime settings overrides.")
            except Exception as e:
                logger.warning(f"Failed to load runtime_settings.json: {e}")

        logger.info("TradeBridge configuration loaded successfully.")
    except Exception as exc:
        logger.error(f"Failed to load settings at startup: {exc}")
        raise exc

    # 2. Connect to MetaTrader 5
    settings: Settings = app.state.settings
    try:
        login = int(settings.mt5_login)
        password = str(settings.mt5_password)
        server = str(settings.mt5_server)
        connected = mt5.initialize(login=login, password=password, server=server)
        if connected:
            acc_info = mt5.account_info()
            balance = acc_info.balance if acc_info else "unknown"
            logger.info(
                f"Connected to MetaTrader 5 demo account: {login} on {server} (Balance: {balance})"
            )
        else:
            err = mt5.last_error()
            logger.warning(
                f"MetaTrader 5 initialization failed: {err}. Server starting with mt5_connected: False"
            )
    except Exception as exc:
        logger.warning(f"Error during MT5 initialization: {exc}")

    yield

    # 3. Graceful shutdown
    try:
        mt5.shutdown()
        logger.info("MetaTrader 5 connection closed.")
    except Exception:
        pass


app = FastAPI(
    title="TradeBridge",
    description="TradingView to MetaTrader 5 Execution Bridge with Safety Systems",
    version="0.9.0",
    lifespan=lifespan,
)


@app.get("/")
def get_root() -> Dict[str, Any]:
    """Root endpoint returning service identity and current phase."""
    return {"service": "TradeBridge", "phase": 9}


@app.get("/health")
def get_health() -> Dict[str, Any]:
    """Health check endpoint showing MT5 status, kill switch state, account, and balance."""
    is_connected = False
    account_login = None
    balance = None

    try:
        term_info = mt5.terminal_info()
        acc_info = mt5.account_info()
        if term_info is not None and acc_info is not None:
            is_connected = True
            account_login = acc_info.login
            balance = float(acc_info.balance)
    except Exception as exc:
        logger.warning(f"Error checking MT5 health: {exc}")

    settings: Settings = getattr(app.state, "settings", None)
    mode_str = settings.mode if settings else "demo"

    res = {
        "status": "ok",
        "mt5_connected": is_connected,
        "kill_switch": kill_switch_active,
        "mode": mode_str,
    }
    if is_connected:
        res["account"] = account_login
        res["balance"] = balance

    return res


@app.post("/kill")
async def post_kill(request: Request) -> JSONResponse:
    """Toggle in-memory emergency kill switch."""
    global kill_switch_active
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "reason": "invalid JSON"})

    if "kill" not in data:
        return JSONResponse(status_code=400, content={"status": "error", "reason": "missing 'kill' parameter"})

    kill_switch_active = bool(data["kill"])
    msg = f"Kill switch {'ACTIVATED' if kill_switch_active else 'DEACTIVATED'}"
    logger.warning(msg)
    return JSONResponse(status_code=200, content={"status": "ok", "kill_switch": kill_switch_active})


@app.get("/positions")
def get_positions() -> Dict[str, Any]:
    """Get active open MT5 positions (ticket, symbol, type, volume, open price, SL, TP, profit)."""
    pos_list = []
    try:
        if mt5.terminal_info():
            positions = mt5.positions_get()
            if positions:
                for p in positions:
                    action_type = "BUY" if p.type == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL"
                    pos_list.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": action_type,
                        "volume": float(p.volume),
                        "open_price": float(p.price_open),
                        "sl": float(p.sl),
                        "tp": float(p.tp),
                        "profit": float(p.profit),
                    })
    except Exception as exc:
        logger.error(f"Error fetching MT5 positions: {exc}")
    return {"status": "ok", "positions": pos_list}


@app.get("/settings")
def get_settings() -> Dict[str, Any]:
    """Get current runtime risk settings."""
    settings: Settings = getattr(app.state, "settings", None)
    if settings is None:
        settings = load_settings()
    return {
        "status": "ok",
        "settings": {
            "default_risk_pct": settings.default_risk_pct,
            "default_max_lot": settings.default_max_lot,
            "max_positions": settings.max_positions,
            "max_daily_loss_pct": settings.max_daily_loss_pct,
            "mode": settings.mode,
        },
    }


@app.post("/settings")
async def post_settings(request: Request) -> JSONResponse:
    """Update risk defaults, max lot, max positions, max daily loss in memory and runtime config file."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "reason": "invalid JSON"})

    settings: Settings = getattr(app.state, "settings", None)
    if settings is None:
        settings = load_settings()
        app.state.settings = settings

    if "default_risk_pct" in data:
        val = float(data["default_risk_pct"])
        if not (0 < val <= 5.0):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "reason": "default_risk_pct must be between 0.1 and 5.0"},
            )
        settings.default_risk_pct = val

    if "default_max_lot" in data:
        val = float(data["default_max_lot"])
        if val <= 0:
            return JSONResponse(status_code=400, content={"status": "error", "reason": "default_max_lot must be > 0"})
        settings.default_max_lot = val

    if "max_positions" in data:
        val = int(data["max_positions"])
        if val <= 0:
            return JSONResponse(status_code=400, content={"status": "error", "reason": "max_positions must be > 0"})
        settings.max_positions = val

    if "max_daily_loss_pct" in data:
        val = float(data["max_daily_loss_pct"])
        if not (0 < val <= 100.0):
            return JSONResponse(
                status_code=400,
                content={"status": "error", "reason": "max_daily_loss_pct must be > 0"},
            )
        settings.max_daily_loss_pct = val

    # Persist to config/runtime_settings.json (NEVER to .env)
    runtime_data = {
        "default_risk_pct": settings.default_risk_pct,
        "default_max_lot": settings.default_max_lot,
        "max_positions": settings.max_positions,
        "max_daily_loss_pct": settings.max_daily_loss_pct,
    }
    try:
        RUNTIME_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RUNTIME_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(runtime_data, f, indent=2)
        logger.info(f"Runtime settings saved to {RUNTIME_SETTINGS_FILE.name}")
    except Exception as exc:
        logger.warning(f"Failed to write runtime settings: {exc}")

    return JSONResponse(status_code=200, content={"status": "ok", "settings": runtime_data})


@app.get("/dashboard")
def get_dashboard() -> FileResponse:
    """Serve the single-page dashboard HTML."""
    dashboard_path = BASE_DIR / "dashboard" / "index.html"
    if not dashboard_path.exists():
        return JSONResponse(status_code=404, content={"status": "error", "reason": "dashboard file not found"})
    return FileResponse(dashboard_path, media_type="text/html")


@app.get("/alerts")
def get_alerts() -> Dict[str, Any]:
    """Return the recent alert history for dashboard display."""
    return {"status": "ok", "alerts": list(recent_alerts)}


@app.get("/logs")
def get_logs() -> Dict[str, Any]:
    """Return the last 100 lines of logs/tradebridge.log."""
    if not LOG_FILE.exists():
        return {"status": "ok", "lines": []}

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return {"status": "ok", "lines": [line.rstrip() for line in lines[-100:]]}
    except Exception as exc:
        logger.error(f"Failed to read logs: {exc}")
        return {"status": "error", "reason": str(exc), "lines": []}


@app.post("/webhook")
async def post_webhook(request: Request) -> JSONResponse:
    """TradingView webhook endpoint with safety gates.

    Workflow:
      1. validate_alert() - checks secret, action, symbol mapping, price order, risk limits.
      2. Safety check: Kill switch active? -> reject.
      3. Safety check: Max daily loss reached? -> reject.
      4. Safety check: Max open positions reached? -> reject.
      5. Read live broker specs and account balance.
      6. calculate_lot() - pure-python precision lot calculation.
      7. execute_order() - real MetaTrader 5 order execution with SL/TP.
    """
    try:
        data = await request.json()
    except Exception:
        logger.warning("Webhook received invalid non-JSON body")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "reason": "invalid JSON body"},
        )

    logger.info(f"Incoming alert: {sanitize_payload(data)}")

    settings: Settings = getattr(app.state, "settings", None)
    if settings is None:
        try:
            settings = load_settings()
            app.state.settings = settings
        except Exception as exc:
            logger.error(f"Configuration unavailable: {exc}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "reason": "configuration error"},
            )

    # 1. Validate Alert
    try:
        validated_alert = validate_alert(data, settings, seen_ids)
    except ValueError as exc:
        logger.warning(f"Validation failed: {exc}")
        _record_alert(None, None, "rejected", str(exc))
        return JSONResponse(
            status_code=400,
            content={"status": "error", "reason": str(exc)},
        )

    # 2. Safety Gate 1: Kill switch check
    if kill_switch_active:
        msg = "kill switch active"
        logger.warning(f"Webhook rejected by safety gate: {msg}")
        _record_alert(validated_alert, None, "rejected", msg)
        return JSONResponse(status_code=400, content={"status": "error", "reason": msg})

    # 3. Retrieve live account balance
    acc_info = None
    try:
        if mt5.terminal_info():
            acc_info = mt5.account_info()
    except Exception:
        acc_info = None

    if acc_info is not None and acc_info.balance > 0:
        balance = float(acc_info.balance)
    else:
        balance = float(data.get("balance", 10000.0))

    # 4. Safety Gate 2: Max daily loss check
    max_daily_loss_pct = float(getattr(settings, "max_daily_loss_pct", 3.0))
    daily_realized_loss = _calculate_daily_realized_loss()
    daily_loss_limit_cash = balance * (max_daily_loss_pct / 100.0)
    if daily_realized_loss <= -daily_loss_limit_cash:
        msg = "daily loss limit reached"
        logger.warning(
            f"Webhook rejected by safety gate: {msg} "
            f"(realized loss: {daily_realized_loss:.2f}, limit: -{daily_loss_limit_cash:.2f})"
        )
        _record_alert(validated_alert, None, "rejected", msg)
        return JSONResponse(status_code=400, content={"status": "error", "reason": msg})

    # 5. Safety Gate 3: Max open positions check
    max_positions = int(getattr(settings, "max_positions", 5))
    open_count = _count_open_positions()
    if open_count >= max_positions:
        msg = "max open positions reached"
        logger.warning(f"Webhook rejected by safety gate: {msg} (open: {open_count}, max: {max_positions})")
        _record_alert(validated_alert, None, "rejected", msg)
        return JSONResponse(status_code=400, content={"status": "error", "reason": msg})

    # 6. Extract Broker Specifications (prefer MT5 symbol_info over symbols.json fallback)
    symbol = validated_alert["symbol"]
    info = None
    try:
        if mt5.terminal_info() and mt5.symbol_select(symbol, True):
            info = mt5.symbol_info(symbol)
    except Exception:
        info = None

    fallback_spec = settings.symbols.get(symbol, {})

    if info is not None:
        tick_value_per_unit = float(info.trade_tick_value) if info.trade_tick_value else float(fallback_spec.get("tick_value_per_unit", 100.0))
        min_lot = float(info.volume_min) if info.volume_min else float(fallback_spec.get("min_lot", 0.01))
        max_lot_broker = float(info.volume_max) if info.volume_max else float(fallback_spec.get("max_lot", 2.0))
        step = float(info.volume_step) if info.volume_step else float(fallback_spec.get("step", 0.01))
        pip_size = float(info.point) if info.point else float(fallback_spec.get("pip_size", 0.01))
    else:
        try:
            terminal_available = bool(mt5.terminal_info())
        except Exception:
            terminal_available = False
        if terminal_available:
            msg = f"symbol {symbol} not available in MT5"
            logger.warning(msg)
            _record_alert(validated_alert, None, "rejected", msg)
            return JSONResponse(status_code=400, content={"status": "error", "reason": msg})

        if symbol not in settings.symbols:
            msg = f"symbol {symbol} not in symbols configuration"
            logger.warning(msg)
            _record_alert(validated_alert, None, "rejected", msg)
            return JSONResponse(status_code=400, content={"status": "error", "reason": msg})

        tick_value_per_unit = float(fallback_spec["tick_value_per_unit"])
        min_lot = float(fallback_spec["min_lot"])
        max_lot_broker = float(fallback_spec["max_lot"])
        step = float(fallback_spec["step"])
        pip_size = float(fallback_spec.get("pip_size", 0.01))

    max_lot = min(float(validated_alert["max_lot"]), max_lot_broker)

    # 7. Calculate Lot Size
    try:
        lot = calculate_lot(
            balance=balance,
            risk_pct=validated_alert["risk_pct"],
            entry=validated_alert["entry"],
            sl=validated_alert["sl"],
            tick_value_per_unit=tick_value_per_unit,
            min_lot=min_lot,
            max_lot=max_lot,
            step=step,
            pip_size=pip_size,
        )
    except ValueError as exc:
        logger.warning(f"Risk calculation failed: {exc}")
        _record_alert(validated_alert, None, "rejected", str(exc))
        return JSONResponse(
            status_code=400,
            content={"status": "error", "reason": str(exc)},
        )

    # 8. Execute Order in MetaTrader 5
    try:
        result = execute_order(validated_alert, lot, settings)
    except ValueError as exc:
        logger.error(f"Execution rejected: {exc}")
        _record_alert(validated_alert, lot, "rejected", str(exc))
        return JSONResponse(
            status_code=400,
            content={"status": "error", "reason": str(exc)},
        )
    except Exception as exc:
        logger.error(f"Unexpected execution failure: {exc}")
        _record_alert(validated_alert, lot, "rejected", "execution failure")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "reason": "execution failure"},
        )

    # 9. Success recording
    ticket_str = str(result.get("ticket", "N/A"))
    _record_alert(validated_alert, lot, "executed", ticket_str)
    logger.info(f"Order processed successfully: {result}")
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "result": result},
    )
