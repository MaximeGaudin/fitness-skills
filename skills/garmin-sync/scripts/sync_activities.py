"""Download recent Garmin activities to local markdown files for AI analysis.

Usage:
    python sync_activities.py [--days 15] [--commit]

Data root:
    All activity files are written under $MEMORY_DIR/fitness/activities
    (MEMORY_DIR defaults to ~/.memory). The directory is created if missing.

Output (in $MEMORY_DIR/fitness/activities/):
    - One markdown file per activity: <date>_<type>_<id>.md
    - index.md with a summary table of all synced activities

With --commit: git add those paths and commit from the data root (skip if not a git repo or nothing to commit).
"""

import argparse
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml
from garminconnect import Garmin

TOKEN_DIR = os.path.expanduser("~/.garminconnect")
MEMORY_DIR = Path(os.environ.get("MEMORY_DIR", os.path.expanduser("~/.memory")))
DATA_ROOT = MEMORY_DIR / "fitness"
ACTIVITIES_DIR = DATA_ROOT / "activities"


def load_comments() -> dict[str, str]:
    """Load user comments from activities/comments.yaml."""
    comments_path = ACTIVITIES_DIR / "comments.yaml"
    if not comments_path.is_file():
        return {}
    try:
        data = yaml.safe_load(comments_path.read_text()) or {}
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def save_comment(dt: str, comment: str) -> None:
    """Save a user comment to activities/comments.yaml."""
    comments = load_comments()
    comments[dt] = comment
    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)
    comments_path = ACTIVITIES_DIR / "comments.yaml"
    comments_path.write_text(
        yaml.dump(comments, allow_unicode=True, default_flow_style=False, sort_keys=True)
    )


def git_commit_activities(written_paths: list[Path], activity_count: int) -> None:
    """Stage written files under activities/ and create a commit if there are changes."""
    if not (DATA_ROOT / ".git").is_dir():
        print("Not a git repository — skipping commit.")
        return

    rel = [str(p.relative_to(DATA_ROOT)) for p in written_paths]
    r = subprocess.run(
        ["git", "-C", str(DATA_ROOT), "add", "--"] + rel,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"git add failed: {r.stderr or r.stdout}")
        return

    diff = subprocess.run(
        ["git", "-C", str(DATA_ROOT), "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if diff.returncode == 0:
        print("No git changes to commit (files identical to HEAD).")
        return

    msg = f"garmin-sync: activities ({activity_count} session(s), {date.today().isoformat()})"
    r2 = subprocess.run(
        ["git", "-C", str(DATA_ROOT), "commit", "-m", msg],
        capture_output=True,
        text=True,
    )
    if r2.returncode != 0:
        print(f"git commit failed: {r2.stderr or r2.stdout}")
        return
    print(r2.stdout.strip() or "Committed.")


def load_dotenv():
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
        print("ERROR: GARMIN_EMAIL / GARMIN_PASSWORD not set")
        sys.exit(1)
    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))
    client.login(TOKEN_DIR)
    return client


def fmt_duration(secs: float | None) -> str:
    if not secs:
        return "—"
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(speed_mps: float | None) -> str:
    if not speed_mps or speed_mps <= 0:
        return "—"
    secs_per_km = 1000.0 / speed_mps
    m, s = divmod(int(secs_per_km), 60)
    return f"{m}:{s:02d}/km"


def fmt_dist(meters: float | None) -> str:
    if not meters:
        return "—"
    return f"{meters / 1000:.2f} km"


def _format_step_target(step: dict) -> str:
    """Turn a workout step's target into a readable string."""
    target_key = step.get("targetType", {}).get("workoutTargetTypeKey", "no.target")
    v1 = step.get("targetValueOne")
    v2 = step.get("targetValueTwo")
    zn = step.get("zoneNumber")

    if target_key == "heart.rate.zone":
        if zn is not None:
            return f"Zone {int(zn)}"
        if v1 is not None and v2 is not None:
            return f"{int(v1)}–{int(v2)} bpm"
        if v1 is not None:
            return f"Zone {int(v1)}"
        return "HR zone"

    if target_key == "no.target" or v1 is None:
        step_type = step.get("stepType", {}).get("stepTypeKey", "")
        ec = (step.get("endCondition") or {}).get("conditionTypeKey", "")
        if step_type == "warmup":
            return "Timer"
        if ec == "lap.button":
            return "Lap"
        if step_type == "cooldown":
            return "Lap"
        return "—"

    if target_key == "pace.zone":
        slow_pace = 1000.0 / v1 if v1 > 0 else 0
        fast_pace = 1000.0 / v2 if v2 and v2 > 0 else 0
        mid = (slow_pace + fast_pace) / 2
        m, s = divmod(int(mid), 60)
        return f"~{m}:{s:02d}/km"

    return "—"


