from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.exception_handlers import register_exception_handlers
from app.api.payment.methods import router as payment_router
from app.common.logging import configure_logging
from app.config import get_settings
from app.di.container import get_container


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await get_container().resolve(AsyncEngine).dispose()


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)

    app = FastAPI(title="Payments Service", version="1.0.0", lifespan=lifespan)

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(payment_router)
    app.include_router(api_v1)

    @app.get("/health", tags=["health"], include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    register_exception_handlers(app)
    return app


app = create_app()
