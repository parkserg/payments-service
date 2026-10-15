from collections import Counter, deque
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response, status

app = FastAPI(title="Webhook mock")
received: deque[dict[str, Any]] = deque(maxlen=100)
calls: Counter[str] = Counter()


async def _record(request: Request, response_status: int) -> Response:
    payload = await request.json()
    received.append(
        {
            "path": request.url.path,
            "received_at": datetime.now(UTC).isoformat(),
            "response_status": response_status,
            "payload": payload,
        }
    )
    return Response(status_code=response_status)


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    return await _record(request, status.HTTP_200_OK)


@app.post("/webhook/fail")
async def webhook_fail(request: Request) -> Response:
    return await _record(request, status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post("/webhook/flaky/{failures}")
async def webhook_flaky(failures: int, request: Request) -> Response:
    key = f"{request.headers.get('X-Payment-Id')}:{failures}"
    calls[key] += 1
    ok = calls[key] > failures
    return await _record(
        request, status.HTTP_200_OK if ok else status.HTTP_500_INTERNAL_SERVER_ERROR
    )


@app.get("/received")
async def get_received() -> list[dict[str, Any]]:
    return list(received)
