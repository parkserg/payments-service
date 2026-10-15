from abc import ABC, abstractmethod

from app.domain.entities.payment import Payment


class WebhookNotifier(ABC):
    @abstractmethod
    async def notify(self, payment: Payment) -> None:
        """Сообщает клиенту итоговый статус платежа на `payment.webhook_url`.

        Raises:
            WebhookDeliveryError: клиент недоступен или ответил ошибкой.
        """
