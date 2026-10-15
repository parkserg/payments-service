import asyncio
import random

from app.config import Settings
from app.domain.entities.payment import Payment
from app.domain.services.payment_gateway import ChargeResult, PaymentGateway


class EmulatedPaymentGateway(PaymentGateway):
    """Эмуляция внешнего шлюза: задержка 2–5 с, ~90 % успешных списаний."""

    def __init__(self, settings: Settings) -> None:
        self._min_delay = settings.gateway_min_delay
        self._max_delay = settings.gateway_max_delay
        self._success_rate = settings.gateway_success_rate

    async def charge(self, payment: Payment) -> ChargeResult:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        if random.random() < self._success_rate:
            return ChargeResult.SUCCEEDED
        return ChargeResult.FAILED
