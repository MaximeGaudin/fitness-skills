---
name: garmin-workouts
description: Schedule running and strength workouts to Garmin Connect so they sync to the watch. Use when the user asks to push, sync, or schedule workouts to their Garmin, or when planning a new training week.
---

# Garmin Workout Scheduling

Build running and strength workouts and push them to Garmin Connect so they sync to the user's watch.

## Configuration

Persistent user data lives under **`MEMORY_DIR`** (default `$HOME/.memory`). This skill only uses it to look for a fallback `.env` in `$MEMORY_DIR/fitness/`.

Scripts are referenced by paths **relative to this skill directory**.

## Prerequisites

- **`uv`** for the Python environment. First run:
  ```bash
  uv venv && uv pip install -r requirements.txt
  ```
- **Secrets:** requires `GARMIN_EMAIL` and `GARMIN_PASSWORD` in the environment (never commit them). Fallback: a `.env` file in the current directory or `$MEMORY_DIR/fitness/.env`; otherwise the script prompts. Session tokens are cached in `~/.garminconnect/`.
- Uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library with the user's own account.

## Workout structure (running)

Every running workout follows this pattern on the watch:

1. **Mobility** (step type `warmup`) — 8 min timed, for joint and dynamic mobility before heading out. Optional HR ceiling with `--warmup-hr-max <bpm>` (range starts at `--warmup-hr-min`, default 60). No HR target if omitted.
2. **Ramp-up** — one timed block (walk, then progressive easy jog). Scales with the session: **10 min minimum**, up to **15 min** (`--intensity easy`), **18 min** (`moderate`) or **20 min** (`hard`). Formula: `ramp_up_minutes` in `schedule_workouts.py`.
3. **Main** — one interval at the target HR zone (`zoneNumber`) for the full planned duration.
4. **Buffer** — ends with the **lap button**.
5. **Recovery** — ends with the **lap button** (cooldown step).

Finish-fast workouts get two HR intervals (easy volume + fast finish), then buffer + recovery.

The **Main** step uses an HR zone target. Rough mapping from effort to zone:

| Effort | HR zone | Feel |
|--------|---------|------|
| Easy | Zone 2 | Conversational |
| Moderate | Zone 3 | Working |
| Tempo | Zone 4 | Sustained, hard |

Zones come from the user's Garmin profile; this skill never hardcodes heart-rate values.

Give every workout a `--desc` that states the objective and mindset, short and motivating.

## Scheduling workouts

`--duration` = **main set** in minutes. The script adds 8 min mobility + ramp-up + buffer (lap) + recovery (lap). Repeat `--intensity` once per workout when batching (`easy` | `moderate` | `hard`).

```bash
# Short run — 20 min main set in Zone 2
uv run scripts/schedule_workouts.py \
  --date 2026-01-19 --name "Monday — easy 20min" --duration 20 --hr-zone 2 \
    --desc "Easy pace, conversational." \
    --intensity easy

# Finish-fast — easy volume, then the last 10 minutes in Zone 4
uv run scripts/schedule_workouts.py \
  --date 2026-01-21 --name "Wednesday — 30min fast finish" --duration 30 --hr-zone 2 \
    --desc "Build-up run." --fast-last 10 --tempo-zone 4 \
    --intensity hard
```

Several workouts can be batched in one command by repeating the flag groups.

**Running + strength in one command:** `--strength` alone only works for a single workout. With several `--date` groups, mark strength sessions with `--strength-index N` (0-based). Repeat `--steps` once per workout in the same order, using `""` for running slots.

### Strength workouts

`--strength` uploads with sport type **`strength_training`**. `--strength --hiit-lap` builds lap-ended cross-training blocks.

```bash
# Strength session (45 min, timed steps)
uv run scripts/schedule_workouts.py \
  --date 2026-01-20 --name "Tuesday — Strength 45min" --duration 45 \
    --desc "Full-body strength." \
    --strength --steps "Warm-up:5,Round 1:10,Round 2:10,Round 3:10,Balance:5,Stretching:5"
```

`--steps` format: `"Label:duration,Label:duration,..."` where `duration` is minutes (`5` / `5m`), seconds (`30s`), or `LAP`.

**Lap-advanced blocks:** use **`Label:LAP`** (case-insensitive) to advance with the lap button (e.g. `Technical — bench, empty bar:LAP,AMRAP 16min:16,...`).

**Detailed stretches:** instead of one global `Stretching:5`, list each stretch with its hold, e.g. `Hamstring stretch:60s,Glute stretch:60s,Child's pose:30s`.

**HIIT / cross-training (lap blocks):** named blocks, each ended by the lap button. Use **`--hiit-lap`** with comma-separated names (no `Label:minutes`). Combine with **`--weekly-until`** to schedule the same session every week on the weekday of `--date`.

```bash
uv run scripts/schedule_workouts.py \
  --date 2026-01-20 \
  --weekly-until 2026-03-31 \
  --name "Weekly HIIT 60min" \
  --duration 60 \
  --strength --hiit-lap \
  --steps "Warm-up,Core,Strength,Cardio,Cool-down" \
  --desc "Cross-training class."
```

`--duration` is an estimate for lap-based sessions. In a running + HIIT batch use **`--hiit-lap-index N`** (together with `--strength-index N`). Delete the old workout on Garmin Connect before re-pushing a changed structure.

## Deleting workouts

`client.delete_workout(workout_id)`. List existing workouts with `client.get_workouts()`.
