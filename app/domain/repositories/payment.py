from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.entities.payment import Payment
from app.domain.exceptions.payment import PaymentNotFoundError


class PaymentRepository(ABC):
    @abstractmethod
    async def add(self, payment: Payment) -> None: ...

    @abstractmethod
    async def try_get(self, payment_id: UUID) -> Payment | None: ...

    async def get(self, payment_id: UUID) -> Payment:
        payment = await self.try_get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

    @abstractmethod
    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        """Читает платёж с блокировкой строки до конца транзакции."""

    @abstractmethod
    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None: ...

    @abstractmethod
    async def save(self, payment: Payment) -> None: ...
