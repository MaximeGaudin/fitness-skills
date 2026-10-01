"""Generate a round-trip running route as GPX + PNG image + interactive HTML map.

Uses OpenRouteService (foot-hiking, green+quiet weightings) to create
trail-preferring loops from a given start point.

The start point comes from --lat/--lon, or from the HOME_LAT / HOME_LON
environment variables (also read from a .env file). There is no default.

Usage:
    python generate_route.py \
        --duration 25 --pace "7:00" \
        [--lat 0.0 --lon 0.0] [--seed 42] [--name "long run"] [--no-open]

Output (in $MEMORY_DIR/fitness/routes/):
    - <date>_<name>.gpx   — importable into Garmin Connect
    - <date>_<name>.png   — static map image cropped to the route
    - <date>_<name>.html  — interactive Leaflet map
"""

import argparse
import os
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path

import folium
import gpxpy
import gpxpy.gpx
import openrouteservice
from PIL import Image, ImageDraw, ImageFont
from staticmap import CircleMarker, Line, StaticMap

MEMORY_DIR = Path(
    os.environ.get("MEMORY_DIR", os.path.expanduser("~/.memory"))
)
DATA_ROOT = MEMORY_DIR / "fitness"
ROUTES_DIR = DATA_ROOT / "routes"


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


def compute_distance_m(duration_min: int, pace_str: str) -> float:
    """Estimate total running distance from duration and pace.

    Uses the full duration since you're moving the entire time
    (warmup = easy jog, recovery = walk).
    """
    total_secs = duration_min * 60
    parts = pace_str.split(":")
    pace_secs_per_km = int(parts[0]) * 60 + int(parts[1])
    return (total_secs / pace_secs_per_km) * 1000.0


def resolve_start(lat_arg: float | None, lon_arg: float | None) -> tuple[float, float]:
    """Return the start point as (lon, lat) from CLI args or HOME_LAT / HOME_LON.

    Exits with a clear error if neither source provides both coordinates.
    """
    lat = lat_arg if lat_arg is not None else os.getenv("HOME_LAT")
    lon = lon_arg if lon_arg is not None else os.getenv("HOME_LON")
    if lat in (None, "") or lon in (None, ""):
        print(
            "ERROR: no start point. Pass --lat/--lon or set HOME_LAT and HOME_LON "
            "(environment or .env file)."
        )
        sys.exit(1)
    try:
        lat_f, lon_f = float(lat), float(lon)
    except ValueError:
        print(f"ERROR: invalid coordinates lat={lat!r} lon={lon!r} (expected decimal degrees)")
        sys.exit(1)
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        print(f"ERROR: coordinates out of range: lat={lat_f} lon={lon_f}")
        sys.exit(1)
    return lon_f, lat_f


def fetch_route(
    client: openrouteservice.Client,
    start: tuple[float, float],
    distance_m: float,
    seed: int = 42,
):
    """Call ORS round_trip directions for a loop from `start` (lon, lat).

    Points scale with distance: more waypoints force ORS to build a
    complex loop through smaller paths instead of taking main roads.
    """
    points = max(3, min(8, int(distance_m / 2000)))
    return client.directions(
        coordinates=[list(start)],
        profile="foot-hiking",
        options={
            "round_trip": {
                "length": distance_m,
                "points": points,
                "seed": seed,
            },
            "profile_params": {
                "weightings": {"green": 1, "quiet": 1},
            },
            "avoid_features": ["ferries", "steps"],
        },
        elevation=True,
        format="geojson",
    )


def route_to_gpx(geojson_route) -> gpxpy.gpx.GPX:
    """Convert ORS GeoJSON response to a GPX object."""
    gpx = gpxpy.gpx.GPX()
    gpx.name = "Running route"
    track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(track)
    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    coords = geojson_route["features"][0]["geometry"]["coordinates"]
    for lon, lat, *rest in coords:
        ele = rest[0] if rest else None
        segment.points.append(gpxpy.gpx.GPXTrackPoint(lat, lon, elevation=ele))

    return gpx


def compute_elevation(coords) -> tuple[float, float]:
    """Compute total ascent and descent from 3D coordinates."""
    ascent = 0.0
    descent = 0.0
    for i in range(1, len(coords)):
        prev_ele = coords[i - 1][2] if len(coords[i - 1]) > 2 else 0
        curr_ele = coords[i][2] if len(coords[i]) > 2 else 0
        diff = curr_ele - prev_ele
        if diff > 0:
            ascent += diff
        else:
            descent -= diff
    return ascent, descent


