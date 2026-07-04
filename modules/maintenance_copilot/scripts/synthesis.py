"""Compose a strict-JSON, quote-verified answer grounded ONLY in retrieved chunks.

The LLM must return the ``answer_schema.CopilotAnswer`` contract (enforced by
server-side guided decoding where the provider supports it, with JSON-object
and prompt-instruction fallbacks). The output is then deterministically
verified: the ``exact_quote`` must be a literal substring of a provided chunk
(re-anchored to the original span so the model can never silently "fix" OCR
artifacts), hallucinated citations are dropped, and citation metadata is
overwritten from retrieval. Validation failures are fed back to the model for
a bounded number of retries, then degrade to a deterministic
``clarification_needed`` answer. The confidence floor still routes weak
retrievals to mandatory manual review.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import answer_schema  # type: ignore[import-not-found]
import answer_validation  # type: ignore[import-not-found]
import budget  # type: ignore[import-not-found]
import config  # type: ignore[import-not-found]
from guardrails import (  # type: ignore[import-not-found]
    ADVISORY_NOTE,
    answer_confidence,
    needs_manual_review,
)

# Kept as an alias: the notice now lives beside the fallback builder it feeds.
_REVIEW_NOTICE = answer_schema.REVIEW_NOTICE

_SYSTEM_PROMPT = (
    "You are an exact-extraction data assistant for a secure enterprise "
    "aircraft-maintenance system. Answer the user's question STRICTLY using "
    "the provided document chunks. Do not use outside knowledge. Never state "
    "a dispatch decision.\n"
    "Rules:\n"
    "1. NO HALLUCINATION: if the chunks do not answer the question, set "
    'answer_type to "clarification_needed", make primary_answer a short '
    'explanation of what is missing, set exact_quote to "" and citations to '
    "[], set data_collection_requirement.needs_user_input to true and list "
    "the missing information in missing_fields.\n"
    "2. VERBATIM EXTRACTION: exact_quote MUST be one literal, continuous "
    "substring copied character-for-character from the text of exactly one "
    "chunk. Do not alter casing or punctuation, and do not correct typos or "
    "OCR errors in the source text.\n"
    "3. CITATION MAPPING: every citations[].chunk_id must be copied exactly "
    "from the chunk_id line of a chunk you actually used.\n"
    '4. ANSWER TYPE: use "extractive" when the quote itself directly answers '
    'the question, "synthesized" when you combine or summarize chunks.\n'
    "5. SENSITIVITY: set is_sensitive to true if the query or answer involves "
    "PII, financial figures or limits, medical data, or legal clauses.\n"
    "6. Offer up to 3 short follow-up questions in related_suggestions.\n"
    "7. Output ONLY one valid JSON object matching exactly this schema — no "
    "prose, no code fences: "
    '{"answer_type": "extractive" | "synthesized" | "clarification_needed", '
    '"response": {"primary_answer": string, "exact_quote": string, '
    '"is_sensitive": boolean}, "citations": [{"chunk_id": string}], '
    '"related_suggestions": [string], '
    '"data_collection_requirement": {"needs_user_input": boolean, '
    '"missing_fields": [string]}}'
)

# Downgrade ladder when a provider rejects the requested response_format.
_MODE_LADDER = ("schema", "json_object", "prompt")

_CORRECTION_TEMPLATE = (
    "Your previous output failed validation: {error}. "
    "Return ONLY the corrected JSON object, nothing else."
)


def _chunk_block(hit: dict) -> str:
    """Render one retrieved chunk with the metadata the model must copy exactly."""
    return (
        "<chunk>\n"
        f"chunk_id: {hit['chunk_id']}\n"
        f"source_id: {hit.get('source_id', '')}\n"
        f"source_name: {hit.get('source_name', '')}\n"
        f"text:\n{hit['text']}\n"
        "</chunk>"
    )


def fit_hits_to_budget(query: str, hits: list[dict]) -> list[dict]:
    """Return the leading hits whose chunk blocks fit the synthesis input budget.

    Chunks are kept in ranked order until the estimated prompt size would
    exceed the model's input budget (context minus reserved output). At least
    the top hit is always kept — if it alone overruns the budget its text is
    truncated — so a grounded answer is still attempted rather than dropped.
    """
    available = budget.input_budget("synthesis")
    overhead = (
        budget.estimate_tokens(_SYSTEM_PROMPT)
        + budget.estimate_tokens(query)
        + 16  # "Question:"/"Chunks:" framing
    )
    remaining = max(0, available - overhead)
    fitted: list[dict] = []
    used = 0
    for hit in hits:
        block_cost = budget.estimate_tokens(_chunk_block(hit))
        if used + block_cost <= remaining:
            fitted.append(hit)
            used += block_cost
        elif not fitted:
            # Top hit alone overruns: truncate its text so we still answer.
            frame_cost = budget.estimate_tokens(_chunk_block({**hit, "text": ""}))
            budget_for_text = max(0, remaining - frame_cost)
            fitted.append({**hit, "text": budget.fit_text(hit["text"], budget_for_text)})
            break
        else:
            break
    return fitted


def build_synthesis_messages(query: str, hits: list[dict]) -> list[dict]:
    """Build chat messages carrying per-chunk metadata blocks.

    Chunks are trimmed to :func:`fit_hits_to_budget` so the prompt plus the
    reserved completion stay within the deployed model's context window.
    """
    blocks = "\n".join(_chunk_block(h) for h in hits)
    user = f"Question: {query}\n\nChunks:\n{blocks}"
    return [{"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user}]


def _response_format_for(mode: str) -> dict | None:
    """Map a JSON mode to the OpenAI-style ``response_format`` argument."""
    if mode == "schema":
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "copilot_answer",
                "strict": True,
                "schema": answer_schema.LLM_JSON_SCHEMA,
            },
        }
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def _call_with_downgrade(
    chat_fn: Callable[..., str], messages: list[dict], mode: str, warnings: list[str]
) -> tuple[str, str]:
    """Invoke the LLM, degrading schema → json_object → prompt on provider errors.

    Prompt mode calls ``chat_fn`` without ``response_format`` so bare
    callables (tests, providers without JSON support) keep working; a failure
    there is a genuine provider error and propagates.
    """
    while True:
        response_format = _response_format_for(mode)
        try:
            if response_format is None:
                return chat_fn(messages), mode
            return chat_fn(messages, response_format=response_format), mode
        except Exception:
            idx = _MODE_LADDER.index(mode)
            if idx + 1 >= len(_MODE_LADDER):
                raise
            mode = _MODE_LADDER[idx + 1]
            warnings.append(f"json_mode_downgraded:{mode}")


def synthesize(
    query: str,
    hits: list[dict],
    chat_fn: Callable[..., str],
    max_retries: int = 2,
) -> dict:
    """Produce a schema-validated, quote-verified answer over ``hits``.

    Args:
        query: The user question.
        hits: Retrieved chunks (each with ``chunk_id``, ``text``, ``score``
            and source metadata from ``IndexStore.query``).
        chat_fn: Callable ``(messages, **kw) -> str``; receives
            ``response_format=`` in schema/json_object modes.
        max_retries: Validation-feedback retries after the first attempt.

    Returns:
        ``{"structured": <CopilotAnswer dump>, "answer", "answer_type",
        "confidence", "needs_review", "disclaimer", "citations",
        "validation_warnings", "attempts", "json_mode"}``.
    """
    fitted = fit_hits_to_budget(query, hits)
    base_messages = build_synthesis_messages(query, fitted)
    mode = config.synthesis_json_mode()
    warnings: list[str] = []
    answer: answer_schema.CopilotAnswer | None = None
    messages = list(base_messages)
    attempts = 0
    last_error = ""

    for _ in range(1 + max_retries):
        attempts += 1
        raw, mode = _call_with_downgrade(chat_fn, messages, mode, warnings)
        try:
            parsed = answer_schema.parse_answer(raw)
            answer, check_warnings = answer_validation.verify_and_repair(parsed, fitted)
            warnings.extend(check_warnings)
            break
        except (
            answer_schema.AnswerParseError,
            answer_validation.QuoteNotFoundError,
            answer_validation.CitationMismatchError,
        ) as exc:
            last_error = str(exc)
            correction = {
                "role": "user",
                "content": _CORRECTION_TEMPLATE.format(error=last_error),
            }
            retry = messages + [{"role": "assistant", "content": raw}, correction]
            # A growing transcript must still fit the input budget; if it will
            # not, restart from the base prompt plus the latest correction.
            estimated = sum(budget.estimate_tokens(m["content"]) for m in retry)
            if estimated > budget.input_budget("synthesis"):
                retry = base_messages + [correction]
            messages = retry

    if answer is None:
        warnings.append(f"fallback:validation_failed:{last_error[:160]}")
        answer = answer_schema.clarification_fallback(
            "the model could not produce a schema-valid, quote-verified answer"
        )

    # Guardrail gate, enforced in code exactly as before: weak retrieval or an
    # answer grounded in nothing is never presented as settled.
    confidence = answer_confidence(hits)
    if (
        needs_manual_review(confidence, len(answer.citations))
        and answer.answer_type != "clarification_needed"
    ):
        answer.answer_type = "clarification_needed"
        answer.response.primary_answer = (
            f"{answer_schema.REVIEW_NOTICE} {answer.response.primary_answer}".strip()
        )
        answer.data_collection_requirement.needs_user_input = True
        # Citations are retained so the reviewing engineer sees the evidence.

    needs_review = answer.answer_type == "clarification_needed"
    return {
        "structured": answer.model_dump(),
        "answer": answer.response.primary_answer,
        "answer_type": answer.answer_type,
        "confidence": confidence,
        "needs_review": needs_review,
        "disclaimer": ADVISORY_NOTE,
        "citations": sorted(c.chunk_id for c in answer.citations),
        "validation_warnings": warnings,
        "attempts": attempts,
        "json_mode": mode,
    }
