from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError

from app.domain.exceptions.payment import DuplicateIdempotencyKeyError
from app.domain.repositories.unit_of_work import UnitOfWork
from app.infrastructure.database import SessionContext
from app.infrastructure.models.payment import IDEMPOTENCY_KEY_CONSTRAINT


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Открывает сессию в SessionContext; репозитории берут её оттуда же."""

    def __init__(self, sessions: SessionContext) -> None:
        self._sessions = sessions

    async def __aenter__(self) -> Self:
        self._sessions.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._sessions.current.rollback()
        finally:
            await self._sessions.close()

    async def commit(self) -> None:
        session = self._sessions.current
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            if _is_idempotency_key_violation(exc):
                raise DuplicateIdempotencyKeyError from exc
            raise

    async def rollback(self) -> None:
        await self._sessions.current.rollback()


def _is_idempotency_key_violation(exc: IntegrityError) -> bool:
    # Драйвер asyncpg кладёт исходную UniqueViolationError в __cause__; текст ошибки
    # содержит имя нарушенного ограничения при любом уровне обёрток.
    cause = exc.orig.__cause__ if exc.orig is not None else None
    constraint = getattr(cause, "constraint_name", None)
    return constraint == IDEMPOTENCY_KEY_CONSTRAINT or IDEMPOTENCY_KEY_CONSTRAINT in str(exc.orig)
