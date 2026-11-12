"""Structured output with one corrective retry: if the answer doesn't parse or fails our own
validation, the model sees the error once; a second failure fails the step (never a guess)."""

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ValidationError

RETRY_MESSAGE = (
    "Your previous answer was rejected: {error}\n"
    "Answer again with the same tool, fixing exactly that problem."
)
MAX_ERROR_CHARS = 2000


class StructuredOutputFailed(RuntimeError):
    """The model didn't produce a valid answer after the retry."""


class Rejected(ValueError):
    """Raised by a `validate` callback: the answer parsed but breaks a rule the schema can't."""


async def invoke_structured[Out: BaseModel, Result](
    model: BaseChatModel,
    schema: type[Out],
    messages: Sequence[BaseMessage],
    *,
    config: RunnableConfig,
    validate: Callable[[Out], Result],
) -> Result:
    runnable = model.with_structured_output(schema, method="function_calling", include_raw=True)
    history = list(messages)
    error = ""
    for _ in range(2):
        answer: dict[str, Any] = await runnable.ainvoke(history, config=config)  # type: ignore[assignment]
        try:
            parsed = answer.get("parsed")
            if answer.get("parsing_error") is not None or not isinstance(parsed, schema):
                raise Rejected(str(answer.get("parsing_error") or "no tool call in the answer"))
            return validate(parsed)
        except (Rejected, ValidationError) as exc:
            error = str(exc)[:MAX_ERROR_CHARS]
            history.extend(_feedback(answer.get("raw"), RETRY_MESSAGE.format(error=error)))
    raise StructuredOutputFailed(f"{schema.__name__} was still invalid after a retry: {error}")


def _feedback(raw: object, text: str) -> list[BaseMessage]:
    """Providers require every tool call to be answered, so the error goes back as the
    tool result; an answer without a tool call gets a plain follow-up message."""
    if not isinstance(raw, AIMessage) or not raw.tool_calls:
        return [HumanMessage(text)]
    return [
        raw,
        *(ToolMessage(text, tool_call_id=call["id"] or "") for call in raw.tool_calls),
    ]
