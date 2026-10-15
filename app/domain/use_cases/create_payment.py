import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domain.entities.outbox_event import OutboxEvent
from app.domain.entities.payment import Currency, Payment
from app.domain.exceptions.payment import (
    DuplicateIdempotencyKeyError,
    IdempotencyKeyConflictError,
    IdempotentPaymentNotFoundError,
)
from app.domain.repositories.outbox import OutboxRepository
from app.domain.repositories.payment import PaymentRepository
from app.domain.repositories.unit_of_work import UnitOfWork


@dataclass(frozen=True, kw_only=True)
class CreatePaymentCommand:
    idempotency_key: str
    amount: Decimal
    currency: Currency
    description: str
    webhook_url: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """SHA-256 тела запроса: по нему повтор отличают от переиспользования ключа."""
        canonical = json.dumps(
            {
                "amount": format(self.amount.normalize(), "f"),
                "currency": self.currency.value,
                "description": self.description,
                "metadata": self.metadata,
                "webhook_url": self.webhook_url,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class CreatePaymentResult:
    payment: Payment
    created: bool
    """False, если вернули ранее созданный платёж по тому же idempotency key."""


@dataclass(frozen=True, slots=True)
class CreatePaymentUseCase:
    uow: UnitOfWork
    payments: PaymentRepository
    outbox: OutboxRepository

    async def execute(self, command: CreatePaymentCommand) -> CreatePaymentResult:
        request_hash = command.fingerprint()

        async with self.uow:
            existing = await self.payments.get_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                return self._replay(existing, command.idempotency_key, request_hash)

            payment = Payment.create(
                amount=command.amount,
                currency=command.currency,
                description=command.description,
                metadata=command.metadata,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                webhook_url=command.webhook_url,
            )
            # Платёж и событие пишутся в одной транзакции (outbox pattern):
            # событие не потеряется и не появится без платежа.
            await self.payments.add(payment)
            await self.outbox.add(OutboxEvent.payment_created(payment))
            try:
                await self.uow.commit()
            except DuplicateIdempotencyKeyError:
                pass
            else:
                return CreatePaymentResult(payment=payment, created=True)

        # Параллельный запрос с тем же ключом закоммитился раньше нас.
        async with self.uow:
            existing = await self.payments.get_by_idempotency_key(command.idempotency_key)
        if existing is None:
            raise IdempotentPaymentNotFoundError(command.idempotency_key)
        return self._replay(existing, command.idempotency_key, request_hash)

    @staticmethod
    def _replay(payment: Payment, idempotency_key: str, request_hash: str) -> CreatePaymentResult:
        if not payment.matches_request(request_hash):
            raise IdempotencyKeyConflictError(idempotency_key)
        return CreatePaymentResult(payment=payment, created=False)
