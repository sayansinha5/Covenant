"""LangGraph buyer agent. Tools can draft and cancel. None of them can fund a contract."""

import json
from dataclasses import dataclass, field
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import TypedDict

from app.ai.factory import Tier, get_chat_model
from app.ai.prompts import load_prompt
from app.ai.tracing import run_config
from app.core.config import Settings
from app.core.money import format_amount
from app.db.base import utcnow
from app.domain.policy import WORK_TYPES
from app.integrations.paypal import PayPalClient
from app.models import Contract, ContractEvent, Worker
from app.services.contracts import Actor
from app.services.escrow import cancel as cancel_escrow
from app.services.escrow import committed_this_month
from app.services.hiring import WorkerAmbiguous, WorkerUnavailable, resolve_worker
from app.services.hiring import draft_contract as write_contract
from app.services.hiring import revise_contract as rewrite_contract
from app.services.mandates import active_mandate

MAX_TOOL_CALLS = 8
COMPONENT = "buyer"


class BuyerState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    calls: int


@dataclass
class Turn:
    session: AsyncSession
    settings: Settings
    paypal: PayPalClient
    org_id: str
    user_id: str
    org_name: str
    assistant_name: str
    actor_name: str
    cards: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, str]] = field(default_factory=list)

    @property
    def actor(self) -> Actor:
        return Actor("buyer_agent", self.user_id)


def build_tools(turn: Turn) -> list[BaseTool]:
    """The only tools the in-app assistant gets. There is no fund tool."""

    @tool
    async def search_workers(category: str, max_price: str = "", min_reputation: int = 0) -> str:
        """Find up to 5 verified workers the org can hire. category is one of the work types."""
        if category not in WORK_TYPES:
            return json.dumps({"error": f"Unknown category {category}."})
        rows = list(
            await turn.session.scalars(
                select(Worker)
                .where(
                    Worker.status == "verified",
                    Worker.org_id != turn.org_id,
                    Worker.reputation >= min_reputation,
                )
                .order_by(Worker.reputation.desc())
                .limit(20)
            )
        )
        chosen = [worker for worker in rows if category in (worker.categories or [])]
        if max_price:
            cap = _decimal(max_price)
            chosen = [worker for worker in chosen if cap is None or worker.price <= cap]
        chosen = chosen[:5]
        card = {
            "type": "shortlist",
            "workers": [_worker_card(worker) for worker in chosen],
        }
        turn.cards.append(card)
        count = len(chosen)
        noun = "worker" if count == 1 else "workers"
        turn.steps.append({"name": "search_workers", "status": f"{count} {noun}"})
        return json.dumps(card)

    @tool
    async def get_worker(worker_id: str) -> str:
        """Read one verified worker. worker_id is the id or the display name."""
        try:
            worker = await resolve_worker(turn.session, org_id=turn.org_id, ref=worker_id)
        except WorkerAmbiguous as exc:
            return json.dumps({"error": exc.detail})
        except WorkerUnavailable:
            return json.dumps({"error": "That worker isn't available."})
        card = {"type": "worker", **_worker_card(worker)}
        turn.cards.append(card)
        turn.steps.append({"name": "get_worker", "status": worker.display_name})
        return json.dumps(card)

    @tool
    async def get_mandate() -> str:
        """Read the active mandate and how much of this month's budget is already committed."""
        mandate = await active_mandate(turn.session, turn.org_id)
        if mandate is None:
            summary = {"signed": False, "reason": "There's no signed mandate."}
        else:
            spent = await committed_this_month(
                turn.session, turn.org_id, utcnow(), excluding_contract_id=""
            )
            summary = {
                "signed": True,
                "monthly_budget": format_amount(mandate.monthly_budget),
                "per_task_cap": format_amount(mandate.per_task_cap),
                "approval_threshold": format_amount(mandate.approval_threshold),
                "allowed_work_types": list(mandate.allowed_work_types),
                "committed_this_month": format_amount(spent),
            }
        turn.steps.append({"name": "get_mandate", "status": "Read the mandate"})
        return json.dumps(summary)

    @tool
    async def draft_contract(worker_id: str, request_text: str, budget: str = "") -> str:
        """Draft a contract with the Spec Writer and check the mandate. Does not fund it.
        worker_id is the id or the display name."""
        try:
            contract, kind = await write_contract(
                turn.session,
                turn.settings,
                turn.paypal,
                org_id=turn.org_id,
                user_actor=turn.actor,
                worker_id=worker_id,
                request_text=request_text,
                budget=_decimal(budget) if budget else None,
            )
        except Exception as exc:
            message = getattr(exc, "detail", None) or str(exc)
            card = {"type": "error", "message": message[:400]}
            turn.cards.append(card)
            return json.dumps(card)
        worker = await turn.session.get(Worker, contract.worker_id)
        card = {
            "type": kind if kind != "error" else "error",
            "contract_id": contract.id,
            "number": f"C-{contract.number}",
            "title": contract.title,
            "amount": format_amount(contract.amount),
            "currency": contract.currency,
            "state": contract.state,
            "worker_name": worker.display_name if worker else "",
            "message": contract.title,
        }
        turn.cards.append(card)
        turn.steps.append({"name": "draft_contract", "status": contract.state})
        return json.dumps(card)

    @tool
    async def revise_contract(contract_id: str, change_request: str) -> str:
        """Revise a contract that is still waiting for agreement or approval."""
        try:
            contract = await rewrite_contract(
                turn.session,
                turn.settings,
                org_id=turn.org_id,
                contract_id=contract_id,
                change_request=change_request,
                user_actor=turn.actor,
            )
        except Exception as exc:
            message = getattr(exc, "detail", None) or str(exc)
            return json.dumps({"error": message[:400]})
        card = {
            "type": "proposal",
            "contract_id": contract.id,
            "number": f"C-{contract.number}",
            "title": contract.title,
            "amount": format_amount(contract.amount),
            "currency": contract.currency,
            "state": contract.state,
        }
        turn.cards.append(card)
        turn.steps.append({"name": "revise_contract", "status": "Revised"})
        return json.dumps(card)

    @tool
    async def get_contract_status(contract_id: str) -> str:
        """Read a contract's state and the latest timeline line. Only this org's contracts."""
        contract = await turn.session.get(Contract, contract_id)
        if contract is None or contract.hirer_org_id != turn.org_id:
            return json.dumps({"error": "That contract doesn't exist."})
        event = await turn.session.scalar(
            select(ContractEvent)
            .where(ContractEvent.contract_id == contract.id)
            .order_by(ContractEvent.created_at.desc())
        )
        return json.dumps(
            {
                "id": contract.id,
                "number": f"C-{contract.number}",
                "state": contract.state,
                "title": contract.title,
                "last": event.message if event else "",
            }
        )

    @tool
    async def cancel_contract(contract_id: str) -> str:
        """Cancel a contract before the worker accepts. A hold, if any, is released."""
        try:
            contract = await cancel_escrow(
                turn.session,
                org_id=turn.org_id,
                contract_id=contract_id,
                actor=turn.actor,
                actor_name=turn.assistant_name,
            )
        except Exception as exc:
            message = getattr(exc, "detail", None) or str(exc)
            return json.dumps({"error": message[:400]})
        turn.steps.append({"name": "cancel_contract", "status": contract.state})
        return json.dumps({"id": contract.id, "state": contract.state})

    return [
        search_workers,
        get_worker,
        get_mandate,
        draft_contract,
        revise_contract,
        get_contract_status,
        cancel_contract,
    ]


