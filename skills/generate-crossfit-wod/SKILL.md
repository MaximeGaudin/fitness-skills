---
name: generate-crossfit-wod
description: Fetch the official CrossFit.com WOD and adapt it to the home gym — substitute exercises blocked by missing equipment or mastery, scale loads to current level, and emit a YAML file for the TV timer. Use when the user says "crossfit wod", "today's wod", "official wod", "adapt crossfit", or wants to follow CrossFit.com programming.
---

# CrossFit WOD Adapter

Fetch the official CrossFit.com WOD and adapt it to the user's home gym, staying as close as possible to the original while substituting what's missing and scaling to the user's current level.

## Configuration

All persistent user data lives under `FITNESS_DIR="${MEMORY_DIR:-$HOME/.memory}/fitness"`. Read and write under it; create it if missing. Starter files are in the repository's `examples/` folder.

| File | Purpose |
|------|---------|
| `$FITNESS_DIR/goal.md` | Training goals, constraints, weekly schedule |
| `$FITNESS_DIR/data/equipment.yaml` | Available equipment |
| `$FITNESS_DIR/data/exercises/<id>.yaml` | Exercise files (cues, video, muscles, equipment) |
| `$FITNESS_DIR/data/personal-records.yaml` | Working weights & PRs (current loads) |
| `$FITNESS_DIR/mastery.yaml` | Mastered exercises: the ONLY exercises allowed |
| `$FITNESS_DIR/wods/*.yaml` | Past WODs (progression reference) |
| `$FITNESS_DIR/activities/index.md` | Recent Garmin activity summary (optional, from **garmin-sync**) |

`$FITNESS_SKILLS_DIR` is the path to the cloned fitness-skills repository (used to run the TV build).

The WOD YAML schema is defined in the **wod-generator** skill (`wod-schema.md`). This skill produces files in the **same** schema, plus a `source:` block (below).

## Core principles

1. **Stay as close to the original as possible.** Deviate only when forced by equipment, mastery, or safety.
2. **Mastery gate still applies.** Never program an exercise with `status: learning` or absent from `mastery.yaml` in the main WOD. Substitute instead.
3. **Progressive load from personal records.** Every loaded exercise uses weights from `personal-records.yaml`. Never copy Rx weights blindly.
4. **Respect the warm-up.** Always progressive; longer if `goal.md` says sessions happen early in the morning or on a cold body.

## Workflow

### 0. Sync recent activities (optional)

If the **garmin-sync** skill is installed, sync first so load scaling uses fresh data, then read `activities/index.md`.

### 1. Fetch the official WOD

Fetch `https://www.crossfit.com/workout/` and extract today's WOD. If today is a **rest day**, see "Rest days" below.

Extract: format (For Time, AMRAP, EMOM, heavy day, chipper, couplet...); exercises and rep scheme; Rx / Intermediate / Beginner prescriptions; Stimulus & Strategy notes.

### 2. Check the day's constraints

Read the weekly schedule in `goal.md`. Don't generate on a planned rest day. If today is a run-only day, generate a run WOD (see `wod-schema.md`) regardless of what CrossFit programs.

### 3. Analyze and substitute

For each exercise, check two gates:

**Gate 1 — Equipment available?** Read `data/equipment.yaml`. If the exercise needs equipment the user doesn't have, substitute.

**Gate 2 — Exercise mastered?** Read `mastery.yaml`. If not mastered, substitute.

#### Substitution examples (preserve the stimulus: same movement pattern, muscle groups, intensity)

| Original | Missing | Substitute with |
|---|---|---|
| Box jumps (Rx height) | tall box | Highest available box height, or broad jumps |
| Wall-ball shots | Rx ball weight | Available ball weight, adjust reps |
| Rowing (cal/m) | rower | Bike, elliptical or run (match duration) |
| Assault/Echo bike | bike | Other cardio machine or jump rope (match duration) |
| Muscle-ups | rings | Pull-ups + dips (separate movements) |
| Ring rows | rings | Inverted rows under a racked barbell |
| Rope climbs | rope | Towel or strict pull-ups |
| GHD sit-ups | GHD | Sit-ups (AbMat if available) |
| Kettlebell moves | KB | Dumbbell or plate-with-handles equivalent |
| Handstand walk | skill/space | Pike shoulder taps or wall walks |
| Toes-to-bar | skill | Hanging knee raises |
| Weighted vest | vest | Skip the vest, adjust load elsewhere |
| Long runs | space/weather | Cardio machine at equivalent duration |

Always check the user's `equipment.yaml` for what is actually available. When substituting, add a `notes` field: `"Sub for [original]: [reason]"`. If an exercise is mastered AND the equipment is available, use it as-is (just scale the load).

### 4. Scale the load to current level

**Never copy Rx weights.** For each loaded exercise: read `personal-records.yaml`, use `next_weight_kg` if available, else `current_weight_kg`; if never done, start with an empty bar / very light; check the last 3-5 WODs with the same exercise for consistent overload.

**Rep scheme adaptation:** heavy singles/doubles/triples at beginner loads → more reps (3-3-3 Rx → 5-5-5). High-rep light WODs → keep the scheme, adjust the load. "For Time" with a target time domain → scale reps AND load to finish in the intended window.

### 5. Convert the format if needed

