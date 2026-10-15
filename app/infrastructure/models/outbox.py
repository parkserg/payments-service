from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.entities.outbox_event import EventType, OutboxEvent
from app.infrastructure.models.base import Base


class OutboxModel(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        # Relay читает только неопубликованные события, опубликованные индекс не раздувают.
        Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where="published_at IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    aggregate_id: Mapped[UUID]
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @classmethod
    def from_entity(cls, event: OutboxEvent) -> "OutboxModel":
        return cls(
            id=event.id,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type.value,
            payload=event.payload,
            created_at=event.created_at,
            published_at=event.published_at,
        )

    def to_entity(self) -> OutboxEvent:
        return OutboxEvent(
            id=self.id,
            aggregate_id=self.aggregate_id,
            event_type=EventType(self.event_type),
            payload=self.payload,
            created_at=self.created_at,
            published_at=self.published_at,
        )
