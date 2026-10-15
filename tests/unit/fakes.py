import copy
from types import TracebackType
from typing import Self
from uuid import UUID

from app.domain.entities.outbox_event import OutboxEvent
from app.domain.entities.payment import Payment
from app.domain.exceptions.delivery import EventPublishError, WebhookDeliveryError
from app.domain.exceptions.payment import DuplicateIdempotencyKeyError
from app.domain.repositories.outbox import OutboxRepository
from app.domain.repositories.payment import PaymentRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.event_publisher import EventPublisher
from app.domain.services.payment_gateway import ChargeResult, PaymentGateway
from app.domain.services.webhook_notifier import WebhookNotifier


class Storage:
    """Общее «хранилище», которое переживает отдельные транзакции."""

    def __init__(self) -> None:
        self.payments: dict[UUID, Payment] = {}
        self.outbox: dict[UUID, OutboxEvent] = {}


class FakeUnitOfWork(UnitOfWork):
    """Изменения копятся в pending и попадают в storage только при commit()."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.pending_payments: dict[UUID, Payment] = {}
        self.pending_outbox: dict[UUID, OutboxEvent] = {}
        self.active = False
        self.commits = 0
        self.before_commit: list[Payment] = []
        """Платежи, которые «параллельный запрос» вставит прямо перед нашим commit."""

    async def __aenter__(self) -> Self:
        assert not self.active, "nested transaction"
        self.active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.rollback()
        self.active = False

    async def commit(self) -> None:
        for payment in self.before_commit:
            self.storage.payments[payment.id] = payment
        self.before_commit = []

        stored_keys = {p.idempotency_key: p.id for p in self.storage.payments.values()}
        for payment in self.pending_payments.values():
            owner = stored_keys.get(payment.idempotency_key)
            if owner is not None and owner != payment.id:
                await self.rollback()
                raise DuplicateIdempotencyKeyError
        self.storage.payments.update(self.pending_payments)
        self.storage.outbox.update(self.pending_outbox)
        self.commits += 1
        await self.rollback()

    async def rollback(self) -> None:
        self.pending_payments.clear()
        self.pending_outbox.clear()

    def require_active(self) -> None:
        assert self.active, "repository used outside of `async with uow`"


class FakePaymentRepository(PaymentRepository):
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def add(self, payment: Payment) -> None:
        self._uow.require_active()
        self._uow.pending_payments[payment.id] = copy.deepcopy(payment)

    async def try_get(self, payment_id: UUID) -> Payment | None:
        self._uow.require_active()
        payment = self._uow.storage.payments.get(payment_id)
        return copy.deepcopy(payment) if payment else None

    async def get_for_update(self, payment_id: UUID) -> Payment | None:
        return await self.try_get(payment_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        self._uow.require_active()
        for payment in self._uow.storage.payments.values():
            if payment.idempotency_key == idempotency_key:
                return copy.deepcopy(payment)
        return None

    async def save(self, payment: Payment) -> None:
        self._uow.require_active()
        self._uow.pending_payments[payment.id] = copy.deepcopy(payment)


class FakeOutboxRepository(OutboxRepository):
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def add(self, event: OutboxEvent) -> None:
        self._uow.require_active()
        self._uow.pending_outbox[event.id] = copy.deepcopy(event)

    async def get_unpublished(self, limit: int) -> list[OutboxEvent]:
        self._uow.require_active()
        events = sorted(
            (e for e in self._uow.storage.outbox.values() if not e.is_published),
            key=lambda e: e.created_at,
        )
        return [copy.deepcopy(e) for e in events[:limit]]

    async def save(self, event: OutboxEvent) -> None:
        self._uow.require_active()
        self._uow.pending_outbox[event.id] = copy.deepcopy(event)


class FakeDatabase:
    """UoW и репозитории поверх одного хранилища — как их собирает DI-контейнер."""

    def __init__(self) -> None:
        self.storage = Storage()
        self.uow = FakeUnitOfWork(self.storage)
        self.payments = FakePaymentRepository(self.uow)
        self.outbox = FakeOutboxRepository(self.uow)


class FakeGateway(PaymentGateway):
    def __init__(self, result: ChargeResult = ChargeResult.SUCCEEDED) -> None:
        self.result = result
        self.calls = 0

    async def charge(self, payment: Payment) -> ChargeResult:
        self.calls += 1
        return self.result


class FakeNotifier(WebhookNotifier):
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.delivered: list[Payment] = []

    async def notify(self, payment: Payment) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise WebhookDeliveryError("receiver is down")
        self.delivered.append(payment)


class FakePublisher(EventPublisher):
    def __init__(self, fail_on: set[UUID] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.published: list[OutboxEvent] = []

    async def publish(self, event: OutboxEvent) -> None:
        if event.id in self.fail_on:
            raise EventPublishError("broker is down")
        self.published.append(event)
