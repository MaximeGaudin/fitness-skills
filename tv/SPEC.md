# TV WOD Companion — Specification

## Overview

A single-page static web app displayed on a TV during home workouts. It shows the **active phase** (exercises, reps, weights, technical video) and progress dots. There is **no on-screen countdown**: timing runs on the watch. Built for maximum compatibility with old or limited TV browsers.

---

## Architecture

```
tv/
├── build.py              # Build script (+ optional serve / Cloudflare Pages deploy)
├── templates/
│   ├── page.html         # Jinja2 HTML template
│   ├── style.css         # All styles (inlined at build)
│   └── timer.js          # All logic (inlined at build)
├── dist/index.html       # Generated output (git-ignored)
├── requirements.txt      # Python deps (pyyaml, jinja2)
└── SPEC.md               # This file
```

**Data sources** (defaults under `$FITNESS_DIR`, i.e. `${MEMORY_DIR:-~/.memory}/fitness`):
- `wods/*.yaml` — WOD definitions (one per session, schema in `skills/wod-generator/wod-schema.md`)
- `data/exercises/*.yaml` — exercise catalog
- `data/equipment.yaml` — equipment labels and flags

The build produces a **single self-contained HTML file** with all CSS and JS inlined. No runtime dependencies except image URLs and the YouTube embed for technical blocks.

---

## Build

```bash
python tv/build.py [wod.yaml] [--data-dir DIR] [--exercises-dir DIR] [--equipment FILE] \
                   [--out FILE] [--serve] [--deploy]
```

| Flag | Behavior |
|------|----------|
| (no wod) | Builds the most recent `*.yaml` in `$FITNESS_DIR/wods/` |
| `--data-dir` | Folder with `exercises/` and `equipment.yaml` (default `$FITNESS_DIR/data`) |
| `--exercises-dir`, `--equipment` | Override each source individually |
| `--out` | Output file (default `tv/dist/index.html`) |
| `--serve` | Serves the output folder on port 8080 after building |
| `--deploy` | Publishes the output folder with `wrangler pages deploy` to the project named in `CLOUDFLARE_PAGES_PROJECT` |

Try it with the bundled examples:

```bash
uv run --with pyyaml --with jinja2 tv/build.py examples/wods/example.yaml \
  --exercises-dir examples/exercises --equipment examples/equipment.example.yaml --serve
```

### Steps

1. Load the WOD YAML
2. Resolve exercise references from the exercise catalog
3. Build the phase list: Setup, warm-up, YAML `blocks`, recovery + cleanup, cool-down
4. Render `page.html` with Jinja2, inlining `style.css` and `timer.js`
5. Write the output file (then optionally serve / deploy)

---

## Fields used from data files

Exercise file:
- `nom_en` (fallback `name`, `nom`) — displayed name
- `image_url` — thumbnail in exercise tiles
- `video_url` — YouTube embed for technical blocks
- `equipement` — equipment ids, used for the Setup and Cleanup checklists
- `cues` — first two kept in the data (not displayed yet)

Equipment file (`equipment:` list):
- `id`, `name` — checklist label
- `always_out: true` — never listed in Setup / Cleanup
- `barbell: true` — Setup shows "Load X kg (Y kg/side)" from the heaviest `weight_kg` used with it

---

## Frontend

### Compatibility constraints

The TV browser may be old. All code must be:
- **HTML**: basic elements only (`table`, `div`, `span`, `img`, `iframe`, `button`)
- **CSS**: no flexbox, no grid, no CSS variables, no animations/transitions. Uses `display: table`, `float`, `position: absolute`, hardcoded hex colors.
- **JS**: strictly ES5. No `const`/`let`, arrow functions, template literals, `padStart`, `forEach`/`map`, `e.code` or `addEventListener`. Uses `var`, `function`, `getElementById`, `innerHTML`, `onclick`, `onkeydown`, `keyCode`.

### Layout (1920x1080)

```
┌──────────────────────────────────────────────────────────┐
│ TOP BAR: Title | Clock | Day Date | FORMAT | Duration      │
├──────────────────────────────────────────────────────────┤
│ PHASE HEADER: BLOCK NAME                    ● ○ ○ ○ ○ ○   │
├──────────────────────────────────────────────────────────┤
│  [Strategy lines, if any]                                │
│  ┌─────────────────────┬─────────────────────┐           │
│  │ Col 1: exercises    │ Col 2: exercises    │           │
│  └─────────────────────┴─────────────────────┘           │
├──────────────────────────────────────────────────────────┤
│  [← Previous]                              [Next →]      │
└──────────────────────────────────────────────────────────┘
```

**Technical block:** optional strategy box, full-width YouTube iframe (autoplay + loop when shown), footer with the practice sets.

**Warm-up** uses compact rows (smaller type, no thumbnails).

**Cleanup:** two-column checklist of equipment used in the session.

Content is sized to fit the viewport; no scrolling expected.

### Video lazy-loading

YouTube iframes use `data-src` until the technical block is shown, so autoplay doesn't start on earlier phases.

### Phases (build order)

1. Setup (equipment checklist + session preview)
2. Warm-up
3. All YAML `blocks`
4. Recovery + Cleanup (`recovery_break` or defaults)
5. Cool-down
6. Session complete (after advancing past the last phase)

No countdown or auto-advance between phases.

### Controls

| Input | Action |
|-------|--------|
| Right arrow / Next | Next phase |
| Left arrow / Previous | Previous phase |

### Progress dots

One dot per phase. **Green** = done, **Red** = current, **Gray** = upcoming.

---

## Design tokens

| Token | Value | Usage |
|-------|-------|-------|
| Background | `#0a0a0f` | Page background |
| Panel BG | `#14141f` | Cards, top bar |
| Border | `#222` | Panel borders |
| Text | `#f0f0f0` | Primary text |
| Muted | `#7a8599` | Secondary text, notes |
| Accent red | `#e94560` | Block names, prescriptions, format badge |
| Accent green | `#4ecca3` | Next button, completed dots, cleanup accent |
| Dark fill | `#1c1c2e` | Inactive dots, placeholder thumbnails |
