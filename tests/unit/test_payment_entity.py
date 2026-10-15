from decimal import Decimal

import pytest

from app.domain.entities.payment import Currency, Payment, PaymentStatus
from app.domain.exceptions.payment import InvalidPaymentAmountError, PaymentAlreadyProcessedError


def make_payment(amount: Decimal = Decimal("10.00")) -> Payment:
    return Payment.create(
        amount=amount,
        currency=Currency.USD,
        description="test",
        metadata={},
        idempotency_key="k",
        request_hash="h",
        webhook_url="https://example.com/hook",
    )


def test_create_starts_pending() -> None:
    payment = make_payment()
    assert payment.status is PaymentStatus.PENDING
    assert payment.processed_at is None


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1"), Decimal("1.001")])
def test_create_rejects_invalid_amount(amount: Decimal) -> None:
    with pytest.raises(InvalidPaymentAmountError):
        make_payment(amount)


def test_succeed_sets_status_and_processed_at() -> None:
    payment = make_payment()
    payment.succeed()
    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.processed_at is not None


def test_cannot_complete_twice() -> None:
    payment = make_payment()
    payment.fail()
    with pytest.raises(PaymentAlreadyProcessedError):
        payment.succeed()
