from dataclasses import dataclass
from typing import ClassVar

from app.domain.exceptions.base import DomainError


@dataclass(eq=False)
class WebhookDeliveryError(DomainError):
    reason: str

    code: ClassVar[str] = "webhook_delivery_failed"

    @property
    def message(self) -> str:
        return self.reason


@dataclass(eq=False)
class EventPublishError(DomainError):
    reason: str

    code: ClassVar[str] = "event_publish_failed"

    @property
    def message(self) -> str:
        return self.reason
