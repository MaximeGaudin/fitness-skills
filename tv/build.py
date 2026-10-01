#!/usr/bin/env python3
"""
Build the TV companion page from a WOD YAML file.

Usage:
    python build.py [path/to/wod.yaml] [--data-dir DIR] [--exercises-dir DIR]
                    [--equipment FILE] [--out FILE] [--serve] [--deploy]

Defaults (all overridable):
    FITNESS_DIR     = $FITNESS_DIR, else $MEMORY_DIR/fitness, else ~/.memory/fitness
    wod             = most recent *.yaml in $FITNESS_DIR/wods/
    --data-dir      = $FITNESS_DIR/data
    --exercises-dir = <data-dir>/exercises
    --equipment     = <data-dir>/equipment.yaml
    --out           = tv/dist/index.html (next to this script)

--serve   start a local HTTP server on port 8080 after building
--deploy  publish the output folder to Cloudflare Pages with `wrangler`
          (requires CLOUDFLARE_PAGES_PROJECT in the environment)
"""

import argparse
import html as html_mod
import json
import os
import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

TV_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = TV_DIR / "templates"
DEFAULT_OUT = TV_DIR / "dist" / "index.html"


def default_fitness_dir() -> Path:
    if os.environ.get("FITNESS_DIR"):
        return Path(os.environ["FITNESS_DIR"]).expanduser()
    memory = os.environ.get("MEMORY_DIR") or os.path.expanduser("~/.memory")
    return Path(memory).expanduser() / "fitness"


# Set by main() from CLI flags.
EXERCISES_DIR: Path = Path()
EQUIPMENT_PATH: Path = Path()


def extract_youtube_id(url: str) -> str:
    if not url:
        return ""
    m = re.search(r'(?:v=|youtu\.be/)([\w-]{11})', url)
    return m.group(1) if m else ""


def _name(d: dict, fallback: str = "") -> str:
    """Display name: English name first, then the generic name keys."""
    return d.get("name_en") or d.get("nom_en") or d.get("name") or d.get("nom") or fallback


def load_equipment_catalog() -> dict:
    """Return {equipment_id: item} from the equipment YAML (key `equipment` or `equipement`)."""
    if not EQUIPMENT_PATH.exists():
        return {}
    with open(EQUIPMENT_PATH) as f:
        data = yaml.safe_load(f) or {}
    items = data.get("equipment") or data.get("equipement") or []
    return {item["id"]: item for item in items if item.get("id")}


def _label(catalog: dict, eid: str) -> str:
    item = catalog.get(eid)
    if item:
        return _name(item, eid)
    return eid.replace("-", " ").title()


def _barbell_ids(catalog: dict) -> set:
    return {eid for eid, item in catalog.items() if item.get("barbell")}


def collect_equipment_ids(wod: dict, catalog: dict) -> list:
    """Equipment ids used by the session, minus items flagged `always_out: true`."""
    always_out = {eid for eid, item in catalog.items() if item.get("always_out")}
    ids = set()

    def add_from_data(data: dict):
        for x in (data or {}).get("equipement") or (data or {}).get("equipment") or []:
            if x and x not in always_out:
                ids.add(x)

    for ex in wod.get("warmup", {}).get("exercises", []):
        if ex.get("id") and ex.get("_data"):
            add_from_data(ex["_data"])

    for block in wod.get("blocks", []):
        if block.get("type") == "technical" and block.get("exercise_id"):
            data = block.get("_exercise_data") or load_exercise(block["exercise_id"])
            add_from_data(data)
        for ex in block.get("exercises", []):
            if ex.get("id"):
                data = ex.get("_data") or load_exercise(ex["id"])
                add_from_data(data)

    return sorted(ids, key=lambda i: _label(catalog, i))


def _format_duration(ex: dict) -> str | None:
    """Human-readable duration from duration_minutes or duration_seconds."""
    if ex.get("duration_minutes"):
        secs = int(ex["duration_minutes"] * 60)
    elif ex.get("duration_seconds"):
        secs = int(ex["duration_seconds"])
    else:
        return None
    if secs >= 60 and secs % 60 == 0:
        return f"{secs // 60} min"
    if secs >= 60:
        return f"{secs // 60}min {secs % 60}s"
    return f"{secs}s"


