from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.payment import Payment
from app.domain.repositories.payment import PaymentRepository
from app.infrastructure.database import SessionContext
from app.infrastructure.models.payment import PaymentModel


class SqlAlchemyPaymentRepository(PaymentRepository):
    def __init__(self, sessions: SessionContext) -> None:
        self._sessions = sessions

    @property
    def _session(self) -> AsyncSession:
        return self._sessions.current

    async def add(self, payment: Payment) -> None:
        self._session.add(PaymentModel.from_entity(payment))

    async def try_get(self, payment_id: UUID) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id)
        return model.to_entity() if model else None

    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.id == payment_id).with_for_update()
        )
        return model.to_entity() if model else None

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.idempotency_key == idempotency_key)
        )
        return model.to_entity() if model else None

    async def save(self, payment: Payment) -> None:
        await self._session.merge(PaymentModel.from_entity(payment))
