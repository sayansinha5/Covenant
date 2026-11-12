"""Send one task to an agent and read its JSON delivery back. Redirects are never followed."""

import json
from typing import Any

import httpx
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types.a2a_pb2 import Message, Part, Role, SendMessageRequest, TaskState

from app.core.config import Settings
from app.core.ids import uuid7
from app.integrations.a2a.ssrf import check_agent_url

CARD_PATH = "/.well-known/agent-card.json"
MAX_BYTES = 1024 * 1024
TERMINAL = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}


class AgentCallError(RuntimeError):
    pass


async def fetch_card(settings: Settings, base_url: str) -> dict[str, Any]:
    check_agent_url(base_url, settings.allowed_agent_hosts)
    url = base_url.rstrip("/") + CARD_PATH
    async with _http(settings) as http:
        try:
            response = await http.get(url)
        except httpx.HTTPError as exc:
            raise AgentCallError(f"Couldn't fetch the agent card: {exc}") from exc
    if response.is_redirect:
        raise AgentCallError("The agent card URL redirected, which Covenant never follows.")
    if response.status_code != 200:
        raise AgentCallError(f"The agent card answered HTTP {response.status_code}.")
    if len(response.content) > MAX_BYTES:
        raise AgentCallError("The agent card is larger than 1 MB.")
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise AgentCallError("The agent card isn't JSON.") from exc
    if not isinstance(body, dict):
        raise AgentCallError("The agent card isn't a JSON object.")
    return body


async def run_task(settings: Settings, base_url: str, token: str, payload: dict[str, Any]) -> Any:
    """Send `payload` as one JSON message and return the parsed JSON artifact."""
    check_agent_url(base_url, settings.allowed_agent_hosts)
    request = SendMessageRequest(
        message=Message(
            message_id=uuid7(),
            role=Role.ROLE_USER,
            parts=[Part(text=json.dumps(payload), media_type="application/json")],
        )
    )
    async with _http(settings, token=token, timeout=settings.ai_timeout_seconds) as http:
        client = await ClientFactory(
            ClientConfig(httpx_client=http, streaming=False)
        ).create_from_url(base_url.rstrip("/"))
        try:
            task = None
            async for event in client.send_message(request):
                task = event.task if event.HasField("task") else task
                if task is not None and task.status.state in TERMINAL:
                    break
        except Exception as exc:
            detail = getattr(exc, "data", None)
            extra = f" ({detail})" if detail else ""
            raise AgentCallError(f"The agent call failed: {exc}{extra}") from exc
        finally:
            await client.close()
    if task is None or task.status.state != TaskState.TASK_STATE_COMPLETED:
        state = task.status.state if task is not None else "no task"
        raise AgentCallError(f"The agent didn't complete the task ({state}).")
    return _delivery(task)


def _delivery(task: Any) -> Any:
    texts: list[str] = []
    for artifact in task.artifacts:
        for part in artifact.parts:
            if part.text:
                texts.append(part.text)
            elif part.HasField("data"):
                return json.loads(json.dumps(part.data))  # Struct -> plain JSON
    if not texts:
        raise AgentCallError("The agent completed without a delivery.")
    try:
        return json.loads("".join(texts))
    except json.JSONDecodeError as exc:
        raise AgentCallError("The agent's delivery isn't JSON.") from exc


def _http(
    settings: Settings, *, token: str = "", timeout: float | None = None
) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        timeout=timeout or settings.agent_http_timeout_seconds,
        follow_redirects=False,
        headers=headers,
    )
