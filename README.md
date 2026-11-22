# Skills Radar

A local desktop radar for **Claude / AI-agent skill repositories** on GitHub.
It ranks repos by a real score instead of "last pushed", and gives you a fast,
widget-style dashboard to keep track of what's rising and what's established.

> **Status: work in progress (v0.1).** Expect changes to the scoring and the UI.

## What it does

- **`tracker.py`** queries the GitHub Search API for repos tagged
  `claude-skills`, `agent-skills`, `claude-code-skills` and `claude-skill`,
  filters out noise (forks, archived, < 5 stars, no push in 90 days), records
  star history and computes a score.
- **`dashboard.html`** is a single-file dashboard (no server, no build) with four views:
  - **Score**: the main ranking (popularity + momentum + freshness)
  - **Hot**: fastest-growing repos right now (stars/day)
  - **New**: youngest repos that already passed the star threshold
  - **All-time**: most-starred repos ever, flagged *active / stale / archived*
- **`setup-radar.ps1`** (Windows) schedules an hourly background refresh and
  adds a *Skills Radar* shortcut that opens the dashboard as an app window.

An in-app guide (**? Guide**, or press `?`) explains every view and the score formula.

## Score

```
popularity = ln(1 + stars)         / ln(1 + stars of the most-starred repo)
momentum   = ln(1 + stars per day) / ln(1 + stars/day of the fastest repo)
freshness  = 0.5 ^ (days since last push / 10)

score = 100 × (0.30 × popularity + 0.50 × momentum + 0.20 × freshness)
```

Stars/day is measured over the last 7 days from the recorded history. Until
about a day of history exists, it is estimated from the lifetime average
(shown with `~`). Weights, topics and thresholds are constants at the top of
`tracker.py`.

## Quick start

Requirements: Python 3.10+ (standard library only). On Windows, Microsoft Edge
for the app window; any browser works for opening `dashboard.html` directly.

```bash
git clone https://github.com/kumadev-IT/claude-skills-radar.git
cd claude-skills-radar
python tracker.py          # creates data/ranking.js (~1 min without a token)
```

Then open `dashboard.html` in your browser.

### Windows: background refresh + app shortcut

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-radar.ps1             # hourly refresh + shortcut
powershell -ExecutionPolicy Bypass -File .\setup-radar.ps1 -Uninstall  # remove both
```

### Optional: GitHub token

Without a token the tracker paces itself to GitHub's anonymous limit
(10 searches/min). A token with no scopes raises the limit:

```bash
GITHUB_TOKEN=ghp_xxx python tracker.py
```

## Data

`data/` is generated locally and is not committed. Repository names,
descriptions and avatars come from the public GitHub API and belong to their
respective owners; Skills Radar only links to them.

## License

[MIT](LICENSE) © 2026 kumadev.

Portions of `tracker.py` are derived from
[linny006/trending-claude-skills](https://github.com/linny006/trending-claude-skills)
(MIT); see the third-party notice in [LICENSE](LICENSE).
