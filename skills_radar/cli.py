"""Command line entry point: `skills-radar [open|refresh|status|stop|install|uninstall|serve]`."""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from . import APP_ID, DEFAULT_PORT, __version__
from .paths import data_dir, gui_python, package_parent


def say(msg: str) -> None:
    """print() that is safe under pythonw (no console attached)."""
    if sys.stdout:
        print(msg, flush=True)


# === Talking to the local server ====================================


def _call(port: int, path: str, method: str = "GET", timeout: float = 1.0) -> dict | None:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def server_status(port: int) -> dict | None:
    st = _call(port, "/api/status", timeout=0.6)
    return st if st and st.get("app") == APP_ID else None


def _port_taken(port: int) -> bool:
    import socket
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_server(port: int) -> dict | None:
    st = server_status(port)
    if st and st.get("version") == __version__:
        return st
    if st:  # an older/newer version is still running: replace it
        _call(port, "/api/shutdown", "POST")
        for _ in range(30):
            time.sleep(0.1)
            if not _port_taken(port):
                break
    if _port_taken(port):
        raise SystemExit(f"Port {port} is used by another program. Use --port or SKILLS_RADAR_PORT.")
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(package_parent()), env.get("PYTHONPATH")]))
    cmd = [gui_python(), "-m", "skills_radar", "--port", str(port), "serve"]
    out = open(d / "server.out", "ab")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": out, "stderr": out, "env": env,
                "cwd": str(package_parent())}
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:  # survive the parent terminal / job object closing
            subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kw)
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)
    for _ in range(50):
        time.sleep(0.15)
        st = server_status(port)
        if st:
            return st
    return None


# === Opening an app-style window ====================================


def _find_chromium() -> list[str] | None:
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        rels = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
                r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Chromium\Application\chrome.exe"]
        for rel in rels:
            for root in filter(None, roots):
                p = Path(root) / rel
                if p.exists():
                    return [str(p)]
    elif sys.platform == "darwin":
        for app in ("Google Chrome", "Microsoft Edge", "Brave Browser", "Chromium", "Arc"):
            for base in (Path("/Applications"), Path.home() / "Applications"):
                if (base / f"{app}.app").exists():
                    return ["open", "-na", str(base / f"{app}.app"), "--args"]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                     "microsoft-edge", "microsoft-edge-stable", "brave-browser"):
            p = shutil.which(name)
            if p:
                return [p]
    return None


def open_window(url: str, tab: bool = False) -> None:
    browser = None if tab else _find_chromium()
    if not browser:
        webbrowser.open(url)
        return
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.DETACHED_PROCESS
    else:
        kw["start_new_session"] = True
    subprocess.Popen(browser + [f"--app={url}", "--window-size=520,880"], **kw)


# === Commands =======================================================


def cmd_open(port: int, tab: bool) -> int:
    st = start_server(port)
    if not st:
        say(f"Could not start the local server. See {data_dir() / 'server.log'}")
        return 1
    open_window(f"http://127.0.0.1:{port}/", tab)
    return 0


def cmd_refresh(port: int) -> int:
    if server_status(port):
        _call(port, "/api/refresh", "POST")
        say("Refreshing via the running server...")
        while (st := server_status(port)) and st["refreshing"]:
            time.sleep(1)
        if st and st.get("last_error"):
            say("Refresh failed: " + st["last_error"])
            return 1
        say("Done.")
        return 0
    from . import tracker
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    say("Refreshing (about 1 minute without a GitHub token)...")
    summary = tracker.run(data_dir())
    say(f"Ranked {summary['ranked']} repos. Top: {', '.join(summary['top'])}")
    return 0


def cmd_status(port: int) -> int:
    st = server_status(port)
    say(f"skills-radar {__version__}")
    say(f"data dir : {data_dir()}")
    if not st:
        say("server   : not running")
        return 0
    age = st["data_age_minutes"]
    say(f"server   : running on http://127.0.0.1:{port}/ (pid {st['pid']})")
    say(f"data     : {'none yet' if age is None else f'{age:.0f} min old'}"
        f"{' - refreshing now' if st['refreshing'] else ''} - auto-refresh every {st['refresh_every_minutes']} min")
    if st.get("last_error"):
        say(f"last err : {st['last_error']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skills-radar",
                                description="Local radar for trending Claude / agent skill repos.")
    p.add_argument("--port", type=int, default=int(os.environ.get("SKILLS_RADAR_PORT", DEFAULT_PORT)))
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", metavar="command")
    o = sub.add_parser("open", help="open the dashboard (default): starts the server if needed")
    o.add_argument("--tab", action="store_true", help="use a normal browser tab instead of an app window")
    sub.add_parser("refresh", help="fetch fresh data from GitHub now")
    sub.add_parser("status", help="show server and data status")
    sub.add_parser("stop", help="stop the background server")
    i = sub.add_parser("install", help="add Skills Radar to the app menu (and Desktop on Windows)")
    i.add_argument("--hotkey", default="CTRL+ALT+R", help="Windows global hotkey (default CTRL+ALT+R, '' for none)")
    sub.add_parser("uninstall", help="remove the app menu entry and stop the server")
    s = sub.add_parser("serve", help="run the server in the foreground")
    s.add_argument("--every", type=int, default=60, help="auto-refresh interval in minutes")
    a = p.parse_args(argv)

    cmd = a.cmd or "open"
    if cmd == "open":
        return cmd_open(a.port, getattr(a, "tab", False))
    if cmd == "serve":
        from .server import serve
        serve(a.port, data_dir(), a.every)
        return 0
    if cmd == "refresh":
        return cmd_refresh(a.port)
    if cmd == "status":
        return cmd_status(a.port)
    if cmd == "stop":
        say("Stopped." if _call(a.port, "/api/shutdown", "POST") else "Server was not running.")
        return 0
    if cmd == "install":
        from .shortcuts import install
        for path in install(a.hotkey or None):
            say(f"Created {path}")
        if sys.platform == "win32" and a.hotkey:
            say(f"Hotkey: {a.hotkey} opens Skills Radar from anywhere.")
        return 0
    if cmd == "uninstall":
        from .shortcuts import uninstall
        _call(a.port, "/api/shutdown", "POST")
        for path in uninstall():
            say(f"Removed {path}")
        say(f"Data kept in {data_dir()} (delete it manually if you want).")
        return 0
    return 0