def _workout_step_role(step: dict) -> str:
    """Classify step: warmup | ramp_up | main | buffer_lap | recovery_lap | other."""
    ec = (step.get("endCondition") or {}).get("conditionTypeKey")
    if ec == "lap.button":
        st = (step.get("stepType") or {}).get("stepTypeKey")
        return "recovery_lap" if st == "cooldown" else "buffer_lap"
    st = (step.get("stepType") or {}).get("stepTypeKey")
    if st == "warmup":
        return "warmup"
    tt = (step.get("targetType") or {}).get("workoutTargetTypeKey")
    if tt == "heart.rate.zone" or step.get("zoneNumber") is not None:
        return "main"
    return "ramp_up"


def _labels_for_workout_steps(workout_steps: list[dict]) -> tuple[list[str], list[bool]]:
    """Human labels and is_main flags aligned with workout_steps order."""
    labels: list[str] = []
    is_coeur_flags: list[bool] = []
    coeur_idx = 0
    prev_zone: int | None = None
    for step in workout_steps:
        role = _workout_step_role(step)
        zn = step.get("zoneNumber")
        z = int(zn) if zn is not None else None

        if role == "warmup":
            labels.append(step.get("description") or "Warm-up")
            is_coeur_flags.append(False)
        elif role == "ramp_up":
            labels.append(step.get("description") or "Ramp-up")
            is_coeur_flags.append(False)
        elif role == "buffer_lap":
            labels.append(step.get("description") or "Buffer (lap)")
            is_coeur_flags.append(False)
        elif role == "recovery_lap":
            labels.append(step.get("description") or "Recovery (lap)")
            is_coeur_flags.append(False)
        elif role == "main":
            coeur_idx += 1
            if coeur_idx == 1:
                labels.append("Main")
            elif z is not None and prev_zone is not None and z != prev_zone:
                labels.append(f"Finish (Z{z})")
            else:
                labels.append(f"Main ({coeur_idx})")
            is_coeur_flags.append(True)
            prev_zone = z
        else:
            labels.append("Block")
            is_coeur_flags.append(False)

    return labels, is_coeur_flags


def extract_workout_segments(typed_splits: dict, workout_steps: list[dict] | None = None) -> list[dict]:
    """Extract workout segments with targets from typed splits + workout definition."""
    splits = typed_splits.get("splits", [])
    interval_types = {"INTERVAL_WARMUP", "INTERVAL_ACTIVE", "INTERVAL_COOLDOWN"}
    segments = [s for s in splits if s.get("type") in interval_types]
    if not segments:
        return []

    step_targets = []
    if workout_steps:
        for step in workout_steps:
            step_targets.append(_format_step_target(step))

    use_labels = (
        workout_steps
        and len(workout_steps) == len(segments)
        and len(segments) > 0
    )
    if use_labels:
        labels, is_coeur_flags = _labels_for_workout_steps(workout_steps)
    else:
        labels, is_coeur_flags = [], []

    active_fallback = 0
    result = []
    for i, seg in enumerate(segments):
        seg_type = seg.get("type", "")
        if use_labels and i < len(labels):
            label = labels[i]
            is_coeur = is_coeur_flags[i]
        else:
            tgt = step_targets[i] if i < len(step_targets) else ""
            if seg_type == "INTERVAL_ACTIVE":
                active_fallback += 1
                label = f"Block {active_fallback}"
                is_coeur = "Zone" in (tgt or "")
            elif seg_type == "INTERVAL_COOLDOWN":
                label = "Recovery"
                is_coeur = False
            else:
                label = "Warm-up"
                is_coeur = False
        target = step_targets[i] if i < len(step_targets) else "—"

        result.append({
            "label": label,
            "target": target,
            "is_coeur": is_coeur,
            "distance": seg.get("distance"),
            "duration": seg.get("duration"),
            "averageSpeed": seg.get("averageSpeed"),
            "averageHR": seg.get("averageHR"),
            "elevationGain": seg.get("elevationGain"),
        })

    return result


