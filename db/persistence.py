import structlog

from core.event_bus import EventBus
from db.repository import Repository
from models import Event, EventType, Fill, OrderRequest, Position


class PersistenceService:
    def __init__(self, event_bus: EventBus, repository: Repository) -> None:
        self._event_bus = event_bus
        self._repo = repository
        self._logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        self._event_bus.subscribe(EventType.ORDER_REQUEST, self._persist_order)
        self._event_bus.subscribe(EventType.FILL, self._persist_fill)
        self._event_bus.subscribe(
            EventType.POSITION_UPDATE, self._persist_position
        )
        self._logger.info("persistence_service_started")

    async def stop(self) -> None:
        self._event_bus.unsubscribe(
            EventType.ORDER_REQUEST, self._persist_order
        )
        self._event_bus.unsubscribe(EventType.FILL, self._persist_fill)
        self._event_bus.unsubscribe(
            EventType.POSITION_UPDATE, self._persist_position
        )

    async def _persist_order(self, event: Event) -> None:
        assert isinstance(event.payload, OrderRequest)
        await self._repo.insert_order(event.payload)

    async def _persist_fill(self, event: Event) -> None:
        assert isinstance(event.payload, Fill)
        await self._repo.insert_fill(event.payload)
        await self._repo.update_order_status(
            event.payload.order_id, "filled"
        )

    async def _persist_position(self, event: Event) -> None:
        assert isinstance(event.payload, Position)
        await self._repo.upsert_position(event.payload)
