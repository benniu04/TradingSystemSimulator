
import pytest
from fastapi.testclient import TestClient

from api.server import create_app
from config import Settings
from core.event_bus import EventBus
from db.repository import Repository
from execution.order_manager import OrderManager
from risk.position_tracker import PositionTracker


@pytest.fixture
def client():
    bus = EventBus()
    tracker = PositionTracker(bus)
    settings = Settings()
    om = OrderManager(bus, settings)
    repo = Repository(settings)
    app = create_app(bus, tracker, om, repo)
    return TestClient(app)


def test_health_endpoint(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_portfolio_endpoint(client: TestClient):
    resp = client.get("/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_equity" in data
    assert "positions" in data
    assert "total_unrealized_pnl" in data
    assert "total_realized_pnl" in data


def test_positions_endpoint(client: TestClient):
    resp = client.get("/positions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_position_not_found(client: TestClient):
    resp = client.get("/positions/UNKNOWN")
    assert resp.status_code == 404


def test_ws_portfolio():
    bus = EventBus()
    tracker = PositionTracker(bus)
    settings = Settings()
    om = OrderManager(bus, settings)
    repo = Repository(settings)
    app = create_app(bus, tracker, om, repo)

    client = TestClient(app)
    with client.websocket_connect("/ws/portfolio") as ws:
        data = ws.receive_json()
        assert "total_equity" in data
        assert "positions" in data
