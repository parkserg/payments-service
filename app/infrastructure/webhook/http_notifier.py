import httpx

from app.config import Settings
from app.domain.entities.payment import Payment
from app.domain.exceptions.delivery import WebhookDeliveryError
from app.domain.services.webhook_notifier import WebhookNotifier


class HttpxWebhookNotifier(WebhookNotifier):
    def __init__(self, settings: Settings) -> None:
        self._timeout = settings.webhook_timeout

    async def notify(self, payment: Payment) -> None:
        payload = {
            "event": f"payment.{payment.status.value}",
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "description": payment.description,
            "metadata": payment.metadata,
            "created_at": payment.created_at.isoformat(),
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        }
        # Webhook доставляется at-least-once; по этому заголовку получатель отсекает дубли.
        headers = {"X-Payment-Id": str(payment.id)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(payment.webhook_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"Webhook for payment {payment.id} failed: {exc!r}") from exc
        if not response.is_success:
            raise WebhookDeliveryError(
                f"Webhook for payment {payment.id} returned HTTP {response.status_code}"
            )
