from uuid import UUID

from pydantic import BaseModel


class PaymentCreatedMessage(BaseModel):
    """Контракт сообщения в очереди payments.new."""

    payment_id: UUID
