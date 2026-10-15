import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.exception_statuses import status_for
from app.domain.exceptions.base import DomainError

logger = logging.getLogger(__name__)


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status_code = status_for(exc)
    if status_code >= 500:
        logger.error("Unmapped domain error: %r", exc)
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers={"WWW-Authenticate": "ApiKey"} if status_code == 401 else None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