def compute_km_splits(details: dict) -> list[dict]:
    """Compute per-km splits from activity detail metrics (point-by-point data)."""
    descriptors = details.get("metricDescriptors", [])
    samples = details.get("activityDetailMetrics", [])
    if not descriptors or not samples:
        return []

    key_to_idx = {d["key"]: i for i, d in enumerate(descriptors)}
    dist_idx = key_to_idx.get("sumDistance")
    dur_idx = key_to_idx.get("sumElapsedDuration")
    hr_idx = key_to_idx.get("directHeartRate")
    elev_idx = key_to_idx.get("directElevation")
    speed_idx = key_to_idx.get("directSpeed")

    if dist_idx is None or dur_idx is None:
        return []

    splits = []
    km_boundary = 1000.0
    split_start_dist = 0.0
    split_start_dur = 0.0
    split_start_elev = None
    hr_values = []
    speed_values = []

    for sample in samples:
        m = sample.get("metrics", [])
        dist = m[dist_idx] if dist_idx < len(m) else None
        dur = m[dur_idx] if dur_idx < len(m) else None
        hr = m[hr_idx] if hr_idx is not None and hr_idx < len(m) else None
        elev = m[elev_idx] if elev_idx is not None and elev_idx < len(m) else None
        spd = m[speed_idx] if speed_idx is not None and speed_idx < len(m) else None

        if dist is None or dur is None:
            continue

        if split_start_elev is None and elev is not None:
            split_start_elev = elev

        if hr is not None and hr > 0:
            hr_values.append(hr)
        if spd is not None and spd > 0:
            speed_values.append(spd)

        if dist >= km_boundary:
            split_dist = km_boundary - split_start_dist
            split_dur = dur - split_start_dur
            avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
            avg_speed = sum(speed_values) / len(speed_values) if speed_values else None
            elev_gain = max(0, elev - split_start_elev) if elev is not None and split_start_elev is not None else None

            splits.append({
                "distance": split_dist,
                "duration": split_dur,
                "averageSpeed": avg_speed,
                "averageHR": avg_hr,
                "elevationGain": elev_gain,
            })

            split_start_dist = km_boundary
            split_start_dur = dur
            split_start_elev = elev
            hr_values = []
            speed_values = []
            km_boundary += 1000.0

    # Last partial km
    last_dist = None
    last_dur = None
    for sample in reversed(samples):
        m = sample.get("metrics", [])
        d = m[dist_idx] if dist_idx < len(m) else None
        t = m[dur_idx] if dur_idx < len(m) else None
        if d is not None and t is not None:
            last_dist = d
            last_dur = t
            break

    if last_dist is not None and last_dist > split_start_dist + 50:
        split_dist = last_dist - split_start_dist
        split_dur = last_dur - split_start_dur
        avg_hr = sum(hr_values) / len(hr_values) if hr_values else None
        avg_speed = sum(speed_values) / len(speed_values) if speed_values else None
        splits.append({
            "distance": split_dist,
            "duration": split_dur,
            "averageSpeed": avg_speed,
            "averageHR": avg_hr,
            "elevationGain": None,
        })

    return splits


