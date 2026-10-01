---
name: garmin-sync
description: Download recent Garmin activities as local markdown files for AI analysis. Use when the user asks to sync, download, or review their recent workouts/activities from Garmin, or before planning the next training week. Use `--commit` on the sync script when the user wants new activity files committed to git.
---

# Garmin Activity Sync

Download recent activities from Garmin Connect as structured markdown files for analysis and planning.

## Configuration

All persistent user data lives under a root set by **`MEMORY_DIR`** (default `$HOME/.memory`); the script creates it if missing. Activities are written to `$MEMORY_DIR/fitness/activities/`.

Scripts are referenced by paths **relative to this skill directory**.

## Prerequisites

- **`uv`** for the Python environment. First run:
  ```bash
  uv venv && uv pip install -r requirements.txt
  ```
- **Secrets:** requires `GARMIN_EMAIL` and `GARMIN_PASSWORD` in the environment. Export them in your shell before running (never commit them). As a fallback, the script reads a `.env` file from the current directory or from `$MEMORY_DIR/fitness/.env`. Session tokens are cached in `~/.garminconnect/` and refreshed automatically.
- This uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library with the user's own account. It may break when Garmin changes its API.

## Usage

```bash
# Sync last 15 days (default)
uv run scripts/sync_activities.py

# Sync last 30 days
uv run scripts/sync_activities.py --days 30

# Sync and commit new/updated markdown under $MEMORY_DIR/fitness (must be a git repo)
uv run scripts/sync_activities.py --commit

# Attach a comment to a specific date (defaults to today)
uv run scripts/sync_activities.py --comment "Tough but finished" --comment-date 2026-01-19 --commit
```

With `--commit`, the script stages the files it wrote under `$MEMORY_DIR/fitness/activities/` (including `index.md` and `comments.yaml`) and creates one commit, e.g. `garmin-sync: activities (N session(s), YYYY-MM-DD)`. If there is no diff vs `HEAD` it skips. If `$MEMORY_DIR/fitness` is not a git repository, it prints a message and skips.

## Output

Files are saved in `$MEMORY_DIR/fitness/activities/`:
- **`index.md`** — summary table of all synced activities (date, type, duration, main-set time, distance, pace, HR, elevation gain)
- **`<date>_<type>_<id>.md`** — one file per activity with full details

Each activity file contains:
- Key metrics: duration, distance, pace (avg/max), heart rate (avg/max), elevation, cadence, calories, VO2max, training effect
- **Main set time** (sum of time in HR-targeted main blocks, excluding warm-up, ramp-up and lap-ended buffer/recovery steps)
- **Notes** — user comment, if one was provided for that date
- Heart-rate zone breakdown: time and percentage in each zone
- Workout segments (for structured workouts): labels for warm-up, main blocks, buffer and recovery laps
- Per-km splits: distance, duration, pace, average HR, elevation gain

## User comments

When the user gives feedback about a session, pass it via `--comment`. The comment is stored in `$MEMORY_DIR/fitness/activities/comments.yaml` (keyed by date) and rendered as a `## Notes` blockquote in the activity markdown.

- `--comment-date` defaults to **today**
- Comments **persist across re-syncs**; the YAML file is the source of truth
- Running `--comment` again for the same date **overwrites** the previous comment

## When to sync

- **Before planning the next training week** — see how the user performed and adapt the plan
- **When the user asks to review recent runs** — for data-driven feedback
- **After a key workout** — to compare performance against targets

## Using the data

After syncing, read `$MEMORY_DIR/fitness/activities/index.md` for an overview, then open individual activity files. Look at: HR zone distribution vs target, pace consistency across splits, elevation gain, and training-effect progression over weeks.
