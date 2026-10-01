# WOD YAML Schema

Reference schema for WOD files stored in `${MEMORY_DIR:-$HOME/.memory}/fitness/wods/YYYY-MM-DD.yaml`. Complete, buildable examples live in the repository's `examples/wods/`.

The WOD file is **lean**: exercises are referenced by `id` only (matching `data/exercises/<id>.yaml`). All static info (name, cues, video, muscles, equipment) lives in the exercise file and is **never duplicated** in the WOD. Only workout-specific parameters appear here.

**Loads:** `weight_kg` is the load you add: plates added to the bar for barbell lifts (bar excluded, `0` = empty bar), weight per dumbbell for dumbbell lifts, the selected stack weight for cables.

## Example A: Conditioning WOD (AMRAP with technical slot)

```yaml
date: "2026-01-19"
day: monday
type: strength
title: "Push Day Foundations + Discover: Bench Press"
format: AMRAP
total_duration_minutes: 36

warmup:
  duration_minutes: 5
  exercises:
    - id: jumping-jacks
      reps: 30
    - id: push-ups
      reps: 10
      notes: Chest activation, controlled tempo
    - id: air-squats
      reps: 10
    - id: front-plank
      duration_seconds: 20

blocks:
  - name: "Technical — Bench Press"
    type: technical
    duration_minutes: 8
    exercise_id: bench-press
    practice_sets:
      - reps: 8
        weight_kg: 0
        notes: "Empty bar — shoulder blades pinned, bar path to mid-chest"
      - reps: 8
        weight_kg: 0
        notes: "Empty bar — 3 s descent, touch the chest"
      - reps: 5
        weight_kg: 10
        notes: "Bar + 10 kg (5 kg/side) — keep the leg drive"

  - name: "Main WOD — x5 Rounds"
    type: AMRAP
    duration_minutes: 16
    strategy: |
      Target 4-5 rounds. Bench sets unbroken at this load.
    exercises:
      - id: bench-press
        reps: 8
        weight_kg: 10
        notes: "Bar + 10 kg — form first"
      - id: push-ups
        reps: 12
      - id: air-squats
        reps: 15
      - id: bodyweight-lunges
        reps: 12
        notes: 6 per leg, alternating
      - id: front-plank
        duration_seconds: 30

recovery_break:
  duration_minutes: 3
  notes: "Drink, breathe. Restart the watch before stretching."

cooldown:
  duration_minutes: 5
  exercises:
    - name: Doorway chest stretch
      duration_seconds: 45
      sides: 2
    - name: Front delt stretch
      duration_seconds: 45
      sides: 2
    - name: Overhead triceps stretch
      duration_seconds: 45
      sides: 2

strategy: >
  Target: 4-5 rounds. Bench sets should stay unbroken at this load.
  Push-ups will fatigue after round 3 — break into 8+4 if needed.
  Use squats and lunges as active recovery for the upper body.

summary:
  target_muscles: [chest, triceps, front delts, quadriceps, core]
  split: push
  estimated_intensity: moderate
  new_exercise_introduced: bench-press
  benchmark: false
  progression_notes: >
    First session. Bench press introduced with the empty bar, then 10 kg.
    Log the AMRAP round count as a baseline.
```

## Example B: Heavy EMOM (strength-focused)

```yaml
date: "2026-01-21"
day: wednesday
type: strength
title: "Heavy Squat Day"
format: EMOM
total_duration_minutes: 30

warmup:
  duration_minutes: 5
  exercises:
    - id: jumping-jacks
      reps: 30
    - id: air-squats
      reps: 15
      notes: Slow tempo, focus on depth
    - id: bodyweight-lunges
      reps: 10
    - id: front-plank
      duration_seconds: 20

blocks:
  - name: "Heavy EMOM — Back Squat"
    type: EMOM
    duration_minutes: 14
    rounds: 7
    interval_seconds: 120
    exercises:
      - id: back-squat
        reps: 4
        weight_kg: 30
        notes: "Bar + 30 kg (15 kg/side) — 4 reps every 2 min"

cooldown:
  duration_minutes: 5
  exercises:
    - name: Standing quad stretch
      duration_seconds: 45
      sides: 2
    - name: Hamstring stretch
      duration_seconds: 45
      sides: 2
    - name: Pigeon stretch (glutes)
      duration_seconds: 45
      sides: 2

strategy: >
  Heavy day — quality over speed. Each set of 4 takes ~15-20 s,
  leaving ~100 s of rest. If form breaks, rack the bar and reset.

summary:
  target_muscles: [quadriceps, glutes, hamstrings, core]
  split: legs
  estimated_intensity: hard
  new_exercise_introduced: null
  benchmark: false
  progression_notes: >
    Next session: +5 kg if all 7 sets were completed with good depth.
```

## Run day

