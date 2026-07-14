"""Mixin classes that compose :class:`ToolRegistry`.

The registry was historically a single ~1400-line god class. Its behaviour is
unchanged; the methods are simply grouped into focused mixins by concern:

- :class:`InlineToolsMixin` -- small tool handlers implemented on the registry.

All mixins rely on attributes initialised in ``ToolRegistry.__init__`` and are
only ever used mixed into that class, never standalone.
"""

from .inline_tools import InlineToolsMixin

__all__ = ["InlineToolsMixin"]
