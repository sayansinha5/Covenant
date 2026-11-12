"""The hard-check registry. Every check an acceptance spec may use is a pure function here;
a spec naming any other type, or passing params a check doesn't accept, is rejected."""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from langdetect import DetectorFactory, LangDetectException, detect_langs
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Scope = Literal["each_item", "whole"]
EACH: frozenset[Scope] = frozenset({"each_item"})
WHOLE: frozenset[Scope] = frozenset({"whole"})
EITHER: frozenset[Scope] = EACH | WHOLE

# Language detection is unreliable on a few words, so shorter text is not judged.
MIN_DETECT_LETTERS = 20
SOURCE_LANGUAGE_CONFIDENCE = 0.9
MAX_PATTERN_LENGTH = 200
QUOTE_CHARS = 60

ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
CSS_HIDDEN = re.compile(
    r"<[^>]+style\s*=\s*[\"'][^\"']*"
    r"(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?![.\d])|opacity\s*:\s*0(?![.\d]))",
    re.IGNORECASE,
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
LETTER = re.compile(r"[^\W\d_]")

LANGUAGE_NAMES = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "nl": "Dutch",
    "pt": "Portuguese",
}

DetectorFactory.seed = 0  # langdetect is random unless seeded


@dataclass(frozen=True, slots=True)
class DeliveredFile:
    name: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Target:
    """What a check looks at: one item and its source row (`each_item`), or the list of
    items and all source rows (`whole`). Files belong to the whole delivery."""

    value: Any
    source: Any = None
    files: tuple[DeliveredFile, ...] = ()


@dataclass(frozen=True, slots=True)
class Outcome:
    passed: bool
    reason: str = ""


PASSED = Outcome(passed=True)


def failed(reason: str) -> Outcome:
    return Outcome(passed=False, reason=reason)


class MissingField(LookupError):
    pass


# ── Params ──────────────────────────────────────────────────────────────────


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


FieldPath = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$", max_length=100)
]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]


class FieldParams(Params):
    """`field` is a dotted path into the item; empty means the item itself."""

    field: FieldPath | None = None


class RequiredFieldParams(Params):
    field: FieldPath


class CountParams(Params):
    count: int = Field(ge=0)


class SchemaParams(Params):
    json_schema: dict[str, Any]

    @field_validator("json_schema")
    @classmethod
    def _valid_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError(f"json_schema is not a valid JSON Schema: {exc.message}") from None
        return value


class UnchangedParams(RequiredFieldParams):
    source_field: FieldPath | None = None


class LanguageParams(FieldParams):
    language: LanguageCode


class SourceLanguageParams(FieldParams):
    source_language: LanguageCode


class MinLengthParams(FieldParams):
    min: int = Field(ge=1)


class MaxLengthParams(FieldParams):
    max: int = Field(ge=1)


class RegexParams(FieldParams):
    pattern: str = Field(min_length=1, max_length=MAX_PATTERN_LENGTH)

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"pattern is not a valid regular expression: {exc}") from None
        return value


class GroundedParams(FieldParams):
    source_fields: list[FieldPath] | None = None


class FileTypeParams(Params):
    types: list[str] = Field(min_length=1)

    @field_validator("types")
    @classmethod
    def _normalise(cls, value: list[str]) -> list[str]:
        return [t.strip().lower().lstrip(".") for t in value]


class FileCountParams(Params):
    min: int = Field(ge=0)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "FileCountParams":
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


# ── Helpers ─────────────────────────────────────────────────────────────────


def get_field(value: Any, path: str | None) -> Any:
    if path is None:
        return value
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise MissingField(path)
        value = value[key]
    return value


def strings(value: Any) -> Iterator[str]:
    """Every string inside a value (dict values and list entries, recursively)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def text_of(value: Any) -> str:
    return "\n".join(strings(value))


def quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= QUOTE_CHARS else f"{text[: QUOTE_CHARS - 1]}…"


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def detect(text: str) -> tuple[str, float] | None:
    """Most likely language and its probability, or None when there's too little text."""
    if len(LETTER.findall(text)) < MIN_DETECT_LETTERS:
        return None
    try:
        best = detect_langs(text)[0]
    except LangDetectException:
        return None
    return str(best.lang), float(best.prob)


def numbers(text: str) -> set[Decimal]:
    found = set()
    for raw in NUMBER.findall(text):
        try:
            found.add(Decimal(raw.replace(",", ".")).normalize())
        except InvalidOperation:
            continue
    return found


