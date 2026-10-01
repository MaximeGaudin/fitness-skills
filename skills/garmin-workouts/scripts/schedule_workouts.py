"""Schedule running and strength workouts on Garmin Connect.

Usage (running):
    python schedule_workouts.py \
        --date 2026-01-05 --name "Monday - easy 20min" --duration 20 --hr-zone 2 \
            --desc "Easy pace, conversational." \
            [--intensity easy|moderate|hard] [--warmup-hr-max 120]

Usage (strength - step durations as Label:minutes or Label:seconds; use Label:LAP for
lap-ended steps, e.g. a technical block):
    python schedule_workouts.py \
        --date 2026-01-07 --name "Wednesday - Strength 45min" --duration 45 \
            --desc "Full-body strength." \
            --strength --steps "Warm-up:5,Round 1:10,Round 2:10,Round 3:10,Balance:5,Stretching:5"

Batch (running + strength): use --strength-index N (0-based) per strength session - do not use
--strength alone with multiple workouts. Repeat --steps for each workout in order (use "" for
running slots), e.g. --steps "" --steps "" --steps "Warm-up:5,..."

Weekly: single workout + --weekly-until YYYY-MM-DD - uploads once, then schedules it on the
weekday of --date, every week through the end date (inclusive).

HIIT (lap-ended blocks): --strength --hiit-lap --steps "Warm-up,Core,Strength,Cardio,Cool-down"
(comma-separated names, no timers). Multi-batch: --hiit-lap-index N with --strength-index N.
"""

import argparse
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from garminconnect import Garmin
from garminconnect.workout import (
    ExecutableStep,
    FitnessEquipmentWorkout,
    RunningWorkout,
    WorkoutSegment,
)

TOKEN_DIR = os.path.expanduser("~/.garminconnect")
MEMORY_DIR = Path(os.environ.get("MEMORY_DIR", os.path.expanduser("~/.memory")))
DATA_ROOT = MEMORY_DIR / "fitness"
WARMUP_TIMER_SECS = 480.0  # 8 min mobility block before every run

# Lap button end (mkuthan/garmin-workouts: no duration → lap.button, conditionTypeId 1)
LAP_BUTTON_CONDITION = {
    "conditionTypeId": 1,
    "conditionTypeKey": "lap.button",
    "displayOrder": 1,
    "displayable": True,
}

HR_ZONE_TARGET = {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone",
    "displayOrder": 4,
}

# Custom HR range in bpm (used by the optional mobility-block HR cap; not a Z1-Z5 zone)
HR_BPM_RANGE_TARGET = {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone",
    "displayOrder": 4,
}

NO_TARGET = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}

TIME_CONDITION = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}