def _prescription(ex: dict) -> str:
    """Build the prescription label for an exercise."""
    if ex.get("reps"):
        label = f'{ex["reps"]} reps'
    else:
        label = _format_duration(ex) or "—"
    if ex.get("weight_kg"):
        label += f' @ {ex["weight_kg"]}kg'
    return label


def _split_exercises(exercises: list) -> tuple[list, list]:
    for i, ex in enumerate(exercises, 1):
        ex["index"] = i
    n = len(exercises)
    mid = (n + 1) // 2
    return exercises[:mid], exercises[mid:]


def _strategy_lines(block: dict) -> list:
    raw = (block.get("strategy") or "").strip()
    if not raw:
        return []
    return [ln for ln in raw.splitlines() if ln.strip()]


def load_exercise(exercise_id: str) -> dict:
    path = EXERCISES_DIR / f"{exercise_id}.yaml"
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    print(f"  warning: no exercise file for '{exercise_id}' in {EXERCISES_DIR}")
    return {"id": exercise_id, "nom": exercise_id, "nom_en": exercise_id}


def resolve_wod_exercises(wod: dict) -> dict:
    """Enrich WOD data with exercise details for the HTML template."""
    exercise_cache = {}

    def get_ex(eid):
        if eid not in exercise_cache:
            exercise_cache[eid] = load_exercise(eid)
        return exercise_cache[eid]

    if "warmup" in wod and "exercises" in wod["warmup"]:
        for ex in wod["warmup"]["exercises"]:
            if "id" in ex:
                ex["_data"] = get_ex(ex["id"])

    for block in wod.get("blocks", []):
        if block.get("type") == "technical" and "exercise_id" in block:
            block["_exercise_data"] = get_ex(block["exercise_id"])
        for ex in block.get("exercises", []) or []:
            if "id" in ex:
                ex["_data"] = get_ex(ex["id"])

    return wod


def find_latest_wod(wods_dir: Path) -> Path:
    yamls = sorted(wods_dir.glob("*.yaml"))
    if not yamls:
        print("No WOD files found in", wods_dir)
        sys.exit(1)
    return yamls[-1]


def _exercise_tile(ex: dict) -> dict:
    data = ex.get("_data", {})
    return {
        "name": _name(data) or _name(ex) or ex.get("id", "Exercise"),
        "image": data.get("image_url") or "",
        "prescription": _prescription(ex),
        "notes": ex.get("notes", ""),
        "cues": (data.get("cues") or [])[:2],
    }


def _build_setup_block(wod: dict, catalog: dict) -> dict:
    """Auto-generate a Setup block: equipment checklist + workout preview."""
    preview = []
    if "warmup" in wod:
        preview.append(f"Warm-up · {wod['warmup'].get('duration_minutes', 10)} min")
    for block in wod.get("blocks", []):
        bname = block.get("name", "Block")
        bdur = block.get("duration_minutes", "?")
        btype = block.get("type", "")
        if btype == "technical":
            preview.append(f"{bname} · {bdur} min (LAP)")
        elif btype == "AMRAP":
            preview.append(f"{bname} · AMRAP {bdur} min")
        elif btype == "EMOM":
            rounds = block.get("rounds", "?")
            preview.append(f"{bname} · EMOM {rounds} rounds / {bdur} min")
        else:
            preview.append(f"{bname} · {bdur} min")
    rb = wod.get("recovery_break") or {}
    preview.append(f"Recovery · {rb.get('duration_minutes', 3)} min")
    if "cooldown" in wod:
        preview.append(f"Cool-down · {wod['cooldown'].get('duration_minutes', 4)} min")
    preview.append(f"Total · ~{wod.get('total_duration_minutes', '?')} min")

    # Heaviest barbell load in the session (weight_kg = plates added to the bar).
    barbells = _barbell_ids(catalog)
    max_bar_weight = {}
    for block in wod.get("blocks", []):
        for ex in block.get("exercises", []) or []:
            eq = set((ex.get("_data") or {}).get("equipement") or [])
            for bid in eq & barbells:
                if ex.get("weight_kg"):
                    max_bar_weight[bid] = max(max_bar_weight.get(bid, 0), ex["weight_kg"])
        eq = set((block.get("_exercise_data") or {}).get("equipement") or [])
        for s in block.get("practice_sets", []) or []:
            for bid in eq & barbells:
                if s.get("weight_kg"):
                    max_bar_weight[bid] = max(max_bar_weight.get(bid, 0), s["weight_kg"])

    eq_items = []
    for eid in collect_equipment_ids(wod, catalog):
        notes = "Get out"
        if max_bar_weight.get(eid):
            w = max_bar_weight[eid]
            notes = f"Load {w}kg ({w / 2:g}kg/side)"
        eq_items.append({
            "name": _label(catalog, eid),
            "image": "",
            "prescription": "",
            "notes": notes,
            "cues": [],
        })
    el, er = _split_exercises(eq_items)
    return {
        "name": "Setup",
        "type": "manual",
        "duration_seconds": 0,
        "setup": True,
        "exercises": eq_items,
        "exercises_left": el,
        "exercises_right": er,
        "compact": False,
        "strategy_lines": preview,
    }


