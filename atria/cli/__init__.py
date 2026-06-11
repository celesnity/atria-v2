"""Command-line interface entry point for Atria."""

from atria.cli.main import main
from atria.cli.non_interactive import _run_non_interactive

__all__ = ["main", "_run_non_interactive"]
