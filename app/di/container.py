from collections.abc import Callable
from functools import lru_cache

import punq
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.domain.repositories.outbox import OutboxRepository
from app.domain.repositories.payment import PaymentRepository
from app.domain.repositories.unit_of_work import UnitOfWork
from app.domain.services.event_publisher import EventPublisher
from app.domain.services.payment_gateway import PaymentGateway
from app.domain.services.webhook_notifier import WebhookNotifier
from app.domain.use_cases.create_payment import CreatePaymentUseCase
from app.domain.use_cases.get_payment import GetPaymentUseCase
from app.domain.use_cases.process_payment import ProcessPaymentUseCase
from app.domain.use_cases.publish_outbox import PublishOutboxUseCase
from app.infrastructure.database import SessionContext, create_engine, create_session_factory
from app.infrastructure.gateway.emulator import EmulatedPaymentGateway
from app.infrastructure.messaging.broker import create_broker
from app.infrastructure.messaging.publisher import RabbitEventPublisher
from app.infrastructure.repositories.outbox import SqlAlchemyOutboxRepository
from app.infrastructure.repositories.payment import SqlAlchemyPaymentRepository
from app.infrastructure.repositories.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.webhook.http_notifier import HttpxWebhookNotifier


def build_container(settings: Settings) -> punq.Container:
    container = punq.Container()
    container.register(Settings, instance=settings)

    engine = create_engine(settings)
    container.register(AsyncEngine, instance=engine)
    # UoW и репозитории не хранят состояния: сессию транзакции они берут из SessionContext.
    container.register(SessionContext, instance=SessionContext(create_session_factory(engine)))
    container.register(UnitOfWork, SqlAlchemyUnitOfWork, scope=punq.Scope.singleton)
    container.register(PaymentRepository, SqlAlchemyPaymentRepository, scope=punq.Scope.singleton)
    container.register(OutboxRepository, SqlAlchemyOutboxRepository, scope=punq.Scope.singleton)

    container.register(RabbitBroker, instance=create_broker(settings))
    container.register(EventPublisher, RabbitEventPublisher, scope=punq.Scope.singleton)
    container.register(PaymentGateway, EmulatedPaymentGateway, scope=punq.Scope.singleton)
    container.register(WebhookNotifier, HttpxWebhookNotifier, scope=punq.Scope.singleton)

    container.register(CreatePaymentUseCase)
    container.register(GetPaymentUseCase)
    container.register(ProcessPaymentUseCase)
    container.register(PublishOutboxUseCase)
    return container


@lru_cache
def get_container() -> punq.Container:
    return build_container(get_settings())


def resolve_depends[T](service: type[T]) -> Callable[[], T]:
    """Зависимость FastAPI, которая достаёт сервис из контейнера."""

    def dependency() -> T:
        resolved: T = get_container().resolve(service)
        return resolved

    return dependency
