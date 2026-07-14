"""Web UI module for Minder."""

from pathlib import Path
from minder.web.server import create_app, start_server


def find_static_directory() -> Path:
    """Find the built web UI static directory.

    Returns:
        Path to the static directory containing built web UI files,
        or None if not found.
    """
    import minder as _minder_pkg

    package_dir = Path(_minder_pkg.__file__).parent

    # Check for built static files in the package
    static_dir = package_dir / "web" / "static"
    if static_dir.exists() and (static_dir / "index.html").exists():
        return static_dir

    # Check for development directory (for fallback)
    dev_static = package_dir.parent.parent / "minder" / "web" / "static"
    if dev_static.exists() and (dev_static / "index.html").exists():
        return dev_static

    return None


__all__ = ["create_app", "start_server", "find_static_directory"]
