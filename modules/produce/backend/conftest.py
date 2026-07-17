"""Ensure the backend package root is importable in tests (`import app`, `import db`)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