def format_activity_md(act: dict, km_splits: list, hr_zones: list | None, workout_segments: list | None = None, comment: str | None = None) -> str:
    """Format a single activity as a markdown document."""
    lines = []

    name = act.get("activityName", "Untitled")
    act_type = act.get("activityType", {}).get("typeKey", "unknown")
    start = act.get("startTimeLocal", "—")
    duration = fmt_duration(act.get("duration"))
    distance = fmt_dist(act.get("distance"))
    avg_speed = act.get("averageSpeed")
    avg_pace = fmt_pace(avg_speed)
    max_speed = act.get("maxSpeed")
    max_pace = fmt_pace(max_speed)
    avg_hr = act.get("averageHR")
    max_hr = act.get("maxHR")
    calories = act.get("calories")
    elev_gain = act.get("elevationGain")
    elev_loss = act.get("elevationLoss")
    avg_cadence = act.get("averageRunningCadenceInStepsPerMinute")
    training_effect_aerobic = act.get("aerobicTrainingEffect")
    training_effect_anaerobic = act.get("anaerobicTrainingEffect")
    vo2max = act.get("vO2MaxValue")

    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"- **Type**: {act_type}")
    lines.append(f"- **Date**: {start}")
    lines.append(f"- **Duration**: {duration}")
    lines.append(f"- **Distance**: {distance}")
    lines.append(f"- **Avg pace**: {avg_pace}")
    lines.append(f"- **Max pace**: {max_pace}")

    if avg_hr:
        lines.append(f"- **Avg HR**: {avg_hr} bpm")
    if max_hr:
        lines.append(f"- **Max HR**: {max_hr} bpm")
    if calories:
        lines.append(f"- **Calories**: {calories} kcal")
    if elev_gain is not None:
        lines.append(f"- **Elevation gain**: {elev_gain:.0f} m")
    if elev_loss is not None:
        lines.append(f"- **Elevation loss**: {elev_loss:.0f} m")
    if avg_cadence:
        lines.append(f"- **Avg cadence**: {avg_cadence:.0f} spm")
    if training_effect_aerobic:
        lines.append(f"- **Aerobic training effect**: {training_effect_aerobic:.1f}")
    if training_effect_anaerobic:
        lines.append(f"- **Anaerobic training effect**: {training_effect_anaerobic:.1f}")
    if vo2max:
        lines.append(f"- **VO2max**: {vo2max}")

    if workout_segments:
        coeur_secs = sum(s.get("duration", 0) for s in workout_segments if s.get("is_coeur"))
        if coeur_secs > 0:
            lines.append(f"- **Main set time**: {fmt_duration(coeur_secs)}")

    if comment:
        lines.append("")
        lines.append("## Notes")
        lines.append("")
        for cline in comment.split("\n"):
            lines.append(f"> {cline}")

    if hr_zones:
        lines.append("")
        lines.append("## Time in HR zones")
        lines.append("")
        lines.append("| Zone | Range (bpm) | Time | % |")
        lines.append("|------|-------------|-------|---|")
        total_secs = sum(z.get("secsInZone", 0) for z in hr_zones)
        for i, z in enumerate(hr_zones):
            zone_num = z.get("zoneNumber", i + 1)
            lo = z.get("zoneLowBoundary", "?")
            if i + 1 < len(hr_zones):
                hi = hr_zones[i + 1].get("zoneLowBoundary", "?")
            else:
                hi = "max"
            secs = z.get("secsInZone", 0)
            pct = (secs / total_secs * 100) if total_secs > 0 else 0
            lines.append(f"| Z{zone_num} | {lo}–{hi} | {fmt_duration(secs)} | {pct:.0f}% |")

    if workout_segments and len(workout_segments) >= 2:
        lines.append("")
        lines.append("## Workout segments")
        lines.append("")
        lines.append("| Segment | Target | Duration | Distance | Pace | Avg HR |")
        lines.append("|---------|----------|-------|----------|--------|---------|")
        for seg in workout_segments:
            s_label = seg["label"]
            s_target = seg.get("target", "—")
            s_dur = fmt_duration(seg.get("duration"))
            s_dist = fmt_dist(seg.get("distance"))
            s_pace = fmt_pace(seg.get("averageSpeed"))
            s_hr = f'{seg["averageHR"]:.0f}' if seg.get("averageHR") else "—"
            lines.append(f"| {s_label} | {s_target} | {s_dur} | {s_dist} | {s_pace} | {s_hr} |")

    if km_splits:
        lines.append("")
        lines.append("## Splits per km")
        lines.append("")
        lines.append("| km | Duration | Pace | Avg HR |")
        lines.append("|----|-------|--------|---------|")
        for i, s in enumerate(km_splits, 1):
            s_dur = fmt_duration(s.get("duration"))
            s_pace = fmt_pace(s.get("averageSpeed"))
            s_hr = f'{s["averageHR"]:.0f}' if s.get("averageHR") else "—"
            dist_m = s.get("distance", 0)
            label = f"{i}" if dist_m >= 950 else f"{i} ({dist_m:.0f}m)"
            lines.append(f"| {label} | {s_dur} | {s_pace} | {s_hr} |")

    lines.append("")
    lines.append("---")
    lines.append(f"*Garmin Activity ID: {act.get('activityId')}*")

    return "\n".join(lines)


