---
name: wod-generator
description: Generate a daily WOD (Workout of the Day) as a structured YAML file for the home-gym TV timer, gated by exercise mastery and progressive overload. Use when the user asks to generate, plan, or create their next workout, WOD, or training session, or says "next wod", "plan tomorrow", "generate workout".
---

# WOD Generator

Generate a structured WOD YAML file that the TV timer (`tv/build.py` in the fitness-skills repository) turns into a full-screen page, and that can be pushed to a Garmin watch.

## Configuration

All persistent user data lives under `FITNESS_DIR="${MEMORY_DIR:-$HOME/.memory}/fitness"`. Read and write under it; create it if missing. Starter files are in the repository's `examples/` folder.

| File | Purpose |
|------|---------|
| `$FITNESS_DIR/goal.md` | Training goals, constraints, weekly schedule, mindset |
| `$FITNESS_DIR/data/equipment.yaml` | Available equipment |
| `$FITNESS_DIR/data/exercises/<id>.yaml` | One file per exercise (name, cues, video, muscles, equipment) |
| `$FITNESS_DIR/data/personal-records.yaml` | **Working weights & PRs**: current load per exercise, used for progressive overload |
| `$FITNESS_DIR/mastery.yaml` | **Mastered exercises registry**: the ONLY exercises allowed in WODs |
| `$FITNESS_DIR/wods/*.yaml` | Past WODs (training history + progression reference) |
| `$FITNESS_DIR/activities/index.md` | Recent Garmin activity summary (from the **garmin-sync** skill, optional) |

`$FITNESS_SKILLS_DIR` is the path to the cloned fitness-skills repository (used to run the TV build).

The WOD file schema is in **wod-schema.md** (this folder).

## Critical rule: exercise mastery gate

**NEVER program an exercise the user hasn't mastered.** `$FITNESS_DIR/mastery.yaml` is the single source of truth:

- `status: mastered` → can be used freely in WODs
- `status: learning` → introduced in a technical slot, not yet cleared for WODs
- Exercises NOT in `mastery.yaml` → cannot be used at all

Exercise details live in `$FITNESS_DIR/data/exercises/<id>.yaml`. The WOD file only contains the exercise `id` + workout-specific params (reps, duration, weight, notes); the TV build resolves the rest.

To introduce a new exercise, use the **technical slot** (see session structure). Only ONE new exercise per session. After the user confirms good form, set its status to `mastered`.

When updating `mastery.yaml`: set `introduced_date` when adding as `learning`, set `mastered_date` when promoting, and always keep the full history.

## Workflow

### 1. Determine the target date

Ask the user, or default to the next planned training day from `goal.md`.

### 2. Check the day's constraints

Read `$FITNESS_DIR/goal.md`: weekly schedule, session length, days reserved for runs or other sports, rest days. Never generate a session on a day the goal file marks as rest. If the day is a run-only day, generate a run WOD (see **wod-schema.md**) and skip the technical slot.

### 3. Gather recent training data

- Read `mastery.yaml` to know which exercises are allowed
- Read `wods/*.yaml`, sorted by date, focusing on the last 7-10 WODs
- If the **garmin-sync** skill is installed and data is older than a day, sync first, then read `activities/index.md`
- Identify which muscle groups were trained recently and their volume

### 4. Pick the new exercise to introduce (technical slot)

**Hypertrophy bias**: grow the mastered pool with loaded, hypertrophy-friendly exercises. Bodyweight-only moves are fine for warm-up and conditioning but won't drive growth.

**Equipment**: only consider exercises whose `equipement` list is fully covered by `data/equipment.yaml`. Prefer loaded stations (barbell, dumbbells, cables) over bodyweight alternatives for the main WOD and technical slot.

Look in `data/exercises/` for exercises NOT yet in `mastery.yaml`. Prioritize:
1. **Loaded compound movements** over bodyweight/isolation
2. Big hypertrophy drivers first: squat, bench, row, overhead press, deadlift variations, then cable/machine accessories
3. Movements filling gaps in the mastered pool (e.g. no horizontal push yet → bench press)
4. Exercises matching today's muscle-group split
5. Different equipment stations across the week

### 5. Plan the WOD

**Programming principles:**

- **Exercise pool**: ONLY `status: mastered` exercises in warm-up and main blocks, plus the **technical-slot exercise**, which MUST also appear in the main WOD (moderate reps, focus on form)
- **Split**: rotate push/pull/legs/full-body; never hit the same primary group 2 days in a row
- **Format**: AMRAP or EMOM, so session length is predictable
- **Duration**: fit the session length from `goal.md` (typically 20-30 min working time, excluding warm-up/cool-down)
- **Exact weight prescription**: for every loaded exercise read `data/personal-records.yaml` and use `next_weight_kg` (or `current_weight_kg` if repeating). For a brand-new exercise start conservative (empty bar or very light). The user should never have to guess plates
- **Progressive overload**: compare with the last time the same exercises appeared; nudge weight up or target more rounds
- **Injury prevention**: always warm up, prioritize compounds, no max-effort singles
- **Longevity > performance**: keep 1-2 reps in reserve; never program to failure in timed formats

**Two session archetypes** (alternate across the week):

#### A) Conditioning WOD (AMRAP or multi-movement EMOM)
High density, moderate load, hypertrophy through volume within a time cap.
- 3-6 exercises per round; 8-15 reps (compounds), 12-20 (isolation/bodyweight)
- Load: moderate (60-70% effort), challenging by round 3+; target 4-6 rounds

