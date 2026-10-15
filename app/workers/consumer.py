import asyncio
import logging

from aio_pika.abc import HeadersType
from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitBroker, RabbitMessage
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.logging import configure_logging
from app.config import get_settings
from app.di.container import get_container
from app.domain.exceptions.payment import PaymentNotFoundError
from app.domain.use_cases.process_payment import (
    ProcessingOutcome,
    ProcessPaymentCommand,
    ProcessPaymentUseCase,
)
from app.infrastructure.messaging.schemas import PaymentCreatedMessage
from app.infrastructure.messaging.topology import (
    DEAD_LETTER_EXCHANGE,
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW,
    PAYMENTS_NEW_QUEUE,
    RETRY_EXCHANGE,
    declare_topology,
    retry_delays,
    retry_queue,
)

ATTEMPT_HEADER = "x-attempt"
ERROR_HEADER = "x-last-error"

# Повтор не поможет: сообщение ссылается на несуществующий платёж.
NON_RETRYABLE_ERRORS: tuple[type[Exception], ...] = (PaymentNotFoundError,)

logger = logging.getLogger("app.workers.consumer")

settings = get_settings()
configure_logging(settings.log_level)
container = get_container()
broker: RabbitBroker = container.resolve(RabbitBroker)
app = FastStream(broker)
retry_queues = [retry_queue(delay) for delay in retry_delays(settings)]


@app.on_startup
async def declare_broker_topology() -> None:
    # Retry- и DLQ-очереди должны существовать до того, как подписчик начнёт получать сообщения.
    await broker.connect()
    await declare_topology(broker, settings)


@app.after_shutdown
async def dispose_engine() -> None:
    await container.resolve(AsyncEngine).dispose()


@broker.subscriber(PAYMENTS_NEW_QUEUE, PAYMENTS_EXCHANGE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def handle_payment_created(body: PaymentCreatedMessage, message: RabbitMessage) -> None:
    attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
    logger.info("Processing payment %s (attempt %d)", body.payment_id, attempt)

    use_case: ProcessPaymentUseCase = container.resolve(ProcessPaymentUseCase)
    try:
        result = await use_case.execute(ProcessPaymentCommand(payment_id=body.payment_id))
    except NON_RETRYABLE_ERRORS as exc:
        logger.error("Payment %s cannot be processed: %r", body.payment_id, exc)
        await _dead_letter(message, attempt, exc)
    except Exception as exc:
        if attempt < settings.retry_max_attempts:
            await _schedule_retry(message, attempt, exc)
        else:
            logger.error("Payment %s failed after %d attempts: %r", body.payment_id, attempt, exc)
            await _dead_letter(message, attempt, exc)
    else:
        _log_processed(result.payment.id, result.payment.status, result.outcome)


def _log_processed(payment_id: object, status: str, outcome: ProcessingOutcome) -> None:
    match outcome:
        case ProcessingOutcome.CHARGED:
            logger.info("Payment %s processed: %s, webhook delivered", payment_id, status)
        case ProcessingOutcome.ALREADY_PROCESSED:
            logger.info("Payment %s was already %s, webhook re-delivered", payment_id, status)
        case ProcessingOutcome.CONCURRENTLY_PROCESSED:
            logger.warning(
                "Payment %s was processed concurrently (%s); this gateway result was discarded",
                payment_id,
                status,
            )


async def _schedule_retry(message: RabbitMessage, attempt: int, exc: Exception) -> None:
    queue = retry_queues[attempt - 1]
    logger.warning("Attempt %d failed (%r), retrying via %s", attempt, exc, queue.name)
    await broker.publish(
        message.body,
        exchange=RETRY_EXCHANGE,
        routing_key=queue.routing_key,
        headers=_headers(attempt + 1, exc),
        message_id=message.message_id,
        content_type=message.content_type,
        persist=True,
    )


async def _dead_letter(message: RabbitMessage, attempt: int, exc: Exception) -> None:
    await broker.publish(
        message.body,
        exchange=DEAD_LETTER_EXCHANGE,
        routing_key=PAYMENTS_NEW,
        headers=_headers(attempt, exc),
        message_id=message.message_id,
        content_type=message.content_type,
        persist=True,
    )


def _headers(attempt: int, exc: Exception) -> HeadersType:
    return {ATTEMPT_HEADER: attempt, ERROR_HEADER: repr(exc)[:1000]}


if __name__ == "__main__":
    asyncio.run(app.run())
