"""Chartball-style portrait game-replay Short.

Pulls all event-level rows for a single MLB game from Cloud SQL (via SSH to
e2-micro), generates one PNG frame per state change, stitches them into a
60-90s portrait MP4 via FFmpeg.

Usage:
    .venv/bin/python scripts/build_game_chart.py                     # yesterday's most-flip-prone game
    .venv/bin/python scripts/build_game_chart.py --date 2026-06-07   # specific date
    .venv/bin/python scripts/build_game_chart.py --game-pk 823453    # specific game

Output:
    videos/game_charts/<game_pk>/frames/*.png    (intermediate frames)
    videos/game_charts/<game_pk>/chart.mp4       (final stitched video)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ──────────────────────────────────────────────────────────────────────────────
# Config

REPO = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO / "videos" / "game_charts"

# Palette mirrors the mlbsims site: cool off-white bg, deep navy AWAY,
# accent blue HOME, same --muted gray as the site CSS.
W, H = 1080, 1920
BG = (244, 246, 248)        # #f4f6f8
FG = (26, 26, 26)           # #1a1a1a (site --fg)
AWAY = (15, 23, 42)         # #0f172a (methodology PDF cover navy)
HOME = (31, 111, 235)       # #1f6feb (site --accent)
MUTED = (107, 114, 128)     # #6b7280 (site --muted)
DIAMOND_BG = (255, 255, 255)
FAINT = (220, 225, 230)

CHART_CENTER = (W // 2, 1010)
DIAMOND_R = 330
OUTER_R = 380
ARC_WIDTH = 22

FRAME_HOLD_FPS = 30          # MP4 framerate
FRAME_DURATION_S = 1.2       # how long each game-state image fully holds
CROSSFADE_S = 0.35           # crossfade between consecutive states
CROSSFADE_STEPS = 10         # number of in-between blended frames
INTRO_HOLD_S = 2.5           # opening title frame
OUTRO_HOLD_S = 4.0           # final score lingers

HIT_EVENTS = {"single", "double", "triple", "home_run"}
ADVANCE_EVENTS = HIT_EVENTS | {"walk", "intent_walk", "hit_by_pitch", "field_error"}
EVENT_BASES = {
    "single": 1, "double": 2, "triple": 3, "home_run": 4,
    "walk": 1, "intent_walk": 1, "hit_by_pitch": 1,
    "field_error": 1, "fielders_choice": 1,
}

# Team brief names — keep in sync with constants.MLB_TEAMS_INFO
TEAM_NAMES = {
    "ARI": "Arizona\nDiamondbacks", "AZ": "Arizona\nDiamondbacks",
    "ATL": "Atlanta\nBraves", "ATH": "Oakland/SAC\nAthletics",
    "BAL": "Baltimore\nOrioles", "BOS": "Boston\nRed Sox",
    "CHC": "Chicago\nCubs", "CIN": "Cincinnati\nReds",
    "CLE": "Cleveland\nGuardians", "COL": "Colorado\nRockies",
    "CWS": "Chicago\nWhite Sox", "DET": "Detroit\nTigers",
    "HOU": "Houston\nAstros", "KC": "Kansas City\nRoyals",
    "LAA": "Los Angeles\nAngels", "LAD": "Los Angeles\nDodgers",
    "MIA": "Miami\nMarlins", "MIL": "Milwaukee\nBrewers",
    "MIN": "Minnesota\nTwins", "NYM": "New York\nMets",
    "NYY": "New York\nYankees", "PHI": "Philadelphia\nPhillies",
    "PIT": "Pittsburgh\nPirates", "SD": "San Diego\nPadres",
    "SEA": "Seattle\nMariners", "SF": "San Francisco\nGiants",
    "STL": "St. Louis\nCardinals", "TB": "Tampa Bay\nRays",
    "TEX": "Texas\nRangers", "TOR": "Toronto\nBlue Jays",
    "WSH": "Washington\nNationals",
}

# ──────────────────────────────────────────────────────────────────────────────
# Font discovery (Mac)

def _find_font():
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(path).exists():
            return path
    return None


_FONT_PATH = _find_font() or ""


def font(size: int):
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, size)
    return ImageFont.load_default()


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def format_name(last_first: str) -> str:
    """'Stott, Bryson' → 'B.Stott'. Returns input on parse failure."""
    if not last_first or "," not in last_first:
        return last_first or ""
    last, first = (p.strip() for p in last_first.split(",", 1))
    return f"{first[0]}.{last}" if first else last


# ──────────────────────────────────────────────────────────────────────────────
# DB pull via SSH to e2

DUMP_PY = r'''
import json, os, psycopg2, psycopg2.extras, sys

conn = psycopg2.connect(
    host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
    dbname=os.environ["DB_NAME"], user=os.environ["DB_READER_USER"],
    password=os.environ["DB_READER_PASSWORD"],
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

mode = sys.argv[1]
arg = sys.argv[2]
out = {}

if mode == "find_game":
    # Pick the game on the given date with the most lead changes.
    # Lead change = away_score - home_score sign flip across consecutive
    # terminal-pitch rows. If multiple, pick highest combined score.
    cur.execute("""
        SELECT game_pk, away_team, home_team,
               max(post_away_score) AS final_away,
               max(post_home_score) AS final_home
        FROM pitches
        WHERE game_date = %s AND events IS NOT NULL
        GROUP BY 1, 2, 3
    """, (arg,))
    candidates = cur.fetchall()
    best = None
    best_score = (-1, -1)  # (lead_changes, total_runs)
    for c in candidates:
        cur.execute("""
            SELECT post_away_score, post_home_score
            FROM pitches
            WHERE game_pk = %s AND events IS NOT NULL
            ORDER BY at_bat_number, pitch_number
        """, (c["game_pk"],))
        diffs = [(r["post_away_score"] or 0) - (r["post_home_score"] or 0)
                 for r in cur.fetchall()]
        flips = sum(
            1 for i in range(1, len(diffs))
            if diffs[i] and diffs[i - 1] and (diffs[i] * diffs[i - 1] < 0)
        )
        total = (c["final_away"] or 0) + (c["final_home"] or 0)
        score = (flips, total)
        if score > best_score:
            best_score = score
            best = c
    if not best:
        sys.exit(f"no games found for date {{arg}}")
    out["game_pk"] = best["game_pk"]
    out["away_team"] = best["away_team"]
    out["home_team"] = best["home_team"]

elif mode == "fetch_events":
    cur.execute("""
        SELECT inning, inning_topbot, events, des,
               home_team, away_team, game_date,
               post_home_score, post_away_score,
               home_score AS pre_home_score, away_score AS pre_away_score,
               player_name AS pitcher_name,
               batter AS batter_id, pitcher AS pitcher_id,
               at_bat_number, pitch_number
        FROM pitches
        WHERE game_pk = %s AND events IS NOT NULL
        ORDER BY at_bat_number, pitch_number
    """, (int(arg),))
    out["events"] = [dict(r) for r in cur.fetchall()]
    if out["events"]:
        out["game_date"] = out["events"][0]["game_date"].isoformat()
        out["away_team"] = out["events"][0]["away_team"]
        out["home_team"] = out["events"][0]["home_team"]
    # Decimal/Date types need stringifying
    for e in out["events"]:
        if e.get("game_date"):
            e["game_date"] = e["game_date"].isoformat()
print(json.dumps(out, default=str))
'''


_DUMPER_REMOTE_PATH = "/tmp/_chart_dumper.py"
_DUMPER_PUSHED = False


def _push_dumper():
    """SCP the dumper script to e2 once per process. Avoids the quoting hell of
    passing a multiline Python program through gcloud ssh --command."""
    global _DUMPER_PUSHED
    if _DUMPER_PUSHED:
        return
    local = Path("/tmp/_chart_dumper.py")
    local.write_text(DUMP_PY)
    subprocess.run(
        ["gcloud", "compute", "scp", str(local),
         f"mlb-pipeline:{_DUMPER_REMOTE_PATH}",
         "--zone", "us-east1-b"],
        check=True, capture_output=True,
    )
    _DUMPER_PUSHED = True


def ssh_query(mode: str, arg: str) -> dict:
    _push_dumper()
    cmd = [
        "gcloud", "compute", "ssh", "mlb-pipeline", "--zone", "us-east1-b",
        "--command",
        "cd ~/ultra-secret-automation-project && "
        "set -a && source secrets/cloudsql.env && set +a && "
        f".venv/bin/python {_DUMPER_REMOTE_PATH} {mode} {arg}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"SSH query failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
    # gcloud prints "Warning: ..." lines too; take the last JSON-shaped line
    last_json = None
    for line in res.stdout.splitlines():
        s = line.strip()
        if s.startswith("{"):
            last_json = s
    if not last_json:
        sys.exit(f"no JSON in SSH response:\n{res.stdout}")
    return json.loads(last_json)


# ──────────────────────────────────────────────────────────────────────────────
# State sequence — one entry per frame

def build_state_sequence(events: list[dict]) -> list[dict]:
    """One frame per state change. State change = anything in ADVANCE_EVENTS
    OR a run scoring OR a half-inning end."""
    states = []
    half_bases = 0
    half_hits = 0
    prev_half = None
    inning_summary: dict[tuple[int, str], dict] = {}

    last_event = None  # most recent event whose frame we'll display
    last_pitcher = ""

    for i, e in enumerate(events):
        half_key = (e["inning"], e["inning_topbot"])
        if half_key != prev_half:
            # Half-inning rolled over — reset arc tracking
            half_bases = 0
            half_hits = 0
            prev_half = half_key
        # Tally
        ev_bases = EVENT_BASES.get(e["events"], 0)
        half_bases += ev_bases
        if e["events"] in HIT_EVENTS:
            half_hits += 1

        # Update inning summary for the team currently batting
        team_offense = "away" if e["inning_topbot"] == "Top" else "home"
        summ = inning_summary.setdefault(
            e["inning"], {"away_hits": 0, "home_hits": 0, "away_runs": 0, "home_runs": 0}
        )
        runs_this_play = ((e["post_away_score"] or 0) - (e["pre_away_score"] or 0)) \
            if team_offense == "away" else \
            ((e["post_home_score"] or 0) - (e["pre_home_score"] or 0))
        summ[f"{team_offense}_runs"] += runs_this_play
        if e["events"] in HIT_EVENTS:
            summ[f"{team_offense}_hits"] += 1

        is_state_change = (
            e["events"] in ADVANCE_EVENTS
            or runs_this_play > 0
            or (i + 1 < len(events)
                and (events[i + 1]["inning"], events[i + 1]["inning_topbot"]) != half_key)
        )
        last_pitcher = e["pitcher_name"] or last_pitcher
        if is_state_change:
            states.append({
                "inning": e["inning"],
                "half": e["inning_topbot"],
                "post_away": e["post_away_score"] or 0,
                "post_home": e["post_home_score"] or 0,
                "pitcher": last_pitcher,
                "batter_id": e["batter_id"],
                "batter_label": batter_label_from_des(e.get("des"), e.get("batter_id")),
                "des": e.get("des") or "",
                "half_bases": half_bases,
                "half_hits": half_hits,
                "inning_summary": _snapshot_summary(inning_summary, e["inning"], e["inning_topbot"]),
                "is_hit_event": e["events"] in HIT_EVENTS,
                "event_kind": e["events"],
            })
        last_event = e

    return states


def batter_label_from_des(des: str | None, batter_id) -> str:
    """Pull batter name out of the play description. e.g. 'Bryson Stott homers...'
    → 'B.Stott'. Falls back to '#<id>' on failure."""
    if not des:
        return f"#{batter_id}" if batter_id else "BATTER"
    first_token = des.split(" ")[0]  # First name
    parts = des.split(" ")
    if len(parts) >= 2:
        last_token = parts[1].rstrip(",.")
        return f"{first_token[0]}.{last_token}"
    return first_token


def _snapshot_summary(d: dict, current_inning: int, current_half: str) -> list[dict]:
    """Return a list of {inning, away, home, away_finalized, home_finalized} for
    all innings up to current_inning."""
    out = []
    for inning in sorted(d.keys()):
        if inning > current_inning:
            break
        s = d[inning]
        # Away (top) finalizes when home half begins (or current is later inning)
        away_final = (inning < current_inning) or (current_half == "Bot")
        home_final = inning < current_inning
        out.append({
            "inning": inning,
            "away": s["away_runs"],   # show runs in the summary circles
            "home": s["home_runs"],
            "away_finalized": away_final,
            "home_finalized": home_final,
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Frame rendering (extends POC)

def _draw_diamond(draw, cx, cy, r):
    pts = [
        (cx, cy - r),     # 2B (top)
        (cx + r, cy),     # 1B (right)
        (cx, cy + r),     # home (bottom)
        (cx - r, cy),     # 3B (left)
    ]
    draw.polygon(pts, fill=DIAMOND_BG)
    # Subtle foul lines
    home = pts[2]
    draw.line([home, (cx - r - 110, cy - r - 110)], fill=FAINT, width=2)
    draw.line([home, (cx + r + 110, cy - r - 110)], fill=FAINT, width=2)
    return pts


def _draw_bases(draw, pts):
    top, right, bottom, left = pts
    size = 14
    for x, y in (top, right, left):
        draw.polygon(
            [(x, y - size), (x + size, y), (x, y + size), (x - size, y)],
            fill=DIAMOND_BG, outline=FG, width=3,
        )
    bx, by = bottom
    rad = 16
    draw.ellipse([bx - rad, by - rad, bx + rad, by + rad],
                 fill=DIAMOND_BG, outline=FG, width=3)


def _draw_arc(draw, cx, cy, r, bases, color):
    """CCW from home (PIL 90°). Multiple revolutions become concentric rings."""
    if bases <= 0:
        return
    full_loops = int(bases // 4)
    remainder = (bases % 4.0)
    # Concentric rings for each completed run-equivalent loop
    for i in range(full_loops):
        ring_r = r - i * (ARC_WIDTH + 4)
        bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
        draw.arc(bbox, start=0, end=360, fill=color, width=ARC_WIDTH)
    # Partial outermost-pending arc
    if remainder > 0:
        deg = remainder * 90.0
        start = (90 - deg) % 360
        end = 90
        ring_r = r - full_loops * (ARC_WIDTH + 4)
        bbox = [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r]
        draw.arc(bbox, start=start, end=end, fill=color, width=ARC_WIDTH)
        # End-cap
        cap_r = 9
        cap1 = (cx + ring_r * math.cos(math.radians(90)),
                cy + ring_r * math.sin(math.radians(90)))
        cap2 = (cx + ring_r * math.cos(math.radians(start)),
                cy + ring_r * math.sin(math.radians(start)))
        for (x, y) in (cap1, cap2):
            draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r],
                         fill=DIAMOND_BG, outline=color, width=3)


def _draw_inning_dot(draw, cx, cy, r, value, color, faded):
    col = MUTED if faded else color
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    draw.text((cx, cy), str(value), fill=col, font=font(28), anchor="mm")


def render_image(st: dict, meta: dict, kind: str = "play") -> Image.Image:
    """Return a PIL Image for the given state. Caller can save or blend it."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((W // 2, 70), meta["title"], fill=FG, font=font(30), anchor="mm")
    draw.text((W // 2, 115), meta["venue"], fill=MUTED, font=font(24), anchor="mm")

    # Score block
    left_x, right_x = 230, W - 230
    sy = 290
    draw.text((left_x, sy), str(st["post_away"]),
              fill=AWAY, font=font(200), anchor="mm")
    for i, line in enumerate(meta["away_name"].split("\n")):
        draw.text((left_x, sy + 165 + i * 54), line,
                  fill=AWAY, font=font(46), anchor="mm")
    draw.text((right_x, sy), str(st["post_home"]),
              fill=HOME, font=font(200), anchor="mm")
    for i, line in enumerate(meta["home_name"].split("\n")):
        draw.text((right_x, sy + 165 + i * 54), line,
                  fill=HOME, font=font(46), anchor="mm")

    # Diamond + arc
    cx, cy = CHART_CENTER
    pts = _draw_diamond(draw, cx, cy, DIAMOND_R)
    team_color = HOME if st["half"] == "Bot" else AWAY
    _draw_arc(draw, cx, cy, OUTER_R, st["half_bases"], team_color)
    _draw_bases(draw, pts)

    # Center text
    if kind == "intro":
        draw.text((cx, cy - 30), "GAME", fill=MUTED, font=font(64), anchor="mm")
        draw.text((cx, cy + 30), "CHART", fill=MUTED, font=font(64), anchor="mm")
        draw.text((cx, cy + 120), meta.get("game_subtitle", ""),
                  fill=FG, font=font(34), anchor="mm")
    elif kind == "outro":
        winner = "AWAY" if st["post_away"] > st["post_home"] else "HOME"
        win_color = AWAY if winner == "AWAY" else HOME
        margin = abs(st["post_away"] - st["post_home"])
        draw.text((cx, cy - 30), "FINAL", fill=MUTED, font=font(64), anchor="mm")
        draw.text((cx, cy + 50),
                  f"{'AWAY' if winner == 'AWAY' else 'HOME'} +{margin}",
                  fill=win_color, font=font(48), anchor="mm")
    else:
        # Play frame
        inning_label = ordinal(st["inning"])
        draw.text((cx, cy - 80), inning_label, fill=MUTED, font=font(72), anchor="mm")
        draw.text((cx, cy - 20), "INNING", fill=MUTED, font=font(28), anchor="mm")
        # Pitcher = defense (opposite of the team currently batting).
        # Batter = offense (same color as the half-inning's team_color).
        pitcher_color = AWAY if st["half"] == "Bot" else HOME
        batter_color = team_color
        draw.text((cx, cy + 60), "PITCHING", fill=MUTED, font=font(22), anchor="mm")
        draw.text((cx, cy + 100), format_name(st["pitcher"]),
                  fill=pitcher_color, font=font(42), anchor="mm")
        draw.text((cx, cy + 200), st["batter_label"],
                  fill=batter_color, font=font(42), anchor="mm")
        draw.text((cx, cy + 240), "BATTING", fill=MUTED, font=font(22), anchor="mm")

    # Inning summary
    sum_y = 1600
    draw.text((110, sum_y - 30), "INNING SUMMARY:", fill=MUTED, font=font(22), anchor="lm")
    x = 140
    for s in st.get("inning_summary", [])[:9]:  # cap visible to 9 innings
        is_current = (s["inning"] == st["inning"])
        draw.text((x, sum_y), ordinal(s["inning"]), fill=MUTED, font=font(20), anchor="mm")
        _draw_inning_dot(draw, x, sum_y + 50, 28, s["away"], AWAY,
                         faded=not is_current and s["away_finalized"])
        _draw_inning_dot(draw, x, sum_y + 120, 28, s["home"], HOME,
                         faded=not is_current and s["home_finalized"])
        x += 100

    # Legend
    lg_x = 720
    lg_y = sum_y - 30
    draw.text((lg_x, lg_y), "KEY:", fill=MUTED, font=font(22), anchor="lm")
    draw.text((lg_x, lg_y + 45), "HITS", fill=FG, font=font(22), anchor="lm")
    draw.rectangle([lg_x, lg_y + 75, lg_x + 230, lg_y + 90], fill=MUTED)
    draw.text((lg_x, lg_y + 125), "OTHER ADVANCES", fill=FG, font=font(20), anchor="lm")
    for tx in range(lg_x, lg_x + 230, 6):
        draw.line([(tx, lg_y + 155), (tx, lg_y + 170)], fill=MUTED, width=2)

    return img


def render_frame(out_path: Path, st: dict, meta: dict, kind: str = "play"):
    """Thin wrapper for callers that want a file directly."""
    render_image(st, meta, kind).save(out_path)


# ──────────────────────────────────────────────────────────────────────────────
# FFmpeg stitch

def stitch_video(frames_dir: Path, output: Path, images: list[Image.Image],
                 holds: list[float]):
    """Save each image as a PNG, plus blended PNGs between consecutive images
    for a soft crossfade, then concat at the configured fps.

    images[i] holds for holds[i] seconds. Between images[i] and images[i+1]
    we insert CROSSFADE_STEPS blended PNGs spanning CROSSFADE_S seconds.
    """
    assert len(images) == len(holds)
    list_file = frames_dir / "concat.txt"
    lines: list[str] = []

    crossfade_step_s = CROSSFADE_S / CROSSFADE_STEPS

    for i, (img, hold) in enumerate(zip(images, holds)):
        unique_path = frames_dir / f"state_{i:03d}.png"
        img.save(unique_path)
        lines.append(f"file '{unique_path}'")
        lines.append(f"duration {hold:.4f}")

        if i < len(images) - 1:
            next_img = images[i + 1]
            for k in range(1, CROSSFADE_STEPS + 1):
                alpha = k / (CROSSFADE_STEPS + 1)
                blended = Image.blend(img, next_img, alpha)
                blend_path = frames_dir / f"trans_{i:03d}_{k:02d}.png"
                blended.save(blend_path)
                lines.append(f"file '{blend_path}'")
                lines.append(f"duration {crossfade_step_s:.4f}")

    # concat demuxer requires the final file to be re-listed without duration
    lines.append(f"file '{frames_dir / f'state_{len(images) - 1:03d}.png'}'")
    list_file.write_text("\n".join(lines))

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-fps_mode", "cfr",
        "-r", str(FRAME_HOLD_FPS),
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920:flags=lanczos",
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        str(output),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{res.stderr[-2000:]}")


# ──────────────────────────────────────────────────────────────────────────────
# Main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", type=str, help="game date YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--game-pk", type=int, help="specific game_pk to render")
    ap.add_argument("--keep-frames", action="store_true",
                    help="don't delete intermediate frame PNGs after stitching")
    args = ap.parse_args()

    if args.game_pk:
        game_pk = args.game_pk
        print(f"using explicit game_pk={game_pk}")
        meta_query = ssh_query("fetch_events", str(game_pk))
        events = meta_query["events"]
        away_team = meta_query["away_team"]
        home_team = meta_query["home_team"]
        game_date = meta_query["game_date"]
    else:
        date = args.date or (dt.date.today() - dt.timedelta(days=1)).isoformat()
        print(f"finding best game for {date}…")
        sel = ssh_query("find_game", date)
        game_pk = sel["game_pk"]
        away_team = sel["away_team"]
        home_team = sel["home_team"]
        print(f"  selected game_pk={game_pk} ({away_team} @ {home_team})")
        meta_query = ssh_query("fetch_events", str(game_pk))
        events = meta_query["events"]
        game_date = meta_query["game_date"]

    if not events:
        sys.exit(f"no events for game_pk={game_pk}")

    states = build_state_sequence(events)
    print(f"events: {len(events)}, frames to render: {len(states)}")
    if not states:
        sys.exit("no state-change frames produced")

    # Output dirs
    frames_dir = OUT_ROOT / str(game_pk) / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    output = OUT_ROOT / str(game_pk) / "chart.mp4"

    day = dt.date.fromisoformat(game_date)
    meta = {
        "title": f"MLB GAME CHART — {day.strftime('%A, %B %-d, %Y')}",
        "venue": f"{away_team} at {home_team}",
        "away_name": TEAM_NAMES.get(away_team, away_team),
        "home_name": TEAM_NAMES.get(home_team, home_team),
        "game_subtitle": f"{away_team} at {home_team}",
    }

    # Build all unique state Images in memory, plus their hold durations.
    # Order: intro → each play state → outro.
    intro_state = {**states[0], "post_away": 0, "post_home": 0, "half_bases": 0,
                   "inning_summary": []}
    images: list[Image.Image] = [render_image(intro_state, meta, kind="intro")]
    holds: list[float] = [INTRO_HOLD_S]

    for st in states:
        images.append(render_image(st, meta, kind="play"))
        holds.append(FRAME_DURATION_S)

    images.append(render_image(states[-1], meta, kind="outro"))
    holds.append(OUTRO_HOLD_S)

    print(f"  rendered {len(images)} keyframes + {(len(images) - 1) * CROSSFADE_STEPS} transition frames")
    stitch_video(frames_dir, output, images, holds)

    duration_s = sum(holds) + (len(images) - 1) * CROSSFADE_S
    print(f"\nstitched → {output}")
    print(f"  ~{duration_s:.1f}s, {len(states)} play states ({CROSSFADE_S}s crossfades)")

    if not args.keep_frames:
        shutil.rmtree(frames_dir)
        print(f"  (cleaned intermediate frames; pass --keep-frames to retain)")

    # Copy to Desktop for easy review
    desktop = Path.home() / "Desktop" / f"game_chart_{game_pk}.mp4"
    shutil.copy(output, desktop)
    print(f"  also copied to {desktop}")


if __name__ == "__main__":
    main()
