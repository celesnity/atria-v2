"""Token-budgeting helpers so every LLM call fits a bounded context window.

The deployed chat model has a fixed context length that must hold *both* the
prompt and the reserved completion. These helpers keep each request inside it:
they cap the requested output tokens (so the server stops reserving a huge
default completion) and trim oversized input — retrieved passages for synthesis,
chunk text for extraction — to whatever the window leaves after that reservation
plus a safety margin.

Everything is env-tunable so the module adapts to whatever model is deployed:

- ``MC_MODEL_CTX`` — total context length (input + output). Default ``30000``.
- ``MC_<ROLE>_MAX_OUTPUT_TOKENS`` — reserved completion tokens for a role.
"""

from __future__ import annotations

import os

# Chars-per-token heuristic used to size input without a tokenizer dependency.
# English averages ~4 chars/token; 3.5 deliberately *over*-estimates tokens so a
# trimmed prompt stays safely under the hard limit rather than nudging past it.
_CHARS_PER_TOKEN = 3.5

# Fallback reserved-completion tokens per role when no env override is set.
_DEFAULT_OUTPUT_TOKENS = {"synthesis": 1024, "kg_extract": 1536}
_DEFAULT_OUTPUT_FALLBACK = 1024

# Tokens held back from the input budget for chat scaffolding (role tags,
# message framing) the char heuristic does not otherwise account for.
_SAFETY_MARGIN = 512


def _int_env(key: str, default: int) -> int:
    """Read a positive int from the environment, falling back on bad/absent values."""
    try:
        value = int(os.environ[key])
    except (KeyError, TypeError, ValueError):
        return default
    return value if value > 0 else default


def model_context_limit() -> int:
    """Max total tokens (prompt + completion) the chat model accepts."""
    return _int_env("MC_MODEL_CTX", 30000)


def output_tokens(role: str) -> int:
    """Reserved completion tokens for *role* (``MC_<ROLE>_MAX_OUTPUT_TOKENS``)."""
    default = _DEFAULT_OUTPUT_TOKENS.get(role, _DEFAULT_OUTPUT_FALLBACK)
    return _int_env(f"MC_{role.upper()}_MAX_OUTPUT_TOKENS", default)


def estimate_tokens(text: str) -> int:
    """Rough upper-bound token estimate for *text* (no tokenizer dependency)."""
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def input_budget(role: str, margin: int = _SAFETY_MARGIN) -> int:
    """Tokens left for the prompt after the output reservation + safety margin."""
    return max(0, model_context_limit() - output_tokens(role) - margin)


def fit_text(text: str, max_tokens: int) -> str:
    """Truncate *text* so its estimated token count does not exceed *max_tokens*."""
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text
    limit_chars = int(max_tokens * _CHARS_PER_TOKEN)
    return text[:limit_chars].rstrip() + " …[truncated to fit context]"
