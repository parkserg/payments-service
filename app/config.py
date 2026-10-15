from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"
    api_key: SecretStr

    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    outbox_batch_size: int = Field(default=100, gt=0)
    outbox_poll_interval: float = Field(default=1.0, gt=0, description="секунды")

    gateway_min_delay: float = Field(default=2.0, ge=0)
    gateway_max_delay: float = Field(default=5.0, ge=0)
    gateway_success_rate: float = Field(default=0.9, ge=0, le=1)

    webhook_timeout: float = Field(default=5.0, gt=0)

    consumer_prefetch: int = Field(default=10, gt=0)
    retry_max_attempts: int = Field(default=3, ge=1, description="всего попыток обработки")
    retry_base_delay: float = Field(default=2.0, gt=0, description="секунды, удваивается")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # обязательные поля (api_key) приходят из окружения
