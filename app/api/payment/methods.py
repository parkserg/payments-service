from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status

from app.api.auth.dependencies import verify_api_key
from app.api.payment.schemas import CreatePaymentRequest, PaymentAcceptedResponse, PaymentResponse
from app.di.container import resolve_depends
from app.domain.use_cases.create_payment import CreatePaymentCommand, CreatePaymentUseCase
from app.domain.use_cases.get_payment import GetPaymentCommand, GetPaymentUseCase

router = APIRouter(prefix="/payments", tags=["payments"], dependencies=[Depends(verify_api_key)])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PaymentAcceptedResponse,
    responses={
        status.HTTP_409_CONFLICT: {"description": "Ключ уже использован с другим телом запроса"},
    },
)
async def create_payment(
    body: CreatePaymentRequest,
    response: Response,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        description="Уникальный ключ запроса; повтор с тем же ключом не создаёт новый платёж",
    ),
    use_case: CreatePaymentUseCase = Depends(resolve_depends(CreatePaymentUseCase)),
) -> PaymentAcceptedResponse:
    result = await use_case.execute(
        CreatePaymentCommand(
            idempotency_key=idempotency_key,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata=body.metadata,
            webhook_url=str(body.webhook_url),
        )
    )
    if not result.created:
        response.headers["Idempotent-Replayed"] = "true"
    return PaymentAcceptedResponse.from_entity(result.payment)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    use_case: GetPaymentUseCase = Depends(resolve_depends(GetPaymentUseCase)),
) -> PaymentResponse:
    payment = await use_case.execute(GetPaymentCommand(payment_id=payment_id))
    return PaymentResponse.from_entity(payment)
