from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.entities.payment import Payment
from app.domain.exceptions.payment import PaymentNotFoundError
from app.domain.repositories.payment import PaymentRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.payment_gateway import ChargeResult, PaymentGateway
from app.domain.services.webhook_notifier import WebhookNotifier


@dataclass(frozen=True)
class ProcessPaymentCommand:
    payment_id: UUID


class ProcessingOutcome(StrEnum):
    CHARGED = "charged"
    """Списание проведено этим вызовом, статус сохранён."""

    ALREADY_PROCESSED = "already_processed"
    """Статус был итоговым ещё до вызова (повторная доставка): только повтор webhook."""

    CONCURRENTLY_PROCESSED = "concurrently_processed"
    """Шлюз вызван, но параллельный обработчик сохранил результат раньше; наш отброшен."""


@dataclass(frozen=True)
class ProcessPaymentResult:
    payment: Payment
    outcome: ProcessingOutcome


@dataclass(frozen=True, slots=True)
class ProcessPaymentUseCase:
    """Проводит платёж через шлюз и уведомляет клиента.

    Сценарий идемпотентен: сообщение может прийти повторно (at-least-once доставка или
    retry после неудачного webhook). Тогда шлюз повторно не вызывается, а webhook
    отправляется заново с уже сохранённым статусом.
    """

    uow: UnitOfWork
    payments: PaymentRepository
    gateway: PaymentGateway
    notifier: WebhookNotifier

    async def execute(self, command: ProcessPaymentCommand) -> ProcessPaymentResult:
        async with self.uow:
            payment = await self.payments.get(command.payment_id)
        if payment.is_pending:
            result = await self._charge(payment)
        else:
            result = ProcessPaymentResult(payment, ProcessingOutcome.ALREADY_PROCESSED)
        await self.notifier.notify(result.payment)
        return result

    async def _charge(self, payment: Payment) -> ProcessPaymentResult:
        # Обращение к шлюзу идёт вне транзакции, чтобы не держать соединение с БД секундами.
        charge = await self.gateway.charge(payment)

        async with self.uow:
            locked = await self.payments.get_for_update(payment.id)
            if locked is None:
                raise PaymentNotFoundError(payment.id)
            if not locked.is_pending:
                # Дубль сообщения обработан параллельно: результат уже сохранён, наш отбрасываем.
                return ProcessPaymentResult(locked, ProcessingOutcome.CONCURRENTLY_PROCESSED)
            if charge is ChargeResult.SUCCEEDED:
                locked.succeed()
            else:
                locked.fail()
            await self.payments.save(locked)
            await self.uow.commit()

        return ProcessPaymentResult(locked, ProcessingOutcome.CHARGED)