def build_index(activities: list[dict], coeur_by_id: dict[int, float] | None = None) -> str:
    """Build an index.md with a summary table."""
    coeur_by_id = coeur_by_id or {}
    lines = []
    lines.append("# Recent activities")
    lines.append("")
    lines.append("| Date | Type | Duration | Main set | Distance | Pace | Avg HR | Elev. gain |")
    lines.append("|------|------|-------|------|----------|--------|---------|-----|")

    for act in activities:
        dt = act.get("startTimeLocal", "—")[:10]
        act_type = act.get("activityType", {}).get("typeKey", "?")
        duration = fmt_duration(act.get("duration"))
        distance = fmt_dist(act.get("distance"))
        pace = fmt_pace(act.get("averageSpeed"))
        hr = act.get("averageHR", "—")
        elev = act.get("elevationGain")
        elev_str = f"{elev:.0f} m" if elev is not None else "—"
        coeur_secs = coeur_by_id.get(act.get("activityId"))
        coeur_str = fmt_duration(coeur_secs) if coeur_secs else "—"
        lines.append(f"| {dt} | {act_type} | {duration} | {coeur_str} | {distance} | {pace} | {hr} | {elev_str} |")

    lines.append("")
    lines.append(f"*Last sync: {date.today().isoformat()}*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Sync recent Garmin activities to markdown")
    parser.add_argument("--days", type=int, default=15, help="Number of days to look back (default 15)")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="After writing files, git add activities/*.md and commit from the data root ($MEMORY_DIR/fitness).",
    )
    parser.add_argument("--comment", type=str, help="User comment for a specific session")
    parser.add_argument(
        "--comment-date",
        type=str,
        default=None,
        help="Date for the comment (YYYY-MM-DD, default: today)",
    )
    args = parser.parse_args()

    if args.comment:
        comment_date = args.comment_date or date.today().isoformat()
        save_comment(comment_date, args.comment)
        print(f"Comment saved for {comment_date}.")

    client = login()

    end_date = date.today()
    start_date = end_date - timedelta(days=args.days)
    print(f"Fetching activities from {start_date} to {end_date}...")

    activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())

    if not activities:
        print("No activities found.")
        return

    print(f"Found {len(activities)} activities.")
    ACTIVITIES_DIR.mkdir(parents=True, exist_ok=True)

    comments = load_comments()
    coeur_by_id: dict[int, float] = {}
    written_paths: list[Path] = []

    for act in activities:
        act_id = act.get("activityId")
        act_type = act.get("activityType", {}).get("typeKey", "unknown")
        dt = act.get("startTimeLocal", "unknown")[:10]

        km_splits = []
        hr_zones = None
        workout_segments = []

        try:
            details = client.get_activity_details(act_id)
            km_splits = compute_km_splits(details)
        except Exception:
            pass

        try:
            typed_splits = client.get_activity_typed_splits(act_id)
            workout_steps = None
            workout_id = act.get("workoutId")
            if workout_id:
                try:
                    w = client.get_workout_by_id(workout_id)
                    segs = w.get("workoutSegments", [])
                    workout_steps = segs[0].get("workoutSteps", []) if segs else []
                except Exception:
                    pass
            workout_segments = extract_workout_segments(typed_splits, workout_steps)
        except Exception:
            pass

        coeur_secs = sum(s.get("duration", 0) for s in workout_segments if s.get("is_coeur"))
        if coeur_secs > 0:
            coeur_by_id[act_id] = coeur_secs

        try:
            hr_zones = client.get_activity_hr_in_timezones(act_id)
        except Exception:
            pass

        comment = comments.get(dt)
        md = format_activity_md(act, km_splits, hr_zones, workout_segments, comment)
        filename = f"{dt}_{act_type}_{act_id}.md"
        out_path = ACTIVITIES_DIR / filename
        out_path.write_text(md)
        written_paths.append(out_path)
        print(f"  {filename}")

    index_md = build_index(activities, coeur_by_id)
    index_path = ACTIVITIES_DIR / "index.md"
    index_path.write_text(index_md)
    written_paths.append(index_path)
    print(f"\nIndex written to {index_path}")

    comments_yaml = ACTIVITIES_DIR / "comments.yaml"
    if comments_yaml.is_file():
        written_paths.append(comments_yaml)

    if args.commit:
        git_commit_activities(written_paths, len(activities))

    print("Done.")


if __name__ == "__main__":
    main()
