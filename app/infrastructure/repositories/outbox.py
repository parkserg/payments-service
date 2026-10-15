from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.outbox_event import OutboxEvent
from app.domain.repositories.outbox import OutboxRepository
from app.infrastructure.database import SessionContext
from app.infrastructure.models.outbox import OutboxModel


class SqlAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, sessions: SessionContext) -> None:
        self._sessions = sessions

    @property
    def _session(self) -> AsyncSession:
        return self._sessions.current

    async def add(self, event: OutboxEvent) -> None:
        self._session.add(OutboxModel.from_entity(event))

    async def get_unpublished(self, limit: int) -> list[OutboxEvent]:
        models = await self._session.scalars(
            select(OutboxModel)
            .where(OutboxModel.published_at.is_(None))
            .order_by(OutboxModel.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [model.to_entity() for model in models]

    async def save(self, event: OutboxEvent) -> None:
        await self._session.merge(OutboxModel.from_entity(event))
