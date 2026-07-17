"""Process-oriented tool handlers (run command & process management)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from minder.core.context_engineering.tools.context import ToolExecutionContext
from minder.core.context_engineering.tools.implementations.bash_tool import truncate_output
from minder.models.operation import Operation, OperationType


class ProcessToolHandler:
    """Encapsulates bash execution and process monitoring tools."""

    _SERVER_PATTERNS = (
        r"flask\s+run",
        r"python.*app\.py",
        r"python.*manage\.py\s+runserver",
        r"django.*runserver",
        r"uvicorn",
        r"gunicorn",
        r"python.*-m\s+http\.server",
        r"npm\s+(run\s+)?(start|dev|serve)",
        r"yarn\s+(run\s+)?(start|dev|serve)",
        r"node.*server",
        r"nodemon",
        r"next\s+(dev|start)",
        r"rails\s+server",
        r"php.*artisan\s+serve",
        r"hugo\s+server",
        r"jekyll\s+serve",
    )

    def __init__(self, bash_tool: Any) -> None:
        self._bash_tool = bash_tool

    def run_command(self, args: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
        if not self._bash_tool:
            return {"success": False, "error": "BashTool not available"}

        command = args["command"]
        background = args.get("background", False)

        if not background and self._is_server_command(command):
            background = True

        operation = Operation(
            id=str(hash(f"{command}{datetime.now()}")),
            type=OperationType.BASH_EXECUTE,
            target=command,
            parameters={"command": command, "background": background},
            created_at=datetime.now(),
        )

        if not self._ensure_command_approval(command, background, operation, context):
            return {
                "success": False,
                "interrupted": True,
                "denied": True,
                "output": None,
            }

        # Create output callback for streaming bash output to UI
        output_callback = None
        if context.ui_callback and hasattr(context.ui_callback, "on_bash_output_line"):

            def _output_callback(line: str, is_stderr: bool = False) -> None:
                context.ui_callback.on_bash_output_line(line, is_stderr)

            output_callback = _output_callback

        result = self._bash_tool.execute(
            command,
            background=background,
            operation=operation,
            task_monitor=context.task_monitor,
            auto_confirm=getattr(context, "is_subagent", False),
            output_callback=output_callback,
        )

        if result.success and context.undo_manager:
            context.undo_manager.record_operation(operation)

        output_parts = [part for part in (result.stdout, result.stderr) if part]
        combined_output = truncate_output("\n".join(output_parts))

        if result.success:
            return {
                "success": True,
                "output": combined_output or "Command executed",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "error": None,
            }

        error_parts = [p for p in (result.error, combined_output) if p]
        error_message = "\n".join(error_parts) if error_parts else "Command execution failed"
        # Detect if the command was interrupted by user (Fix 5)
        interrupted = "interrupted" in (result.error or "").lower()
        return {
            "success": False,
            "output": combined_output or None,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "error": error_message,
            "interrupted": interrupted,
        }

    # list_processes / get_process_output / kill_process were removed along with
    # their tools — only run_command remains.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_command_approval(
        self,
        command: str,
        background: bool,
        operation: Operation,
        context: ToolExecutionContext,
    ) -> bool:
        mode_manager = context.mode_manager
        if mode_manager and not mode_manager.needs_approval(operation):
            operation.approved = True
            return True

        approval_manager = context.approval_manager
        if not approval_manager:
            operation.approved = True
            return True

        # Auto-approve sessions must never block on an interactive prompt. Honor
        # auto_approve_remaining directly — otherwise the force_prompt path below
        # tries to open a prompt_toolkit menu, which crashes in the worker.
        if getattr(approval_manager, "auto_approve_remaining", False):
            operation.approved = True
            return True

        # Early exit if already interrupted - don't show approval modal
        if context.task_monitor and context.task_monitor.should_interrupt():
            return False

        if (
            hasattr(approval_manager, "pre_approved_commands")
            and command in approval_manager.pre_approved_commands
        ):
            approval_manager.pre_approved_commands.discard(command)
            operation.approved = True
            return True

        preview = f"Execute{' (background)' if background else ''}: {command}"
        working_dir = (
            str(self._bash_tool.working_dir)
            if getattr(self._bash_tool, "working_dir", None)
            else "."
        )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Check if request_approval already returned a result (WebApprovalManager) or needs to be awaited
            approval_result = approval_manager.request_approval(
                operation=operation,
                preview=preview,
                command=command,
                working_dir=working_dir,
                force_prompt=True,
            )

            # If it's already a result object, use it directly
            if hasattr(approval_result, "approved"):
                result = approval_result
            else:
                # If it's a coroutine, run it
                result = asyncio.run(approval_result)

            if not result.approved:
                return False
            operation.approved = True
            return True

        operation.approved = True
        return True

    @classmethod
    def _is_server_command(cls, command: str) -> bool:
        return any(re.search(pattern, command, re.IGNORECASE) for pattern in cls._SERVER_PATTERNS)