def ramp_up_minutes(duration_min: int, intensity: str) -> int:
    """Single ramp-up block (walk + progressive jog): min 10 min, scales with session, cap 15-20.

    intensity: easy | moderate | hard
    """
    if intensity == "hard":
        cap = 20
        bonus = min(cap - 10, max(0, duration_min * 10 // 60))
    elif intensity == "moderate":
        cap = 18
        bonus = min(cap - 10, max(0, duration_min * 8 // 60))
    else:
        cap = 15
        bonus = min(cap - 10, max(0, duration_min * 5 // 60))
    return 10 + bonus


def _step_time(
    order,
    step_type_id,
    step_type_key,
    duration_secs,
    target=None,
    zone=None,
    *,
    description: str | None = None,
    notes: str | None = None,
    hr_bpm_low: float | None = None,
    hr_bpm_high: float | None = None,
):
    step = ExecutableStep(
        stepOrder=order,
        stepType={
            "stepTypeId": step_type_id,
            "stepTypeKey": step_type_key,
            "displayOrder": step_type_id,
        },
        endCondition=TIME_CONDITION,
        endConditionValue=float(duration_secs),
        targetType=target or NO_TARGET,
    )
    if zone is not None:
        step.zoneNumber = int(zone)
    if hr_bpm_low is not None and hr_bpm_high is not None:
        step.targetType = HR_BPM_RANGE_TARGET
        step.targetValueOne = float(hr_bpm_low)
        step.targetValueTwo = float(hr_bpm_high)
    if description:
        step.description = description
    if notes:
        step.notes = notes
    return step


def _step_lap(order, step_type_key: str, *, description: str | None = None, notes: str | None = None):
    """End step with lap button (no fixed duration). step_type_key: warmup | interval | cooldown."""
    if step_type_key == "warmup":
        step_type_id = 1
    elif step_type_key == "cooldown":
        step_type_id = 2
    else:
        step_type_id = 3
    step = ExecutableStep(
        stepOrder=order,
        stepType={
            "stepTypeId": step_type_id,
            "stepTypeKey": step_type_key,
            "displayOrder": step_type_id,
        },
        endCondition=LAP_BUTTON_CONDITION,
        endConditionValue=None,
        targetType=NO_TARGET,
    )
    if description:
        step.description = description
    if notes:
        step.notes = notes
    return step


def build_workout(
    name: str,
    duration_min: int,
    hr_zone: int,
    description: str = "",
    fast_last_min: int = 0,
    tempo_zone: int | None = None,
    intensity: str = "easy",
    warmup_hr_min: float | None = None,
    warmup_hr_max: float | None = None,
) -> RunningWorkout:
    """`duration_min` = main set. 8 min mobility + ramp-up + main set (timed),
    then buffer and recovery ended with the lap button.

    intensity: easy | moderate | hard - caps the ramp-up duration (15-20 min).
    warmup_hr_min / warmup_hr_max: optional bpm range for the mobility block (no target if unset).
    """
    main_secs = duration_min * 60
    mise_secs = float(ramp_up_minutes(duration_min, intensity) * 60)

    steps = []
    order = 1

    steps.append(
        _step_time(
            order,
            1,
            "warmup",
            WARMUP_TIMER_SECS,
            description="Mobility",
            notes="Mobility - joint and dynamic mobility before heading out.",
            hr_bpm_low=(warmup_hr_min if warmup_hr_max is not None else None),
            hr_bpm_high=warmup_hr_max,
        )
    )
    order += 1
    steps.append(
        _step_time(
            order,
            3,
            "interval",
            mise_secs,
            description="Ramp-up",
            notes="Ramp-up - walk, then progressive easy jog.",
        )
    )
    order += 1

    if fast_last_min > 0 and tempo_zone:
        easy_secs = main_secs - (fast_last_min * 60)
        steps.append(
            _step_time(
                order,
                3,
                "interval",
                float(easy_secs),
                HR_ZONE_TARGET,
                hr_zone,
                description="Main",
                notes=f"Main - Zone {hr_zone} (easy volume).",
            )
        )
        order += 1
        steps.append(
            _step_time(
                order,
                3,
                "interval",
                float(fast_last_min * 60),
                HR_ZONE_TARGET,
                tempo_zone,
                description="Finish",
                notes=f"Finish - Zone {tempo_zone} (tempo / fast finish).",
            )
        )
        order += 1
    else:
        steps.append(
            _step_time(
                order,
                3,
                "interval",
                float(main_secs),
                HR_ZONE_TARGET,
                hr_zone,
                description="Main",
                notes=f"Main - Zone {hr_zone} (single block).",
            )
        )
        order += 1

    steps.append(
        _step_lap(
            order,
            "interval",
            description="Buffer",
            notes="Buffer - press lap to end; finish wherever you like.",
        )
    )
    order += 1
    steps.append(
        _step_lap(
            order,
            "cooldown",
            description="Recovery",
            notes="Recovery - walk; press lap to end.",
        )
    )

    timed_secs = WARMUP_TIMER_SECS + mise_secs + main_secs
    estimated_total = int(timed_secs)

    return RunningWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=estimated_total,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={
                    "sportTypeId": 1,
                    "sportTypeKey": "running",
                    "displayOrder": 1,
                },
                workoutSteps=steps,
            )
        ],
    )


def _parse_step_duration_to_seconds(raw_value: str) -> int | None:
    """Parse a ``--steps`` duration token to seconds.

    Supported formats:
    - ``LAP`` (case-insensitive): manual advance with lap button.
    - ``N`` or ``Nm``: N minutes.
    - ``Ns``: N seconds.
    """
    token = raw_value.strip()
    if token.upper() == "LAP":
        return None
    match = re.fullmatch(r"(?i)(\d+)\s*([sm]?)", token)
    if not match:
        raise ValueError(
            f"Invalid step duration {raw_value!r}. Use minutes (e.g. 5 or 5m), seconds (e.g. 30s), or LAP."
        )
    value = int(match.group(1))
    unit = match.group(2).lower() or "m"
    return value if unit == "s" else value * 60


def _parse_strength_step_defs(step_defs: str) -> list[tuple[str, int | None]]:
    """Parse --steps for strength: ``Label:duration`` or ``Label:LAP``.

    Duration accepts minutes (``5``/``5m``) or seconds (``30s``).
    ``LAP`` is case-insensitive. Whitespace around labels and values is stripped.
    """
    out: list[tuple[str, int | None]] = []
    for part in step_defs.split(","):
        part = part.strip()
        if not part:
            continue
        label, _, mins_raw = part.rpartition(":")
        label = label.strip()
        mins_raw = mins_raw.strip()
        if not label:
            raise ValueError(f"Invalid --steps segment (missing label): {part!r}")
        duration_secs = _parse_step_duration_to_seconds(mins_raw)
        out.append((label, duration_secs))
    return out


def build_strength_workout(
    name: str,
    duration_min: int,
    description: str = "",
    step_defs: str = "",
) -> FitnessEquipmentWorkout:
    """Build a strength workout with named timed steps and optional lap-ended steps (``Label:LAP``).

    Lap steps use ``endConditionKey: lap.button`` on the watch. First lap step is typed ``warmup``,
    last lap step ``cooldown``, others ``interval`` (Garmin segment types).
    """
    steps: list[ExecutableStep] = []

    if step_defs:
        parsed = _parse_strength_step_defs(step_defs)
        n = len(parsed)
        if n == 0:
            raise ValueError("--steps produced no segments")
        for i, (label, duration_secs) in enumerate(parsed):
            order = i + 1
            if duration_secs is None:
                if i == 0:
                    kind = "warmup"
                elif i == n - 1:
                    kind = "cooldown"
                else:
                    kind = "interval"
                s = _step_lap(
                    order,
                    kind,
                    description=label,
                    notes=f"{label} - press lap to end.",
                )
                steps.append(s)
            else:
                step_type_id = 1 if order == 1 else 3
                step_type_key = "warmup" if order == 1 else "interval"
                s = _step_time(order, step_type_id, step_type_key, float(duration_secs))
                s.description = label
                steps.append(s)
    else:
        steps.append(_step_time(1, 3, "interval", float(duration_min * 60)))

    timed_total = sum(int(s.endConditionValue) for s in steps if s.endConditionValue is not None)
    has_lap = any(s.endConditionValue is None for s in steps)
    if has_lap:
        total_secs = max(timed_total, duration_min * 60)
    else:
        total_secs = timed_total

    return FitnessEquipmentWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=total_secs,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={
                    "sportTypeId": 5,
                    "sportTypeKey": "strength_training",
                    "displayOrder": 7,
                },
                workoutSteps=steps,
            )
        ],
    )


