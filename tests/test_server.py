"""Unit and integration tests for FastAPI endpoints in Phase 6."""

from unittest.mock import MagicMock, patch
import pytest
from starlette.testclient import TestClient

from server.config import Settings
import server.main as main_module
from server.main import app, seen_ids


@pytest.fixture(autouse=True)
def setup_test_app():
    """Ensure app has valid settings, deactivated kill switch, and clean caches."""
    seen_ids.clear()
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
    seen_ids.clear()
    main_module.kill_switch_active = False
    main_module.recent_alerts.clear()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_root_endpoint(client):
    """GET / returns service identity and phase 9."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"service": "TradeBridge", "phase": 9}


def test_health_endpoint_disconnected(client):
    """GET /health returns mt5_connected: False and kill_switch status."""
    with patch("server.main.mt5.terminal_info", return_value=None):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mt5_connected"] is False
        assert data["kill_switch"] is False


def test_health_endpoint_connected(client):
    """GET /health returns account, balance, and kill_switch when connected."""
    mock_acc = MagicMock()
    mock_acc.login = 12345678
    mock_acc.balance = 10000.0

    with patch("server.main.mt5.terminal_info", return_value=MagicMock()), \
         patch("server.main.mt5.account_info", return_value=mock_acc):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["mt5_connected"] is True
        assert data["account"] == 12345678
        assert data["balance"] == 10000.0
        assert data["kill_switch"] is False


def test_kill_switch_toggle(client):
    """POST /kill toggles the in-memory kill switch flag."""
    # Activate kill switch
    res1 = client.post("/kill", json={"kill": True})
    assert res1.status_code == 200
    assert res1.json()["kill_switch"] is True
    assert main_module.kill_switch_active is True

    # Deactivate kill switch
    res2 = client.post("/kill", json={"kill": False})
    assert res2.status_code == 200
    assert res2.json()["kill_switch"] is False
    assert main_module.kill_switch_active is False


def test_kill_switch_rejects_webhook(client):
    """When kill switch is active, POST /webhook rejects every alert."""
    # Turn kill switch ON
    client.post("/kill", json={"kill": True})

    payload = {
        "secret": "test_secret_12345",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3902.0,
        "sl": 3900.0,
        "tp": 3910.0,
        "alert_id": "kill-test-alert-1",
    }
    response = client.post("/webhook", json=payload)
    assert response.status_code == 400
    assert response.json()["status"] == "error"
    assert response.json()["reason"] == "kill switch active"

    # Turn kill switch OFF -> alert accepted
    client.post("/kill", json={"kill": False})
    payload["alert_id"] = "kill-test-alert-2"

    mock_receipt = {"status": "executed", "ticket": 777}
    with patch("server.main.execute_order", return_value=mock_receipt):
        response2 = client.post("/webhook", json=payload)
        assert response2.status_code == 200
        assert response2.json()["status"] == "ok"


def test_max_open_positions_safety(client):
    """When open positions reach max_positions limit, rejects with exact reason."""
    payload = {
        "secret": "test_secret_12345",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3902.0,
        "sl": 3900.0,
        "tp": 3910.0,
        "alert_id": "max-pos-alert",
    }
    # Mock open positions count at limit (5 >= 5)
    with patch("server.main._count_open_positions", return_value=5):
        response = client.post("/webhook", json=payload)
        assert response.status_code == 400
        assert response.json()["reason"] == "max open positions reached"


def test_max_daily_loss_safety(client):
    """When daily realized loss reaches limit, rejects with exact reason."""
    payload = {
        "secret": "test_secret_12345",
        "action": "BUY",
        "symbol": "XAUUSD",
        "entry": 3902.0,
        "sl": 3900.0,
        "tp": 3910.0,
        "alert_id": "daily-loss-alert",
        "balance": 10000.0,
    }
    # 3% of $10,000 is $300. Mock realized loss at -$350.00
    with patch("server.main._calculate_daily_realized_loss", return_value=-350.0):
        response = client.post("/webhook", json=payload)
        assert response.status_code == 400
        assert response.json()["reason"] == "daily loss limit reached"


def test_get_positions(client):
    """GET /positions formats open MT5 positions."""
    mock_pos = MagicMock()
    mock_pos.ticket = 123456
    mock_pos.symbol = "XAUUSD"
    mock_pos.type = 0  # BUY
    mock_pos.volume = 0.50
    mock_pos.price_open = 3900.0
    mock_pos.sl = 3890.0
    mock_pos.tp = 3920.0
    mock_pos.profit = 150.0

    with patch("server.main.mt5.terminal_info", return_value=MagicMock()), \
         patch("server.main.mt5.positions_get", return_value=[mock_pos]):
        response = client.get("/positions")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["positions"]) == 1
        pos = data["positions"][0]
        assert pos["ticket"] == 123456
        assert pos["type"] == "BUY"
        assert pos["volume"] == 0.50
        assert pos["profit"] == 150.0


def test_settings_endpoints(client):
    """GET /settings and POST /settings update and retrieve runtime configurations."""
    # Read initial
    res1 = client.get("/settings")
    assert res1.status_code == 200
    assert res1.json()["settings"]["default_risk_pct"] == 1.0

    # Update
    res2 = client.post("/settings", json={
        "default_risk_pct": 2.5,
        "default_max_lot": 3.0,
        "max_positions": 8,
        "max_daily_loss_pct": 5.0,
    })
    assert res2.status_code == 200
    updated = res2.json()["settings"]
    assert updated["default_risk_pct"] == 2.5
    assert updated["default_max_lot"] == 3.0
    assert updated["max_positions"] == 8
    assert updated["max_daily_loss_pct"] == 5.0


def test_dashboard_endpoint(client):
    """GET /dashboard serves the dashboard HTML file."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "TradeBridge Dashboard" in response.text
    assert "kill-switch-btn" in response.text


def test_alerts_endpoint(client):
    """GET /alerts returns recorded recent alert history."""
    response = client.get("/alerts")
    assert response.status_code == 200
    assert "alerts" in response.json()
