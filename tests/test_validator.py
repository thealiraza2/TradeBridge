"""Unit tests for TradeBridge alert validator and configuration loader."""

from pathlib import Path
import pytest

from server.config import Settings, load_settings
from server.validator import validate_alert


@pytest.fixture
def dummy_settings():
    """Provide a valid mock Settings object for validator testing."""
    return Settings(
        mt5_login=12345678,
        mt5_password="test_password",
        mt5_server="TestBroker-Demo",
        webhook_secret="secure_webhook_secret_1234567890abcdef",
        default_risk_pct=1.0,
        default_max_lot=2.0,
        max_positions=5,
        max_daily_loss_pct=3.0,
        mode="demo",
        symbols={
            "XAUUSD": {"tick_value_per_unit": 100.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.01},
            "EURUSD": {"tick_value_per_unit": 10.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.0001},
            "GBPUSD": {"tick_value_per_unit": 10.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.0001},
            "USDJPY": {"tick_value_per_unit": 10.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.01},
        },
        tv_to_mt5={
            "OANDA:XAUUSD": "XAUUSD",
            "GOLD": "XAUUSD",
        },
        whitelist=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY"],
    )


def test_valid_buy_alert_passes(dummy_settings):
    """A valid BUY alert passes all checks and returns a formatted payload."""
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3890.50,
        "sl": 3880.50,
        "tp": 3910.50,
        "risk_pct": 1.5,
        "max_lot": 1.0,
        "alert_id": "alert-001",
        "comment": "TradeBridge-GOLD-LONG",
    }
    seen_ids = set()
    result = validate_alert(alert, dummy_settings, seen_ids)

    assert result["action"] == "BUY"
    assert result["symbol"] == "XAUUSD"
    assert result["entry"] == 3890.50
    assert result["sl"] == 3880.50
    assert result["tp"] == 3910.50
    assert result["risk_pct"] == 1.5
    assert result["max_lot"] == 1.0
    assert result["alert_id"] == "alert-001"
    assert result["comment"] == "TradeBridge-GOLD-LONG"
    assert "alert-001" in seen_ids


def test_valid_sell_alert_passes(dummy_settings):
    """A valid SELL alert (tp < entry < sl) passes all checks."""
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "SELL",
        "symbol": "EURUSD",
        "entry": 1.0850,
        "sl": 1.0870,
        "tp": 1.0800,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "alert-002",
    }
    seen_ids = set()
    result = validate_alert(alert, dummy_settings, seen_ids)

    assert result["action"] == "SELL"
    assert result["symbol"] == "EURUSD"
    assert result["entry"] == 1.0850
    assert result["sl"] == 1.0870
    assert result["tp"] == 1.0800
    assert "alert-002" in seen_ids


def test_symbol_mapping_from_tv_to_mt5(dummy_settings):
    """TradingView symbol names are mapped through tv_to_mt5 to MT5 symbol names."""
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "OANDA:XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "alert-map-1",
    }
    seen_ids = set()
    result = validate_alert(alert, dummy_settings, seen_ids)
    assert result["symbol"] == "XAUUSD"

    alert2 = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "GOLD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "alert-map-2",
    }
    result2 = validate_alert(alert2, dummy_settings, seen_ids)
    assert result2["symbol"] == "XAUUSD"


def test_missing_risk_pct_and_max_lot_use_settings_defaults(dummy_settings):
    """When risk_pct and max_lot are omitted, settings defaults are applied."""
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "alert-defaults",
    }
    seen_ids = set()
    result = validate_alert(alert, dummy_settings, seen_ids)
    assert result["risk_pct"] == dummy_settings.default_risk_pct
    assert result["max_lot"] == dummy_settings.default_max_lot


def test_wrong_secret_rejected(dummy_settings):
    """Alert with incorrect or missing secret must be rejected immediately."""
    seen_ids = set()

    # Wrong secret
    alert_bad_secret = {
        "secret": "wrong_secret_value",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "secret-1",
    }
    with pytest.raises(ValueError, match="invalid secret"):
        validate_alert(alert_bad_secret, dummy_settings, seen_ids)

    # Missing secret
    alert_no_secret = {
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "secret-2",
    }
    with pytest.raises(ValueError, match="invalid secret"):
        validate_alert(alert_no_secret, dummy_settings, seen_ids)


def test_bad_action_rejected(dummy_settings):
    """Alerts with actions other than BUY or SELL must be rejected."""
    seen_ids = set()
    for bad_action in ["HOLD", "CLOSE", "buy", "sell", "LONG", 123]:
        alert = {
            "secret": dummy_settings.webhook_secret,
            "action": bad_action,
            "symbol": "XAUUSD",
            "entry": 3900.0,
            "sl": 3890.0,
            "tp": 3920.0,
            "alert_id": f"action-{bad_action}",
        }
        with pytest.raises(ValueError, match="invalid action, must be BUY or SELL"):
            validate_alert(alert, dummy_settings, seen_ids)


def test_non_whitelisted_symbol_rejected(dummy_settings):
    """Symbols not present in the whitelist (after mapping) must be rejected."""
    seen_ids = set()
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "BTCUSD",
        "entry": 60000.0,
        "sl": 59000.0,
        "tp": 63900.0,
        "alert_id": "whitelist-1",
    }
    with pytest.raises(ValueError, match="symbol not whitelisted"):
        validate_alert(alert, dummy_settings, seen_ids)


