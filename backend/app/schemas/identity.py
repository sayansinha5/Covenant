from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.core.security import PASSWORD_MAX_LENGTH, password_problems
from app.schemas.common import Email, Name, RequestModel, ResponseModel

Industry = Literal["retail_handicrafts", "software", "services", "media", "other"]
Role = Literal["owner", "admin", "viewer"]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
AssistantName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]


class SignupRequest(RequestModel):
    full_name: Name
    email: Email
    password: Annotated[str, StringConstraints(max_length=PASSWORD_MAX_LENGTH)]
    accept_sandbox: bool

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        problems = password_problems(value)
        if problems:
            raise ValueError("Password needs " + ", ".join(problems))
        return value

    @field_validator("accept_sandbox")
    @classmethod
    def _must_accept(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Confirm that this is a sandbox demo")
        return value


class LoginRequest(RequestModel):
    email: Email
    password: Annotated[str, StringConstraints(max_length=PASSWORD_MAX_LENGTH)]


class OrganizationCreate(RequestModel):
    name: Name
    industry: Industry
    country: CountryCode
    can_hire: bool
    can_provide: bool
    assistant_name: AssistantName | None = None

    @model_validator(mode="after")
    def _capabilities(self) -> "OrganizationCreate":
        if not (self.can_hire or self.can_provide):
            raise ValueError("Choose at least one of Hire workers or Provide work")
        if self.can_hire and not self.assistant_name:
            self.assistant_name = "Mira"
        return self


class OrganizationUpdate(RequestModel):
    name: Name | None = None
    industry: Industry | None = None
    country: CountryCode | None = None
    can_hire: bool | None = None
    can_provide: bool | None = None
    assistant_name: AssistantName | None = None
    payout_email: Email | None = None


class OrganizationOut(ResponseModel):
    id: str
    name: str
    industry: str
    country: str
    can_hire: bool
    can_provide: bool
    assistant_name: str | None
    payout_email: str | None
    onboarded_at: datetime | None


class MembershipOut(ResponseModel):
    role: Role
    organization: OrganizationOut


class UserOut(ResponseModel):
    id: str
    email: str
    full_name: str
    is_platform_admin: bool
    membership: MembershipOut | None = None


class SessionOut(ResponseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (OAuth token type, not a secret)
    expires_in: int = Field(description="Access token lifetime in seconds")
    user: UserOut
