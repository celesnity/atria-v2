"""UI components for REPL interface.

This package contains modular UI components extracted from the main REPL class.
Each component is responsible for a specific aspect of the user interface.
"""

from atria.repl.ui.text_utils import truncate_text
from atria.repl.ui.message_printer import MessagePrinter
from atria.repl.ui.input_frame import InputFrame
from atria.repl.ui.prompt_builder import PromptBuilder
from atria.repl.ui.toolbar import Toolbar
from atria.repl.ui.context_display import ContextDisplay

__all__ = [
    "truncate_text",
    "MessagePrinter",
    "InputFrame",
    "PromptBuilder",
    "Toolbar",
    "ContextDisplay",
]
