# fitness-skills

Agent skills for a data-driven home-gym training loop: generate a daily WOD gated by what you've actually mastered, show it on a TV, push it to your Garmin watch, pull the results back for analysis, and generate running loops as GPX.

The skills are plain `SKILL.md` files plus small Python scripts. They work with [Claude Code](https://docs.claude.com/en/docs/claude-code) and [Cursor](https://cursor.com) (or any agent that supports the Agent Skills format).

## What's inside

| Path | What it does |
|------|--------------|
| `skills/wod-generator` | Plans the next WOD (AMRAP / EMOM) from your goal, equipment, mastery registry and past sessions, with exact loads and progressive overload. Writes a YAML file (`wod-schema.md`). |
| `skills/generate-crossfit-wod` | Fetches the official CrossFit.com WOD and adapts it to your equipment, mastery and loads, in the same YAML format. |
| `skills/garmin-workouts` | Pushes running (HR-zone) and strength workouts to Garmin Connect so they show up on the watch. |
| `skills/garmin-sync` | Downloads recent Garmin activities as markdown (HR zones, splits, workout segments) for the agent to analyse. |
| `skills/route-generator` | Builds round-trip running loops with OpenRouteService: GPX + PNG + interactive HTML map. |
| `tv/` | Turns a WOD YAML file into a single self-contained HTML page for a TV (setup checklist, warm-up, blocks, technical video, cleanup, cool-down). Works on old TV browsers (ES5, no flexbox). |
| `examples/` | Starter data: goal, equipment, mastery registry, personal records, 108 exercise sheets and two fictional WODs. |

## How the pieces fit together

```
goal.md + equipment.yaml + mastery.yaml + personal-records.yaml + exercises/
                │
                ▼
   wod-generator  /  generate-crossfit-wod  ──►  wods/YYYY-MM-DD.yaml
                                                      │
                          ┌───────────────────────────┼──────────────────────────┐
                          ▼                                                      ▼
                tv/build.py ──► HTML page on the TV                 garmin-workouts ──► watch
                                                                                     │
                                                          you train ◄────────────────┘
                                                              │
                                                              ▼
                                  garmin-sync ──► activities/*.md ──► analysis, next WOD

   route-generator ──► routes/*.gpx (+ maps) ──► Garmin Connect course import
```

1. You describe your goal, schedule and equipment once, and keep a registry of exercises you've mastered.
2. `wod-generator` (or `generate-crossfit-wod`) writes the day's session, only using mastered exercises, plus at most one new exercise in a "technical slot".
3. `tv/build.py` renders it for the TV; `garmin-workouts` puts the same structure on your watch, which does the timing.
4. `garmin-sync` brings the results back so the next WOD and load progression are based on what actually happened.

## Data layout

Your personal data never lives in this repository. Everything is read from and written to `$MEMORY_DIR/fitness` (default `~/.memory/fitness`):

```
$MEMORY_DIR/fitness/
├── goal.md                       ← examples/goal.example.md
├── mastery.yaml                  ← examples/mastery.example.yaml
├── data/
│   ├── equipment.yaml            ← examples/equipment.example.yaml
│   ├── personal-records.yaml     ← examples/personal-records.example.yaml
│   └── exercises/                ← examples/exercises/
├── wods/                         (written by the WOD skills)
├── activities/                   (written by garmin-sync)
└── routes/                       (written by route-generator)
```

Bootstrap it from the examples:

```bash
export MEMORY_DIR="$HOME/.memory"
F="$MEMORY_DIR/fitness"
mkdir -p "$F/data" "$F/wods"
cp examples/goal.example.md "$F/goal.md"
cp examples/mastery.example.yaml "$F/mastery.yaml"
cp examples/equipment.example.yaml "$F/data/equipment.yaml"
cp examples/personal-records.example.yaml "$F/data/personal-records.yaml"
cp -R examples/exercises "$F/data/exercises"
```

Then edit `goal.md`, `equipment.yaml` and `mastery.yaml` to match you. Making `$MEMORY_DIR/fitness` a git repository is a good idea (`garmin-sync --commit` uses it).

The bundled exercise sheets are written in French with an English display name (`nom_en`, which the TV shows). Field names are documented at the end of `skills/wod-generator/wod-schema.md`.

## Setup

Requirements: Python 3.10+ and [uv](https://docs.astral.sh/uv/).

Each script-based skill has its own `requirements.txt`. From the skill folder:

```bash
cd skills/garmin-sync && uv venv && uv pip install -r requirements.txt
cd ../garmin-workouts && uv venv && uv pip install -r requirements.txt
cd ../route-generator && uv venv && uv pip install -r requirements.txt
cd ../../tv && uv venv && uv pip install -r requirements.txt
```

Try the TV page with the examples (no account needed):

```bash
uv run --with pyyaml --with jinja2 tv/build.py examples/wods/example.yaml \
  --exercises-dir examples/exercises --equipment examples/equipment.example.yaml --serve
# open http://localhost:8080 and use the arrow keys
```

### Environment variables

See `.env.example`. Export them in your shell profile, or put the secrets in `$MEMORY_DIR/fitness/.env` (the scripts read a `.env` from the current directory or from there). `MEMORY_DIR` itself must be set in the environment, not in a `.env` file.

| Variable | Used by | Notes |
|----------|---------|-------|
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | garmin-sync, garmin-workouts | Your own Garmin Connect account. Tokens are cached in `~/.garminconnect/` |
| `ORS_API_KEY` | route-generator | Free key from openrouteservice.org |
| `HOME_LAT`, `HOME_LON` | route-generator | Start point of the loops (or pass `--lat` / `--lon`). Required, no default |
| `MEMORY_DIR` | all | Root of your personal data (default `~/.memory`) |
| `FITNESS_SKILLS_DIR` | wod-generator, generate-crossfit-wod | Path to this repository, to run `tv/build.py` |
| `CLOUDFLARE_PAGES_PROJECT` | `tv/build.py --deploy` | Optional, if you host the TV page on Cloudflare Pages |

## Install the skills

### Claude Code

Skills live in `~/.claude/skills/<name>/` (user-wide) or `.claude/skills/<name>/` (per project). Symlink them so `git pull` keeps them up to date:

```bash
mkdir -p ~/.claude/skills
for s in skills/*/; do ln -s "$(pwd)/$s" ~/.claude/skills/"$(basename "$s")"; done
```

Or copy them instead: `cp -R skills/* ~/.claude/skills/`.

### Cursor

Cursor reads Agent Skills from `.cursor/skills/` in a project (or `~/.cursor/skills/` user-wide):

```bash
mkdir -p ~/.cursor/skills
for s in skills/*/; do ln -s "$(pwd)/$s" ~/.cursor/skills/"$(basename "$s")"; done
```

Then ask the agent things like "plan tomorrow's WOD", "adapt today's CrossFit WOD", "push this week's runs to my Garmin", "sync my Garmin activities", or "generate a 30-minute running loop".

## Disclaimers

- **Unofficial Garmin API.** `garmin-sync` and `garmin-workouts` use [`garminconnect`](https://github.com/cyberjunky/python-garminconnect), an unofficial library that talks to Garmin Connect with your own credentials. It is not affiliated with or endorsed by Garmin, may break when Garmin changes things, and you are responsible for complying with Garmin's terms of use. Keep your credentials out of git.
- **Not medical advice.** These tools generate training suggestions automatically. They are not a substitute for a qualified coach or a doctor. Check with a medical professional before starting a new training program, and stop if something hurts.
- CrossFit is a trademark of CrossFit, LLC. This project is not affiliated with CrossFit.

## License

MIT, see [LICENSE](LICENSE).
