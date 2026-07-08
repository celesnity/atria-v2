"""Agent-level bench harness: drive the real Atria ReAct loop with a real LLM.

Mirrors the production execution paths:
- Stack construction follows atria/core/agents/deps_builder.py (headless worker)
  and atria/web/agent_executor.py (system-prompt assembly, executor wiring).
- DB access follows the web-server pattern: a dedicated asyncio loop runs in a
  background thread and is registered via atria.db.sync.set_main_loop, so the
  sync ReactExecutor's run_sync() calls schedule onto one long-lived loop that
  owns the SQLAlchemy AsyncEngine.

Run cases sequentially in one process. Per-case identity is injected via the
ATRIA_SEARCH_USER_ID env var (the knowledge_search tool reads it at call time;
sequential execution makes the documented single-user limitation safe here).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
# Workaround: the venv's .pth files carry the macOS hidden flag, so `atria`
# is not importable from directly-run scripts without this.
sys.path.insert(0, str(REPO_ROOT))


def load_env(env_path: Path | None = None) -> None:
    """Load KEY=VAL lines from .env without overriding already-set vars.

    Rewrites a docker-internal DATABASE_URL (host `db`) to the native
    localhost:5433 Postgres, matching the documented native-run recipe.
    Resolves ${VAR} references against what is already loaded.
    """
    env_path = env_path or (REPO_ROOT / ".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                val = re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), val)
                os.environ[key] = val
    db_url = os.environ.get("DATABASE_URL", "")
    if "@db:" in db_url:
        os.environ["DATABASE_URL"] = "postgresql://atria:atria@localhost:5433/atria"


class RecorderCallback:
    """ui_callback duck-type that records tool calls and assistant messages."""

    RESULT_CAP = 30_000

    def __init__(self) -> None:
        self.tool_calls: list[dict[str, Any]] = []
        self.assistant_messages: list[str] = []

    def on_tool_call(self, tool_name: str, args_str: str) -> None:
        self.tool_calls.append({"tool": tool_name, "args": args_str, "result": None})

    def on_tool_result(self, tool_name: str, args_str: str, result: Any) -> None:
        text = str(result)
        if len(text) > self.RESULT_CAP:
            text = text[: self.RESULT_CAP] + f"...[truncated {len(text)} chars total]"
        for call in reversed(self.tool_calls):
            if call["tool"] == tool_name and call["result"] is None:
                call["result"] = text
                return
        self.tool_calls.append({"tool": tool_name, "args": args_str, "result": text})

    def on_assistant_message(self, content: str, *args: Any, **kwargs: Any) -> None:
        if content:
            self.assistant_messages.append(str(content))


class BenchHarness:
    """Builds the real agent stack once; runs one fresh session per case."""

    def __init__(self, working_dir: Path | None = None) -> None:
        self.working_dir = working_dir or REPO_ROOT
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._suite = None
        self._agent = None
        self._session_manager = None
        self._mode_manager = None
        self._config = None
        self._system_content: Optional[str] = None

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._start_background_loop()
        self._build_stack()

    def shutdown(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=10)
            self._loop = None
            self._loop_thread = None

    def _start_background_loop(self) -> None:
        from atria.db.sync import set_main_loop

        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_run, name="bench-db-loop", daemon=True)
        thread.start()
        set_main_loop(loop)
        self._loop = loop
        self._loop_thread = thread

    def _build_stack(self) -> None:
        from atria.core.runtime.config import ConfigManager
        from atria.core.runtime import ModeManager
        from atria.core.runtime.services.runtime_service import RuntimeService
        from atria.core.context_engineering.tools.implementations.file_ops import (
            FileOperations,
        )
        from atria.core.context_engineering.tools.implementations.write_tool import (
            WriteTool,
        )
        from atria.core.context_engineering.tools.implementations.edit_tool.tool import (
            EditTool,
        )
        from atria.core.context_engineering.tools.implementations.bash_tool.tool import (
            BashTool,
        )
        from atria.core.context_engineering.tools.implementations.notebook_edit_tool import (
            NotebookEditTool,
        )
        from atria.core.context_engineering.history.session_manager import (
            PgSessionManager,
        )

        wd = self.working_dir
        config_manager = ConfigManager(working_dir=wd)
        config = config_manager.get_config()
        mode_manager = ModeManager()

        runtime_service = RuntimeService(config_manager, mode_manager)
        suite = runtime_service.build_suite(
            file_ops=FileOperations(config, wd),
            write_tool=WriteTool(config, wd),
            edit_tool=EditTool(config, wd),
            bash_tool=BashTool(config, wd),
            notebook_edit_tool=NotebookEditTool(wd),
            ask_user_tool=None,  # headless: no interactive ask-user channel
            mcp_manager=None,
        )

        agent = getattr(suite.agents, "assistant", None) or suite.agents.normal

        # System prompt assembly mirrors agent_executor.py: base prompt plus the
        # file-based module SKILL block (this is what carries knowledge_search's
        # usage guidance to the LLM). The assistant agent's prompt already embeds
        # the module SKILL block natively, so guard against double-appending it.
        system_content = agent.system_prompt
        try:
            from atria.core.modules.prompt import build_skill_block
            from atria.core.modules.registry import get_registry

            modules_block = build_skill_block(get_registry())
        except Exception:
            modules_block = ""
        if modules_block and modules_block not in system_content:
            system_content += "\n\n" + modules_block

        self._suite = suite
        self._agent = agent
        self._config = config
        self._mode_manager = mode_manager
        self._session_manager = PgSessionManager(working_directory=str(wd))
        self._system_content = system_content

    # -- execution -----------------------------------------------------------

    def run_case(
        self,
        final_user_turn: str,
        seeded_turns: list[dict[str, str]] | None = None,
        search_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Run one conversation turn through the real ReAct loop.

        Args:
            final_user_turn: The user message the agent must answer.
            seeded_turns: Prior scripted turns, e.g. [{"role": "user", ...},
                {"role": "assistant", ...}], inserted as history.
            search_user_id: Identity for knowledge_search ACL (env-injected).

        Returns:
            Dict with final_answer, tool_calls, assistant_messages, error,
            latency_ms, session_id.
        """
        from atria.db.sync import run_sync
        from atria.repl.react_executor import ReactExecutor
        from atria.core.runtime.approval.manager import ApprovalManager
        from atria.core.context_engineering.history.undo_manager import UndoManager
        from atria.core.runtime.cost_tracker import CostTracker

        if search_user_id is not None:
            os.environ["ATRIA_SEARCH_USER_ID"] = search_user_id
        else:
            os.environ.pop("ATRIA_SEARCH_USER_ID", None)

        session = run_sync(
            self._session_manager.create_session(
                working_directory=str(self.working_dir), channel="cli"
            )
        )
        self._session_manager.current_session = session

        messages: list[dict[str, str]] = [{"role": "system", "content": self._system_content}]
        for turn in seeded_turns or []:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": final_user_turn})

        approval_manager = ApprovalManager()
        approval_manager.auto_approve_remaining = True

        recorder = RecorderCallback()
        executor = ReactExecutor(
            session_manager=self._session_manager,
            config=self._config,
            mode_manager=self._mode_manager,
            console=None,
            llm_caller=None,
            tool_executor=None,
            cost_tracker=CostTracker(),
        )

        start = time.monotonic()
        try:
            summary, error, latency_ms = executor.execute(
                query=final_user_turn,
                messages=messages,
                agent=self._agent,
                tool_registry=self._suite.tool_registry,
                approval_manager=approval_manager,
                undo_manager=UndoManager(),
                ui_callback=recorder,
            )
        except Exception as exc:  # keep the batch alive; record the failure
            summary, error, latency_ms = (
                None,
                f"{type(exc).__name__}: {exc}",
                int((time.monotonic() - start) * 1000),
            )

        # execute()'s summary is only the last tool-call display string; the real
        # final text arrives via on_assistant_message.
        final_answer = (
            recorder.assistant_messages[-1] if recorder.assistant_messages else summary
        ) or ""
        return {
            "final_answer": final_answer,
            "assistant_messages": recorder.assistant_messages,
            "tool_calls": recorder.tool_calls,
            "error": error,
            "latency_ms": latency_ms,
            "session_id": getattr(session, "id", None),
        }


