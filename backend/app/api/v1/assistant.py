"""The in-app assistant. Streaming is server-sent events. The agent cannot fund a contract."""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.buyer.agent import Turn, run_turn
from app.api.deps import (
    OrgPrincipal,
    get_app_settings,
    get_database,
    get_paypal,
    get_session,
    require_hirer,
    require_org,
)
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.ids import uuid7
from app.core.rate_limit import RateLimiter
from app.db.engine import Database
from app.integrations.paypal import PayPalClient
from app.models import AgentConversation, AgentMessage, Organization, User
from app.schemas.common import RequestModel, ResponseModel

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ConversationOut(ResponseModel):
    id: str
    title: str


class MessageOut(ResponseModel):
    id: str
    role: str
    content: str
    tool_name: str | None = None
    card: dict[str, Any] | None = None


class MessageIn(RequestModel):
    text: str = Field(min_length=1, max_length=4000)


def _limit(request: Request, principal: OrgPrincipal = Depends(require_org)) -> None:
    limiter: RateLimiter = request.app.state.rate_limiter
    limiter.hit(request.app.state.settings.rate_limit_assistant, "assistant", principal.org_id)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    rows = await session.scalars(
        select(AgentConversation)
        .where(
            AgentConversation.org_id == principal.org_id,
            AgentConversation.user_id == principal.user_id,
        )
        .order_by(AgentConversation.created_at.desc())
        .limit(30)
    )
    return [ConversationOut(id=row.id, title=row.title) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    row = AgentConversation(id=uuid7(), org_id=principal.org_id, user_id=principal.user_id)
    session.add(row)
    await session.commit()
    return ConversationOut(id=row.id, title=row.title)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    session: AsyncSession = Depends(get_session),
) -> list[MessageOut]:
    await _owned(session, principal, conversation_id)
    rows = await session.scalars(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conversation_id)
        .order_by(AgentMessage.created_at)
    )
    return [
        MessageOut(
            id=row.id,
            role=row.role,
            content=row.content,
            tool_name=row.tool_name,
            card=row.card,
        )
        for row in rows
    ]


@router.post("/conversations/{conversation_id}/messages", dependencies=[Depends(_limit)])
async def post_message(
    conversation_id: str,
    body: MessageIn,
    principal: OrgPrincipal = Depends(require_org),
    _hirer: Organization = Depends(require_hirer),
    settings: Settings = Depends(get_app_settings),
    paypal: PayPalClient = Depends(get_paypal),
    database: Database = Depends(get_database),
) -> StreamingResponse:
    async with database.session() as session:
        await _owned(session, principal, conversation_id)

    async def generate() -> AsyncIterator[str]:
        async with database.session() as session:
            conversation = await _owned(session, principal, conversation_id)
            if conversation.title == "New conversation":
                conversation.title = body.text.strip()[:80]
            history = [
                {"role": row.role, "content": row.content}
                for row in await session.scalars(
                    select(AgentMessage)
                    .where(
                        AgentMessage.conversation_id == conversation_id,
                        AgentMessage.role.in_(("user", "assistant")),
                    )
                    .order_by(AgentMessage.created_at)
                )
            ]
            org = await session.get_one(Organization, principal.org_id)
            user = await session.get_one(User, principal.user_id)
            turn = Turn(
                session=session,
                settings=settings,
                paypal=paypal,
                org_id=principal.org_id,
                user_id=principal.user_id,
                org_name=org.name,
                assistant_name=org.assistant_name or "Mira",
                actor_name=user.full_name,
            )
            session.add(
                AgentMessage(
                    id=uuid7(),
                    conversation_id=conversation_id,
                    role="user",
                    content=body.text,
                )
            )
            try:
                answer = await run_turn(turn, history, body.text)
            except Exception as exc:  # the model or a tool failed; the user gets a safe line
                answer = "I couldn't finish that. Nothing was funded."
                yield _frame("error", {"message": str(getattr(exc, "detail", "") or answer)[:300]})
            for step in turn.steps:
                session.add(
                    AgentMessage(
                        id=uuid7(),
                        conversation_id=conversation_id,
                        role="tool",
                        content=step["status"],
                        tool_name=step["name"],
                    )
                )
                yield _frame("step", step)
            for card in turn.cards:
                yield _frame("card", card)
            message = AgentMessage(
                id=uuid7(),
                conversation_id=conversation_id,
                role="assistant",
                content=answer,
                card=turn.cards[-1] if turn.cards else None,
            )
            session.add(message)
            await session.commit()
            for start in range(0, len(answer), 24):
                yield _frame("token", {"text": answer[start : start + 24]})
            yield _frame("done", {"id": message.id})

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _owned(
    session: AsyncSession, principal: OrgPrincipal, conversation_id: str
) -> AgentConversation:
    row = await session.get(AgentConversation, conversation_id)
    if row is None or row.org_id != principal.org_id or row.user_id != principal.user_id:
        raise NotFoundError("This conversation doesn't exist.", code="CONVERSATION_NOT_FOUND")
    return row


def _frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