def same(left: Any, right: Any) -> bool:
    if left == right:
        return True
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        return str(left).strip() == str(right).strip()


def _with_field(params: FieldParams | RequiredFieldParams, target: Target) -> Any:
    return get_field(target.value, params.field)


def _label(field: str | None) -> str:
    return f"'{field}'" if field else "The item"


def _in_field(field: str | None) -> str:
    return f" in '{field}'" if field else ""


# ── Checks ──────────────────────────────────────────────────────────────────


def item_count_equals(params: CountParams, target: Target) -> Outcome:
    if not isinstance(target.value, list):
        return failed("The delivery is not a list of items.")
    if len(target.value) != params.count:
        return failed(f"Expected {params.count} items, got {len(target.value)}.")
    return PASSED


def json_schema_valid(params: SchemaParams, target: Target) -> Outcome:
    error = next(iter(Draft202012Validator(params.json_schema).iter_errors(target.value)), None)
    if error is None:
        return PASSED
    where = "/".join(str(part) for part in error.absolute_path)
    return failed(
        f"Doesn't match the agreed format{f' at {where}' if where else ''}: {error.message}"
    )


def field_present(params: RequiredFieldParams, target: Target) -> Outcome:
    try:
        value = _with_field(params, target)
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    empty = isinstance(value, str) and not value.strip()
    if value is None or empty or (isinstance(value, list | dict) and not value):
        return failed(f"'{params.field}' is empty.")
    return PASSED


def field_unchanged(params: UnchangedParams, target: Target) -> Outcome:
    if not isinstance(target.source, dict):
        return failed("There's no source row to compare against.")
    source_field = params.source_field or params.field
    try:
        expected = get_field(target.source, source_field)
    except MissingField:
        return failed(f"The source row has no '{source_field}'.")
    try:
        actual = _with_field(params, target)
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    if not same(actual, expected):
        return failed(
            f"'{params.field}' changed from {quote(str(expected))!r} to {quote(str(actual))!r}."
        )
    return PASSED


def language_is(params: LanguageParams, target: Target) -> Outcome:
    try:
        text = text_of(_with_field(params, target))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    found = detect(text)
    if found is not None and found[0] != params.language:
        return failed(
            f"{_label(params.field)} reads as {language_name(found[0])}, "
            f"not {language_name(params.language)}."
        )
    return PASSED


def no_source_language_left(params: SourceLanguageParams, target: Target) -> Outcome:
    try:
        text = text_of(_with_field(params, target))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    for sentence in SENTENCE_BREAK.split(text):
        found = detect(sentence)
        if found and found[0] == params.source_language and found[1] >= SOURCE_LANGUAGE_CONFIDENCE:
            return failed(f"Still in {language_name(params.source_language)}: {quote(sentence)!r}")
    return PASSED


def min_length(params: MinLengthParams, target: Target) -> Outcome:
    try:
        text = text_of(_with_field(params, target))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    if len(text) < params.min:
        return failed(
            f"{_label(params.field)} has {len(text)} characters; at least {params.min} needed."
        )
    return PASSED


def max_length(params: MaxLengthParams, target: Target) -> Outcome:
    try:
        text = text_of(_with_field(params, target))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    if len(text) > params.max:
        return failed(
            f"{_label(params.field)} has {len(text)} characters; at most {params.max} allowed."
        )
    return PASSED


def regex_match(params: RegexParams, target: Target) -> Outcome:
    try:
        value = _with_field(params, target)
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    if not isinstance(value, str) or re.search(params.pattern, value) is None:
        return failed(f"{_label(params.field)} doesn't match the pattern {params.pattern}.")
    return PASSED


def source_grounded(params: GroundedParams, target: Target) -> Outcome:
    """Every number in the field must appear somewhere in the matching source row."""
    if not isinstance(target.source, dict):
        return failed("There's no source row to compare against.")
    try:
        delivered = numbers(text_of(_with_field(params, target)))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    fields = params.source_fields or list(target.source)
    source_text = " ".join(str(target.source.get(name, "")) for name in fields)
    invented = sorted(delivered - numbers(source_text))
    if invented:
        listed = ", ".join(format(n, "f") for n in invented[:5])
        return failed(f"Numbers not found in the source: {listed}.")
    return PASSED


def file_type_in(params: FileTypeParams, target: Target) -> Outcome:
    allowed = set(params.types)
    wrong = [
        f.name
        for f in target.files
        if f.name.rsplit(".", 1)[-1].lower() not in allowed and f.mime_type.lower() not in allowed
    ]
    if wrong:
        return failed(f"Files of a type that wasn't agreed: {', '.join(wrong[:5])}.")
    return PASSED


