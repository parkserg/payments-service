from decimal import Decimal

import pytest

from app.domain.entities.payment import Currency
from app.domain.use_cases.create_payment import CreatePaymentCommand


@pytest.fixture
def command() -> CreatePaymentCommand:
    return CreatePaymentCommand(
        idempotency_key="key-1",
        amount=Decimal("100.50"),
        currency=Currency.RUB,
        description="Order #1",
        metadata={"order_id": 1},
        webhook_url="https://example.com/hook",
    )
