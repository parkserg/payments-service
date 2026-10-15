from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class UnitOfWork(ABC):
    """Одна бизнес-транзакция.

    Репозитории внедряются в use case отдельно и работают в транзакции, открытой текущим
    `async with uow`. Вне его обращение к репозиторию — ошибка. Без явного commit()
    изменения откатываются при выходе.
    """

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    async def commit(self) -> None:
        """Фиксирует транзакцию.

        Raises:
            DuplicateIdempotencyKeyError: платёж с таким idempotency key уже существует.
        """

    @abstractmethod
    async def rollback(self) -> None: ...
