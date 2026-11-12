from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Principal,
    get_app_settings,
    get_principal,
    get_session,
    get_token_issuer,
)
from app.core.config import Settings
from app.core.errors import ForbiddenError
from app.core.rate_limit import auth_rate_limit
from app.core.security import TokenIssuer
from app.models import User
from app.schemas.identity import LoginRequest, SessionOut, SignupRequest, UserOut
from app.services.identity import (
    IdentityService,
    InvalidRefreshToken,
    IssuedSession,
    describe_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "covenant_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "covenant"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _service(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    issuer: TokenIssuer = Depends(get_token_issuer),
) -> IdentityService:
    return IdentityService(session, settings, issuer)


def _require_csrf_header(request: Request) -> None:
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise ForbiddenError("Missing request header.", code="CSRF_HEADER_REQUIRED")


def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_days * 86_400,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=urlparse(settings.frontend_origin).hostname not in LOCAL_HOSTS,
    )


def _session_response(response: Response, settings: Settings, issued: IssuedSession) -> SessionOut:
    _set_refresh_cookie(response, settings, issued.refresh_token)
    return SessionOut(
        access_token=issued.access_token, expires_in=issued.expires_in, user=issued.user
    )


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
)
async def signup(
    data: SignupRequest,
    response: Response,
    service: IdentityService = Depends(_service),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    return _session_response(response, settings, await service.signup(data))


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
async def login(
    data: LoginRequest,
    response: Response,
    service: IdentityService = Depends(_service),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    return _session_response(response, settings, await service.login(data))


@router.post("/refresh", dependencies=[Depends(_require_csrf_header)])
async def refresh(
    request: Request,
    response: Response,
    service: IdentityService = Depends(_service),
    settings: Settings = Depends(get_app_settings),
) -> SessionOut:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise InvalidRefreshToken("Sign in to continue.")
    return _session_response(response, settings, await service.refresh(token))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_csrf_header)],
)
async def logout(
    request: Request, response: Response, service: IdentityService = Depends(_service)
) -> None:
    await service.logout(request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


@router.get("/me")
async def me(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    user = await session.get(User, principal.user_id)
    assert user is not None  # noqa: S101  (get_principal loaded it)
    return await describe_user(session, user)
