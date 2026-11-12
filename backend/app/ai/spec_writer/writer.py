"""Spec Writer workflow: one structured-output call (tier `medium`), then code fills in and
checks everything that must not come from a model."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from app.ai.arbiter.hard_checks import (
    REGISTRY,
    MissingField,
    Scope,
    detect,
    get_field,
    language_name,
    text_of,
)
from app.ai.factory import Tier, get_chat_model
from app.ai.prompts import load_prompt
from app.ai.spec_writer.source import columns
from app.ai.spec_writer.spec import AcceptanceSpec
from app.ai.spotlight import spotlight
from app.ai.structured import Rejected, invoke_structured
from app.ai.tracing import run_config
from app.core.config import Settings
from app.core.money import format_amount
from app.domain.policy import WorkType

COMPONENT = "spec_writer"
SAMPLE_ROWS = 3
COUNT_CHECK_ID = "item_count"
CODE_FILLED = {"item_count_equals"}
SOURCE_FIELD_CHECKS = {"field_unchanged", "source_grounded"}
LANGUAGE_CHECKS = {"language_is", "no_source_language_left"}
LANGUAGE_SAMPLE_ROWS = 10


@dataclass(frozen=True, slots=True)
class SourceFile:
    file_id: str | None
    name: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SpecRequest:
    request_text: str
    work_type: WorkType
    worker_name: str
    worker_kind: Literal["agent", "human"]
    price: Decimal
    currency: str
    source: SourceFile | None = None
    previous: AcceptanceSpec | None = None
    change_request: str | None = None


@dataclass(frozen=True, slots=True)
class WrittenSpec:
    spec: AcceptanceSpec
    prompt_version: str
    run_id: str | None


class DraftCheck(BaseModel):
    id: str = Field(description="Short snake_case id, unique within the spec")
    type: str = Field(description="One of the check types listed in the instructions")
    params: dict[str, Any] = Field(default_factory=dict, description="Params for that type")
    applies_to: Scope


class DraftCriterion(BaseModel):
    id: str = Field(description="Short snake_case id")
    name: str
    description: str = Field(description="What a 10/10 looks like for one item")
    weight: float = Field(description="Share of the item score; all weights sum to 1.0")


class SpecDraft(BaseModel):
    """The acceptance spec for one contract, as proposed by the Spec Writer."""

    title: str = Field(description="Short contract title, at most 200 characters")
    deliverable_description: str = Field(description="One or two plain sentences")
    item_schema: dict[str, Any] | None = Field(
        description="JSON Schema for one delivered item when the deliverable is JSON, else null"
    )
    hard_checks: list[DraftCheck]
    rubric: list[DraftCriterion] = Field(description="2 to 5 quality criteria")


async def write_spec(
    settings: Settings,
    request: SpecRequest,
    *,
    org_id: str,
    contract_id: str | None = None,
    model: BaseChatModel | None = None,
) -> WrittenSpec:
    prompt = load_prompt(COMPONENT)
    traced = run_config(
        settings,
        component=COMPONENT,
        prompt_version=prompt.version_id,
        contract_id=contract_id,
        org_id=org_id,
    )
    request_block = spotlight("request", request.request_text)
    worker_block = spotlight("worker_name", request.worker_name)
    source_block = spotlight("source", _source_summary(request.source))
    change_block = spotlight("change_request", request.change_request or "(none)")
    messages = prompt.messages(
        request_tag=request_block.tag,
        worker_tag=worker_block.tag,
        source_tag=source_block.tag,
        change_tag=change_block.tag,
        request=request_block.block,
        worker_name=worker_block.block,
        source=source_block.block,
        change_request=change_block.block,
        work_type=request.work_type,
        worker_kind=request.worker_kind,
        check_types=_check_catalogue(),
        previous_spec=(
            request.previous.model_dump_json(indent=2) if request.previous else "(first draft)"
        ),
    )
    spec = await invoke_structured(
        model or get_chat_model(settings, Tier.MEDIUM),
        SpecDraft,
        messages,
        config=traced.config,
        validate=lambda draft: complete(settings, request, draft),
    )
    return WrittenSpec(spec=spec, prompt_version=prompt.version_id, run_id=traced.run_id)


def complete(settings: Settings, request: SpecRequest, draft: SpecDraft) -> AcceptanceSpec:
    """Turn a draft into a spec: code sets the item count, price, bands, pass score, deadline
    and source language, fills `json_schema_valid` from `item_schema`, and checks field names
    against the source columns. Any problem is a `Rejected` the model gets one chance to fix."""
    rows = request.source.rows if request.source else None
    checks: list[dict[str, Any]] = []
    expected_count = len(rows) if rows else None
    if expected_count is not None:
        checks.append(
            {
                "id": COUNT_CHECK_ID,
                "type": "item_count_equals",
                "params": {"count": expected_count},
                "applies_to": "whole",
            }
        )
    for check in draft.hard_checks:
        if check.type in CODE_FILLED and rows:
            continue
        params = dict(check.params)
        if check.type == "item_count_equals" and expected_count is None:
            expected_count = params.get("count") if isinstance(params.get("count"), int) else None
        if check.type == "json_schema_valid":
            if draft.item_schema is None:
                raise Rejected("json_schema_valid needs item_schema; set it or drop the check")
            params = {"json_schema": draft.item_schema}
        if check.type in SOURCE_FIELD_CHECKS:
            _require_source_fields(check, params, rows)
        if check.type in LANGUAGE_CHECKS and rows:
            params = _with_source_language(check, params, rows)
        check_id = _unique(check.id, {c["id"] for c in checks})
        checks.append(check.model_dump() | {"id": check_id, "params": params})
    _no_contradictions(checks)

    deadline = (
        settings.agent_default_deadline_minutes
        if request.worker_kind == "agent"
        else settings.human_default_deadline_hours * 60
    )
    return AcceptanceSpec.model_validate(
        {
            "title": draft.title,
            "work_type": request.work_type,
            "deliverable_description": draft.deliverable_description,
            "input_ref": request.source.file_id if request.source else None,
            "expected_item_count": expected_count,
            "item_schema": draft.item_schema,
            "hard_checks": checks,
            "rubric": [criterion.model_dump() for criterion in draft.rubric],
            "item_pass_score": settings.arbiter_item_pass_score,
            "bands": {
                "pass_min": settings.arbiter_pass_band_min,
                "partial_min": settings.arbiter_partial_band_min,
            },
            "deadline_minutes": round(deadline),
            "price": format_amount(request.price),
            "currency": request.currency,
        }
    )


def _unique(check_id: str, taken: set[str]) -> str:
    """Check ids are labels, so a repeated one is renumbered instead of rejected."""
    candidate, number = check_id, 2
    while candidate in taken:
        candidate, number = f"{check_id[:36]}_{number}", number + 1
    return candidate


def _with_source_language(
    check: DraftCheck, params: dict[str, Any], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """The source language is a fact of the file: code detects it and overrides the model's
    `source_language`, and refuses a target language the source is already written in."""
    field = params.get("field")
    sample = [
        text_of(get_field(row, field)) for row in rows[:LANGUAGE_SAMPLE_ROWS] if _has(row, field)
    ]
    found = detect("\n".join(sample))
    if found is None:
        return params
    source_language = found[0]
    if check.type == "no_source_language_left":
        return params | {"source_language": source_language}
    if params.get("language") == source_language:
        raise Rejected(
            f"Check {check.id!r}: the source is already in {language_name(source_language)}, "
            "so language_is must name the language the work is delivered in"
        )
    return params


def _has(row: dict[str, Any], field: str | None) -> bool:
    try:
        get_field(row, field)
    except MissingField:
        return False
    return True


def _no_contradictions(checks: list[dict[str, Any]]) -> None:
    """A field can't be both kept as-is and required in another language, or every honest
    delivery would fail."""
    unchanged = {c["params"]["field"] for c in checks if c["type"] == "field_unchanged"}
    for check in checks:
        if check["type"] not in LANGUAGE_CHECKS or not unchanged:
            continue
        field = check["params"].get("field")
        if field is None:
            raise Rejected(
                f"Check {check['id']!r} ({check['type']}) has no field, so it would also read "
                f"the fields that must stay unchanged ({', '.join(sorted(unchanged))}); "
                "add one check per translated field instead"
            )
        if field in unchanged:
            raise Rejected(
                f"'{field}' can't be both unchanged (field_unchanged) and translated "
                f"({check['type']}); decide whether it is translated"
            )


def _require_source_fields(
    check: DraftCheck, params: dict[str, Any], rows: list[dict[str, Any]] | None
) -> None:
    if not rows:
        raise Rejected(f"{check.type} compares with an input file, and none is attached")
    known = columns(rows)
    names = [params.get("source_field") or params.get("field")]
    names += list(params.get("source_fields") or [])
    unknown = [name for name in names if name and str(name).split(".")[0] not in known]
    if unknown:
        raise Rejected(
            f"Check {check.id!r} names {', '.join(map(str, unknown))}, which the input file "
            f"doesn't have; its columns are {', '.join(known)}"
        )


def _source_summary(source: SourceFile | None) -> str:
    if source is None:
        return "(no input file)"
    sample = json.dumps(source.rows[:SAMPLE_ROWS], ensure_ascii=False, indent=2)
    return (
        f"File: {source.name}\nRows: {len(source.rows)}\n"
        f"Columns: {', '.join(columns(source.rows))}\nFirst rows:\n{sample}"
    )


def _check_catalogue() -> str:
    lines = []
    for name, check_type in REGISTRY.items():
        params = check_type.params.model_json_schema().get("properties", {})
        described = (
            ", ".join(f"{key} ({_type_of(value)})" for key, value in params.items()) or "none"
        )
        scopes = " or ".join(sorted(check_type.scopes))
        lines.append(f"- {name}: applies_to {scopes}; params: {described}")
    return "\n".join(lines)


def _type_of(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        return "|".join(_type_of(option) for option in schema["anyOf"])
    return str(schema.get("type", "object"))
