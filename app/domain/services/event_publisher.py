from abc import ABC, abstractmethod

from app.domain.entities.outbox_event import OutboxEvent


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: OutboxEvent) -> None:
        """Публикует событие в брокер и дожидается подтверждения.

        Raises:
            EventPublishError: брокер не принял сообщение.
        """