def file_count_between(params: FileCountParams, target: Target) -> Outcome:
    count = len(target.files)
    if not params.min <= count <= params.max:
        return failed(f"Expected {params.min} to {params.max} files, got {count}.")
    return PASSED


def no_hidden_text(params: FieldParams, target: Target) -> Outcome:
    try:
        text = text_of(_with_field(params, target))
    except MissingField:
        return failed(f"'{params.field}' is missing.")
    if ZERO_WIDTH.search(text):
        return failed("Contains invisible (zero-width or direction-control) characters.")
    if comment := HTML_COMMENT.search(text):
        return failed(f"Contains a hidden HTML comment: {quote(comment.group())!r}")
    if CSS_HIDDEN.search(text):
        return failed("Contains text hidden with CSS.")
    return PASSED


# ── Registry ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CheckType:
    params: type[Params]
    scopes: frozenset[Scope]
    run: Callable[[Any, Target], Outcome]
    describe: Callable[[Any], str]


REGISTRY: dict[str, CheckType] = {
    "item_count_equals": CheckType(
        CountParams, WHOLE, item_count_equals, lambda p: f"All {p.count} items present"
    ),
    "json_schema_valid": CheckType(
        SchemaParams, EITHER, json_schema_valid, lambda p: "Valid JSON in the agreed format"
    ),
    "field_present": CheckType(
        RequiredFieldParams, EACH, field_present, lambda p: f"'{p.field}' filled in"
    ),
    "field_unchanged": CheckType(
        UnchangedParams, EACH, field_unchanged, lambda p: f"'{p.field}' unchanged from the source"
    ),
    "language_is": CheckType(
        LanguageParams,
        EITHER,
        language_is,
        lambda p: f"{_label(p.field)} written in {language_name(p.language)}",
    ),
    "no_source_language_left": CheckType(
        SourceLanguageParams,
        EITHER,
        no_source_language_left,
        lambda p: f"No {language_name(p.source_language)} left{_in_field(p.field)}",
    ),
    "min_length": CheckType(
        MinLengthParams,
        EITHER,
        min_length,
        lambda p: f"{_label(p.field)} at least {p.min} characters",
    ),
    "max_length": CheckType(
        MaxLengthParams,
        EITHER,
        max_length,
        lambda p: f"{_label(p.field)} at most {p.max} characters",
    ),
    "regex_match": CheckType(
        RegexParams, EACH, regex_match, lambda p: f"{_label(p.field)} matches {p.pattern}"
    ),
    "source_grounded": CheckType(
        GroundedParams,
        EACH,
        source_grounded,
        lambda p: f"Numbers in {_label(p.field)} come from the source",
    ),
    "file_type_in": CheckType(
        FileTypeParams, WHOLE, file_type_in, lambda p: f"Files are {', '.join(p.types)}"
    ),
    "file_count_between": CheckType(
        FileCountParams, WHOLE, file_count_between, lambda p: f"{p.min} to {p.max} files"
    ),
    "no_hidden_text": CheckType(FieldParams, EITHER, no_hidden_text, lambda p: "No hidden text"),
}


class HardCheck(BaseModel):
    """One entry of a spec's `hard_checks`. Validation is the registry gate: an unknown type,
    a scope the check doesn't support or params it doesn't accept all raise here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    applies_to: Scope

    @model_validator(mode="after")
    def _registered(self) -> "HardCheck":
        check_type = REGISTRY.get(self.type)
        if check_type is None:
            raise ValueError(
                f"Unknown hard check type {self.type!r}; use one of: {', '.join(REGISTRY)}"
            )
        if self.applies_to not in check_type.scopes:
            allowed = " or ".join(sorted(check_type.scopes))
            raise ValueError(f"Check {self.id!r} ({self.type}) must apply to {allowed}")
        try:
            check_type.params.model_validate(self.params)
        except ValueError as exc:
            raise ValueError(f"Check {self.id!r} ({self.type}) has invalid params: {exc}") from None
        return self

    def _typed(self) -> tuple[CheckType, Params]:
        check_type = REGISTRY[self.type]
        return check_type, check_type.params.model_validate(self.params)

    def run(self, target: Target) -> Outcome:
        check_type, params = self._typed()
        return check_type.run(params, target)

    def describe(self) -> str:
        check_type, params = self._typed()
        return check_type.describe(params)
