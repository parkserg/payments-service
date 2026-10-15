from abc import ABC, abstractmethod
from enum import StrEnum

from app.domain.entities.payment import Payment


class ChargeResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, payment: Payment) -> ChargeResult:
        """Списывает средства.

        Отказ шлюза — штатный бизнес-исход (`ChargeResult.FAILED`), а не исключение.
        """
