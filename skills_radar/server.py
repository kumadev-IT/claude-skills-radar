"""Tiny local server: serves the dashboard and refreshes data in the background.

Binds to 127.0.0.1 only and rejects requests whose Host header isn't the local
address (protects against DNS-rebinding from web pages).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from . import APP_ID, __version__, tracker
from .icon import ensure_icons

log = logging.getLogger("skills_radar.server")

WEB_TYPES = {
    "/": ("dashboard.html", "text/html; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
}


class Refresher:
    def __init__(self, data_dir: Path, every_minutes: int):
        self.data_dir = data_dir
        self.every = every_minutes
        self.lock = threading.Lock()
        self.running = False
        self.last_error: str | None = None
        self.last_summary: dict | None = None

    def data_age_minutes(self) -> float | None:
        f = self.data_dir / "ranking.json"
        return (time.time() - f.stat().st_mtime) / 60 if f.exists() else None

    def start(self) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self) -> None:
        log.info("refresh started")
        try:
            self.last_summary = tracker.run(self.data_dir)
            self.last_error = None
            log.info("refresh done: %s", self.last_summary)
        except Exception as e:  # keep serving old data on any failure
            self.last_error = f"{type(e).__name__}: {e}"
            log.exception("refresh failed")
        finally:
            self.running = False

    def loop(self) -> None:
        while True:
            age = self.data_age_minutes()
            if age is None or age >= self.every:
                self.start()
            time.sleep(60)


def make_handler(port: int, data_dir: Path, refresher: Refresher, server_ref: list):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    web = resources.files("skills_radar") / "web"
    icons = ensure_icons(data_dir)

    class Handler(BaseHTTPRequestHandler):
        server_version = f"SkillsRadar/{__version__}"

        def log_message(self, fmt, *args):
            log.debug("%s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") in allowed_hosts:
                return True
            self._send(403, b"forbidden", "text/plain")
            return False

        def status(self) -> dict:
            age = refresher.data_age_minutes()
            return {"app": APP_ID, "version": __version__, "pid": os.getpid(),
                    "refreshing": refresher.running, "last_error": refresher.last_error,
                    "data_age_minutes": None if age is None else round(age, 1),
                    "refresh_every_minutes": refresher.every, "data_dir": str(data_dir)}

        def do_GET(self):
            if not self._host_ok():
                return
            path = self.path.split("?", 1)[0]
            if path in WEB_TYPES:
                name, ctype = WEB_TYPES[path]
                return self._send(200, (web / name).read_bytes(), ctype)
            if path == "/icon.png":
                return self._send(200, icons["png"].read_bytes(), "image/png")
            if path == "/data/ranking.js":
                f = data_dir / "ranking.js"
                if f.exists():
                    return self._send(200, f.read_bytes(), "text/javascript; charset=utf-8")
                return self._send(200, b"window.RANKING = null;\n", "text/javascript; charset=utf-8")
            if path == "/api/status":
                return self._json(self.status())
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._host_ok():
                return
            if self.path == "/api/refresh":
                started = refresher.start()
                return self._json({"started": started, **self.status()})
            if self.path == "/api/shutdown":
                self._json({"stopping": True})
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return
            self._send(404, b"not found", "text/plain")

    return Handler


def serve(port: int, data_dir: Path, refresh_every_minutes: int = 60) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(data_dir / "server.log", encoding="utf-8")],
    )
    refresher = Refresher(data_dir, refresh_every_minutes)
    server_ref: list = []
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(port, data_dir, refresher, server_ref))
    server_ref.append(httpd)
    threading.Thread(target=refresher.loop, daemon=True).start()
    log.info("serving on http://127.0.0.1:%d (data: %s)", port, data_dir)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        log.info("stopped")
