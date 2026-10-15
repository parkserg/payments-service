from contextvars import ContextVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class SessionContext:
    """Сессия текущей транзакции, общая для UnitOfWork и репозиториев.

    Хранится в ContextVar, поэтому каждая asyncio-задача (HTTP-запрос, сообщение из очереди)
    видит только свою сессию, а репозитории и UoW могут быть синглтонами.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._current: ContextVar[AsyncSession | None] = ContextVar("db_session", default=None)

    @property
    def current(self) -> AsyncSession:
        session = self._current.get()
        if session is None:
            raise RuntimeError("No active transaction: use the repository inside `async with uow`")
        return session

    def open(self) -> AsyncSession:
        if self._current.get() is not None:
            raise RuntimeError("Nested transactions are not supported")
        session = self._session_factory()
        self._current.set(session)
        return session

    async def close(self) -> None:
        session = self.current
        self._current.set(None)
        await session.close()