async def run_turn(turn: Turn, history: list[dict[str, str]], user_text: str) -> str:
    """One user message. Returns the assistant's final text. Cards land on `turn.cards`."""
    tools = build_tools(turn)
    prompt = load_prompt(COMPONENT)
    mandate = await _mandate_line(turn)
    system = prompt.messages(
        assistant_name=turn.assistant_name,
        org_name=turn.org_name,
        mandate=mandate,
        message=user_text,
    )[0]
    messages: list[Any] = [system]
    for item in history[-12:]:
        if item["role"] == "user":
            messages.append(HumanMessage(item["content"]))
        elif item["role"] == "assistant":
            messages.append(AIMessage(item["content"]))
    messages.append(HumanMessage(user_text))
    model = get_chat_model(turn.settings, Tier.MEDIUM).bind_tools(tools)
    by_name = {item.name: item for item in tools}
    traced = run_config(
        turn.settings, component=COMPONENT, prompt_version=prompt.version_id, org_id=turn.org_id
    )

    async def agent(state: BuyerState) -> dict[str, Any]:
        reply = await model.ainvoke(state["messages"], config=traced.config)
        return {"messages": [reply]}

    async def tools_node(state: BuyerState) -> dict[str, Any]:
        last = state["messages"][-1]
        outputs: list[ToolMessage] = []
        calls = getattr(last, "tool_calls", None) or []
        for call in calls:
            name = str(call.get("name") or "")
            try:
                result = await by_name[name].ainvoke(call.get("args") or {})
            except Exception as exc:
                result = json.dumps({"error": str(exc)[:300]})
            outputs.append(ToolMessage(str(result), tool_call_id=str(call.get("id") or name)))
        return {"messages": outputs, "calls": state["calls"] + len(calls)}

    def route(state: BuyerState) -> str:
        last = state["messages"][-1]
        calls = getattr(last, "tool_calls", None)
        if calls and state["calls"] < MAX_TOOL_CALLS:
            return "tools"
        return END

    graph: StateGraph[BuyerState] = StateGraph(BuyerState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    final = await graph.compile().ainvoke({"messages": messages, "calls": 0})
    last = final["messages"][-1]
    text = last.content if isinstance(last.content, str) else str(last.content)
    return text or "I couldn't put a reply together. Try asking in a different way."


async def _mandate_line(turn: Turn) -> str:
    mandate = await active_mandate(turn.session, turn.org_id)
    if mandate is None:
        return "No signed mandate yet."
    return (
        f"Monthly budget {format_amount(mandate.monthly_budget)}, "
        f"per task {format_amount(mandate.per_task_cap)}, "
        f"ask before {format_amount(mandate.approval_threshold)}. "
        f"Allowed: {', '.join(mandate.allowed_work_types)}."
    )


def _worker_card(worker: Worker) -> dict[str, Any]:
    return {
        "id": worker.id,
        "name": worker.display_name,
        "kind": worker.kind,
        "price": format_amount(worker.price),
        "currency": worker.currency,
        "reputation": worker.reputation,
        "jobs_completed": worker.jobs_completed,
        "categories": list(worker.categories or []),
    }


def _decimal(value: str) -> Any:
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None