def build_blocks_json(wod: dict) -> list:
    """Build blocks for TV (passive phases — timing is on the watch)."""
    blocks = []
    catalog = load_equipment_catalog()

    blocks.append(_build_setup_block(wod, catalog))

    if "warmup" in wod:
        exercises = [_exercise_tile(ex) for ex in wod["warmup"].get("exercises", [])]
        left, right = _split_exercises(exercises)
        blocks.append({
            "name": "Warm-up",
            "type": "manual",
            "duration_seconds": 0,
            "exercises": exercises,
            "exercises_left": left,
            "exercises_right": right,
            "compact": True,
            "strategy_lines": [],
        })

    for block in wod.get("blocks", []):
        b = {
            "name": block.get("name", "Block"),
            "duration_seconds": block.get("duration_minutes", 10) * 60,
            "type": "manual",
            "strategy_lines": _strategy_lines(block),
        }

        if block.get("type") == "technical":
            data = block.get("_exercise_data", {})
            sets = []
            for i, s in enumerate(block.get("practice_sets", []), 1):
                w = f" @ {s['weight_kg']}kg" if s.get("weight_kg") else ""
                sets.append({
                    "name": f"Set {i}: {s['reps']} reps{w}",
                    "image": data.get("image_url") or "",
                    "prescription": f"{s['reps']} reps{w}",
                    "notes": s.get("notes", ""),
                    "cues": (data.get("cues") or [])[:2],
                })
            b["exercises"] = sets
            b["exercises_left"], b["exercises_right"] = _split_exercises(sets)
            b["video_url"] = data.get("video_url") or ""
            b["video_id"] = extract_youtube_id(b["video_url"])
        else:
            exercises = [_exercise_tile(ex) for ex in block.get("exercises", []) or []]
            b["exercises"] = exercises
            b["exercises_left"], b["exercises_right"] = _split_exercises(exercises)
            if block.get("type") == "EMOM":
                b["rounds"] = block.get("rounds", 10)
                b["interval_seconds"] = block.get("interval_seconds", 60)
                b["duration_seconds"] = b["rounds"] * b["interval_seconds"]
            else:
                n_ex = len(exercises)
                b["compact"] = n_ex >= 5
                b["dense"] = n_ex >= 7

        blocks.append(b)

    rb = wod.get("recovery_break") or {}
    rb_min = int(rb.get("duration_minutes", 3))
    rb_notes = rb.get("notes", "Drink, breathe. Start the recovery timer on your watch if needed.")

    cleanup = [{
        "name": _label(catalog, eid),
        "image": "",
        "prescription": "",
        "notes": "Put away",
        "cues": [],
    } for eid in collect_equipment_ids(wod, catalog)]
    rxl, rxr = _split_exercises(cleanup)
    blocks.append({
        "name": f"Recovery + Cleanup — {rb_min} min",
        "type": "manual",
        "duration_seconds": 0,
        "rangement": True,
        "exercises": cleanup,
        "exercises_left": rxl,
        "exercises_right": rxr,
        "compact": True,
        "strategy_lines": [rb_notes],
    })

    if "cooldown" in wod:
        exercises = []
        for ex in wod["cooldown"].get("exercises", []):
            sides = ex.get("sides", 1) or 1
            exercises.append({
                "name": _name(ex, "Stretch"),
                "image": "",
                "prescription": (_format_duration(ex) or "30s") + (f" x{sides}" if sides > 1 else ""),
                "notes": ex.get("notes", ""),
                "cues": [],
            })
        cl, cr = _split_exercises(exercises)
        blocks.append({
            "name": "Cool-down",
            "type": "manual",
            "duration_seconds": 0,
            "exercises": exercises,
            "exercises_left": cl,
            "exercises_right": cr,
            "compact": False,
            "strategy_lines": [],
        })

    return blocks


