---
name: route-generator
description: Generate round-trip GPS running routes as GPX files plus interactive and static maps using OpenRouteService. Use when the user asks to generate a route, running loop, map, or GPX for a running workout, or wants to visualize a running loop.
---

# Route Generator

Generate round-trip running routes as GPX files + maps using OpenRouteService. Routes start and end at a configured point (usually home) and prefer trails and quiet paths.

## Configuration

Persistent user data lives under **`MEMORY_DIR`** (default `$HOME/.memory`). Output files are written to `$MEMORY_DIR/fitness/routes/`; the script creates it if missing.

The **start point is required** and never hardcoded:

- `--lat` / `--lon` on the command line, or
- `HOME_LAT` / `HOME_LON` environment variables (decimal degrees), also read from a `.env` file in the current directory or `$MEMORY_DIR/fitness/.env`.

If neither is set the script exits with an error. Never write real coordinates into skill files, examples or commits.

Scripts are referenced by paths **relative to this skill directory**.

## Prerequisites

- **`uv`** for the Python environment. First run:
  ```bash
  uv venv && uv pip install -r requirements.txt
  ```
- **Secrets:** requires `ORS_API_KEY` (free key from [openrouteservice.org](https://openrouteservice.org/dev/#/signup); free tier is about 2000 requests/day). Export it or put it in one of the `.env` files above.

## Usage

```bash
# Basic route from HOME_LAT / HOME_LON
uv run scripts/generate_route.py \
  --duration 25 --pace "7:00" --name "short run"

# Different loop shape (change the seed)
uv run scripts/generate_route.py \
  --duration 35 --pace "7:00" --name "long run" --seed 123

# Explicit start point (placeholder values), don't open the image afterwards
uv run scripts/generate_route.py \
  --duration 30 --pace "6:30" --lat 0.0 --lon 0.0 --no-open
```

## How distance is calculated

Total duration × pace = distance (you're moving the whole time: warm-up is an easy jog, recovery a walk). Example: 25 min @ 7:00/km → ~3.6 km.

## Output

Files are saved in `$MEMORY_DIR/fitness/routes/`:
- **GPX**: `<date>_<name>.gpx` — importable into Garmin Connect (Training > Courses > Import)
- **PNG**: `<date>_<name>.png` — static map cropped to the route, opened automatically unless `--no-open`
- **HTML**: `<date>_<name>.html` — interactive Leaflet map

Both maps show the route trace (red), start/finish marker (green), halfway marker (orange), and distance, duration, pace and elevation gain/loss.

## Route characteristics

- Profile: `foot-hiking` with `green` + `quiet` weightings → prefers trails and calm paths
- Shape: loop
- `--seed` produces different loop shapes for the same distance

## Garmin integration

`python-garminconnect` has no method to upload courses. To get the route on the watch: in Garmin Connect web, go to Training > Courses > Import, upload the GPX, then sync the watch. Or just check the HTML map before heading out.
