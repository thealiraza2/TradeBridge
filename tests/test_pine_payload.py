"""Test validation of payloads emitted by the Pine Script v5 sender."""

import json
from server.config import Settings
from server.risk import calculate_lot
from server.validator import validate_alert


def test_pine_script_emitted_json_payload():
    """Verify that the JSON payload constructed by f_build_json passes validation."""
    settings = Settings(
        mt5_login=12345678,
        mt5_password="test_password",
        mt5_server="TestBroker-Demo",
        webhook_secret="test_secret_12345",
        default_risk_pct=1.0,
        default_max_lot=2.0,
        max_positions=5,
        max_daily_loss_pct=3.0,
        mode="demo",
        symbols={
            "XAUUSD": {"tick_value_per_unit": 100.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.01},
        },
        tv_to_mt5={"GOLD": "XAUUSD"},
        whitelist=["XAUUSD"],
    )

    # Simulated output from Pine Script f_build_json("BUY", 3902.50, 3900.50, 3906.50)
    simulated_pine_json = """{
        "secret": "test_secret_12345",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3902.50,
        "sl": 3900.50,
        "tp": 3906.50,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "1731513600000-1",
        "comment": "TradeBridge-XAUUSD-BUY"
    }"""

    data = json.loads(simulated_pine_json)
    seen_ids = set()

    # 1. Validator check
    validated = validate_alert(data, settings, seen_ids)
    assert validated["action"] == "BUY"
    assert validated["symbol"] == "XAUUSD"
    assert validated["entry"] == 3902.50
    assert validated["sl"] == 3900.50
    assert validated["tp"] == 3906.50
    assert validated["risk_pct"] == 1.0
    assert validated["max_lot"] == 2.0
    assert validated["alert_id"] == "1731513600000-1"
    assert validated["comment"] == "TradeBridge-XAUUSD-BUY"

    # 2. Risk check
    lot = calculate_lot(
        balance=10000.0,
        risk_pct=validated["risk_pct"],
        entry=validated["entry"],
        sl=validated["sl"],
        tick_value_per_unit=100.0,
        min_lot=0.01,
        max_lot=validated["max_lot"],
        step=0.01,
        pip_size=0.01,
    )
    assert lot == 0.50
