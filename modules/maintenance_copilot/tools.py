"""Code-bearing skill-tool for maintenance_copilot.

Exposes the copilot's grounded RAG query as an in-process ToolSpec so the agent
can answer maintenance questions and — crucially — broadcast a STRUCTURED
`maintenance_answer` card (answer + citation chips + confidence + review gate) to
the web UI, instead of relaying raw stdout. All the intelligence (retrieval,
citation enforcement, confidence floor, advisory note) already lives in the
`scripts/` pipeline; this only composes it and shapes the payload.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# scripts/ is a flat, non-package dir; putting it on sys.path and importing
# copilot runs copilot's own sys.path.insert, which makes budget/guardrails/
# synthesis/index_store/audit resolvable as bare imports.
_SCRIPTS = Path(__file__).resolve().parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import answer_schema  # noqa: E402
import audit  # noqa: E402
import conn_errors  # noqa: E402
import copilot  # noqa: E402
import guardrails  # noqa: E402

from atria.core.skill_tools import SkillToolContext, ToolSpec  # noqa: E402

# Similarity bands for the UI confidence chip. Below the module's manual-review
# floor (or flagged for review) → red; comfortably grounded → green; between → amber.
_MEDIUM_FLOOR = 0.6


class ServiceUnavailableError(RuntimeError):
    """A copilot sidecar (retrieval or LLM) is unreachable."""

    def __init__(self, service: str) -> None:
        super().__init__(f"maintenance copilot service unavailable: {service}")
        self.service = service


_UNAVAILABLE_ANSWER = (
    "The maintenance copilot's {label} is currently unavailable ({service} sidecar "
    "unreachable), so this question cannot be answered with grounded citations "
    "right now. Please retry once the service is restored; an operator can run "
    "`python copilot.py health` to diagnose."
)

_SERVICE_LABELS = {"qdrant": "retrieval service", "llm": "synthesis model"}

# Appended to the tool result for the model only (run_loop concatenates
# `_llm_suffix`; it is not shown in the UI). The point: a dead sidecar must
# not turn into freelancing over the corpus files.
_UNAVAILABLE_SUFFIX = (
    "\n\n[SYSTEM: The maintenance copilot service is unavailable ({service}). "
    "Tell the user the copilot cannot answer right now and that the structured "
    "card above explains why. Do NOT read the manual files in sample_manuals, "
    "do NOT grep or cat them via bash, and do NOT answer the maintenance "
    "question from your own knowledge.]"
)


def _unavailable_payload(query: str, service: str) -> dict:
    """Build the structured service-unavailable card (still strict-schema JSON).

    Built directly (not via ``clarification_fallback``) because an outage does
    not need user input and must not carry the manual-review notice text.
    """
    label = _SERVICE_LABELS.get(service, "service")
    structured = answer_schema.CopilotAnswer(
        answer_type="clarification_needed",
        response=answer_schema.ResponseBlock(
            primary_answer=_UNAVAILABLE_ANSWER.format(label=label, service=service),
            exact_quote="",
            is_sensitive=False,
        ),
        citations=[],
        related_suggestions=[],
        data_collection_requirement=answer_schema.DataCollectionRequirement(
            needs_user_input=False, missing_fields=[]
        ),
    ).model_dump()
    result = {
        "query": query,
        "answer": structured["response"]["primary_answer"],
        "answer_type": "clarification_needed",
        "exact_quote": "",
        "is_sensitive": False,
        "related_suggestions": [],
        "data_collection_requirement": structured["data_collection_requirement"],
        "citations": [],
        "confidence": 0.0,
        "confidence_band": "low",
        "review_required": True,
        "advisory_note": guardrails.ADVISORY_NOTE,
        "validation_warnings": [f"service_unavailable:{service}"],
        "structured": structured,
    }
    try:
        audit.append_event({"type": "query", "query": query, "citations": [],
                            "needs_review": True, "answer_type": "clarification_needed",
                            "validation_warnings": result["validation_warnings"],
                            "attempts": 0, "json_mode": ""})
    except Exception:
        pass
    return result


def run_query(query: str, k: int = 5, ata: str | None = None, revision: str = "current") -> dict:
    """Run a grounded maintenance query and return the structured card payload.

    Composes ``IndexStore.query`` (embed → Qdrant search, revision-aware) with
    ``synthesize_answer`` (LLM + citation/confidence guardrails). Returns a dict
    ready to render as a maintenance-answer card.
    """
    rev = None if str(revision).lower() == "none" else revision
    try:
        store = copilot._build_store()
        hits = store.query(query, k=k, ata_chapter=ata, revision=rev)
    except Exception as exc:
        if conn_errors.is_connectivity(exc):
            raise ServiceUnavailableError("qdrant") from exc
        raise
    try:
        ans = copilot.synthesize_answer(query, hits)
    except Exception as exc:
        if conn_errors.is_connectivity(exc):
            raise ServiceUnavailableError("llm") from exc
        raise
    structured = ans["structured"]
    response = structured["response"]

    # Merge each verified citation with its hit's legacy chip fields. Citation
    # metadata (source_*/page/confidence/char anchors) is already server-set by
    # answer_validation; only display fields come from the hit here.
    by_id = {h.get("chunk_id"): h for h in hits}
    citations = []
    for cit in structured["citations"]:
        h = by_id.get(cit["chunk_id"], {})
        citations.append(
            {
                "chunk_id": cit["chunk_id"],
                "doc": h.get("doc_type", ""),
                "revision": h.get("revision", ""),
                "ata": h.get("ata_chapter", ""),
                "citation": h.get("citation", cit["chunk_id"]),
                "source_id": cit["source_id"],
                "source_name": cit["source_name"],
                "source_path": cit["source_path"],
                "page_number": cit["page_number"],
                "confidence_score": round(cit["confidence_score"], 3),
                "char_start": cit["char_start"],
                "char_end": cit["char_end"],
            }
        )

    confidence = float(ans.get("confidence", 0.0))
    review_required = structured["answer_type"] == "clarification_needed"
    floor = guardrails.default_min_confidence()
    if review_required or confidence < floor:
        band = "low"
    elif confidence < _MEDIUM_FLOOR:
        band = "medium"
    else:
        band = "high"

    result = {
        "query": query,
        "answer": response["primary_answer"],
        "answer_type": structured["answer_type"],
        "exact_quote": response["exact_quote"],
        "is_sensitive": response["is_sensitive"],
        "related_suggestions": structured["related_suggestions"],
        "data_collection_requirement": structured["data_collection_requirement"],
        "citations": citations,
        "confidence": round(confidence, 3),
        "confidence_band": band,
        "review_required": review_required,
        "advisory_note": ans.get("disclaimer", ""),
        "validation_warnings": ans.get("validation_warnings", []),
        "structured": structured,
    }

    # The CLI path audits every synthesized query; mirror that here so web/agent
    # queries are traceable too. Best-effort: auditing must never fail a query.
    try:
        audit.append_event({"type": "query", "query": query,
                            "citations": [c["chunk_id"] for c in citations],
                            "needs_review": review_required,
                            "answer_type": structured["answer_type"],
                            "validation_warnings": result["validation_warnings"],
                            "attempts": ans.get("attempts", 0),
                            "json_mode": ans.get("json_mode", "")})
    except Exception:
        pass

    return result


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    """Register the maintenance_copilot skill tools."""

    def _handle_query(**kwargs: Any) -> dict:
        text = (kwargs.get("query") or kwargs.get("text") or "").strip()
        if not text:
            return {"success": False, "error": "query is required"}
        llm_suffix: str | None = None
        try:
            result = run_query(
                text,
                int(kwargs.get("k", 5)),
                kwargs.get("ata"),
                kwargs.get("revision", "current"),
            )
        except ServiceUnavailableError as exc:
            # Fail closed but STRUCTURED: the frontend still gets a strict-JSON
            # card, and the model gets an explicit no-freelancing directive
            # instead of a bare error it might "fix" by reading the corpus.
            ctx.logger.warning("maintenance_copilot service unavailable: %s", exc)
            result = _unavailable_payload(text, exc.service)
            llm_suffix = _UNAVAILABLE_SUFFIX.format(service=exc.service)
        except Exception as exc:  # never crash the agent loop; surface as a tool error
            ctx.logger.warning("maintenance_copilot query failed: %s", exc)
            return {"success": False, "error": f"query failed: {exc}"}

        # Push the structured card to the web UI (no-op in TUI/CLI where the
        # broadcaster is unset). The event `type` routes it to the React card.
        if ctx.broadcaster:
            try:
                ctx.broadcaster({"type": "maintenance_answer", **result})
            except Exception as exc:  # broadcast is best-effort; the tool result still returns
                ctx.logger.warning("maintenance_answer broadcast failed: %s", exc)

        out: dict = {"success": True, "output": result}
        if llm_suffix:
            out["_llm_suffix"] = llm_suffix
        return out

    return [
        ToolSpec(
            name="maintenance_copilot_query",
            description=(
                "Answer an aircraft-maintenance question (AMM/MEL/CDL/TSM/defect/dispatch/ATA) "
                "with grounded RAG: returns a cited, confidence-scored answer and renders it as "
                "a maintenance-answer card in the UI. Advisory only — never a dispatch decision."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The maintenance question, in English."},
                    "k": {"type": "integer", "default": 5, "description": "How many passages to retrieve."},
                    "ata": {"type": "string", "description": "Optional ATA chapter filter, e.g. '32'."},
                    "revision": {
                        "type": "string",
                        "default": "current",
                        "description": "'current' (latest only), a specific revision, or 'none'.",
                    },
                },
                "required": ["query"],
            },
            handler=_handle_query,
        ),
    ]
