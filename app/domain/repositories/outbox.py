from abc import ABC, abstractmethod

from app.domain.entities.outbox_event import OutboxEvent


class OutboxRepository(ABC):
    @abstractmethod
    async def add(self, event: OutboxEvent) -> None: ...

    @abstractmethod
    async def get_unpublished(self, limit: int) -> list[OutboxEvent]:
        """Неопубликованные события в порядке создания.

        Строки блокируются до конца транзакции, уже заблокированные пропускаются, поэтому
        несколько relay-процессов не публикуют одно событие одновременно.
        """

    @abstractmethod
    async def save(self, event: OutboxEvent) -> None: ...
