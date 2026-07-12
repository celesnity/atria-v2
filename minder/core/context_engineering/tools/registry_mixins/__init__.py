"""Mixin classes that compose :class:`ToolRegistry`.

The registry was historically a single ~1400-line god class. Its behaviour is
unchanged; the methods are simply grouped into focused mixins by concern:

- :class:`OrchestrationOpsMixin` -- the unified ``subagent`` / ``get_subagent_output`` tools.
- :class:`InlineToolsMixin` -- small tool handlers implemented on the registry.

All mixins rely on attributes initialised in ``ToolRegistry.__init__`` and are
only ever used mixed into that class, never standalone.
"""

from .inline_tools import InlineToolsMixin
from .orchestration_ops import OrchestrationOpsMixin

__all__ = ["OrchestrationOpsMixin", "InlineToolsMixin"]
