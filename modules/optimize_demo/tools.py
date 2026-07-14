"""Atria skill for the Optimize console.

Declared via ``tools: tools.py`` in ``SKILL.md``. ``register(ctx)`` returns agent tools that read
the **live 20-machine fleet simulator** (the same IIOT fleet API the dashboard uses) and produce
Measure/Explain/Predict/Evaluate/Recommend analysis + a best-fit chart recommendation. The tools
reuse Atria's configured model (gpt-5.4-mini) through ``ctx.llm_chat(system, user)`` and fall back
to deterministic analysis when the LLM or the simulator is unavailable — so they degrade cleanly.

This is the agent-facing twin of the dashboard's ``scripts/ai.py``; both share ``scripts/analysis.py``
(the numbers always come from the live simulator, never invented).
"""

from __future__ import annotations

import os
import sys

# The shared analysis core + the live fleet client live under scripts/.
_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import analysis  # noqa: E402
import simulate  # noqa: E402

try:  # atria is present in the app runtime; guard so the file is importable standalone (tests)
    from atria.core.skill_tools import ToolSpec  # type: ignore
except Exception:  # pragma: no cover - standalone/import-without-atria
    ToolSpec = None  # type: ignore[assignment,misc]

_UNREACHABLE = (
    "Fleet simulator not reachable at {url}. Start the IIOT fleet server "
    "(scripts/run_fleet_server.py, :5050) in the [Project]_IOTMock repo, then retry."
)


def _live(args: dict) -> dict:
    url = (args or {}).get("fleet_url")
    return simulate.handle_status({"url": url} if url else {})


def _llm(ctx, system: str, user: str) -> str:
    fn = getattr(ctx, "llm_chat", None) if ctx is not None else None
    if not fn:
        raise RuntimeError("no ctx.llm_chat")
    return fn(system, user)


def _ask_handler(ctx):
    def handler(args: dict) -> dict:
        question = str((args or {}).get("question") or "").strip()
        if not question:
            return {"success": False, "output": "Provide a question about a machine or the fleet."}
        st = _live(args)
        if not st.get("connected"):
            return {"success": False, "output": _UNREACHABLE.format(url=st.get("source", ""))}
        machines, scn = st.get("machines", []), st.get("scn")
        try:
            system, user = analysis.build_ask_messages(question, machines, scn)
            out = analysis.normalize_ask(
                analysis.parse_json(_llm(ctx, system, user)), machines, scn
            )
            src = os.environ.get("ATRIA_MODEL") or "gpt-5.4-mini"
        except Exception:  # noqa: BLE001 - degrade to deterministic
            out = analysis.deterministic_ask(question, machines, scn)
            src = "deterministic"
        text = out["answer"]
        if out.get("charts"):
            c = out["charts"][0]
            it = analysis.INTENT_BY_ID.get(c["intent"], {})
            text += (
                f"\n\nSuggested chart: {it.get('label')} ({it.get('chart')}) for {c['machine']}."
            )
        return {
            "success": True,
            "output": f"{text}\n\n[live fleet · {st.get('plant', '')} · source: {src}]",
        }

    return handler


def _analyze_handler(ctx):
    def handler(args: dict) -> dict:
        st = _live(args)
        if not st.get("connected"):
            return {"success": False, "output": _UNREACHABLE.format(url=st.get("source", ""))}
        machines, scn = st.get("machines", []), st.get("scn")
        try:
            system, user = analysis.build_analyze_messages(machines, scn)
            out = analysis.normalize_analyze(
                analysis.parse_json(_llm(ctx, system, user)), machines, scn
            )
            src = os.environ.get("ATRIA_MODEL") or "gpt-5.4-mini"
        except Exception:  # noqa: BLE001
            out = analysis.deterministic_analyze(machines, scn)
            src = "deterministic"
        stages = ["Measure", "Explain", "Predict", "Evaluate", "Recommend"]
        body = "\n".join(f"{s}: {out[s.lower()]}" for s in stages)
        target = (scn or {}).get("targetMachine", "?")
        return {
            "success": True,
            "output": f"Production-recovery analysis for {target}:\n{body}\n\n[source: {src}]",
        }

    return handler


def register(ctx=None):
    """Return the Optimize skill's agent tools (empty if atria's ToolSpec is unavailable)."""
    if ToolSpec is None:
        return []
    return [
        ToolSpec(
            name="optimize_ask",
            description=(
                "Ask the live manufacturing fleet simulator about a machine or the fleet "
                "(status, comparisons, why a machine is degrading). Reads real telemetry "
                "from the Optimize fleet API and answers with a best-fit chart suggestion."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural-language question about a machine or the fleet.",
                    },
                    "fleet_url": {
                        "type": "string",
                        "description": "Optional fleet API base URL (default http://127.0.0.1:5050).",
                    },
                },
                "required": ["question"],
            },
            handler=_ask_handler(ctx),
        ),
        ToolSpec(
            name="optimize_analyze_fleet",
            description=(
                "Run the Measure/Explain/Predict/Evaluate/Recommend decision loop over the "
                "live fleet simulator and return a production-recovery narrative grounded "
                "in real telemetry."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "fleet_url": {
                        "type": "string",
                        "description": "Optional fleet API base URL (default http://127.0.0.1:5050).",
                    },
                },
            },
            handler=_analyze_handler(ctx),
        ),
    ]
