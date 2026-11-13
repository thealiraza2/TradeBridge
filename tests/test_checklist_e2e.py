"""End-to-End Checklist Verification Tests (Phase 9)

Tests the 13 checklist points covering:
1. Full test pass
2. MT5 login & /health (connected, balance shown)
3. Valid XAUUSD BUY alert -> executes order with correct lot, SL, TP
4. Duplicate alert_id -> rejected
5. Wrong secret -> rejected 400
6. BUY alert with SL above entry -> rejected
7. Tiny SL causing raw_lot > max_lot -> executes at max_lot ceiling
8. Kill switch toggle & reject/accept
9. Pine Script payload format -> executes trade
10. Chrome extension payload format -> executes trade
11. Dashboard endpoints: /dashboard, /positions, /alerts, /logs -> all 200 OK
12. Daily loss limit trigger (0.1% loss blocks new trades)
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from server.main import app
import server.main as main_module
from server.config import Settings


@pytest.fixture(autouse=True)
def setup_test_app():
    """Give the app test settings (no .env file needed) and a clean state."""
    main_module.seen_ids.clear()
    main_module.kill_switch_active = False
    main_module.recent_alerts.clear()

    app.state.settings = Settings(
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
            "EURUSD": {"tick_value_per_unit": 10.0, "min_lot": 0.01, "max_lot": 2.0, "step": 0.01, "pip_size": 0.0001},
        },
        tv_to_mt5={"OANDA:XAUUSD": "XAUUSD", "GOLD": "XAUUSD"},
        whitelist=["XAUUSD", "EURUSD"],
    )
    yield
    main_module.seen_ids.clear()
    main_module.kill_switch_active = False
    main_module.recent_alerts.clear()


@pytest.fixture
def mock_mt5_connected():
    with patch("server.main.mt5") as mock_mt5, patch("server.executor.mt5") as mock_exec_mt5:
        # Mock mt5.initialize()
        mock_mt5.initialize.return_value = True
        mock_mt5.terminal_info.return_value = MagicMock(connected=True)
        mock_mt5.account_info.return_value = MagicMock(
            login=12345678,
            balance=10000.0,
            equity=10000.0,
            currency="USD",
            server="MetaQuotes-Demo",
        )
        mock_mt5.positions_get.return_value = ()
        mock_mt5.history_deals_get.return_value = ()
        mock_mt5.DEAL_ENTRY_OUT = 1

        # Symbol info for XAUUSD
        sym_info = MagicMock(
            visible=True,
            trade_tick_value=100.0,
            trade_tick_size=0.01,
            point=0.01,
            volume_min=0.01,
            volume_step=0.01,
            volume_max=2.0,
            filling_mode=1,
            ask=3900.0,
            bid=3899.8,
        )
        mock_mt5.symbol_info.return_value = sym_info
        mock_exec_mt5.symbol_info.return_value = sym_info

        # Market tick (ask=3900.0, bid=3899.8) matching entry=3900.0
        tick_info = MagicMock(ask=3900.0, bid=3899.8)
        mock_mt5.symbol_info_tick.return_value = tick_info
        mock_exec_mt5.symbol_info_tick.return_value = tick_info

        # Mock order_send success
        order_res = MagicMock(
            retcode=10009, # TRADE_RETCODE_DONE
            order=987654,
            deal=987654,
            volume=0.50,
            price=3900.0,
            comment="TradeBridge-Execution",
        )
        mock_exec_mt5.order_send.return_value = order_res
        mock_exec_mt5.ORDER_TYPE_BUY = 0
        mock_exec_mt5.ORDER_TYPE_SELL = 1
        mock_exec_mt5.TRADE_ACTION_DEAL = 1
        mock_exec_mt5.ORDER_TIME_GTC = 0
        mock_exec_mt5.ORDER_FILLING_FOK = 0
        mock_exec_mt5.ORDER_FILLING_IOC = 1
        mock_exec_mt5.ORDER_FILLING_RETURN = 2
        mock_exec_mt5.TRADE_RETCODE_DONE = 10009
        mock_exec_mt5.TRADE_RETCODE_PLACED = 10008

        # Ensure kill switch is false initially
        main_module.kill_switch_active = False

        yield {
            "main_mt5": mock_mt5,
            "exec_mt5": mock_exec_mt5,
            "order_res": order_res,
        }


def test_checklist_point_2_health_connected_balance(mock_mt5_connected):
    """Checklist 2: MT5 demo login, GET /health - connected, balance shown."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mt5_connected"] is True
    assert data["balance"] == 10000.0
    assert data["account"] == 12345678


def test_checklist_point_3_valid_xauusd_buy_alert(mock_mt5_connected):
    """Checklist 3: curl valid XAUUSD BUY alert - MT5 demo position, lot/SL/TP correct."""
    client = TestClient(app)
    settings = app.state.settings

    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0, # $2 SL on $10k balance with 1% risk ($100) -> 0.50 lot
        "tp": 3910.0,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "checklist-test-003",
        "comment": "TradeBridge-Checklist-BUY",
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["lot"] == 0.50
    assert data["result"]["ticket"] == 987654


def test_checklist_point_4_duplicate_alert_rejected(mock_mt5_connected):
    """Checklist 4: Same alert_id twice - second rejected."""
    client = TestClient(app)
    settings = app.state.settings

    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "checklist-test-004-duplicate",
    }
    # First send succeeds
    r1 = client.post("/webhook", json=payload)
    assert r1.status_code == 200

    # Second send with same alert_id is rejected
    r2 = client.post("/webhook", json=payload)
    assert r2.status_code == 400
    assert "duplicate alert_id" in r2.json()["reason"]


