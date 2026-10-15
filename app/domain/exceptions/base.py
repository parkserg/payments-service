from dataclasses import dataclass
from typing import ClassVar


@dataclass(eq=False)
class DomainError(Exception):
    """Базовое доменное исключение.

    `code` — машиночитаемый код ошибки для клиентов API, `message` — человекочитаемый текст,
    собранный из полей исключения. `eq=False` сохраняет хешируемость исключения.
    """

    code: ClassVar[str] = "domain_error"

    @property
    def message(self) -> str:
        return "Domain error"

    def __str__(self) -> str:
        return self.message
