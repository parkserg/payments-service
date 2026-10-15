from app.domain.use_cases.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.domain.use_cases.publish_outbox import PublishOutboxCommand, PublishOutboxUseCase
from tests.unit.fakes import FakeDatabase, FakePublisher


async def seed(db: FakeDatabase, command: CreatePaymentCommand, count: int) -> None:
    for i in range(count):
        await CreatePaymentUseCase(db.uow, db.payments, db.outbox).execute(
            CreatePaymentCommand(
                idempotency_key=f"key-{i}",
                amount=command.amount,
                currency=command.currency,
                description=command.description,
                webhook_url=command.webhook_url,
            )
        )


async def test_publishes_and_marks_events(command: CreatePaymentCommand) -> None:
    db = FakeDatabase()
    await seed(db, command, 3)
    publisher = FakePublisher()

    result = await PublishOutboxUseCase(db.uow, db.outbox, publisher).execute(
        PublishOutboxCommand(10)
    )

    assert result.published == 3
    assert result.error is None
    assert len(publisher.published) == 3
    assert all(e.is_published for e in db.storage.outbox.values())


async def test_publish_failure_keeps_rest_of_batch(command: CreatePaymentCommand) -> None:
    db = FakeDatabase()
    await seed(db, command, 3)
    events = sorted(db.storage.outbox.values(), key=lambda e: e.created_at)
    publisher = FakePublisher(fail_on={events[1].id})
    use_case = PublishOutboxUseCase(db.uow, db.outbox, publisher)

    first = await use_case.execute(PublishOutboxCommand(10))
    assert first.published == 1
    assert first.error is not None
    assert [
        e.is_published for e in sorted(db.storage.outbox.values(), key=lambda e: e.created_at)
    ] == [True, False, False]

    publisher.fail_on.clear()
    second = await use_case.execute(PublishOutboxCommand(10))
    assert second.published == 2
    assert second.error is None
    assert all(e.is_published for e in db.storage.outbox.values())