def test_buy_with_sl_above_entry_rejected(dummy_settings):
    """BUY alerts requiring sl < entry < tp reject invalid price arrangements."""
    seen_ids = set()

    # SL above entry
    alert_sl_above = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3910.0,
        "tp": 3930.0,
        "alert_id": "side-buy-1",
    }
    with pytest.raises(ValueError, match="BUY requires sl < entry < tp"):
        validate_alert(alert_sl_above, dummy_settings, seen_ids)

    # TP below entry
    alert_tp_below = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 1980.0,
        "alert_id": "side-buy-2",
    }
    with pytest.raises(ValueError, match="BUY requires sl < entry < tp"):
        validate_alert(alert_tp_below, dummy_settings, seen_ids)


def test_sell_with_sl_below_entry_rejected(dummy_settings):
    """SELL alerts requiring tp < entry < sl reject invalid price arrangements."""
    seen_ids = set()

    # SL below entry
    alert_sl_below = {
        "secret": dummy_settings.webhook_secret,
        "action": "SELL",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 1950.0,
        "alert_id": "side-sell-1",
    }
    with pytest.raises(ValueError, match="SELL requires tp < entry < sl"):
        validate_alert(alert_sl_below, dummy_settings, seen_ids)

    # TP above entry
    alert_tp_above = {
        "secret": dummy_settings.webhook_secret,
        "action": "SELL",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3910.0,
        "tp": 3920.0,
        "alert_id": "side-sell-2",
    }
    with pytest.raises(ValueError, match="SELL requires tp < entry < sl"):
        validate_alert(alert_tp_above, dummy_settings, seen_ids)


def test_missing_or_zero_entry_rejected(dummy_settings):
    """Missing, zero, or non-numeric entry/sl/tp must be rejected."""
    seen_ids = set()

    # Missing entry
    alert_missing_entry = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "entry-1",
    }
    with pytest.raises(ValueError, match="missing entry"):
        validate_alert(alert_missing_entry, dummy_settings, seen_ids)

    # Zero entry
    alert_zero_entry = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 0.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "entry-2",
    }
    with pytest.raises(ValueError, match="entry cannot be zero"):
        validate_alert(alert_zero_entry, dummy_settings, seen_ids)


def test_risk_pct_zero_rejected(dummy_settings):
    """risk_pct <= 0 must be rejected."""
    seen_ids = set()
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "risk_pct": 0.0,
        "alert_id": "risk-0",
    }
    with pytest.raises(ValueError, match="risk_pct must be greater than 0 and less than or equal to 5"):
        validate_alert(alert, dummy_settings, seen_ids)


def test_risk_pct_ten_rejected(dummy_settings):
    """risk_pct > 5 must be rejected."""
    seen_ids = set()
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "risk_pct": 10.0,
        "alert_id": "risk-10",
    }
    with pytest.raises(ValueError, match="risk_pct must be greater than 0 and less than or equal to 5"):
        validate_alert(alert, dummy_settings, seen_ids)


def test_duplicate_alert_id_rejected(dummy_settings):
    """Sending the same alert_id twice must reject the second alert."""
    seen_ids = set()
    alert = {
        "secret": dummy_settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3890.0,
        "tp": 3920.0,
        "alert_id": "duplicate-alert-123",
    }

    # First attempt must succeed
    result = validate_alert(alert, dummy_settings, seen_ids)
    assert result["alert_id"] == "duplicate-alert-123"

    # Second attempt with same alert_id must be rejected
    with pytest.raises(ValueError, match="duplicate alert_id: duplicate-alert-123"):
        validate_alert(alert, dummy_settings, seen_ids)


def test_config_loader(tmp_path):
    """Test config.py correctly loads valid .env and handles missing keys."""
    # 1. Missing .env file
    with pytest.raises(FileNotFoundError, match=".env file missing"):
        load_settings(env_path=tmp_path / "nonexistent.env")

    # 2. Missing required key in .env
    bad_env = tmp_path / "bad.env"
    bad_env.write_text("MT5_LOGIN=123456\nMT5_PASSWORD=test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing required environment key: MT5_SERVER"):
        load_settings(env_path=bad_env)

    # 3. Valid .env loading
    good_env = tmp_path / "good.env"
    good_env.write_text(
        "MT5_LOGIN=888888\n"
        "MT5_PASSWORD=secret_pass\n"
        "MT5_SERVER=Broker-Server\n"
        "WEBHOOK_SECRET=token123\n"
        "DEFAULT_RISK_PCT=1.0\n"
        "DEFAULT_MAX_LOT=2.5\n"
        "MAX_POSITIONS=3\n"
        "MAX_DAILY_LOSS_PCT=2.0\n"
        "MODE=demo\n",
        encoding="utf-8",
    )
    settings = load_settings(env_path=good_env)
    assert settings.mt5_login == 888888
    assert settings.mt5_server == "Broker-Server"
    assert settings.webhook_secret == "token123"
    assert settings.default_max_lot == 2.5
    assert settings.mode == "demo"
    assert "XAUUSD" in settings.symbols
    assert "XAUUSD" in settings.whitelist
