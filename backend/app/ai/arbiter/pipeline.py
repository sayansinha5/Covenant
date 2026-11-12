"""The Arbiter: a LangGraph graph with fixed edges. Models score and flag; code decides.

`use_model=False` scores every delivered item 10/10, so the band comes only from the hard
checks and the manipulation scan. Registration and the demo script use that path. A funded
contract uses the model when AI is configured."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.ai.arbiter.decide import near_border, quality_band
from app.ai.arbiter.hard_checks import HardCheck, Target
from app.ai.arbiter.manipulation import scan as scan_manipulation
from app.ai.factory import AINotConfigured, Tier, get_chat_model, get_second_opinion_model
from app.ai.prompts import load_prompt
from app.ai.spotlight import spotlight
from app.ai.structured import Rejected, StructuredOutputFailed, invoke_structured
from app.ai.tracing import run_config
from app.core.config import Settings

COMPONENT = "arbiter"
RATIO_PLACES = Decimal("0.0001")


class ArbiterState(TypedDict, total=False):
    delivery: Any
    source_items: list[Any]
    spec: dict[str, Any]
    unreadable: str
    items: list[dict[str, Any]]
    hard_passed: dict[str, bool]
    hard_reasons: dict[str, list[str]]
    manipulation: dict[str, Any] | None
    scores: dict[str, float]
    comments: dict[str, str]
    confidences: list[float]
    item_results: list[dict[str, Any]]
    pass_ratio: str
    overall_score: float
    passed_count: int
    item_count: int
    low_confidence: bool
    near_border: bool
    bands_disagree: bool
    second_opinion: dict[str, Any] | None
    result: str
    reasoning: str
    judge_model: str
    prompt_version: str
    langsmith_run_id: str | None


def _merged(state: ArbiterState, extra: dict[str, Any]) -> ArbiterState:
    return cast(ArbiterState, {**state, **extra})


@dataclass(frozen=True, slots=True)
class VerdictDraft:
    result: str
    pass_ratio: Decimal
    overall_score: float
    item_results: list[dict[str, Any]]
    manipulation: dict[str, Any] | None
    reasoning: str
    judge_model: str
    second_opinion: dict[str, Any] | None
    prompt_version: str
    langsmith_run_id: str | None


class ItemJudgement(BaseModel):
    item_id: str
    criterion_scores: dict[str, float]
    comment: str = ""


class BatchJudgement(BaseModel):
    items: list[ItemJudgement]
    confidence: float = Field(ge=0, le=1)


class ManipulationFlag(BaseModel):
    is_manipulation: bool
    confidence: float = Field(ge=0, le=1)
    evidence: str = ""


class Explanation(BaseModel):
    paragraph: str = Field(min_length=20, max_length=1200)


def verification_spec(settings: Settings, task: dict[str, Any]) -> dict[str, Any]:
    """The acceptance spec for a registration test: the task's checks, plus the env bands."""
    return {
        "hard_checks": task["checks"],
        "rubric": [
            {
                "id": "quality",
                "name": "Quality",
                "description": "The test task was done as asked.",
                "weight": 1,
            }
        ],
        "item_pass_score": settings.arbiter_item_pass_score,
        "bands": {
            "pass_min": settings.arbiter_pass_band_min,
            "partial_min": settings.arbiter_partial_band_min,
        },
    }


async def arbitrate(
    settings: Settings,
    *,
    spec: dict[str, Any],
    delivery: Any,
    source_items: list[Any] | None = None,
    use_model: bool | None = None,
    contract_id: str | None = None,
    org_id: str | None = None,
) -> VerdictDraft:
    """Run the graph and return a verdict. Nothing here writes to the database or to PayPal."""
    pipeline = _Pipeline(
        settings,
        use_model=settings.ai_configured if use_model is None else use_model,
        contract_id=contract_id,
        org_id=org_id,
    )
    final = await pipeline.compile().ainvoke(
        {"delivery": delivery, "source_items": list(source_items or []), "spec": spec}
    )
    ratio = Decimal(final.get("pass_ratio") or "0")
    return VerdictDraft(
        result=str(final.get("result") or "fail"),
        pass_ratio=ratio,
        overall_score=float(final.get("overall_score") or 0),
        item_results=list(final.get("item_results") or []),
        manipulation=final.get("manipulation"),
        reasoning=str(final.get("reasoning") or "The delivery could not be verified."),
        judge_model=str(final.get("judge_model") or ""),
        second_opinion=final.get("second_opinion"),
        prompt_version=str(final.get("prompt_version") or "arbiter.code"),
        langsmith_run_id=final.get("langsmith_run_id"),
    )