#### B) Heavy EMOM (strength-focused)
Low reps, heavy load, built-in rest.
- 1-2 compound lifts per EMOM; 3-5 reps per interval
- Interval 90-120 s (~30-40 s work, rest the remainder); 8-12 rounds (12-18 min)
- Load: challenging (75-85% effort). Example: "EMOM 12 (every 2 min): 4 back squats"

**Rep scheme variety**: flat (10-10-10), ascending (6→8→10 EMOM), ladder within a round (A×15, B×12, C×9, D×6), heavy pyramid (5-5-3-3-3 increasing weight).

**Benchmark WODs**: every 4-6 weeks repeat a past WOD exactly. Flag with `benchmark: true` and reference the original date.

**Stimulus & strategy**: every WOD MUST include a `strategy` field with target rounds / expected completion, pacing guidance, and the fatigue to expect.

**Session structure:**
1. **Warm-up** (5-10 min): joint mobility + activation + light cardio, mastered exercises only. If `goal.md` says sessions happen early in the morning or on a cold body, make it longer and more progressive
2. **Technical slot** (8-15 min): introduce ONE new exercise. The tutorial video autoplays and loops on the TV. Duration = video + practice sets. For learning, not performance
3. **Main block** (15-25 min): Conditioning WOD or Heavy EMOM
4. **Recovery + cleanup** (2-3 min): `recovery_break` in YAML (`duration_minutes`, `notes`). The TV merges it with the equipment cleanup checklist
5. **Cool-down** (6-8 min): static stretching for every major muscle worked. Hold **45 s per side** minimum (`sides: 2` for bilateral)

**Timing:** block timers run on the **watch** (see **garmin-workouts**). The TV only displays the active phase with Previous / Next navigation.

**Olympic lift introduction path** (priority order for technical slots): deadlift → Romanian deadlift; front squat → back squat; push press; hang power clean; thruster; power snatch.

### 6. Generate the YAML

Save to `$FITNESS_DIR/wods/YYYY-MM-DD.yaml` following **wod-schema.md**.

**Key rules:**
- Exercises referenced by `id` only: no names, cues, muscles or video in the WOD file
- Only workout-specific params: `reps`, `duration_seconds` / `duration_minutes`, `weight_kg`, `notes`
- Every exercise needs `reps` or a duration
- `duration_minutes` for clean minute counts (`4`, not `240s`), `duration_seconds` under 60 s; decimals OK (`1.5`)
- Technical block uses `exercise_id` + `practice_sets`
- Timer metadata: `format`, `duration_minutes`, `rounds` (EMOM), `interval_seconds` (EMOM)

### 7. Enrich exercise files

For every exercise used (warm-up + blocks + technical slot), read `data/exercises/<id>.yaml` and fill missing fields:

**`video_url`**: if `null`, search YouTube for a form tutorial from a reputable coaching channel (e.g. Starting Strength, Jeff Nippard, CrossFit, Squat University, Renaissance Periodization). The video loops during the technical block, so 5-10 min tutorials are fine.

**`image_url`**: if `null` and `video_url` is set, use `https://img.youtube.com/vi/{VIDEO_ID}/hqdefault.jpg`.

### 8. Update mastery.yaml

Add the technical-slot exercise with `status: learning` and `introduced_date`.

### 9. Update personal-records.yaml

For every loaded exercise:
- Existing entry: update `last_used`, set `next_weight_kg` per the overload rules
- New entry: add the starting weight and set `next_weight_kg` to the first progression

Default progression: upper body `+2.5 kg`, lower body `+5 kg`. After a failed session keep `current_weight_kg` unchanged.

### 10. Build the TV page

```bash
uv run --with pyyaml --with jinja2 "$FITNESS_SKILLS_DIR/tv/build.py" "$FITNESS_DIR/wods/YYYY-MM-DD.yaml"
```

This writes `$FITNESS_SKILLS_DIR/tv/dist/index.html` (override with `--out`): a self-contained page with an auto-generated Setup block (equipment checklist + preview), warm-up, blocks (YouTube video for the technical block), recovery + cleanup, cool-down, and Previous / Next navigation. Add `--serve` to serve it on port 8080, or `--deploy` to publish to Cloudflare Pages (needs `wrangler` and `CLOUDFLARE_PAGES_PROJECT`).

### 11. Schedule on the watch (optional)

If the **garmin-workouts** skill is installed, push the session. Build `--steps` from the WOD YAML with `"Label:duration"` (`5`/`5m`, `30s`, or `LAP`). Use **`Technical …:LAP`** so the technical segment ends at the lap button. Include warm-up, each main block, a recovery step (`recovery_break.duration_minutes`) before the cool-down, then one step per stretch. **Bilateral stretches** (`sides: 2`) double the duration (`45s × 2 = 90s`). Example:

```bash
schedule_workouts.py \
  --date YYYY-MM-DD --name "<WOD title>" --duration <total_working_minutes> \
  --desc "<Short description: format, exercises, loads>" \
  --strength \
  --steps "Warm-up:<warmup_min>,<Technical slot name>:LAP,<Main block name>:<main_min>,Recovery:3,<Stretch 1>:<Ns>,..."
```

### 12. Report to the user

Concise summary: date and day; new exercise introduced (technical slot); format and total duration; exercise list with weights/reps; target muscle groups; how it connects to recent training.