def build_hiit_lap_workout(
    name: str,
    duration_min: int,
    description: str,
    block_labels: list[str],
) -> FitnessEquipmentWorkout:
    """HIIT: lap-ended blocks only (no per-block timer).

    First block -> ``warmup``, last -> ``cooldown``, others -> ``interval``.
    """
    labels = [b.strip() for b in block_labels if b.strip()]
    if len(labels) < 2:
        raise ValueError("HIIT lap: at least 2 blocks required (e.g. warm-up + cool-down).")

    steps: list[ExecutableStep] = []
    order = 1
    n = len(labels)
    for i, label in enumerate(labels):
        if i == 0:
            kind = "warmup"
        elif i == n - 1:
            kind = "cooldown"
        else:
            kind = "interval"
        notes = f"{label} - press lap to end."
        steps.append(_step_lap(order, kind, description=label, notes=notes))
        order += 1

    estimated_total = int(duration_min * 60)

    return FitnessEquipmentWorkout(
        workoutName=name,
        description=description,
        estimatedDurationInSecs=estimated_total,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={
                    "sportTypeId": 4,
                    "sportTypeKey": "fitness_equipment",
                    "displayOrder": 6,
                },
                workoutSteps=steps,
            )
        ],
    )


def load_dotenv():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for candidate in [Path.cwd() / ".env", DATA_ROOT / ".env"]:
        if candidate.is_file():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
            break


