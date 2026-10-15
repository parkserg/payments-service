import asyncio
import os
import uuid
from typing import Any

import httpx
import pytest

API_URL = os.environ.get("E2E_API_URL")
API_KEY = os.environ.get("E2E_API_KEY", "dev-secret-key")
WEBHOOK_URL = "http://webhook-mock:8080/webhook"

pytestmark = pytest.mark.skipif(not API_URL, reason="E2E_API_URL is not set")


@pytest.fixture
async def client() -> Any:
    async with httpx.AsyncClient(
        base_url=f"{API_URL}/api/v1", headers={"X-API-Key": API_KEY}, timeout=10
    ) as client:
        yield client


def payment_body(**overrides: Any) -> dict[str, Any]:
    return {
        "amount": "250.00",
        "currency": "USD",
        "description": "e2e",
        "metadata": {"source": "e2e"},
        "webhook_url": WEBHOOK_URL,
        **overrides,
    }


async def test_payment_is_processed(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/payments", json=payment_body(), headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    assert response.status_code == 202
    payment_id = response.json()["payment_id"]

    for _ in range(30):
        payment = (await client.get(f"/payments/{payment_id}")).json()
        if payment["status"] != "pending":
            break
        await asyncio.sleep(0.5)
    assert payment["status"] in {"succeeded", "failed"}
    assert payment["processed_at"] is not None


async def test_idempotency(client: httpx.AsyncClient) -> None:
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    first = await client.post("/payments", json=payment_body(), headers=headers)
    replay = await client.post("/payments", json=payment_body(), headers=headers)
    conflict = await client.post("/payments", json=payment_body(amount="1.00"), headers=headers)

    assert replay.status_code == 202
    assert replay.json()["payment_id"] == first.json()["payment_id"]
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert conflict.status_code == 409


async def test_requires_api_key(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/payments/{uuid.uuid4()}", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
