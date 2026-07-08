"""Pydantic contract for the strict-JSON synthesis answer.

``CopilotAnswer`` is the single source of truth for the structured answer the
synthesis LLM must return: it validates parsed model output, generates the
JSON schema handed to guided decoding (``LLM_JSON_SCHEMA``), and serializes the
payload sent to the CLI/web card. The LLM is only trusted for the fields in
that schema; citation metadata beyond ``chunk_id`` is overwritten server-side
by ``answer_validation.verify_and_repair``.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

AnswerType = Literal["extractive", "synthesized", "clarification_needed"]

REVIEW_NOTICE = (
    "Insufficient grounded evidence — routed for mandatory manual review. "
    "See the retrieved passages and verify against the approved manuals."
)

# Strip a leading/trailing markdown code fence (``` or ```json), same pattern
# as extraction.py — prompt-mode models love wrapping JSON in fences.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class AnswerParseError(ValueError):
    """Raised when the raw LLM output is not valid JSON for the schema.

    The message is compact and model-feedable so the synthesis retry loop can
    hand it straight back to the LLM as a correction instruction.
    """


class ResponseBlock(BaseModel):
    """The answer body: summary, verbatim quote, and sensitivity flag."""

    primary_answer: str = ""
    exact_quote: str = ""
    is_sensitive: bool = False

    @field_validator("primary_answer", "exact_quote", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> object:
        return "" if v is None else v


class Citation(BaseModel):
    """One source citation. Only ``chunk_id`` is trusted from the LLM.

    ``source_id``/``source_name``/``source_path``/``page_number``/
    ``confidence_score`` are overwritten from retrieval metadata, and
    ``char_start``/``char_end`` (offsets of the verified quote *within the
    chunk text*) are set by quote verification. ``page_number`` stays ``None``
    until the corpus gains real page-bearing (PDF/OCR) ingestion.
    """

    chunk_id: str
    source_id: str = ""
    source_name: str = ""
    source_path: str = ""
    page_number: Optional[int] = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class DataCollectionRequirement(BaseModel):
    """Whether the user must supply more information, and which fields."""

    needs_user_input: bool = False
    missing_fields: list[str] = Field(default_factory=list)


class CopilotAnswer(BaseModel):
    """The full structured answer contract."""

    model_config = ConfigDict(extra="ignore")

    answer_type: AnswerType
    response: ResponseBlock
    citations: list[Citation] = Field(default_factory=list)
    related_suggestions: list[str] = Field(default_factory=list)
    data_collection_requirement: DataCollectionRequirement = Field(
        default_factory=DataCollectionRequirement
    )


# Schema handed to schema-guided decoding. Deliberately a hand-rolled SUBSET of
# CopilotAnswer: flat (no $defs/anyOf — small guided-decoding backends choke on
# them) and citations carry ONLY chunk_id, because every other citation field
# is overwritten server-side and asking the model to invent them invites
# hallucinated metadata.
LLM_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer_type": {
            "type": "string",
            "enum": ["extractive", "synthesized", "clarification_needed"],
        },
        "response": {
            "type": "object",
            "properties": {
                "primary_answer": {"type": "string"},
                "exact_quote": {"type": "string"},
                "is_sensitive": {"type": "boolean"},
            },
            "required": ["primary_answer", "exact_quote", "is_sensitive"],
        },
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}},
                "required": ["chunk_id"],
            },
        },
        "related_suggestions": {"type": "array", "items": {"type": "string"}},
        "data_collection_requirement": {
            "type": "object",
            "properties": {
                "needs_user_input": {"type": "boolean"},
                "missing_fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["needs_user_input", "missing_fields"],
        },
    },
    "required": [
        "answer_type",
        "response",
        "citations",
        "related_suggestions",
        "data_collection_requirement",
    ],
}


def parse_answer(raw: str) -> CopilotAnswer:
    """Parse and validate a raw LLM response into a :class:`CopilotAnswer`.

    Args:
        raw: The raw response text (may be wrapped in ```json fences).

    Returns:
        The validated answer model.

    Raises:
        AnswerParseError: If the text is not JSON or fails schema validation;
            the message summarizes the first few issues for retry feedback.
    """
    cleaned = _FENCE_RE.sub("", raw or "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AnswerParseError(f"output is not valid JSON: {exc}") from exc
    try:
        return CopilotAnswer.model_validate(data)
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()[:5]
        )
        raise AnswerParseError(f"JSON does not match the answer schema: {issues}") from exc


def clarification_fallback(
    reason: str, missing_fields: list[str] | None = None
) -> CopilotAnswer:
    """Build the deterministic ``clarification_needed`` answer.

    Used when retries are exhausted or the guardrail gate fires; never derived
    from LLM output, so it is always schema-valid.
    """
    return CopilotAnswer(
        answer_type="clarification_needed",
        response=ResponseBlock(
            primary_answer=f"{REVIEW_NOTICE} ({reason})", exact_quote="", is_sensitive=False
        ),
        citations=[],
        related_suggestions=[],
        data_collection_requirement=DataCollectionRequirement(
            needs_user_input=True,
            missing_fields=missing_fields or ["clarified_question"],
        ),
    )
