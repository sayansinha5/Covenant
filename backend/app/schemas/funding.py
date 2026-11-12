from datetime import datetime
from typing import Annotated, Literal

from pydantic import StringConstraints

from app.schemas.common import RequestModel, ResponseModel

# A path inside the web app (no scheme, no host, no "//"), so the redirect can't leave it.
ReturnPath = Annotated[str, StringConstraints(max_length=200, pattern=r"^(/[A-Za-z0-9_-]+)*/?$")]
VaultSessionStatus = Literal["pending", "connected", "cancelled", "failed"]


class FundingAccountOut(ResponseModel):
    mode: Literal["vault", "approve_each"]
    connected: bool
    payer_email: str | None
    connected_at: datetime | None


class VaultStartRequest(RequestModel):
    return_path: ReturnPath


class VaultStartOut(ResponseModel):
    session_id: str
    approve_url: str


class VaultSessionOut(ResponseModel):
    id: str
    status: VaultSessionStatus
    failure_reason: str | None
