# D9 — Provider-agnostic model factory

**Status:** accepted

**Decision.** `app/ai/factory.py` builds every chat model with LangChain `init_chat_model`, driven
by `AI_PROVIDER` and tiered model names (`AI_FAST`, `AI_MEDIUM`, `AI_SUPER`, `AI_REASONING`,
falling back to `AI_MODEL`). An optional second-opinion provider lets a different model family
re-judge borderline verdicts. Provider packages are imported lazily.
