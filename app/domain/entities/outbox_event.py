from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.common.clock import utcnow
from app.common.ids import generate_uuid
from app.domain.entities.payment import Payment


class EventType(StrEnum):
    PAYMENT_CREATED = "payment.created"


@dataclass(kw_only=True)
class OutboxEvent:
    id: UUID
    aggregate_id: UUID
    event_type: EventType
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime | None = None

    @classmethod
    def payment_created(cls, payment: Payment) -> "OutboxEvent":
        return cls(
            id=generate_uuid(),
            aggregate_id=payment.id,
            event_type=EventType.PAYMENT_CREATED,
            payload={"payment_id": str(payment.id)},
            created_at=utcnow(),
        )

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    def mark_published(self) -> None:
        self.published_at = utcnow()
