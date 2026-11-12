import json
import secrets
from html import escape

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_paypal,
    get_session,
    require_hirer,
    require_manager,
    require_org,
)
from app.core.config import Settings
from app.integrations.paypal import PayPalClient
from app.models import PayPalVaultSession
from app.schemas.funding import (
    FundingAccountOut,
    VaultSessionOut,
    VaultStartOut,
    VaultStartRequest,
)
from app.services import escrow
from app.services.funding import FundingService

router = APIRouter(prefix="/paypal", tags=["paypal"], dependencies=[Depends(require_hirer)])
return_router = APIRouter(prefix="/paypal", tags=["paypal"])

RESULT_TEXT = {
    "connected": "PayPal is connected. You can close this window.",
    "cancelled": "PayPal connection was cancelled. Nothing was saved.",
    "failed": "PayPal connection didn't complete. Nothing was saved.",
    "invalid": "This PayPal link is no longer valid. Start again from Covenant.",
}


def _service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    paypal: PayPalClient = Depends(get_paypal),
) -> FundingService:
    return FundingService(session, settings, paypal)


@router.get("/funding-account")
async def funding_account(
    principal: OrgPrincipal = Depends(require_org),
    service: FundingService = Depends(_service),
) -> FundingAccountOut:
    return await service.describe(principal.org_id)


@router.delete("/funding-account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_funding_account(
    principal: OrgPrincipal = Depends(require_manager),
    service: FundingService = Depends(_service),
) -> None:
    await service.disconnect(principal.org_id)


@router.post("/vault/start", status_code=status.HTTP_201_CREATED)
async def start_vault(
    data: VaultStartRequest,
    principal: OrgPrincipal = Depends(require_manager),
    service: FundingService = Depends(_service),
) -> VaultStartOut:
    started = await service.start_vault(
        org_id=principal.org_id, user_id=principal.user_id, return_path=data.return_path
    )
    return VaultStartOut(session_id=started.session_id, approve_url=started.approve_url)


@router.get("/vault/sessions/{session_id}")
async def vault_session(
    session_id: str,
    principal: OrgPrincipal = Depends(require_org),
    service: FundingService = Depends(_service),
) -> VaultSessionOut:
    return VaultSessionOut.model_validate(await service.get_session(principal.org_id, session_id))


@router.post("/vault/sessions/{session_id}/cancel")
async def cancel_vault_session(
    session_id: str,
    principal: OrgPrincipal = Depends(require_manager),
    service: FundingService = Depends(_service),
) -> VaultSessionOut:
    return VaultSessionOut.model_validate(
        await service.cancel_session(principal.org_id, session_id)
    )


@return_router.get("/vault/return", response_class=HTMLResponse, include_in_schema=False)
async def vault_return(
    state: str = Query(min_length=1, max_length=128),
    outcome: str | None = Query(default=None, max_length=16),
    service: FundingService = Depends(_service),
    settings: Settings = Depends(get_app_settings),
) -> HTMLResponse:
    """PayPal sends the payer's browser here (no Covenant session). The page tells the opener
    window what happened and closes; after a full-page redirect it goes back into the app."""
    vault_session = await service.complete_vault(state, cancelled=outcome == "cancel")
    return _result_page(vault_session, settings.frontend_origin)


@return_router.get("/orders/return", include_in_schema=False)
async def order_return(
    token: str = Query(min_length=1, max_length=64),
    outcome: str | None = Query(default=None, max_length=16),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    """approve_each mode: PayPal sends the payer here after approving (or cancelling) a hold.
    `token` is the PayPal order ID; the authorization itself runs in the hold job."""
    contract_id = await escrow.payer_returned(
        session, order_id=token, cancelled=outcome == "cancel"
    )
    await session.commit()
    if contract_id is None:
        return RedirectResponse(f"{settings.frontend_origin}/?paypal=invalid", status_code=303)
    result = "cancelled" if outcome == "cancel" else "approved"
    return RedirectResponse(
        f"{settings.frontend_origin}/contracts/{contract_id}?paypal={result}", status_code=303
    )


def _js(value: object) -> str:
    """A JSON literal that can't close the surrounding <script> element."""
    return json.dumps(value).replace("<", "\\u003c")


def _result_page(vault_session: PayPalVaultSession | None, frontend_origin: str) -> HTMLResponse:
    result = vault_session.status if vault_session else "invalid"
    if result == "pending":
        result = "failed"
    back_to = frontend_origin + (vault_session.return_path if vault_session else "/")
    message = {
        "source": "covenant",
        "type": "paypal-vault",
        "status": result,
        "sessionId": vault_session.id if vault_session else None,
    }
    nonce = secrets.token_urlsafe(16)
    script = (
        f"const message = {_js(message)};"
        f"const origin = {_js(frontend_origin)};"
        f"const back = {_js(f'{back_to}?paypal={result}')};"
        "if (window.opener) { window.opener.postMessage(message, origin); window.close(); }"
        "else { window.location.replace(back); }"
    )
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>Covenant · PayPal</title>"
        "<style>body{font:14px system-ui,sans-serif;margin:48px;color:#1b1d1f}</style></head>"
        f"<body><p>{escape(RESULT_TEXT[result])}</p>"
        f'<p><a href="{escape(back_to)}">Return to Covenant</a></p>'
        f'<script nonce="{nonce}">{script}</script></body></html>'
    )
    csp = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
        "frame-ancestors 'none'; base-uri 'none'"
    )
    return HTMLResponse(page, headers={"Content-Security-Policy": csp})
