"""Skills Radar tracker: ranks Claude / agent skill repos by a real score.

Pipeline (one run):
  1. Query GitHub Search for a wide candidate pool across several topics
     (established repos sorted by stars + young "rising" repos), plus the
     most-starred repos of all time.
  2. Drop noise: forks, archived repos, < MIN_STARS, stale pushes.
  3. Append a star snapshot to data/history.json and measure real star
     velocity (stars/day over the last VELOCITY_WINDOW_DAYS). Until enough
     history exists, velocity is estimated from lifetime average.
  4. Score = weighted mix of popularity, momentum and freshness (0-100).
  5. Write ranking.json / ranking.js into the data directory.

Standard library only. Token lookup: GITHUB_TOKEN, GH_TOKEN, then `gh auth token`
(a token raises GitHub's search limit from 10 to 30 requests/minute).
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("skills_radar.tracker")

# === Config =========================================================

TOPICS = ["claude-skills", "agent-skills", "claude-code-skills", "claude-skill"]
MIN_STARS = 5              # below this it's mostly noise
MAX_PUSH_AGE_DAYS = 90     # ignore abandoned repos
RISING_MAX_AGE_DAYS = 30   # "rising" query: repos created in the last N days
RISING_MIN_STARS = 3

WEIGHTS = {"popularity": 0.30, "momentum": 0.50, "freshness": 0.20}
FRESHNESS_HALF_LIFE_DAYS = 10   # push recency decays by half every N days
VELOCITY_WINDOW_DAYS = 7
MIN_HISTORY_DAYS = 0.75         # need this much history to trust measured velocity

HISTORY_RESOLUTION_HOURS = 3    # at most one star snapshot per repo per N hours
HISTORY_KEEP_DAYS = 30

DASHBOARD_TOP_N = 150
ALL_TIME_TOP_N = 100
STALE_AFTER_DAYS = 180     # all-time entries untouched this long get flagged

GITHUB_TOKEN = ""  # resolved at run time, see _resolve_token()
API = "https://api.github.com/search/repositories"

NOW = datetime.now(timezone.utc)


# === Fetch ==========================================================


_last_call = 0.0


def _get(params: dict) -> dict:
    global _last_call
    if not GITHUB_TOKEN:  # stay under 10 searches/min instead of hitting the wall
        wait = 6.5 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
    _last_call = time.monotonic()
    url = f"{API}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "skills-radar-tracker",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 2:
                reset = e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Reset")
                wait = 30
                if reset and reset.isdigit():
                    n = int(reset)
                    wait = n if n < 1_000_000 else max(1, n - int(time.time()))
                wait = min(wait + 1, 65)
                log.warning("rate limited, waiting %ss", wait)
                time.sleep(wait)
                continue
            raise
    return {}


def _search(q: str, sort: str, pages: int = 1) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        data = _get({"q": q, "sort": sort, "order": "desc", "per_page": 100, "page": page})
        batch = data.get("items", [])
        out.extend(batch)
        if len(batch) < 100:
            break
    return out


def fetch_candidates() -> list[dict]:
    pushed_since = (NOW - timedelta(days=MAX_PUSH_AGE_DAYS)).date().isoformat()
    created_since = (NOW - timedelta(days=RISING_MAX_AGE_DAYS)).date().isoformat()

    raw: list[dict] = []
    for i, topic in enumerate(TOPICS):
        # Established: highest stars among recently-active repos.
        raw += _search(f"topic:{topic} stars:>={MIN_STARS} pushed:>={pushed_since} fork:false archived:false",
                       "stars", pages=2 if i == 0 else 1)
        # Rising: young repos, so new hits aren't drowned out by giants.
        if i < 2:
            raw += _search(f"topic:{topic} stars:>={RISING_MIN_STARS} created:>={created_since} fork:false",
                           "stars")

    seen: dict[str, dict] = {}
    for r in raw:
        if r.get("fork") or r.get("archived"):
            continue
        seen[r["full_name"]] = r
    log.info("fetched %d results, %d unique candidates", len(raw), len(seen))
    return list(seen.values())


def fetch_all_time() -> list[dict]:
    """Most-starred repos per topic, regardless of activity (archived included)."""
    seen: dict[str, dict] = {}
    for topic in TOPICS:
        for r in _search(f"topic:{topic} stars:>={MIN_STARS} fork:false", "stars"):
            seen[r["full_name"]] = r
    log.info("all-time: %d unique repos", len(seen))
    return list(seen.values())


# === History & scoring ==============================================


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def update_history(history: dict, repos: list[dict]) -> dict:
    """history: {full_name: [[unix_ts, stars], ...]} (oldest first)."""
    now_ts = int(NOW.timestamp())
    res = HISTORY_RESOLUTION_HOURS * 3600
    for r in repos:
        pts = history.setdefault(r["full_name"], [])
        if pts and now_ts - pts[-1][0] < res:
            pts[-1] = [pts[-1][0], r["stargazers_count"]]  # refresh latest point
        else:
            pts.append([now_ts, r["stargazers_count"]])
    cutoff = now_ts - HISTORY_KEEP_DAYS * 86400
    return {k: [p for p in v if p[0] >= cutoff] for k, v in history.items()
            if v and v[-1][0] >= cutoff}


def velocity(points: list, stars: int, created_at: datetime) -> tuple[float, str, int]:
    """Return (stars/day, source, stars gained in window)."""
    now_ts = NOW.timestamp()
    window_start = now_ts - VELOCITY_WINDOW_DAYS * 86400
    base = next((p for p in points if p[0] >= window_start), None)
    if base:
        span_days = (now_ts - base[0]) / 86400
        if span_days >= MIN_HISTORY_DAYS:
            gained = stars - base[1]
            return max(gained, 0) / span_days, "measured", gained
    age_days = max((NOW - created_at).total_seconds() / 86400, 3.0)
    return stars / age_days, "estimated", 0


def base_item(r: dict, history: dict) -> dict:
    created = _parse(r["created_at"])
    pushed = _parse(r["pushed_at"])
    vel, src, gained = velocity(history.get(r["full_name"], []), r["stargazers_count"], created)
    return {
            "id": r["full_name"],
            "name": r["full_name"],
            "url": r["html_url"],
            "owner_avatar": r["owner"]["avatar_url"],
            "description": (r.get("description") or "").strip()[:200],
            "language": r.get("language") or "—",
            "topics": r.get("topics", [])[:8],
            "stars": r["stargazers_count"],
            "forks": r["forks_count"],
            "created_at": r["created_at"],
            "pushed_at": r["pushed_at"],
            "age_days": round((NOW - created).total_seconds() / 86400, 1),
            "days_since_push": round((NOW - pushed).total_seconds() / 86400, 1),
            "stars_per_day": round(vel, 2),
            "velocity_source": src,
            "stars_gained_window": gained,
            "archived": bool(r.get("archived")),
    }


def score_repos(repos: list[dict], history: dict) -> list[dict]:
    items = [base_item(r, history) for r in repos]
    if not items:
        return []
    max_log_stars = math.log1p(max(i["stars"] for i in items)) or 1
    max_log_vel = math.log1p(max(i["stars_per_day"] for i in items)) or 1
    for i in items:
        pop = math.log1p(i["stars"]) / max_log_stars
        mom = math.log1p(i["stars_per_day"]) / max_log_vel
        fresh = 0.5 ** (i["days_since_push"] / FRESHNESS_HALF_LIFE_DAYS)
        i["components"] = {"popularity": round(pop, 3), "momentum": round(mom, 3), "freshness": round(fresh, 3)}
        i["score"] = round(100 * (WEIGHTS["popularity"] * pop + WEIGHTS["momentum"] * mom
                                  + WEIGHTS["freshness"] * fresh), 1)
    items.sort(key=lambda i: (-i["score"], -i["stars"]))
    for n, i in enumerate(items, 1):
        i["rank"] = n
    return items


# === Output =========================================================


def _resolve_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token and shutil.which("gh"):
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            token = out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            token = ""
    return token


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def run(data_dir: Path) -> dict:
    """Fetch, score and write ranking files into data_dir. Returns a short summary."""
    global NOW, GITHUB_TOKEN
    NOW = datetime.now(timezone.utc)
    GITHUB_TOKEN = _resolve_token()
    data_dir.mkdir(parents=True, exist_ok=True)
    history_file = data_dir / "history.json"
    ranking_file = data_dir / "ranking.json"

    repos = fetch_candidates()
    if not repos:
        raise RuntimeError("No candidates fetched from GitHub; keeping previous data.")

    all_time_repos = sorted(fetch_all_time(), key=lambda r: -r["stargazers_count"])[:ALL_TIME_TOP_N]

    history = update_history(_load(history_file, {}),
                             list({r["full_name"]: r for r in repos + all_time_repos}.values()))
    items = score_repos(repos, history)

    prev = _load(ranking_file, {})
    prev_ranks = {i["id"]: i["rank"] for i in prev.get("items", [])}
    prev_all_time = {i["id"]: i["rank"] for i in prev.get("all_time", [])}
    score_ranks = {i["id"]: i["rank"] for i in items}

    top = items[:DASHBOARD_TOP_N]
    for it in top:
        it["prev_rank"] = prev_ranks.get(it["id"])
        it["spark"] = [p[1] for p in history.get(it["id"], [])][-60:]

    all_time = []
    for n, r in enumerate(all_time_repos, 1):
        it = base_item(r, history)
        it.update(rank=n, prev_rank=prev_all_time.get(it["id"]), score_rank=score_ranks.get(it["id"]),
                  stale=it["days_since_push"] > STALE_AFTER_DAYS,
                  spark=[p[1] for p in history.get(it["id"], [])][-60:])
        all_time.append(it)

    ranking = {
        "generated_at": NOW.isoformat(timespec="seconds"),
        "topics": TOPICS,
        "weights": WEIGHTS,
        "velocity_window_days": VELOCITY_WINDOW_DAYS,
        "freshness_half_life_days": FRESHNESS_HALF_LIFE_DAYS,
        "min_stars": MIN_STARS,
        "max_push_age_days": MAX_PUSH_AGE_DAYS,
        "rising_max_age_days": RISING_MAX_AGE_DAYS,
        "max_stars": max(i["stars"] for i in items),
        "max_stars_per_day": max(i["stars_per_day"] for i in items),
        "stale_after_days": STALE_AFTER_DAYS,
        "candidates": len(items),
        "items": top,
        "all_time": all_time,
    }
    _write_atomic(history_file, json.dumps(history, separators=(",", ":")))
    _write_atomic(ranking_file, json.dumps(ranking, indent=1, ensure_ascii=False))
    _write_atomic(data_dir / "ranking.js", "window.RANKING = " + json.dumps(ranking, ensure_ascii=False) + ";\n")

    return {"ranked": len(items), "all_time": len(all_time), "authenticated": bool(GITHUB_TOKEN),
            "top": [i["name"] for i in items[:5]], "generated_at": ranking["generated_at"]}
