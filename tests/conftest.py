import pytest

from config import Settings
from core.event_bus import EventBus


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def settings():
    return Settings(
        use_synthetic_feed=True,
        max_order_value=50000,
        max_position_size=100000,
    )
