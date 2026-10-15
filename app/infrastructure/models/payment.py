from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.payment import Currency, Payment, PaymentStatus
from app.infrastructure.models.base import Base

IDEMPOTENCY_KEY_CONSTRAINT = "uq_payments_idempotency_key"


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name=IDEMPOTENCY_KEY_CONSTRAINT),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency", values_callable=lambda e: [m.value for m in e])
    )
    description: Mapped[str] = mapped_column(Text)
    # Атрибут `metadata` зарезервирован в DeclarativeBase.
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda e: [m.value for m in e])
    )
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @classmethod
    def from_entity(cls, payment: Payment) -> "PaymentModel":
        return cls(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata_=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            request_hash=payment.request_hash,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )

    def to_entity(self) -> Payment:
        return Payment(
            id=self.id,
            amount=self.amount,
            currency=self.currency,
            description=self.description,
            metadata=self.metadata_,
            status=self.status,
            idempotency_key=self.idempotency_key,
            request_hash=self.request_hash,
            webhook_url=self.webhook_url,
            created_at=self.created_at,
            processed_at=self.processed_at,
        )