Encode as **AMRAP**, **EMOM**, or **steady** (run); block timing runs on the watch.

| Original | Convert to | How |
|---|---|---|
| AMRAP / EMOM | same | Keep as-is |
| For Time (<12 min) | AMRAP | Cap = target time from Stimulus. Score = completion |
| For Time (>12 min) | AMRAP | Cap = Rx target + buffer. Score = completion |
| Chipper | AMRAP | Cap = target time. Treat as a 1-round AMRAP |
| Heavy day (5x5) | EMOM | EMOM with a suitable interval (e.g. every 3 min) |
| Intervals + rest | EMOM | Map intervals to EMOM rounds with built-in rest |

Always preserve the intended stimulus from the Stimulus & Strategy notes.

### 6. Build the warm-up (~10 min, 4 phases)

**Phase 1 — Light mobility (2 min):** gentle joint circles (neck, shoulders, wrists, hips, ankles), no effort.

**Phase 2 — Dynamic mobility (2 min):** 3-4 controlled movements targeting today's muscles (inchworms, world's greatest stretch, cat-cow, Cossack squats, thoracic rotations). Don't repeat phase-1 movements.

**Phase 3 — Light cardio (3 min):** jump rope / cardio machine / light jog, easy → moderate.

**Phase 4 — Muscle activation (3 min):** 2-3 movements priming the main WOD exercises, bodyweight or empty bar, low reps.

Warm-up exercises must be mastered; otherwise pick a mastered alternative. Moves not in the exercise database (e.g. joint circles) use an inline `name`.

### 7. Generate the YAML

Save to `$FITNESS_DIR/wods/YYYY-MM-DD.yaml` following `wod-schema.md` (warmup, blocks, recovery_break, cooldown, strategy, summary), plus:

```yaml
source:
  type: crossfit.com
  original_date: "YYMMDD"
  original_url: https://www.crossfit.com/workout/YYYY/MM/DD
  original_description: >
    [Paste the original WOD description as-is]
  substitutions:
    - original: "muscle-ups"
      replaced_with: "pull-ups + dips"
      reason: "No rings"
    - original: "box jumps 30 inch"
      replaced_with: "box jumps 24 inch"
      reason: "Highest available box"
```

**Cool-down (6-8 min):** static stretching for every major muscle worked, **45 s per side** minimum (`sides: 2` for bilateral).

**Session structure:** after the last main block, include a `recovery_break` before the cool-down:

```yaml
recovery_break:
  duration_minutes: 3
  notes: "Drink, breathe. Restart the watch before stretching."
```

### 8. Confirm before proceeding

After generating the YAML, **stop and ask the user**. Present the full adapted WOD (exercises, loads, format, substitutions) and ask: "WOD is ready. Build the TV page and push to Garmin?" Only continue after explicit approval.

### 9. Technical slot (optional)

If the original features an exercise the user hasn't mastered but COULD learn (equipment available, not too advanced), add a technical slot before the main WOD, as in **wod-generator**: video on the TV, 2-3 progressive practice sets, then use it in the main WOD at a light weight. Only ONE new exercise per session; add it to `mastery.yaml` with `status: learning`.

### 10. Enrich exercise files

Same as **wod-generator**: for every exercise used, fill missing `video_url` and `image_url` in `data/exercises/<id>.yaml` with a form tutorial from a reputable coaching channel.

### 11. Update personal-records.yaml

Same overload rules: upper body `next_weight_kg = current + 2.5`; lower body `+ 5`; failed session → keep `current_weight_kg` unchanged.

### 12. Build the TV page

```bash
uv run --with pyyaml --with jinja2 "$FITNESS_SKILLS_DIR/tv/build.py" "$FITNESS_DIR/wods/YYYY-MM-DD.yaml"
```

Writes `$FITNESS_SKILLS_DIR/tv/dist/index.html`. Add `--serve` to serve it locally, or `--deploy` to publish to Cloudflare Pages (needs `wrangler` and `CLOUDFLARE_PAGES_PROJECT`).

### 13. Schedule on the watch (optional)

If the **garmin-workouts** skill is installed, push the session. Most adapted sessions are strength WODs (`--strength --steps`):

```bash
schedule_workouts.py \
  --date YYYY-MM-DD \
  --name "CrossFit WOD YYMMDD - <Short description>" \
  --duration <total_working_minutes> \
  --desc "<Brief description: format, exercises, loads>" \
  --strength \
  --steps "Warm-up:<warmup_min>,<Block1 name>:<block1_min>,...,Recovery:3,<Stretch 1>:90s,..."
```

**Steps**: one step per block, `"Label:duration"` comma-separated (`5`/`5m`, `30s`, or `LAP`). Labels should include exercises, reps and weights so they're readable on the watch, e.g. `AMRAP 12 - 8 Deadlift@40 + 10 Wall ball`. Use **`Technical …:LAP`** for the technical slot. Bilateral stretches (`sides: 2`) double the duration.

### 14. Report to the user

Concise summary: date and day; original CrossFit WOD (brief); substitutions and why; adapted version (format, duration, exercises with weights/reps); load comparison to the last session; any new exercise introduced.

## Rest days

If CrossFit.com programs a rest day on a planned training day, **fetch the previous non-rest-day WOD** and adapt that instead. Tell the user: "CrossFit.com has a rest day today, using [date]'s WOD instead."