def build_image(
    coords,
    distance_m: float,
    duration_min: int,
    pace_str: str,
    ascent: float,
    descent: float,
) -> Image.Image:
    """Render the route to a static PNG map image."""
    tile_url = "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png"
    m = StaticMap(800, 800, url_template=tile_url, tile_size=512)

    lonlats = [(lon, lat) for lon, lat, *_ in coords]
    m.add_line(Line(lonlats, "#e63946", 4))

    m.add_marker(CircleMarker(lonlats[0], "#2d6a4f", 10))
    mid_idx = len(lonlats) // 2
    m.add_marker(CircleMarker(lonlats[mid_idx], "#e76f51", 10))

    img = m.render()

    banner_h = 54
    final = Image.new("RGB", (img.width, img.height + banner_h), "white")
    final.paste(img, (0, 0))

    draw = ImageDraw.Draw(final)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except OSError:
        font = ImageFont.load_default()

    text = (
        f"{distance_m / 1000:.1f} km  ·  {duration_min} min  ·  {pace_str}/km"
        f"  ·  D+ {ascent:.0f} m / D- {descent:.0f} m"
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (final.width - tw) // 2
    y = img.height + (banner_h - (bbox[3] - bbox[1])) // 2
    draw.text((x, y), text, fill="#333333", font=font)

    return final


def build_html(
    coords,
    distance_m: float,
    duration_min: int,
    pace_str: str,
    ascent: float,
    descent: float,
) -> folium.Map:
    """Build an interactive Folium/Leaflet map with the route trace."""
    latlngs = [(lat, lon) for lon, lat, *_ in coords]
    center = latlngs[len(latlngs) // 2]
    m = folium.Map(location=center, zoom_start=14, tiles="CartoDB Voyager")

    folium.PolyLine(latlngs, color="#e63946", weight=4, opacity=0.85).add_to(m)

    folium.Marker(
        latlngs[0],
        popup="Start / Finish",
        icon=folium.Icon(color="green", icon="home", prefix="fa"),
    ).add_to(m)

    mid_idx = len(latlngs) // 2
    folium.Marker(
        latlngs[mid_idx],
        popup="Halfway",
        icon=folium.Icon(color="orange", icon="rotate-left", prefix="fa"),
    ).add_to(m)

    legend_html = f"""
    <div style="position:fixed; bottom:30px; left:30px; z-index:1000;
                background:white; padding:12px 18px; border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.2); font-family:system-ui;">
        <b style="font-size:14px;">Route</b><br>
        <span>Distance: {distance_m / 1000:.1f} km</span><br>
        <span>Duration: {duration_min} min</span><br>
        <span>Pace: {pace_str}/km</span><br>
        <span>D+ {ascent:.0f} m / D- {descent:.0f} m</span>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    m.fit_bounds(folium.PolyLine(latlngs).get_bounds())

    return m


def open_file(path: Path) -> None:
    """Best-effort: open a file with the OS default viewer."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
        else:
            webbrowser.open(path.resolve().as_uri())
    except OSError:
        pass


def slugify(text: str) -> str:
    return text.lower().replace(" ", "-").replace("/", "")[:40]


def main():
    parser = argparse.ArgumentParser(description="Generate a round-trip running route")
    parser.add_argument("--duration", type=int, required=True, help="Total workout duration in minutes")
    parser.add_argument("--pace", required=True, help="Target pace as M:SS per km")
    parser.add_argument("--seed", type=int, default=42, help="ORS seed for route variation")
    parser.add_argument("--name", default="route", help="Name label for output files")
    parser.add_argument("--lat", type=float, default=None, help="Start latitude (overrides HOME_LAT)")
    parser.add_argument("--lon", type=float, default=None, help="Start longitude (overrides HOME_LON)")
    parser.add_argument("--no-open", action="store_true", help="Do not open the PNG after generating")
    args = parser.parse_args()

    load_dotenv()
    start = resolve_start(args.lat, args.lon)
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        print("ERROR: ORS_API_KEY not found in environment or .env file")
        sys.exit(1)

    distance_m = compute_distance_m(args.duration, args.pace)
    print(f"Workout: {args.duration} min @ {args.pace}/km")
    print(f"Estimated running distance: {distance_m:.0f} m ({distance_m / 1000:.1f} km)")

    client = openrouteservice.Client(key=api_key)
    print("Fetching route from OpenRouteService...")
    route = fetch_route(client, start, distance_m, args.seed)

    actual_dist = route["features"][0]["properties"]["summary"]["distance"]
    actual_dur = route["features"][0]["properties"]["summary"]["duration"]
    coords = route["features"][0]["geometry"]["coordinates"]
    ascent, descent = compute_elevation(coords)
    print(f"ORS route: {actual_dist:.0f} m, ~{actual_dur / 60:.0f} min walking estimate")
    print(f"Elevation: D+ {ascent:.0f} m / D- {descent:.0f} m")

    gpx = route_to_gpx(route)

    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    slug = slugify(args.name)
    gpx_path = ROUTES_DIR / f"{today}_{slug}.gpx"
    png_path = ROUTES_DIR / f"{today}_{slug}.png"
    html_path = ROUTES_DIR / f"{today}_{slug}.html"

    gpx_path.write_text(gpx.to_xml())
    print(f"GPX saved: {gpx_path}")

    img = build_image(coords, distance_m, args.duration, args.pace, ascent, descent)
    img.save(str(png_path))
    print(f"Image saved: {png_path}")

    html_map = build_html(coords, distance_m, args.duration, args.pace, ascent, descent)
    html_map.save(str(html_path))
    print(f"HTML saved: {html_path}")

    if not args.no_open:
        open_file(png_path)


if __name__ == "__main__":
    main()
