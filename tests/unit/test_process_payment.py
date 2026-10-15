import pytest

from app.domain.entities.payment import Payment, PaymentStatus
from app.domain.exceptions.delivery import WebhookDeliveryError
from app.domain.services.payment_gateway import ChargeResult
from app.domain.use_cases.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.domain.use_cases.process_payment import (
    ProcessingOutcome,
    ProcessPaymentCommand,
    ProcessPaymentUseCase,
)
from tests.unit.fakes import FakeDatabase, FakeGateway, FakeNotifier


async def create(db: FakeDatabase, command: CreatePaymentCommand) -> ProcessPaymentCommand:
    result = await CreatePaymentUseCase(db.uow, db.payments, db.outbox).execute(command)
    return ProcessPaymentCommand(payment_id=result.payment.id)


@pytest.mark.parametrize(
    ("charge", "expected"),
    [
        (ChargeResult.SUCCEEDED, PaymentStatus.SUCCEEDED),
        (ChargeResult.FAILED, PaymentStatus.FAILED),
    ],
)
async def test_processes_payment_and_notifies(
    command: CreatePaymentCommand, charge: ChargeResult, expected: PaymentStatus
) -> None:
    db = FakeDatabase()
    process = await create(db, command)
    notifier = FakeNotifier()

    result = await ProcessPaymentUseCase(
        db.uow, db.payments, FakeGateway(charge), notifier
    ).execute(process)

    assert result.outcome is ProcessingOutcome.CHARGED
    assert result.payment.status is expected
    assert db.storage.payments[result.payment.id].status is expected
    assert [p.status for p in notifier.delivered] == [expected]


async def test_retry_after_webhook_failure_does_not_charge_twice(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()
    process = await create(db, command)
    gateway = FakeGateway()
    notifier = FakeNotifier(failures=1)
    use_case = ProcessPaymentUseCase(db.uow, db.payments, gateway, notifier)

    with pytest.raises(WebhookDeliveryError):
        await use_case.execute(process)
    # Статус сохранён ещё до webhook.
    assert db.storage.payments[process.payment_id].status is PaymentStatus.SUCCEEDED

    result = await use_case.execute(process)

    assert result.outcome is ProcessingOutcome.ALREADY_PROCESSED
    assert gateway.calls == 1
    assert len(notifier.delivered) == 1


async def test_concurrent_duplicate_discards_own_gateway_result(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()
    process = await create(db, command)

    class ConcurrentGateway(FakeGateway):
        """Пока «наш» шлюз отвечает, параллельный обработчик успевает сохранить failed."""

        async def charge(self, payment: Payment) -> ChargeResult:
            db.storage.payments[payment.id].fail()
            return await super().charge(payment)

    notifier = FakeNotifier()
    use_case = ProcessPaymentUseCase(db.uow, db.payments, ConcurrentGateway(), notifier)

    result = await use_case.execute(process)

    assert result.outcome is ProcessingOutcome.CONCURRENTLY_PROCESSED
    assert result.payment.status is PaymentStatus.FAILED
    assert [p.status for p in notifier.delivered] == [PaymentStatus.FAILED]
