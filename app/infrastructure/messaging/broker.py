from faststream.rabbit import Channel, RabbitBroker

from app.config import Settings


def create_broker(settings: Settings) -> RabbitBroker:
    return RabbitBroker(
        settings.rabbitmq_url,
        default_channel=Channel(
            prefetch_count=settings.consumer_prefetch,
            # Публикация завершается только после подтверждения брокером, а сообщение,
            # которое некуда смаршрутизировать, вызывает ошибку, а не теряется молча.
            publisher_confirms=True,
            on_return_raises=True,
        ),
    )