```yaml
date: "2026-01-22"
day: thursday
type: run
title: Easy Morning Run
format: steady
total_duration_minutes: 25
notes: Light run. HR Z1-Z2, conversational pace.

blocks:
  - type: steady
    duration_minutes: 25
    target_hr_zone: Z1-Z2
    target_pace: "7:00-7:30/km"
```

## Field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | string | yes | ISO date `YYYY-MM-DD` |
| `day` | string | yes | Day of week (English, lowercase) |
| `type` | string | yes | `strength` or `run` |
| `title` | string | yes | Short creative name |
| `format` | string | yes | `AMRAP`, `EMOM`, or `steady` |
| `total_duration_minutes` | number | yes | Total session time (include the recovery break) |
| `warmup` | object | yes (strength) | Warm-up block |
| `blocks` | array | yes | Workout blocks (technical + main) |
| `recovery_break` | object | recommended | `duration_minutes`, `notes`. Omitted → defaults (3 min) |
| `cooldown` | object | yes (strength) | Cool-down stretches |
| `strategy` | string | yes | Pacing guidance, target rounds, expected fatigue |
| `summary` | object | yes | Metadata for the training log and next WOD planning |
| `source` | object | no | Origin of an adapted WOD (see **generate-crossfit-wod**) |

### Exercise reference (warm-up & main blocks)

Only `id` + workout-specific params. The TV build resolves the rest from `data/exercises/<id>.yaml`. A warm-up item that is not in the exercise database (e.g. "Joint mobility") may use an inline `name` instead of `id`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes (or `name`) | Exercise slug, matches `data/exercises/<id>.yaml` |
| `name` | string | warm-up only, if no `id` | Inline name for moves not in the database |
| `reps` | number | if no duration | Rep count |
| `duration_seconds` | number | if no reps | Timed exercise (prefer for values < 60 s) |
| `duration_minutes` | number | if no reps | Timed exercise in minutes (clean minute counts; decimals OK, `1.5` = 1 min 30 s) |
| `weight_kg` | number | **yes for loaded exercises** | Exact load (see "Loads" above). Omit only for pure bodyweight |
| `notes` | string | no | Workout-specific context |

### Block fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Block name (e.g. "Technical — X", "Main WOD — Name — x3 Rounds"). For AMRAPs with a target round count, include `— xN Rounds` so it shows in the TV header |
| `type` | string | yes | `technical`, `AMRAP`, `EMOM`, `steady` |
| `duration_minutes` | number | yes | Block duration |
| `interval_seconds` | number | EMOM only | EMOM interval length |
| `rounds` | number | EMOM only | Number of rounds |
| `strategy` | string | no | Multi-line text shown above the exercises on the TV |
| `exercises` | array | main blocks | Exercise refs with workout params |
| `exercise_id` | string | technical only | ID of the exercise being introduced |
| `practice_sets` | array | technical only | 2-3 sets with progressive loading |

### Practice set fields (technical block)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reps` | number | yes | Reps for this practice set |
| `weight_kg` | number | yes | Load (0 = empty bar or bodyweight) |
| `notes` | string | yes | Coaching notes for this set |

### Cool-down exercise fields

Stretches are NOT in the exercise database; they use inline names.

Target **6-8 min total**, **45 s per side** minimum. Cover every primary muscle group worked. On the watch, a bilateral stretch becomes one step with the total duration (`45 s × 2 sides = 90 s`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Stretch name (`nom` is accepted too) |
| `duration_seconds` | number | yes | Hold duration per side |
| `sides` | number | no | 2 if bilateral |

### Recovery break fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `duration_minutes` | number | no | Shown on the TV as guidance; timing is on the watch (default 3) |
| `notes` | string | no | Text for the recovery screen |

The TV build merges the recovery screen with a **cleanup** checklist built from the `equipement` lists of the exercises used. No YAML field required.

### Summary fields

| Field | Type | Description |
|-------|------|-------------|
| `target_muscles` | array | Primary muscles targeted |
| `split` | string | push, pull, legs, full-body |
| `estimated_intensity` | string | `light`, `moderate`, `hard` |
| `new_exercise_introduced` | string or null | Exercise ID from the technical slot |
| `benchmark` | boolean | If `true`, repeat this WOD in 4-6 weeks to track progress |
| `progression_notes` | string | How this WOD progresses from previous sessions |

## Exercise file schema

Exercise sheets (`data/exercises/<id>.yaml`) use these fields. The bundled sheets in `examples/exercises/` are written in French with an English display name (`nom_en`).

```yaml
id: bench-press
nom: Développé couché            # name (any language)
nom_en: Bench press              # English name, shown on the TV
description: "..."
groupe: poitrine                 # muscle group
muscles_principaux: [pectoraux]  # primary muscles
muscles_secondaires: [triceps]   # secondary muscles
equipement: [rack, bench, barbell, plates]   # ids from data/equipment.yaml
cues:
  - "Shoulder blades pinned to the bench"
video_url: https://www.youtube.com/watch?v=VIDEO_ID
image_url: https://img.youtube.com/vi/VIDEO_ID/hqdefault.jpg
```
