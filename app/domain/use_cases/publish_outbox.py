from dataclasses import dataclass

from app.domain.exceptions.delivery import EventPublishError
from app.domain.repositories.outbox import OutboxRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.event_publisher import EventPublisher


@dataclass(frozen=True)
class PublishOutboxCommand:
    batch_size: int


@dataclass(frozen=True)
class PublishOutboxResult:
    published: int
    error: EventPublishError | None = None
    """Ошибка, на которой пачка прервалась; остаток уйдёт в следующем вызове."""


@dataclass(frozen=True, slots=True)
class PublishOutboxUseCase:
    """Переносит пачку событий из outbox в брокер.

    Гарантия at-least-once: если процесс упадёт после публикации, но до commit, событие
    уйдёт повторно, поэтому потребители должны быть идемпотентны.
    """

    uow: UnitOfWork
    outbox: OutboxRepository
    publisher: EventPublisher

    async def execute(self, command: PublishOutboxCommand) -> PublishOutboxResult:
        published = 0
        error: EventPublishError | None = None
        async with self.uow:
            events = await self.outbox.get_unpublished(command.batch_size)
            for event in events:
                try:
                    await self.publisher.publish(event)
                except EventPublishError as exc:
                    # Сохраняем порядок: остаток пачки уйдёт в следующем цикле.
                    error = exc
                    break
                event.mark_published()
                await self.outbox.save(event)
                published += 1
            await self.uow.commit()
        return PublishOutboxResult(published=published, error=error)