def login() -> Garmin:
    load_dotenv()
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        print("Set GARMIN_EMAIL and GARMIN_PASSWORD env vars, or enter below:")
        email = email or input("Garmin email: ")
        password = password or input("Garmin password: ")

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))
    client.login(TOKEN_DIR)
    return client


def parse_args() -> tuple[list[dict], str | None]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", action="append", required=True)
    parser.add_argument("--name", action="append", required=True)
    parser.add_argument("--duration", action="append", type=int, required=True)
    parser.add_argument("--hr-zone", action="append", type=int, default=[])
    parser.add_argument("--desc", action="append", default=[])
    parser.add_argument("--fast-last", action="append", type=int, default=[])
    parser.add_argument("--tempo-zone", action="append", type=int, default=[])
    parser.add_argument(
        "--strength",
        action="store_true",
        help="Single-workout batch only: mark the only session as strength. For multiple workouts, "
        "use --strength-index N instead.",
    )
    parser.add_argument(
        "--strength-index",
        action="append",
        type=int,
        metavar="N",
        dest="strength_indices",
        help="0-based workout index for a strength session (repeat for each one in the batch).",
    )
    parser.add_argument("--steps", action="append", default=[])
    parser.add_argument(
        "--hiit-lap",
        action="store_true",
        help="Single-workout batch: strength = HIIT with lap-ended blocks only (--steps = comma-separated names).",
    )
    parser.add_argument(
        "--hiit-lap-index",
        action="append",
        type=int,
        metavar="N",
        dest="hiit_lap_indices",
        help="0-based workout index for HIIT lap blocks (repeat per session). Requires --strength-index N.",
    )
    parser.add_argument(
        "--intensity",
        action="append",
        choices=("easy", "moderate", "hard"),
        help="Ramp-up length (repeat once per workout; default easy). easy<=15min, moderate<=18min, hard<=20min.",
    )
    parser.add_argument(
        "--warmup-hr-min",
        type=float,
        default=60.0,
        help="Lower bound (bpm) of the optional mobility-block HR range (only used with --warmup-hr-max).",
    )
    parser.add_argument(
        "--warmup-hr-max",
        type=float,
        default=None,
        help="Optional HR ceiling (bpm) for the mobility block of running workouts. No HR target if omitted.",
    )
    parser.add_argument(
        "--weekly-until",
        dest="weekly_until",
        metavar="YYYY-MM-DD",
        help="Single workout only: after upload, schedule it every week on the weekday of --date "
        "through this date (inclusive).",
    )
    args = parser.parse_args()

    n = len(args.date)
    if len(args.name) != n or len(args.duration) != n:
        parser.error("Each workout needs --date, --name, --duration")

    if args.weekly_until and n != 1:
        parser.error("--weekly-until requires exactly one workout (--date / --name / --duration once each)")

    strength_idx: set[int] = set(args.strength_indices or [])
    if args.strength:
        if n == 1:
            strength_idx.add(0)
        else:
            parser.error(
                "With multiple workouts, use --strength-index N for each strength session "
                "(do not use --strength alone)."
            )

    hiit_lap_idx: set[int] = set(args.hiit_lap_indices or [])
    if args.hiit_lap:
        if n == 1:
            hiit_lap_idx.add(0)
        else:
            parser.error(
                "With multiple workouts, use --hiit-lap-index N for each HIIT lap session "
                "(do not use --hiit-lap alone)."
            )

    hr_padded = args.hr_zone + [2] * (n - len(args.hr_zone))
    hr_zones: list[int] = []
    for i in range(n):
        if i in strength_idx:
            hr_zones.append(0)
        else:
            hr_zones.append(hr_padded[i])

    descs = args.desc + [""] * (n - len(args.desc))
    fast_lasts = args.fast_last + [0] * (n - len(args.fast_last))
    tempo_zones = args.tempo_zone + [None] * (n - len(args.tempo_zone))
    step_defs = args.steps + [""] * (n - len(args.steps))
    intensities = (args.intensity or []) + ["easy"] * (n - len(args.intensity or []))

    for i in hiit_lap_idx:
        if i not in strength_idx:
            parser.error(
                f"--hiit-lap-index {i} must be a strength session (use --strength-index {i})."
            )
        sd = step_defs[i].strip()
        if not sd:
            parser.error("--hiit-lap requires --steps with comma-separated block names (e.g. Warm-up,Core,...).")
        if ":" in sd:
            parser.error(
                "--hiit-lap: --steps must be labels only, comma-separated (no Label:minutes timers)."
            )

    workouts = [
        {
            "date": args.date[i],
            "name": args.name[i],
            "duration": args.duration[i],
            "hr_zone": hr_zones[i],
            "desc": descs[i],
            "fast_last": fast_lasts[i],
            "tempo_zone": tempo_zones[i],
            "strength": i in strength_idx,
            "steps": step_defs[i],
            "intensity": intensities[i],
            "hiit_lap": i in hiit_lap_idx,
        }
        for i in range(n)
    ]

    return workouts, args.weekly_until, (args.warmup_hr_min, args.warmup_hr_max)


