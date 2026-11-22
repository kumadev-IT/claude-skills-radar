# Changelog

## [Unreleased]
### Added
- Score-based ranking (popularity, momentum, freshness) across four GitHub topics.
- Star history with measured 7-day velocity.
- Dashboard with Score, Hot, New and All-time views, activity badges and an in-app guide.
- Cross-platform `skills-radar` command (Windows, macOS, Linux), installable with `uv tool` or `pipx`.
- Local background server with automatic hourly refresh and a working refresh button.
- `skills-radar install`: app-menu launcher (Start Menu + Desktop + Ctrl+Alt+R on Windows,
  `~/Applications` on macOS, `.desktop` entry on Linux) with a generated app icon.
- Uses `GITHUB_TOKEN`, `GH_TOKEN` or the GitHub CLI login automatically when available.
