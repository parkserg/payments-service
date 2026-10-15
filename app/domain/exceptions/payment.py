from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from app.domain.exceptions.base import DomainError


@dataclass(eq=False)
class PaymentNotFoundError(DomainError):
    payment_id: UUID

    code: ClassVar[str] = "payment_not_found"

    @property
    def message(self) -> str:
        return f"Payment {self.payment_id} not found"


@dataclass(eq=False)
class InvalidPaymentAmountError(DomainError):
    reason: str

    code: ClassVar[str] = "invalid_payment_amount"

    @property
    def message(self) -> str:
        return self.reason


@dataclass(eq=False)
class PaymentAlreadyProcessedError(DomainError):
    payment_id: UUID

    code: ClassVar[str] = "payment_already_processed"

    @property
    def message(self) -> str:
        return f"Payment {self.payment_id} is already processed"


@dataclass(eq=False)
class IdempotencyKeyConflictError(DomainError):
    """Ключ уже использован для запроса с другим телом."""

    idempotency_key: str

    code: ClassVar[str] = "idempotency_key_conflict"

    @property
    def message(self) -> str:
        return (
            f"Idempotency key '{self.idempotency_key}' was already used "
            "with a different request body"
        )


@dataclass(eq=False)
class DuplicateIdempotencyKeyError(DomainError):
    """параллельный запрос успел сохранить платёж с тем же ключом."""

    code: ClassVar[str] = "duplicate_idempotency_key"

    @property
    def message(self) -> str:
        return "Payment with the same idempotency key already exists"


@dataclass(eq=False)
class IdempotentPaymentNotFoundError(DomainError):
    """После конфликта idempotency key платёж-победитель не найден.

    Штатно не возникает: параллельный запрос уже закоммитил платёж. Повтор запроса
    с тем же ключом безопасен.
    """

    idempotency_key: str

    code: ClassVar[str] = "idempotent_payment_not_found"

    @property
    def message(self) -> str:
        return (
            f"Payment for idempotency key '{self.idempotency_key}' was not found "
            "after a concurrent insert; retry the request"
        )
