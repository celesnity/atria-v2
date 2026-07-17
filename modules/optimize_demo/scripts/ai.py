"""ai.py — the Optimize console's AI backend (gpt-5.4-mini), called via the AtriaDash bridge.

Contract (same as optimize.py / simulate.py): ``python scripts/ai.py <command>`` with a JSON
payload on **stdin** and one JSON object printed to **stdout**. It ALWAYS exits 0 and prints
valid JSON — on a missing key, a network error, or a bad model reply it falls back to the
deterministic analysis in ``analysis.py`` (so the bridge, which throws on non-zero exit, always
resolves and the demo never hard-fails).

Commands:
    ask      stdin = {question, machines, scn, lang?}  -> {ok, answer, table, charts, follow_ups, source}
    analyze  stdin = {machines, scn | execution_id, lang?} -> whole-loop orchestrator (flat + per-stage)
    measure|explain|predict|evaluate|recommend|replan
             stdin = {execution_id? | machines+scn, lang?, ...} -> one stage's standard response object

The per-stage commands run the same 6-stage pipeline the agent skills use (``pipeline.py``); pass an
``execution_id`` (returned by an earlier stage) so every stage reads ONE shared live snapshot.

The model reuses Minder's env config: ``OPENAI_API_KEY``, ``MINDER_MODEL`` (default gpt-5.4-mini),
``MINDER_API_BASE_URL`` (an OpenAI-compatible /chat/completions endpoint). The pre-rebrand
``ATRIA_*`` names still work as a deprecated fallback. Numbers are never invented — the pipeline
passes the live telemetry it already has, the model only writes prose and picks the machine + chart
intent, and the dashboard draws the chart from the live data.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

try:  # allow both `python scripts/ai.py` and `python -m ...`
    from . import analysis, pipeline, simulate, store
except ImportError:  # pragma: no cover - direct-invocation path
    import analysis  # type: ignore[no-redef]
    import pipeline  # type: ignore[no-redef]
    import simulate  # type: ignore[no-redef]
    import store  # type: ignore[no-redef]

DEFAULT_BASE = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-mini"


def env_setting(name: str, default: str | None = None) -> str | None:
    """Read a MINDER_* setting, falling back to the pre-rebrand ATRIA_* name.

    The rebrand renamed the setters but missed these readers, so ``ATRIA_MODEL`` was still being
    consulted while ``.env`` shipped ``MINDER_MODEL`` -- masked only because the defaults happened
    to match. Prefer MINDER_*, keep ATRIA_* working for anyone with an old environment.
    """
    return os.environ.get("MINDER_" + name) or os.environ.get("ATRIA_" + name) or default


def model_name() -> str:
    return env_setting("MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def _api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("IIOT_AI_API_KEY") or None


def llm_chat(system: str, user: str, max_tokens: int = 900, timeout: float = 55.0) -> str:
    """One OpenAI-compatible chat call via stdlib urllib. Raises on any failure."""
    key = _api_key()
    if not key:
        raise RuntimeError("no API key (OPENAI_API_KEY)")
    base = env_setting("API_BASE_URL", DEFAULT_BASE)
    model = model_name()
    # gpt-5 / o-series family: use max_completion_tokens and DO NOT send a custom temperature.
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_completion_tokens": max_tokens,
    }
    req = urllib.request.Request(
        base,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _make_llm():
    """A (system, user) -> str callable when a key is configured, else None (deterministic path)."""
    if not _api_key():
        return None

    def _call(system: str, user: str) -> str:
        return llm_chat(system, user, max_tokens=500)

    return _call


def _snapshot_from(payload: dict) -> tuple[str, dict]:
    """Resolve one coherent snapshot: prior execution_id -> inline machines+scn -> live fleet fetch."""
    eid = payload.get("execution_id")
    fleet_url = payload.get("fleet_url") or payload.get("url")
    if eid:
        snap = store.get_snapshot(eid)
        if snap:
            return eid, snap
    if payload.get("machines") is not None and payload.get("scn") is not None:
        snap = {
            "ok": True,
            "connected": True,
            "machines": payload.get("machines"),
            "scn": payload.get("scn"),
            "plant": payload.get("plant"),
            "ts": payload.get("ts"),
            "history": payload.get("history"),
            "trends": payload.get("trends"),
        }
        eid2 = eid or pipeline.mint_execution_id(snap)
        try:
            store.save_snapshot(eid2, snap)
        except OSError:
            pass
        return eid2, snap
    eid3, snap, _fresh = pipeline.resolve_run(eid, fleet_url)
    return eid3, snap


def cmd_ask(payload: dict) -> dict:
    question = str(payload.get("question") or "").strip()
    machines = payload.get("machines") or []
    scn = payload.get("scn")
    lang = payload.get("lang") or "en"
    if not question:
        return {
            "ok": True,
            "answer": 'Ask about a machine (e.g. "why is M-02 degrading?") or the ' "fleet.",
            "table": None,
            "charts": [],
            "follow_ups": [],
            "source": "none",
        }
    try:
        system, user = analysis.build_ask_messages(question, machines, scn, lang=lang)
        obj = analysis.parse_json(llm_chat(system, user))
        out = analysis.normalize_ask(obj, machines, scn)
        out["source"] = model_name()
    except Exception as exc:  # noqa: BLE001 - always degrade gracefully to a valid JSON reply
        out = analysis.deterministic_ask(question, machines, scn)
        out["source"] = "fallback"
        out["note"] = "{}: {}".format(type(exc).__name__, exc)[:160]
    out["ok"] = True
    return out


def cmd_analyze(payload: dict) -> dict:
    """Whole-loop orchestrator: Measure -> ... -> Recommend over one snapshot (flat + per-stage keys)."""
    eid, snap = _snapshot_from(payload)
    lang = payload.get("lang") or "en"
    return pipeline.run_pipeline(snap, execution_id=eid, lang=lang, llm=_make_llm())


def cmd_stage(skill: str, payload: dict) -> dict:
    """Run one pipeline stage and return its standard response object."""
    eid, snap = _snapshot_from(payload)
    lang = payload.get("lang") or "en"
    kw: dict = {}
    if skill == "replan_and_dispatch_operations":
        kw["recommendation_id"] = payload.get("recommendation_id")
        kw["fleet_url"] = payload.get("fleet_url") or payload.get("url")
    return pipeline.run_stage(skill, snap, execution_id=eid, lang=lang, llm=_make_llm(), **kw)


# Short dashboard aliases -> full skill names.
_STAGE_ALIAS = {
    "measure": "measure_operational_performance",
    "explain": "explain_performance_loss",
    "predict": "predict_operational_risk",
    "evaluate": "evaluate_operational_alternatives",
    "recommend": "recommend_operational_action",
    "replan": "replan_and_dispatch_operations",
}


def handle(cmd: str, payload: dict) -> dict:
    if cmd == "ask":
        return cmd_ask(payload)
    if cmd == "analyze":
        return cmd_analyze(payload)
    skill = _STAGE_ALIAS.get(cmd, cmd)
    if skill in pipeline.STAGE_BY_SKILL:
        return cmd_stage(skill, payload)
    return {
        "ok": False,
        "error": "unknown command: %r (want ask|analyze|measure|explain|predict|evaluate|recommend|replan)"
        % cmd,
    }


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    out = handle(cmd, payload)
    sys.stdout.write(json.dumps(out))
    # Always exit 0 so the AtriaDash bridge resolves; errors are carried inside the JSON.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
