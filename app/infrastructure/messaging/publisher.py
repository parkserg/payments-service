from faststream.rabbit import RabbitBroker

from app.domain.entities.outbox_event import EventType, OutboxEvent
from app.domain.exceptions.delivery import EventPublishError
from app.domain.services.event_publisher import EventPublisher
from app.infrastructure.messaging.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW

ROUTING_KEYS: dict[EventType, str] = {
    EventType.PAYMENT_CREATED: PAYMENTS_NEW,
}

PUBLISH_TIMEOUT_SECONDS = 10.0


class RabbitEventPublisher(EventPublisher):
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(self, event: OutboxEvent) -> None:
        try:
            await self._broker.publish(
                event.payload,
                exchange=PAYMENTS_EXCHANGE,
                routing_key=ROUTING_KEYS[event.event_type],
                message_id=str(event.id),
                message_type=event.event_type.value,
                persist=True,
                mandatory=True,
                timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # aio-pika бросает разнородные ошибки: сеть, nack, return
            raise EventPublishError(f"Failed to publish event {event.id}: {exc!r}") from exc
