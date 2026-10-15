from dataclasses import dataclass
from uuid import UUID

from app.domain.entities.payment import Payment
from app.domain.repositories.payment import PaymentRepository
from app.domain.repositories.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class GetPaymentCommand:
    payment_id: UUID


@dataclass(frozen=True, slots=True)
class GetPaymentUseCase:
    uow: UnitOfWork
    payments: PaymentRepository

    async def execute(self, command: GetPaymentCommand) -> Payment:
        async with self.uow:
            return await self.payments.get(command.payment_id)
