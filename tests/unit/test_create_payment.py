import dataclasses
from decimal import Decimal

import pytest

from app.domain.entities.outbox_event import EventType
from app.domain.entities.payment import Payment, PaymentStatus
from app.domain.exceptions.payment import (
    DuplicateIdempotencyKeyError,
    IdempotencyKeyConflictError,
    IdempotentPaymentNotFoundError,
)
from app.domain.use_cases.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from tests.unit.fakes import FakeDatabase


async def test_creates_payment_and_outbox_event_atomically(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()
    result = await CreatePaymentUseCase(db.uow, db.payments, db.outbox).execute(command)

    assert result.created
    assert result.payment.status is PaymentStatus.PENDING
    assert db.uow.commits == 1
    assert list(db.storage.payments) == [result.payment.id]
    [event] = db.storage.outbox.values()
    assert event.event_type is EventType.PAYMENT_CREATED
    assert event.payload == {"payment_id": str(result.payment.id)}


async def test_same_key_same_body_returns_existing_payment(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()
    use_case = CreatePaymentUseCase(db.uow, db.payments, db.outbox)
    first = await use_case.execute(command)
    # Тот же запрос с иначе записанной суммой: 100.5 == 100.50.
    second = await use_case.execute(dataclasses.replace(command, amount=Decimal("100.5")))

    assert not second.created
    assert second.payment.id == first.payment.id
    assert len(db.storage.payments) == 1
    assert len(db.storage.outbox) == 1


async def test_same_key_different_body_conflicts(command: CreatePaymentCommand) -> None:
    db = FakeDatabase()
    use_case = CreatePaymentUseCase(db.uow, db.payments, db.outbox)
    await use_case.execute(command)

    with pytest.raises(IdempotencyKeyConflictError):
        await use_case.execute(dataclasses.replace(command, amount=Decimal("999.00")))


async def test_concurrent_insert_with_same_key_is_replayed(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()
    concurrent = Payment.create(
        amount=command.amount,
        currency=command.currency,
        description=command.description,
        metadata=command.metadata,
        idempotency_key=command.idempotency_key,
        request_hash=command.fingerprint(),
        webhook_url=command.webhook_url,
    )
    db.uow.before_commit = [concurrent]

    result = await CreatePaymentUseCase(db.uow, db.payments, db.outbox).execute(command)

    assert not result.created
    assert result.payment.id == concurrent.id
    assert len(db.storage.outbox) == 0


async def test_missing_payment_after_duplicate_key_raises_domain_error(
    command: CreatePaymentCommand,
) -> None:
    db = FakeDatabase()

    async def commit_with_conflict() -> None:
        raise DuplicateIdempotencyKeyError

    db.uow.commit = commit_with_conflict  # type: ignore[method-assign]

    with pytest.raises(IdempotentPaymentNotFoundError):
        await CreatePaymentUseCase(db.uow, db.payments, db.outbox).execute(command)