class _Pipeline:
    def __init__(
        self,
        settings: Settings,
        *,
        use_model: bool,
        contract_id: str | None,
        org_id: str | None,
    ) -> None:
        self.settings = settings
        self.use_model = use_model
        self.contract_id = contract_id
        self.org_id = org_id
        self.run_id: str | None = None
        self.judge_model = "code"

    def compile(self) -> Any:
        graph: StateGraph[ArbiterState] = StateGraph(ArbiterState)
        graph.add_node("load", self.load)
        graph.add_node("split", self.split)
        graph.add_node("hard", self.hard)
        graph.add_node("scan", self.scan)
        graph.add_node("judge", self.judge)
        graph.add_node("aggregate", self.aggregate)
        graph.add_node("second", self.second)
        graph.add_node("decide", self.decide)
        graph.add_node("explain", self.explain)
        graph.add_edge(START, "load")
        graph.add_conditional_edges(
            "load", self._after_load, {"split": "split", "explain": "explain"}
        )
        graph.add_edge("split", "hard")
        graph.add_edge("hard", "scan")
        graph.add_edge("scan", "judge")
        graph.add_conditional_edges(
            "judge", self._after_judge, {"decide": "decide", "aggregate": "aggregate"}
        )
        graph.add_conditional_edges(
            "aggregate", self._after_aggregate, {"second": "second", "decide": "decide"}
        )
        graph.add_edge("second", "decide")
        graph.add_edge("decide", "explain")
        graph.add_edge("explain", END)
        return graph.compile()

    async def load(self, state: ArbiterState) -> dict[str, Any]:
        try:
            raw = json.dumps(state.get("delivery"), ensure_ascii=False, default=str).encode()
        except (TypeError, ValueError):
            return {"unreadable": "The delivery couldn't be read, so it fails.", "result": "fail"}
        if len(raw) > self.settings.max_delivery_bytes:
            return {
                "unreadable": "The delivery is larger than 1 MB, so it fails.",
                "result": "fail",
            }
        return {}

    async def split(self, state: ArbiterState) -> dict[str, Any]:
        sources = state.get("source_items") or []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, value in enumerate(_as_items(state.get("delivery")), start=1):
            source = sources[index - 1] if index - 1 < len(sources) else None
            item_id = _item_id(value, index)
            if item_id in seen:
                item_id = f"{item_id}-{index}"
            seen.add(item_id)
            items.append({"id": item_id, "value": value, "source": source})
        return {"items": items}

    async def hard(self, state: ArbiterState) -> dict[str, Any]:
        items = state.get("items") or []
        passed = {item["id"]: True for item in items}
        reasons: dict[str, list[str]] = {item["id"]: [] for item in items}
        values = [item["value"] for item in items]
        for raw in state.get("spec", {}).get("hard_checks") or []:
            try:
                check = HardCheck.model_validate(raw)
            except ValueError as exc:
                for item in items:
                    passed[item["id"]] = False
                    reasons[item["id"]].append(str(exc))
                continue
            if check.applies_to == "whole":
                outcome = check.run(Target(value=values, source=state.get("source_items")))
                if not outcome.passed:
                    for item in items:
                        passed[item["id"]] = False
                        reasons[item["id"]].append(outcome.reason)
                continue
            for item in items:
                outcome = check.run(Target(value=item["value"], source=item["source"]))
                if not outcome.passed:
                    passed[item["id"]] = False
                    reasons[item["id"]].append(outcome.reason)
        return {"hard_passed": passed, "hard_reasons": reasons}

    async def scan(self, state: ArbiterState) -> dict[str, Any]:
        if hit := scan_manipulation(state.get("delivery")):
            return {"manipulation": hit}
        if not self.use_model:
            return {"manipulation": None}
        try:
            flag = await self._classify(state)
        except (AINotConfigured, StructuredOutputFailed):
            return {"manipulation": None}
        if flag.is_manipulation and flag.confidence >= self.settings.arbiter_manipulation_threshold:
            return {
                "manipulation": {
                    "flagged": True,
                    "severity": "model",
                    "kind": "classifier",
                    "evidence": flag.evidence or "The classifier flagged this delivery.",
                    "confidence": flag.confidence,
                }
            }
        return {"manipulation": None}

    async def judge(self, state: ArbiterState) -> dict[str, Any]:
        if not self.use_model:
            return self._code_scores(state)
        model = get_chat_model(self.settings, Tier.SUPER)
        self.judge_model = model_name(model)
        return await self._score(state, model, "judge")

    async def aggregate(self, state: ArbiterState) -> dict[str, Any]:
        tallied = self._tally(state)
        ratio = Decimal(tallied["pass_ratio"])
        pass_min, partial_min = self._limits(state.get("spec") or {})
        margin = Decimal(str(self.settings.arbiter_border_margin))
        lowest = min(state.get("confidences") or [1.0])
        return {
            **tallied,
            "low_confidence": lowest < self.settings.arbiter_low_confidence,
            "near_border": near_border(
                ratio, pass_min=pass_min, partial_min=partial_min, margin=margin
            ),
        }

    async def second(self, state: ArbiterState) -> dict[str, Any]:
        try:
            model = get_second_opinion_model(self.settings)
        except AINotConfigured:
            return {}
        scored = await self._score(state, model, "judge")
        tallied = self._tally(_merged(state, scored))
        pass_min, partial_min = self._limits(state.get("spec") or {})
        first = quality_band(
            Decimal(state.get("pass_ratio") or "0"), pass_min=pass_min, partial_min=partial_min
        )
        other = quality_band(
            Decimal(tallied["pass_ratio"]), pass_min=pass_min, partial_min=partial_min
        )
        opinion = {"band": other, "pass_ratio": tallied["pass_ratio"], "agreed": first == other}
        if first == other:
            return {"second_opinion": opinion}
        return {"bands_disagree": True, "second_opinion": opinion}

    async def decide(self, state: ArbiterState) -> dict[str, Any]:
        extra = {} if "pass_ratio" in state else self._tally(state)
        merged = _merged(state, extra)
        if (merged.get("manipulation") or {}).get("flagged"):
            result = "manipulation"
        elif merged.get("bands_disagree"):
            result = "needs_review"
        else:
            pass_min, partial_min = self._limits(merged.get("spec") or {})
            result = quality_band(
                Decimal(merged.get("pass_ratio") or "0"), pass_min=pass_min, partial_min=partial_min
            )
        return {"result": result, **extra}

    async def explain(self, state: ArbiterState) -> dict[str, Any]:
        paragraph = _paragraph(state)
        prompt_version = "arbiter.code"
        if self.use_model and not state.get("unreadable"):
            try:
                paragraph, prompt_version = await self._explain(state, paragraph)
            except (AINotConfigured, StructuredOutputFailed):
                prompt_version = "arbiter.code"
        return {
            "reasoning": paragraph,
            "prompt_version": prompt_version,
            "judge_model": self.judge_model,
            "langsmith_run_id": self.run_id,
        }

    def _after_load(self, state: ArbiterState) -> str:
        return "explain" if state.get("unreadable") else "split"

    def _after_judge(self, state: ArbiterState) -> str:
        if (state.get("manipulation") or {}).get("flagged"):
            return "decide"
        return "aggregate"

    def _after_aggregate(self, state: ArbiterState) -> str:
        if self.use_model and (state.get("low_confidence") or state.get("near_border")):
            return "second"
        return "decide"

    def _code_scores(self, state: ArbiterState) -> dict[str, Any]:
        rubric = _rubric(state.get("spec") or {})
        scores = {
            item["id"]: _weighted(rubric, {c["id"]: 10.0 for c in rubric})
            for item in state.get("items") or []
        }
        comments = {item["id"]: "" for item in state.get("items") or []}
        return {"scores": scores, "comments": comments, "confidences": [1.0]}

    async def _score(
        self, state: ArbiterState, model: BaseChatModel, prompt_name: str
    ) -> dict[str, Any]:
        rubric = _rubric(state.get("spec") or {})
        ids = {c["id"] for c in rubric}
        items = state.get("items") or []
        scores: dict[str, float] = {}
        comments: dict[str, str] = {}
        confidences: list[float] = []
        prompt = load_prompt(prompt_name)
        batch_size = self.settings.arbiter_batch_size
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            block = spotlight("delivery", json.dumps(_batch_payload(batch), ensure_ascii=False))
            traced = run_config(
                self.settings,
                component=COMPONENT,
                prompt_version=prompt.version_id,
                contract_id=self.contract_id,
                org_id=self.org_id,
            )
            self.run_id = traced.run_id
            judged = await invoke_structured(
                model,
                BatchJudgement,
                prompt.messages(
                    delivery_tag=block.tag,
                    rubric=json.dumps(rubric, ensure_ascii=False),
                    delivery=block.block,
                ),
                config=traced.config,
                validate=_accept_batch(ids),
            )
            confidences.append(judged.confidence)
            for item in judged.items:
                scores[item.item_id] = _weighted(rubric, item.criterion_scores)
                comments[item.item_id] = item.comment
        return {"scores": scores, "comments": comments, "confidences": confidences or [0.0]}

    async def _classify(self, state: ArbiterState) -> ManipulationFlag:
        prompt = load_prompt("manipulation")
        model = get_chat_model(self.settings, Tier.FAST)
        block = spotlight(
            "delivery", json.dumps(state.get("delivery"), ensure_ascii=False, default=str)[:20_000]
        )
        traced = run_config(
            self.settings,
            component=COMPONENT,
            prompt_version=prompt.version_id,
            contract_id=self.contract_id,
            org_id=self.org_id,
        )
        return await invoke_structured(
            model,
            ManipulationFlag,
            prompt.messages(delivery_tag=block.tag, delivery=block.block),
            config=traced.config,
            validate=lambda parsed: parsed,
        )

    async def _explain(self, state: ArbiterState, fallback: str) -> tuple[str, str]:
        prompt = load_prompt("explain")
        model = get_chat_model(self.settings, Tier.FAST)
        traced = run_config(
            self.settings,
            component=COMPONENT,
            prompt_version=prompt.version_id,
            contract_id=self.contract_id,
            org_id=self.org_id,
        )
        summary = {
            "result": state.get("result"),
            "pass_ratio": state.get("pass_ratio"),
            "passed": state.get("passed_count"),
            "items": state.get("item_count"),
            "manipulation": (state.get("manipulation") or {}).get("evidence"),
        }
        written = await invoke_structured(
            model,
            Explanation,
            prompt.messages(result=json.dumps(summary, ensure_ascii=False)),
            config=traced.config,
            validate=lambda parsed: parsed,
        )
        return written.paragraph, prompt.version_id

    def _tally(self, state: ArbiterState) -> dict[str, Any]:
        items = state.get("items") or []
        item_pass = float(
            (state.get("spec") or {}).get("item_pass_score", self.settings.arbiter_item_pass_score)
        )
        hard = state.get("hard_passed") or {}
        reasons = state.get("hard_reasons") or {}
        scores = state.get("scores") or {}
        comments = state.get("comments") or {}
        results: list[dict[str, Any]] = []
        passed = 0
        total_score = 0.0
        for item in items:
            item_id = str(item["id"])
            score = float(scores.get(item_id, 0))
            hard_ok = bool(hard.get(item_id, False))
            ok = hard_ok and score >= item_pass
            passed += int(ok)
            total_score += score
            results.append(
                {
                    "item_id": item_id,
                    "passed": ok,
                    "score": round(score, 2),
                    "hard_passed": hard_ok,
                    "reasons": reasons.get(item_id) or [],
                    "comment": comments.get(item_id, ""),
                }
            )
        total = len(items)
        ratio = (Decimal(passed) / Decimal(total)).quantize(RATIO_PLACES) if total else Decimal("0")
        overall = round(total_score / total, 2) if total else 0.0
        return {
            "item_results": results,
            "pass_ratio": str(ratio),
            "overall_score": overall,
            "passed_count": passed,
            "item_count": total,
        }

    def _limits(self, spec: dict[str, Any]) -> tuple[Decimal, Decimal]:
        bands = spec.get("bands") or {}
        return (
            Decimal(str(bands.get("pass_min", self.settings.arbiter_pass_band_min))),
            Decimal(str(bands.get("partial_min", self.settings.arbiter_partial_band_min))),
        )


