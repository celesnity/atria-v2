"""Deterministic post-validation of a structured answer against retrieval.

This is the no-trust layer between the LLM and the user: it proves the
``exact_quote`` is a literal substring of a retrieved chunk (re-anchoring it to
the original span so OCR artifacts are preserved by construction), drops
citations that do not resolve to a chunk actually sent to the model, and
overwrites all citation metadata from retrieval — the LLM only ever picks the
``chunk_id``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from answer_schema import CopilotAnswer  # type: ignore[import-not-found]


class QuoteNotFoundError(ValueError):
    """The exact_quote is not a substring of any provided chunk (retryable)."""


class CitationMismatchError(ValueError):
    """No cited chunk_id resolves to a chunk sent to the model (retryable)."""


# Patterns that force is_sensitive regardless of the LLM's own flag. Coarse by
# design: a false positive costs a badge, a false negative leaks silently.
_SENSITIVE_RE = re.compile(
    r"""
    \b\d{3}-\d{2}-\d{4}\b                       # US SSN
    | \b(?:\d[ -]?){13,16}\b                    # card/account number runs
    | [\w.+-]+@[\w-]+\.[\w.]+                   # email address
    | \b(?:passport|ssn|social\ security)\b
    | \b(?:salary|invoice|bank\ account|iban|payroll|credit\ limit)\b
    | \b(?:patient|diagnosis|medical\ record|prescription)\b
    | \b(?:litigation|settlement|nda|non-disclosure|liability\ clause)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def detect_sensitive(text: str) -> bool:
    """Regex backstop for PII/financial/medical/legal content."""
    return bool(_SENSITIVE_RE.search(text or ""))


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces, mapping back to original indexes.

    Returns the normalized string and, per normalized character, the index of
    the original character it came from (a whitespace run maps to its first
    character).
    """
    chars: list[str] = []
    idx_map: list[int] = []
    in_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if in_space:
                continue
            chars.append(" ")
            idx_map.append(i)
            in_space = True
        else:
            chars.append(ch)
            idx_map.append(i)
            in_space = False
    return "".join(chars), idx_map


def locate_quote(quote: str, chunk_text: str) -> tuple[int, int] | None:
    """Locate ``quote`` in ``chunk_text``, returning the ORIGINAL (start, end) span.

    Tries an exact substring match first, then a whitespace-normalized match
    that is mapped back to original character positions. Characters are never
    altered beyond whitespace runs — a quote with "corrected" OCR characters
    will NOT match, which is the point.
    """
    if not quote:
        return None
    pos = chunk_text.find(quote)
    if pos >= 0:
        return (pos, pos + len(quote))
    norm_text, idx_map = _normalize_with_map(chunk_text)
    norm_quote, _ = _normalize_with_map(quote)
    norm_quote = norm_quote.strip()
    if not norm_quote:
        return None
    npos = norm_text.find(norm_quote)
    if npos < 0:
        return None
    start = idx_map[npos]
    end = idx_map[npos + len(norm_quote) - 1] + 1
    return (start, end)


def verify_and_repair(
    answer: CopilotAnswer, fitted_hits: list[dict]
) -> tuple[CopilotAnswer, list[str]]:
    """Verify an answer against the chunks actually sent to the model.

    Args:
        answer: The parsed answer to verify (mutated copy is returned).
        fitted_hits: The budget-fitted hits used to build the prompt.

    Returns:
        ``(repaired_answer, warnings)``. Warnings use stable machine-readable
        prefixes: ``citation_dropped:<id>``, ``quote_repaired``.

    Raises:
        CitationMismatchError: A non-clarification answer cites no valid chunk.
        QuoteNotFoundError: The quote is not a substring of any provided chunk.
    """
    warnings: list[str] = []
    answer = answer.model_copy(deep=True)
    by_id = {h["chunk_id"]: h for h in fitted_hits}

    kept = []
    for cit in answer.citations:
        if cit.chunk_id in by_id:
            kept.append(cit)
        else:
            warnings.append(f"citation_dropped:{cit.chunk_id}")
    answer.citations = kept

    if answer.answer_type == "clarification_needed":
        return answer, warnings

    if not kept:
        raise CitationMismatchError(
            "no citation matches a provided chunk_id — cite only the chunk_id "
            "values shown in the chunks"
        )

    quote = answer.response.exact_quote
    if quote:
        # Prefer the chunks the model itself cited, then any other prompt chunk.
        cited_ids = [c.chunk_id for c in kept]
        ordered_ids = cited_ids + [h["chunk_id"] for h in fitted_hits if h["chunk_id"] not in cited_ids]
        located: tuple[str, tuple[int, int]] | None = None
        for cid in ordered_ids:
            span = locate_quote(quote, by_id[cid]["text"])
            if span is not None:
                located = (cid, span)
                break
        if located is None:
            raise QuoteNotFoundError(
                "exact_quote is not a verbatim substring of any provided chunk — "
                "copy one continuous passage character-for-character, without "
                "fixing typos or OCR errors"
            )
        cid, (start, end) = located
        true_quote = by_id[cid]["text"][start:end]
        if true_quote != quote:
            warnings.append("quote_repaired")
        answer.response.exact_quote = true_quote
        for cit in kept:
            if cit.chunk_id == cid:
                cit.char_start, cit.char_end = start, end
                break

    # Metadata is never the LLM's to assert: overwrite from retrieval.
    for cit in kept:
        hit = by_id[cit.chunk_id]
        source_path = hit.get("source_path", "")
        cit.source_path = source_path
        cit.source_id = Path(source_path).stem if source_path else cit.chunk_id.split("#")[0]
        cit.source_name = Path(source_path).name if source_path else ""
        cit.page_number = hit.get("page_number")
        cit.confidence_score = max(0.0, min(1.0, float(hit.get("score", 0.0))))

    flagged = detect_sensitive(f"{answer.response.primary_answer} {answer.response.exact_quote}")
    answer.response.is_sensitive = answer.response.is_sensitive or flagged
    return answer, warnings