# -- process-pool batch execution ---------------------------------------------
#
# Identity is injected via the process-global ATRIA_SEARCH_USER_ID env var, so
# concurrency must be across PROCESSES: each worker owns one stack and runs one
# case at a time, which keeps the per-case identity write race-free.

_WORKER_HARNESS: Optional[BenchHarness] = None


def _pool_worker_init() -> None:
    global _WORKER_HARNESS
    load_env()
    _WORKER_HARNESS = BenchHarness()
    _WORKER_HARNESS.start()


def _pool_run_case(payload: dict[str, Any]) -> dict[str, Any]:
    start = time.monotonic()
    result = _WORKER_HARNESS.run_case(
        payload["final_user_turn"],
        seeded_turns=payload.get("seeded_turns"),
        search_user_id=payload.get("search_user_id"),
    )
    return {
        **payload.get("meta", {}),
        **result,
        "wall_ms": int((time.monotonic() - start) * 1000),
    }


def run_batch(
    payloads: list[dict[str, Any]],
    out_path: Path,
    id_key: str,
    workers: int = 6,
) -> None:
    """Run payloads through a worker-process pool, appending JSONL as they finish.

    Each payload: {"final_user_turn": str, "seeded_turns": list|None,
    "search_user_id": str|None, "meta": {id_key: ..., ...}}. Case order in the
    output file follows completion order; resume/scoring key off ids.
    """
    import json
    from concurrent.futures import ProcessPoolExecutor, as_completed

    done = 0
    with (
        out_path.open("a") as fh,
        ProcessPoolExecutor(max_workers=workers, initializer=_pool_worker_init) as pool,
    ):
        futures = {pool.submit(_pool_run_case, p): p for p in payloads}
        for future in as_completed(futures):
            payload = futures[future]
            case_id = payload["meta"][id_key]
            done += 1
            try:
                record = future.result()
            except Exception as exc:  # worker died; record and move on
                record = {
                    **payload["meta"],
                    "final_answer": "",
                    "assistant_messages": [],
                    "tool_calls": [],
                    "error": f"worker failure: {type(exc).__name__}: {exc}",
                    "latency_ms": 0,
                    "session_id": None,
                    "wall_ms": 0,
                }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            status = "ERR" if record["error"] else "ok"
            print(
                f"[{done}/{len(payloads)}] {case_id} -> {status} "
                f"tools={[c['tool'] for c in record['tool_calls']]} "
                f"answer={len(record['final_answer'] or '')}ch {record['wall_ms']}ms",
                flush=True,
            )


def main() -> None:
    """Smoke test: one Track 1 case and one Track 8-style case."""
    load_env()
    harness = BenchHarness()
    harness.start()
    try:
        print("=== Track 1 smoke (U001, HR question) ===")
        r1 = harness.run_case("Chính sách thử việc là gì?", search_user_id="U001")
        print("error:", r1["error"])
        print("tools:", [(c["tool"], c["args"][:120]) for c in r1["tool_calls"]])
        print("answer:", (r1["final_answer"] or "")[:600])

        print("\n=== Track 8 smoke (multi-turn seeded) ===")
        r2 = harness.run_case(
            "Gần Hoàn Kiếm, phù hợp cho trẻ em.",
            seeded_turns=[
                {"role": "user", "content": "Tìm nhà hàng."},
                {"role": "assistant", "content": "Bạn muốn khu vực nào?"},
            ],
            search_user_id="U002",
        )
        print("error:", r2["error"])
        print("tools:", [(c["tool"], c["args"][:120]) for c in r2["tool_calls"]])
        print("answer:", (r2["final_answer"] or "")[:600])
    finally:
        harness.shutdown()


if __name__ == "__main__":
    main()