def _as_items(delivery: Any) -> list[Any]:
    if isinstance(delivery, list):
        return delivery
    if isinstance(delivery, dict) and isinstance(delivery.get("items"), list):
        return list(delivery["items"])
    return [delivery]


def _item_id(value: Any, index: int) -> str:
    if isinstance(value, dict) and value.get("id") not in (None, ""):
        return str(value["id"])
    return f"item-{index}"


def _rubric(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rubric = spec.get("rubric")
    if isinstance(rubric, list) and rubric:
        return list(rubric)
    return [
        {
            "id": "quality",
            "name": "Quality",
            "description": "The work matches the request.",
            "weight": 1,
        }
    ]


def _weighted(rubric: list[dict[str, Any]], criterion_scores: dict[str, float]) -> float:
    total_weight = 0.0
    accumulator = 0.0
    for criterion in rubric:
        weight = float(criterion.get("weight") or 0)
        accumulator += float(criterion_scores.get(str(criterion["id"]), 0)) * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return accumulator / total_weight


def _batch_payload(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": item["id"], "source": item["source"], "delivered": item["value"]} for item in items
    ]


def _accept_batch(criterion_ids: set[str]) -> Any:
    def validate(parsed: BatchJudgement) -> BatchJudgement:
        for item in parsed.items:
            for key, score in item.criterion_scores.items():
                if key not in criterion_ids:
                    raise Rejected(f"Unknown criterion {key}")
                if not 0 <= score <= 10:
                    raise Rejected(f"The score for {key} must be from 0 to 10")
        return parsed

    return validate


def _paragraph(state: ArbiterState) -> str:
    if state.get("unreadable"):
        return str(state["unreadable"])
    result = state.get("result") or "fail"
    if result == "manipulation":
        evidence = (state.get("manipulation") or {}).get("evidence") or "A reviewer-directed note."
        return (
            "This delivery is rejected because it tries to influence the review. "
            f"{evidence} The hold will be released and nothing is captured."
        )
    if result == "needs_review":
        return (
            "The two reviews didn't land in the same payment band, so a person needs to decide "
            "before any money moves."
        )
    passed = state.get("passed_count", 0)
    total = state.get("item_count", 0)
    ratio = Decimal(state.get("pass_ratio") or "0")
    closing = {
        "pass": "This meets the agreed bar, so the full hold can be captured.",
        "partial": "This is a partial delivery, so only the passing share of the hold is captured.",
        "fail": "This doesn't meet the agreed bar, so the hold is released.",
    }[result if result in ("pass", "partial", "fail") else "fail"]
    return f"{passed} of {total} items passed ({ratio:.0%}). {closing}"


def model_name(model: BaseChatModel) -> str:
    for attr in ("model_name", "model"):
        value = getattr(model, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(model).__name__
