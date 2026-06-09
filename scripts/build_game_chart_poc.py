"""POC: chartball-style portrait game chart.

Renders ONE static PNG mimicking the chartball aesthetic — used to validate
visuals before wiring up the data + multi-frame + ffmpeg pipeline.

Run:
    .venv/bin/python scripts/build_game_chart_poc.py
Output:
    ~/Desktop/game_chart_test.png   (1080x1920, portrait)

Hardcoded to the 3rd-inning, 4-3 Phillies state from the reference mockup so
we can compare side-by-side. Once the look lands, we'll swap hardcoded values
for a DB pull + generate one frame per event + stitch to MP4.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Canvas + palette ---
W, H = 1080, 1920
BG = (242, 240, 236)        # warm off-white
FG = (24, 24, 24)
AWAY = (24, 24, 24)         # black for away team
HOME = (213, 78, 50)        # chartball-ish red
MUTED = (160, 160, 160)
DIAMOND_BG = (255, 255, 255)
FAINT = (220, 220, 220)


# --- Font discovery (Mac defaults) ---
def find_font(*names):
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


_FONT_PATH = find_font() or ""


def font(size: int):
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, size)
    return ImageFont.load_default()


# --- Geometry ---
CHART_CENTER = (W // 2, 1010)
DIAMOND_R = 330      # half the diagonal of the inner diamond
OUTER_R = 380        # radius of the arc circle around the diamond
ARC_WIDTH = 22       # thickness of the cumulative-advance ring


def draw_diamond(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> list[tuple[int, int]]:
    """Inner diamond (the infield outline). Returns the 4 base points
    as [top, right, bottom, left]."""
    pts = [
        (cx, cy - r),       # top    = 2B
        (cx + r, cy),       # right  = 1B
        (cx, cy + r),       # bottom = home
        (cx - r, cy),       # left   = 3B
    ]
    draw.polygon(pts, fill=DIAMOND_BG)

    # Subtle dashed foul lines from home plate up-left and up-right
    home = pts[2]
    # Left foul line
    draw.line([home, (cx - r - 110, cy - r - 110)], fill=FAINT, width=2)
    # Right foul line
    draw.line([home, (cx + r + 110, cy - r - 110)], fill=FAINT, width=2)

    return pts


def draw_bases(draw: ImageDraw.ImageDraw, pts: list[tuple[int, int]]):
    """Bases drawn as small unfilled diamonds at top/right/left; home plate
    as a small unfilled circle at bottom."""
    top, right, bottom, left = pts
    size = 14
    for x, y in (top, right, left):
        draw.polygon(
            [(x, y - size), (x + size, y), (x, y + size), (x - size, y)],
            fill=DIAMOND_BG, outline=FG, width=3,
        )
    # Home plate
    bx, by = bottom
    rad = 16
    draw.ellipse([bx - rad, by - rad, bx + rad, by + rad],
                 fill=DIAMOND_BG, outline=FG, width=3)


def draw_advance_arc(draw, cx: int, cy: int, r: int, bases_advanced: float,
                     color: tuple[int, int, int]):
    """Draw an arc representing cumulative bases advanced this half-inning.

    Starts at the bottom (home plate, PIL 90°) and grows COUNTER-CLOCKWISE
    in baseball direction: home → 1B (right) → 2B (top) → 3B (left) → home.

    bases_advanced: float, 4.0 = exactly one full revolution = 1 run.
    For >4 bases (multiple revolutions), we collapse to (bases mod 4) for now;
    a v2 could draw concentric rings.
    """
    if bases_advanced <= 0:
        return
    deg = (bases_advanced % 4.0) * 90.0
    if deg == 0 and bases_advanced > 0:
        deg = 360.0
    # PIL arc(): 0°=east, 90°=south, 180°=west, 270°=north — i.e. clockwise.
    # Baseball CCW from south (home = PIL 90°): home → east(1B, PIL 0°) → north(2B, 270°) → west(3B, 180°) → home.
    # PIL's arc() draws clockwise from start to end. To draw a CCW arc from 90
    # going negatively (270 → 180 → 90 → 0 → 270), we negate: draw from
    # (90 - deg) to 90 clockwise.
    start = (90 - deg) % 360
    end = 90
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.arc(bbox, start=start, end=end, fill=color, width=ARC_WIDTH)
    # End-cap markers (small unfilled circles where the arc begins/ends)
    cap_r = 9
    # Starting cap = at angle 90° (bottom)
    cap1 = (cx + r * math.cos(math.radians(90)),
            cy + r * math.sin(math.radians(90)))
    # Ending cap = at angle start (CCW progression)
    cap2 = (cx + r * math.cos(math.radians(start)),
            cy + r * math.sin(math.radians(start)))
    for (x, y) in (cap1, cap2):
        draw.ellipse([x - cap_r, y - cap_r, x + cap_r, y + cap_r],
                     fill=DIAMOND_BG, outline=color, width=3)


def draw_inning_summary_circle(draw, cx: int, cy: int, r: int, value: int,
                               color: tuple[int, int, int], faded: bool = False):
    """A small donut with the value (hits, runs, etc.) inside.

    Past innings are drawn 'faded'; the current inning is highlighted.
    """
    col = MUTED if faded else color
    # Ring
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    # Number
    draw.text((cx, cy), str(value), fill=col, font=font(28), anchor="mm")


def draw_frame(out_path: Path, state: dict):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # --- Header ---
    draw.text((W // 2, 70), state["title"], fill=FG, font=font(32), anchor="mm")
    draw.text((W // 2, 115), state["venue"], fill=MUTED, font=font(26), anchor="mm")

    # --- Score block ---
    left_x, right_x = 230, W - 230
    sy = 290
    # AWAY (left)
    draw.text((left_x, sy), str(state["away_score"]),
              fill=AWAY, font=font(200), anchor="mm")
    for i, line in enumerate(state["away_name"].split("\n")):
        draw.text((left_x, sy + 165 + i * 56), line,
                  fill=AWAY, font=font(48), anchor="mm")
    # HOME (right)
    draw.text((right_x, sy), str(state["home_score"]),
              fill=HOME, font=font(200), anchor="mm")
    for i, line in enumerate(state["home_name"].split("\n")):
        draw.text((right_x, sy + 165 + i * 56), line,
                  fill=HOME, font=font(48), anchor="mm")

    # --- Chart (diamond + advance arc) ---
    cx, cy = CHART_CENTER
    pts = draw_diamond(draw, cx, cy, DIAMOND_R)
    team_color = HOME if state["half"] == "Bot" else AWAY
    draw_advance_arc(draw, cx, cy, OUTER_R, state["half_bases"], team_color)
    draw_bases(draw, pts)

    # --- Center text ---
    inning_label = ordinal(state["inning"])
    draw.text((cx, cy - 80), inning_label, fill=MUTED, font=font(72), anchor="mm")
    draw.text((cx, cy - 20), "INNING", fill=MUTED, font=font(28), anchor="mm")
    draw.text((cx, cy + 60), "PITCHING", fill=MUTED, font=font(22), anchor="mm")
    draw.text((cx, cy + 100), state["pitcher"],
              fill=team_color, font=font(42), anchor="mm")
    draw.text((cx, cy + 200), state["batter"],
              fill=(HOME if state["half"] == "Top" else AWAY),
              font=font(42), anchor="mm")
    draw.text((cx, cy + 240), "BATTING", fill=MUTED, font=font(22), anchor="mm")

    # --- Inning summary bottom-left ---
    sum_y = 1600
    draw.text((110, sum_y - 30), "INNING SUMMARY:",
              fill=MUTED, font=font(22), anchor="lm")
    x = 140
    for i, summary in enumerate(state["inning_summary"]):
        # Per inning: top row (away, faded if past), bottom row (home, faded if past)
        is_current = (i == state["inning"] - 1)
        label = ordinal(i + 1)
        draw.text((x, sum_y), label, fill=MUTED, font=font(22), anchor="mm")
        draw_inning_summary_circle(draw, x, sum_y + 50, 28,
                                   summary["away"], AWAY,
                                   faded=not is_current and summary["away_finalized"])
        draw_inning_summary_circle(draw, x, sum_y + 120, 28,
                                   summary["home"], HOME,
                                   faded=not is_current and summary["home_finalized"])
        x += 130

    # --- Legend bottom-right ---
    lg_x = 620
    lg_y = sum_y - 30
    draw.text((lg_x, lg_y), "KEY:", fill=MUTED, font=font(22), anchor="lm")
    draw.text((lg_x, lg_y + 45), "HITS", fill=FG, font=font(22), anchor="lm")
    draw.rectangle([lg_x, lg_y + 75, lg_x + 320, lg_y + 90], fill=MUTED)
    draw.text((lg_x, lg_y + 125), "OTHER ADVANCES (walks,",
              fill=FG, font=font(22), anchor="lm")
    draw.text((lg_x, lg_y + 155), "steals, base running, etc.)",
              fill=FG, font=font(22), anchor="lm")
    # Tick pattern legend
    for tx in range(lg_x, lg_x + 320, 6):
        draw.line([(tx, lg_y + 105), (tx, lg_y + 120)], fill=MUTED, width=2)

    img.save(out_path)
    print(f"wrote {out_path}  ({out_path.stat().st_size // 1024} KB)")


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def main():
    out = Path.home() / "Desktop" / "game_chart_test.png"
    out.parent.mkdir(exist_ok=True)

    # Hardcoded to mirror the chartball reference (frame 2): 3rd inning, 4-3 Phillies,
    # Sandlin pitching, Stott batting. Inning summary cols carry the prior tally.
    state = {
        "title": "MLB GAME CHART — Sunday, June 7, 2026",
        "venue": "Citizens Bank Park, Philadelphia",
        "away_score": 3,
        "home_score": 4,
        "away_name": "Chicago\nWhite Sox",
        "home_name": "Philadelphia\nPhillies",
        "inning": 3,
        "half": "Bot",            # Phillies (home) batting
        "pitcher": "D.Sandlin",
        "batter": "B.Stott",
        "half_bases": 4.0,        # one full revolution = run scored this inning
        "inning_summary": [
            # values for hits / advance / however we want to interpret
            {"away": 0, "home": 1, "away_finalized": True, "home_finalized": True},
            {"away": 2, "home": 2, "away_finalized": True, "home_finalized": True},
            {"away": 1, "home": 1, "away_finalized": False, "home_finalized": False},
        ],
    }
    draw_frame(out, state)


if __name__ == "__main__":
    main()