def test_checklist_point_5_wrong_secret_rejected():
    """Checklist 5: Wrong secret - rejected (400)."""
    client = TestClient(app)
    payload = {
        "secret": "completely-wrong-secret",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "alert_id": "checklist-test-005-bad-secret",
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 400
    assert "invalid secret" in resp.json()["reason"]


def test_checklist_point_6_buy_sl_above_entry_rejected():
    """Checklist 6: BUY alert with SL above entry - rejected."""
    client = TestClient(app)
    settings = app.state.settings
    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3905.0, # SL above entry for BUY
        "tp": 3910.0,
        "alert_id": "checklist-test-006-bad-sl",
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 400
    assert "BUY requires sl < entry < tp" in resp.json()["reason"]


def test_checklist_point_7_tiny_sl_capped_at_max_lot(mock_mt5_connected):
    """Checklist 7: Tiny SL that makes the lot bigger than max_lot - executed lot = max_lot."""
    client = TestClient(app)
    settings = app.state.settings

    # SL is only $0.05 away. On $10,000 balance & 1% risk ($100), raw lot = 100 / (0.05 * 100) = 20.0 lots!
    # Max lot is 2.0. The lot MUST be capped at exactly 2.0.
    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3899.95,
        "tp": 3910.0,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "checklist-test-007-tiny-sl",
    }
    resp = client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["result"]["lot"] == 2.0


def test_checklist_point_8_kill_switch(mock_mt5_connected):
    """Checklist 8: Kill switch ON - rejected; OFF - works again."""
    client = TestClient(app)
    settings = app.state.settings

    # 1. Turn ON Kill Switch
    r_on = client.post("/kill", json={"kill": True})
    assert r_on.status_code == 200
    assert r_on.json()["kill_switch"] is True

    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "alert_id": "checklist-test-008-kill-test",
    }
    # Webhook rejected while kill switch active
    r_rej = client.post("/webhook", json=payload)
    assert r_rej.status_code == 400
    assert "kill switch active" in r_rej.json()["reason"]

    # 2. Turn OFF Kill Switch
    r_off = client.post("/kill", json={"kill": False})
    assert r_off.status_code == 200
    assert r_off.json()["kill_switch"] is False

    # Webhook accepted again
    payload["alert_id"] = "checklist-test-008-kill-test-recovered"
    r_pass = client.post("/webhook", json=payload)
    assert r_pass.status_code == 200
    assert r_pass.json()["status"] == "ok"


def test_checklist_point_9_10_pine_and_extension_payload(mock_mt5_connected):
    """Checklist 9 & 10: Real alert from TradingView (Pine Script) and Chrome Extension."""
    client = TestClient(app)
    settings = app.state.settings

    # Pine script format
    pine_payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "1731500000_1",
        "comment": "TradeBridge-GOLD-LONG",
    }
    r_pine = client.post("/webhook", json=pine_payload)
    assert r_pine.status_code == 200
    assert r_pine.json()["status"] == "ok"

    # Chrome extension format
    ext_payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "risk_pct": 1.0,
        "max_lot": 2.0,
        "alert_id": "tb-click-1731500000000-42",
        "comment": "TradeBridge-Click-BUY",
    }
    r_ext = client.post("/webhook", json=ext_payload)
    assert r_ext.status_code == 200
    assert r_ext.json()["status"] == "ok"


def test_checklist_point_11_dashboard_positions_alerts_logs(mock_mt5_connected):
    """Checklist 11: Dashboard: positions, alerts, logs - all visible."""
    client = TestClient(app)

    r_dash = client.get("/dashboard")
    assert r_dash.status_code == 200
    assert "<title>TradeBridge Dashboard</title>" in r_dash.text

    r_pos = client.get("/positions")
    assert r_pos.status_code == 200
    assert r_pos.json()["status"] == "ok"

    r_alerts = client.get("/alerts")
    assert r_alerts.status_code == 200
    assert r_alerts.json()["status"] == "ok"

    r_logs = client.get("/logs")
    assert r_logs.status_code == 200
    assert r_logs.json()["status"] == "ok"


def test_checklist_point_13_daily_loss_limit_safety(mock_mt5_connected):
    """Checklist 13: Daily loss limit: set to 0.1% temporarily, confirm new trades block, then restore."""
    client = TestClient(app)
    settings = app.state.settings

    # Simulate $50 closed loss today on $10k balance (0.5% loss)
    mock_deal = MagicMock(profit=-45.0, commission=-3.0, swap=-2.0, entry=1)
    mock_mt5_connected["main_mt5"].history_deals_get.return_value = [mock_deal]

    # Temporarily set max_daily_loss_pct to 0.1% (limit is 0.1% of $10,000 = $10 loss)
    r_set = client.post("/settings", json={"max_daily_loss_pct": 0.1})
    assert r_set.status_code == 200

    payload = {
        "secret": settings.webhook_secret,
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3900.0,
        "sl": 3898.0,
        "tp": 3910.0,
        "alert_id": "checklist-test-013-loss-limit",
    }
    # Because realized loss ($50) > limit ($10), trades must be blocked!
    r_blocked = client.post("/webhook", json=payload)
    assert r_blocked.status_code == 400
    assert "daily loss limit reached" in r_blocked.json()["reason"]

    # Restore real value: 3.0% (limit is $300, so $50 loss is well within limit)
    r_restore = client.post("/settings", json={"max_daily_loss_pct": 3.0})
    assert r_restore.status_code == 200

    payload["alert_id"] = "checklist-test-013-loss-restored"
    r_allowed = client.post("/webhook", json=payload)
    assert r_allowed.status_code == 200
    assert r_allowed.json()["status"] == "ok"
