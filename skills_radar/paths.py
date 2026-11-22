"""Per-user locations, following each OS's conventions."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Where rankings, history, logs and the icon live. Override with SKILLS_RADAR_DATA."""
    override = os.environ.get("SKILLS_RADAR_DATA")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / "skills-radar"


def package_parent() -> Path:
    """Directory containing the skills_radar package (repo root when run from a clone)."""
    return Path(__file__).resolve().parent.parent


def gui_python() -> str:
    """Python interpreter that runs without a console window (pythonw on Windows)."""
    exe = Path(sys.executable)
    if sys.platform == "win32":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return str(w)
    return str(exe)
