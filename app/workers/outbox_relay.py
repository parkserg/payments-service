import asyncio
import contextlib
import logging
import signal

from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from app.common.logging import configure_logging
from app.config import get_settings
from app.di.container import get_container
from app.domain.use_cases.publish_outbox import PublishOutboxCommand, PublishOutboxUseCase
from app.infrastructure.messaging.topology import declare_topology

logger = logging.getLogger("app.workers.outbox_relay")


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = get_container()
    broker: RabbitBroker = container.resolve(RabbitBroker)
    use_case: PublishOutboxUseCase = container.resolve(PublishOutboxUseCase)
    command = PublishOutboxCommand(batch_size=settings.outbox_batch_size)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await broker.start()
    await declare_topology(broker, settings)
    logger.info("Outbox relay started")
    try:
        while not stop.is_set():
            published = 0
            try:
                result = await use_case.execute(command)
            except Exception:
                logger.exception("Outbox relay iteration failed")
            else:
                published = result.published
                if published:
                    logger.info("Published %d outbox event(s)", published)
                if result.error is not None:
                    logger.warning("Outbox publishing paused: %s", result.error)
            # Полная пачка — вероятно, есть ещё события, читаем сразу без паузы.
            if published < command.batch_size:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=settings.outbox_poll_interval)
    finally:
        logger.info("Outbox relay stopping")
        await broker.stop()
        await container.resolve(AsyncEngine).dispose()


if __name__ == "__main__":
    asyncio.run(run())
