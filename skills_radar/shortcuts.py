"""Create/remove a launcher in the OS app menu (and Desktop on Windows)."""
from __future__ import annotations

import os
import plistlib
import stat
import subprocess
import sys
from pathlib import Path

from .icon import ensure_icons
from .paths import data_dir, gui_python, package_parent

NAME = "Skills Radar"


def _win_folders() -> list[Path]:
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    desktop = Path(os.environ.get("USERPROFILE") or Path.home()) / "Desktop"
    return [appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs", desktop]


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def install(hotkey: str | None) -> list[str]:
    icons = ensure_icons(data_dir())
    py, workdir = gui_python(), str(package_parent())
    made: list[str] = []

    if sys.platform == "win32":
        for i, folder in enumerate(_win_folders()):
            if not folder.exists():
                continue
            lnk = folder / f"{NAME}.lnk"
            # The hotkey goes on the Start Menu shortcut only: duplicates would conflict.
            hk = f"$s.Hotkey={_ps_quote(hotkey)};" if hotkey and i == 0 else ""
            script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(str(lnk))});"
                      f"$s.TargetPath={_ps_quote(py)};$s.Arguments='-m skills_radar';"
                      f"$s.WorkingDirectory={_ps_quote(workdir)};$s.IconLocation={_ps_quote(str(icons['ico']))};"
                      f"$s.Description='Trending Claude skills';{hk}$s.Save()")
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            made.append(str(lnk))

    elif sys.platform == "darwin":
        app = Path.home() / "Applications" / f"{NAME}.app"
        macos = app / "Contents" / "MacOS"
        macos.mkdir(parents=True, exist_ok=True)
        launcher = macos / "skills-radar"
        launcher.write_text(f'#!/bin/sh\ncd "{workdir}" && exec "{py}" -m skills_radar\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        with open(app / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleName": NAME, "CFBundleDisplayName": NAME,
                           "CFBundleIdentifier": "io.github.kumadev-it.skills-radar",
                           "CFBundleExecutable": "skills-radar", "CFBundlePackageType": "APPL",
                           "LSUIElement": True}, f)
        made.append(str(app))

    else:
        apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        desktop = apps / "skills-radar.desktop"
        desktop.write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={NAME}\nComment=Trending Claude skills\n"
            f'Exec="{py}" -m skills_radar\nPath={workdir}\nIcon={icons["png"]}\n'
            "Terminal=false\nCategories=Development;\n", encoding="utf-8")
        made.append(str(desktop))
    return made


def uninstall() -> list[str]:
    removed: list[str] = []
    if sys.platform == "win32":
        targets = [f / f"{NAME}.lnk" for f in _win_folders()]
        # Clean up the scheduled task from the earlier PowerShell-only setup, if present.
        subprocess.run(["schtasks", "/Delete", "/TN", "SkillsRadarRefresh", "/F"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    elif sys.platform == "darwin":
        targets = [Path.home() / "Applications" / f"{NAME}.app"]
    else:
        targets = [Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
                   / "applications" / "skills-radar.desktop"]
    for t in targets:
        if t.is_dir():
            for p in sorted(t.rglob("*"), reverse=True):
                p.rmdir() if p.is_dir() else p.unlink()
            t.rmdir()
            removed.append(str(t))
        elif t.exists():
            t.unlink()
            removed.append(str(t))
    return removed
