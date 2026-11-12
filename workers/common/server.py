"""A2A server shared by the three demo workers: agent card, JSON-RPC and a bearer token."""

import json
from collections.abc import Awaitable, Callable

import uvicorn
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers.default_request_handler import LegacyRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types.a2a_pb2 import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    TaskState,
)
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    PROTOCOL_VERSION_CURRENT,
    TransportProtocol,
)
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from common.settings import Settings

Work = Callable[[str], Awaitable[object]]


def make_card(
    name: str, description: str, url: str, skills: list[tuple[str, str, list[str]]]
) -> AgentCard:
    card = AgentCard(
        name=name,
        description=description,
        version="0.1.0",
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["application/json", "text/plain"],
        capabilities=AgentCapabilities(),
        supported_interfaces=[
            AgentInterface(
                url=url,
                protocol_binding=TransportProtocol.JSONRPC,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        skills=[
            AgentSkill(id=skill_id, name=skill_name, description=skill_name, tags=tags)
            for skill_id, skill_name, tags in skills
        ],
    )
    return card


class DeliveryExecutor(AgentExecutor):
    def __init__(self, work: Work) -> None:
        self._work = work

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.update_status(TaskState.TASK_STATE_WORKING)
        try:
            result = await self._work(context.get_user_input())
        except Exception:
            await updater.update_status(TaskState.TASK_STATE_FAILED)
            return
        await updater.add_artifact([Part(text=json.dumps(result), media_type="application/json")])
        await updater.update_status(TaskState.TASK_STATE_COMPLETED)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.update_status(TaskState.TASK_STATE_CANCELED)


def build_app(card: AgentCard, work: Work, token: str) -> Starlette:
    handler = LegacyRequestHandler(
        agent_executor=DeliveryExecutor(work), task_store=InMemoryTaskStore(), agent_card=card
    )
    app = Starlette(
        routes=[
            *create_agent_card_routes(card, card_url=AGENT_CARD_WELL_KNOWN_PATH),
            *create_jsonrpc_routes(handler, "/"),
        ]
    )

    class RequireBearer(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path == AGENT_CARD_WELL_KNOWN_PATH:
                return await call_next(request)
            header = request.headers.get("authorization")
            if header != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(RequireBearer)
    return app


def serve(app: Starlette, settings: Settings, port: int) -> None:
    uvicorn.run(app, host=settings.worker_host, port=port)
