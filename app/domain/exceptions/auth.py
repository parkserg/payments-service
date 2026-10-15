from dataclasses import dataclass
from typing import ClassVar

from app.domain.exceptions.base import DomainError


@dataclass(eq=False)
class InvalidApiKeyError(DomainError):
    code: ClassVar[str] = "invalid_api_key"

    @property
    def message(self) -> str:
        return "Missing or invalid API key"