def _weekly_dates_inclusive(start_date_str: str, until_date_str: str) -> list[str]:
    """start_date_str, then the same weekday every week until until_date_str (inclusive)."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    until = datetime.strptime(until_date_str, "%Y-%m-%d").date()
    d = start
    out: list[str] = []
    while d <= until:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=7)
    return out


def main():
    workouts, weekly_until, (warmup_hr_min, warmup_hr_max) = parse_args()
    client = login()
    print(f"Authenticated. Scheduling {len(workouts)} workout(s)...\n")

    for w in workouts:
        if w["strength"]:
            if w.get("hiit_lap"):
                blocks = [b.strip() for b in w["steps"].split(",") if b.strip()]
                try:
                    workout = build_hiit_lap_workout(
                        w["name"], w["duration"], w["desc"], blocks,
                    )
                except ValueError as err:
                    print(f"  ERROR: {err}")
                    continue
                steps = workout.workoutSegments[0].workoutSteps
                print(f"  Uploading (HIIT lap): {w['name']} (~{w['duration']} min target)")
                labels = [getattr(s, "description", None) or s.stepType["stepTypeKey"] for s in steps]
                print(f"    Steps (lap): {' > '.join(labels)}")
                result = client.upload_workout(workout.to_dict())
            else:
                try:
                    workout = build_strength_workout(
                        w["name"], w["duration"], w["desc"], w["steps"],
                    )
                except ValueError as err:
                    print(f"  ERROR: {err}")
                    continue
                steps = workout.workoutSegments[0].workoutSteps
                print(f"  Uploading (strength): {w['name']} ({w['duration']} min)")
                labels = []
                for s in steps:
                    desc = getattr(s, "description", None) or s.stepType["stepTypeKey"]
                    if s.endConditionValue is None:
                        labels.append(f"{desc} [lap]")
                    else:
                        labels.append(desc)
                print(f"    Steps: {' > '.join(labels)}")
                result = client.upload_workout(workout.to_dict())
        else:
            workout = build_workout(
                w["name"],
                w["duration"],
                w["hr_zone"],
                w["desc"],
                w["fast_last"],
                w["tempo_zone"],
                w["intensity"],
                warmup_hr_min,
                warmup_hr_max,
            )
            steps = workout.workoutSegments[0].workoutSteps
            print(f"  Uploading (running): {w['name']} ({w['duration']} min, Zone {w['hr_zone']})")
            print(
                f"    Steps: {' > '.join(getattr(s, 'description', None) or s.stepType['stepTypeKey'] for s in steps)}"
            )
            result = client.upload_running_workout(workout)

        workout_id = result.get("workoutId")
        if not workout_id:
            print(f"  ERROR: upload failed - {result}")
            continue

        if weekly_until:
            dates = _weekly_dates_inclusive(w["date"], weekly_until)
            if not dates:
                print(
                    f"  ERROR: no dates between {w['date']} and {weekly_until} - check dates.\n"
                )
                continue
            print(f"  Scheduling on {len(dates)} date(s), weekly (workout ID: {workout_id})")
            for d in dates:
                client.schedule_workout(workout_id, d)
                print(f"    {d} OK")
            print()
        else:
            print(f"  Scheduling on {w['date']} (workout ID: {workout_id})")
            client.schedule_workout(workout_id, w["date"])
            print("  OK\n")

    print("Done.")


if __name__ == "__main__":
    main()
