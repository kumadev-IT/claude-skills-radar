# Skills Radar

A local desktop radar for **Claude / AI-agent skill repositories** on GitHub.
It ranks repos by a real score instead of "last pushed" and opens as a small
app window you can pull up many times a day with a hotkey.

> **Status: work in progress, not released yet.** Expect changes to the
> scoring and the UI. Tested on Windows; macOS and Linux support is
> implemented but still needs real-world testing, so feedback is welcome.

## Install

You need either [uv](https://docs.astral.sh/uv/) (recommended, it can also
install Python for you) or Python 3.10+ with `pipx`. There are no third-party
dependencies.

```bash
# 1. install the command
uv tool install git+https://github.com/kumadev-IT/claude-skills-radar
#   or: pipx install git+https://github.com/kumadev-IT/claude-skills-radar

# 2. add it to your app menu (Start Menu + Desktop + Ctrl+Alt+R on Windows)
skills-radar install
```

That's it. From now on you open it like any other app.

**Just try it, no install:**

```bash
uvx --from git+https://github.com/kumadev-IT/claude-skills-radar skills-radar
```

**From a clone:** `python -m skills_radar` from the repo folder (and
`python -m skills_radar install` for the launcher).

## Daily use

- **Open:** press **Ctrl+Alt+R** (Windows), or launch *Skills Radar* from the
  app menu / Spotlight / Desktop, or run `skills-radar`. On macOS and Linux
  you can bind the `skills-radar` command to a keyboard shortcut in your
  system settings.
- It opens as a compact app window (Chrome, Edge, Brave or Chromium if
  installed, otherwise your default browser).
- **Data stays fresh by itself:** a small local server keeps running in the
  background and refreshes from GitHub every 60 minutes. Opening the app is
  instant because the data is already there.
- **↻** (or `R`) fetches fresh data right now, `/` searches, `?` opens the guide.

## Commands

| Command | What it does |
|---|---|
| `skills-radar` | Open the dashboard (starts the background server if needed) |
| `skills-radar open --tab` | Open in a normal browser tab instead of an app window |
| `skills-radar refresh` | Fetch fresh data now and wait for it |
| `skills-radar status` | Server state, data age, data folder |
| `skills-radar stop` | Stop the background server |
| `skills-radar install [--hotkey CTRL+ALT+K]` | Add the launcher (`--hotkey ""` for none) |
| `skills-radar uninstall` | Remove the launcher and stop the server |

To remove everything: `skills-radar uninstall`, then `uv tool uninstall skills-radar`
(or `pipx uninstall skills-radar`), and delete the data folder shown by `skills-radar status`.

## What it shows

The dashboard has four views:

- **Score**: the main ranking (popularity + momentum + freshness)
- **Hot**: the fastest-growing repos right now (stars/day)
- **New**: the youngest repos that have already passed the star threshold
- **All-time**: the most-starred repos ever, flagged *active / stale / archived*

The in-app guide (**? Guide**) explains every view and the score formula.

Repos come from the GitHub topics `claude-skills`, `agent-skills`,
`claude-code-skills` and `claude-skill`. Forks, archived repos, repos with
fewer than 5 stars and repos with no push in 90 days are filtered out (the
All-time view keeps inactive repos and flags them).

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
`skills_radar/tracker.py`.

## How it works

- `skills_radar/tracker.py` queries the GitHub Search API and computes the ranking.
- `skills_radar/server.py` serves the dashboard on `http://127.0.0.1:47821`.
  It is only reachable from your own machine and refreshes data in the
  background, so no cron job or scheduled task is needed.
- Data, history and logs live in your user data folder:
  - Windows: `%LOCALAPPDATA%\skills-radar`
  - macOS: `~/Library/Application Support/skills-radar`
  - Linux: `~/.local/share/skills-radar`

  Set `SKILLS_RADAR_DATA` to change it, or `SKILLS_RADAR_PORT` to change the port.

### GitHub rate limit

Without a token, a refresh takes about a minute because the tracker stays
under GitHub's anonymous search limit. With a token it is faster. The tracker
uses `GITHUB_TOKEN` or `GH_TOKEN` if set, or your GitHub CLI login
(`gh auth token`) if `gh` is installed. A token with no scopes is enough.

## Data

Repository names, descriptions and avatars come from the public GitHub API and
belong to their respective owners; Skills Radar only links to them.

## License

[MIT](LICENSE) © 2026 kumadev.

Portions of `skills_radar/tracker.py` are derived from
[linny006/trending-claude-skills](https://github.com/linny006/trending-claude-skills)
(MIT); see the third-party notice in [LICENSE](LICENSE).
