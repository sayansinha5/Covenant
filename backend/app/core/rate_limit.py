"""Fixed-window rate limits on top of `limits` (the engine slowapi uses), as FastAPI dependencies
so each limit reads its rate from Settings and its key from the request (IP, org or user)."""

from collections.abc import Callable

from fastapi import Request
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.core.errors import AppError


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"
    title = "Too many requests"


class RateLimiter:
    def __init__(self) -> None:
        self._limiter = FixedWindowRateLimiter(MemoryStorage())
        self._items: dict[str, RateLimitItem] = {}

    def hit(self, rate: str, scope: str, key: str) -> None:
        item = self._items.setdefault(rate, parse(rate))
        if not self._limiter.hit(item, scope, key):
            raise RateLimited(
                "Too many requests. Wait a minute and try again.",
                extra={"retry_after_seconds": item.get_expiry()},
            )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(
    scope: str, rate_of: Callable[[Request], str], key_of: Callable[[Request], str] = client_ip
) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        limiter.hit(rate_of(request), scope, key_of(request))

    return dependency


auth_rate_limit = rate_limit("auth", lambda r: r.app.state.settings.rate_limit_auth)
