from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import Settings

PAYMENTS_NEW = "payments.new"

PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
RETRY_EXCHANGE = RabbitExchange("payments.retry", type=ExchangeType.DIRECT, durable=True)
DEAD_LETTER_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_QUEUE = RabbitQueue(
    PAYMENTS_NEW,
    durable=True,
    routing_key=PAYMENTS_NEW,
    arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name},
)
PAYMENTS_NEW_DLQ = RabbitQueue(f"{PAYMENTS_NEW}.dlq", durable=True, routing_key=PAYMENTS_NEW)


def retry_delays(settings: Settings) -> list[float]:
    """Задержки перед 2-й, 3-й, … попыткой: base, base·2, base·4, …"""
    return [settings.retry_base_delay * 2**i for i in range(settings.retry_max_attempts - 1)]


def retry_queue(delay_seconds: float) -> RabbitQueue:
    ttl_ms = int(delay_seconds * 1000)
    name = f"{PAYMENTS_NEW}.retry.{ttl_ms}ms"
    return RabbitQueue(
        name,
        durable=True,
        routing_key=name,
        arguments={
            "x-message-ttl": ttl_ms,
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE.name,
            "x-dead-letter-routing-key": PAYMENTS_NEW,
        },
    )


async def declare_topology(broker: RabbitBroker, settings: Settings) -> None:
    """Идемпотентно объявляет exchanges, очереди и привязки.

    Вызывается и relay, и consumer: relay не должен публиковать в exchange, у которого ещё
    нет очереди, иначе сообщение некуда смаршрутизировать.
    """
    bindings = [
        (PAYMENTS_EXCHANGE, PAYMENTS_NEW_QUEUE),
        (DEAD_LETTER_EXCHANGE, PAYMENTS_NEW_DLQ),
        *((RETRY_EXCHANGE, retry_queue(delay)) for delay in retry_delays(settings)),
    ]
    for exchange_schema, queue_schema in bindings:
        exchange = await broker.declare_exchange(exchange_schema)
        queue = await broker.declare_queue(queue_schema)
        await queue.bind(exchange, routing_key=queue_schema.routing_key)
