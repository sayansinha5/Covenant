from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_paypal, get_session
from app.integrations.paypal import PayPalClient
from app.services import webhooks

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/paypal", include_in_schema=False)
async def paypal_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    paypal: PayPalClient = Depends(get_paypal),
) -> dict[str, str]:
    """PayPal deliveries (no Covenant auth): verified with PayPal, stored, applied by a job."""
    result = await webhooks.receive(session, paypal, request.headers, await request.body())
    return {"status": result}