def build_html(wod: dict) -> str:
    blocks_data = build_blocks_json(wod)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    template = env.get_template("page.html")

    css = (TEMPLATES_DIR / "style.css").read_text()
    js = (TEMPLATES_DIR / "timer.js").read_text()

    block_names = json.dumps([b["name"] for b in blocks_data], ensure_ascii=False)
    block_has_video = json.dumps([1 if b.get("video_url") else 0 for b in blocks_data])

    js_vars = (
        f"var BLOCK_NAMES = {block_names};\n"
        f"var BLOCK_HAS_VIDEO = {block_has_video};\n"
    )

    return template.render(
        title=html_mod.escape(str(wod.get("title", "WOD"))),
        date=html_mod.escape(str(wod.get("date", ""))),
        day=html_mod.escape(str(wod.get("day", "")).capitalize()),
        format=html_mod.escape(str(wod.get("format", "AMRAP"))),
        total_duration=wod.get("total_duration_minutes", 30),
        muscles=html_mod.escape(", ".join(wod.get("summary", {}).get("target_muscles", []))),
        blocks=blocks_data,
        css=css,
        js=js_vars + js,
    )


def deploy(out_dir: Path):
    import subprocess

    project = os.environ.get("CLOUDFLARE_PAGES_PROJECT")
    if not project:
        print("Deploy skipped: set CLOUDFLARE_PAGES_PROJECT to your Cloudflare Pages project name.")
        sys.exit(1)

    result = subprocess.run(
        ["wrangler", "pages", "deploy", str(out_dir),
         "--project-name", project,
         "--branch", "main",
         "--commit-dirty=true"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Deploy failed:\n{result.stderr}")
        sys.exit(1)

    for line in result.stdout.splitlines():
        if "Deployment complete" in line or "https://" in line:
            print(line.strip())


def serve(directory: Path, port: int = 8080):
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.HTTPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port}")
        httpd.serve_forever()


def main():
    global EXERCISES_DIR, EQUIPMENT_PATH

    parser = argparse.ArgumentParser(description="Build the TV companion page from a WOD YAML file.")
    parser.add_argument("wod", nargs="?", help="WOD YAML file (default: latest in $FITNESS_DIR/wods)")
    parser.add_argument("--data-dir", type=Path, help="Folder holding exercises/ and equipment.yaml")
    parser.add_argument("--exercises-dir", type=Path, help="Folder of exercise YAML files")
    parser.add_argument("--equipment", type=Path, help="Equipment YAML file")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output HTML file")
    parser.add_argument("--serve", action="store_true", help="Serve the output folder on :8080")
    parser.add_argument("--deploy", action="store_true", help="Deploy to Cloudflare Pages (wrangler)")
    args = parser.parse_args()

    fitness_dir = default_fitness_dir()
    data_dir = args.data_dir or fitness_dir / "data"
    EXERCISES_DIR = args.exercises_dir or data_dir / "exercises"
    EQUIPMENT_PATH = args.equipment or data_dir / "equipment.yaml"

    wod_path = Path(args.wod) if args.wod else find_latest_wod(fitness_dir / "wods")
    print(f"Building TV companion for: {wod_path.name}")

    with open(wod_path) as f:
        wod = yaml.safe_load(f)

    wod = resolve_wod_exercises(wod)
    html_content = build_html(wod)

    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_content)
    print(f"Generated: {out}")

    if args.deploy:
        deploy(out.parent)

    if args.serve:
        serve(out.parent)


if __name__ == "__main__":
    main()
