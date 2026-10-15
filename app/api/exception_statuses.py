from fastapi import status

from app.domain.exceptions.auth import InvalidApiKeyError
from app.domain.exceptions.base import DomainError
from app.domain.exceptions.payment import (
    IdempotencyKeyConflictError,
    IdempotentPaymentNotFoundError,
    InvalidPaymentAmountError,
    PaymentNotFoundError,
)

EXCEPTION_STATUSES: dict[type[DomainError], int] = {
    InvalidApiKeyError: status.HTTP_401_UNAUTHORIZED,
    PaymentNotFoundError: status.HTTP_404_NOT_FOUND,
    IdempotencyKeyConflictError: status.HTTP_409_CONFLICT,
    IdempotentPaymentNotFoundError: status.HTTP_409_CONFLICT,
    InvalidPaymentAmountError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def status_for(exc: DomainError) -> int:
    for exc_type in type(exc).__mro__:
        if exc_type in EXCEPTION_STATUSES:
            return EXCEPTION_STATUSES[exc_type]
    return status.HTTP_500_INTERNAL_SERVER_ERROR
