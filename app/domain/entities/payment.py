from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.common.clock import utcnow
from app.common.ids import generate_uuid
from app.domain.exceptions.payment import InvalidPaymentAmountError, PaymentAlreadyProcessedError

AMOUNT_PRECISION = Decimal("0.01")


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(kw_only=True)
class Payment:
    id: UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)
    status: PaymentStatus
    idempotency_key: str
    request_hash: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
        webhook_url: str,
    ) -> "Payment":
        if amount <= 0:
            raise InvalidPaymentAmountError("Payment amount must be positive")
        if amount != amount.quantize(AMOUNT_PRECISION):
            raise InvalidPaymentAmountError("Payment amount must have at most 2 decimal places")
        return cls(
            id=generate_uuid(),
            amount=amount,
            currency=currency,
            description=description,
            metadata=metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            webhook_url=webhook_url,
            created_at=utcnow(),
        )

    @property
    def is_pending(self) -> bool:
        return self.status is PaymentStatus.PENDING

    def matches_request(self, request_hash: str) -> bool:
        return self.request_hash == request_hash

    def succeed(self) -> None:
        self._complete(PaymentStatus.SUCCEEDED)

    def fail(self) -> None:
        self._complete(PaymentStatus.FAILED)

    def _complete(self, status: PaymentStatus) -> None:
        if not self.is_pending:
            raise PaymentAlreadyProcessedError(self.id)
        self.status = status
        self.processed_at = utcnow()
