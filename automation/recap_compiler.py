"""Build the daily 'predicted vs actual' MLB recap Short for upload.

Reads pre-computed predictions from sim_site/data/games/{target_date}/ (already
produced by the sim_site 9am cron 24h earlier) and fetches actual results from
the MLB Stats API. Renders a vertical 1080x1920 Short with edge-tts AI
narration over PIL-rendered cards, joined with FFmpeg.

Output is wrapped in a BuiltCompilation with kind="short", pitch_name="recap"
so it flows through the existing manifest -> state DB -> uploader pipeline
without any schema changes.

Idempotent: if compilations/recap/{date}/recap.mp4 already exists, returns the
existing path without rebuilding. State DB unique-key on compilation_id then
prevents re-uploading.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

from automation.compiler import BuiltCompilation

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from sim_site.pipeline import ingest  # noqa: E402

log = logging.getLogger(__name__)

VOICE = "en-US-GuyNeural"
WIDTH, HEIGHT = 1080, 1920

PREDICTIONS_DIR = REPO_ROOT / "sim_site" / "data" / "games"

COLOR_BG = (15, 17, 22)
COLOR_FG = (255, 255, 255)
COLOR_MUTED = (150, 150, 155)
COLOR_ACCENT = (132, 184, 255)
COLOR_OK = (90, 220, 130)
COLOR_MISS = (255, 110, 110)


def _font_paths() -> tuple[str, str]:
    """Return (bold, regular) font file paths for the current platform."""
    if platform.system() == "Darwin":
        return (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        )
    candidates = [
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for bold, regular in candidates:
        if Path(bold).exists() and Path(regular).exists():
            return bold, regular
    raise RuntimeError(
        "No suitable sans-serif font found. "
        "On Debian/Ubuntu: sudo apt-get install fonts-liberation"
    )


_FONT_BOLD, _FONT_REGULAR = _font_paths()


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_FONT_BOLD if bold else _FONT_REGULAR, size)


@dataclass
class RecapResult:
    built: BuiltCompilation
    correct: int
    total: int
    rows: list[dict]  # per-game prediction-vs-actual details for metadata callouts


def _load_predictions(target_date: dt.date) -> list[dict]:
    pred_dir = PREDICTIONS_DIR / target_date.isoformat()
    if not pred_dir.exists():
        return []
    return [json.loads(p.read_text()) for p in sorted(pred_dir.glob("*.json"))]


def _build_rows(predictions: list[dict], target_date: dt.date) -> list[dict]:
    """Pair each prediction with the actual game result. Drops anything not Final."""
    games_through = ingest.fetch_games(target_date.year, through=target_date)
    actuals = games_through[games_through["date"] == target_date.isoformat()]
    actuals_by_pk = {int(row.game_pk): row for _, row in actuals.iterrows()}

    rows = []
    for pred in predictions:
        actual = actuals_by_pk.get(int(pred["game_pk"]))
        if actual is None:
            continue  # postponed / cancelled
        pred_home_wp = pred["win_probability"]["home"]
        pred_away_wp = pred["win_probability"]["away"]
        pred_winner = "home" if pred_home_wp > pred_away_wp else "away"
        actual_winner = "home" if actual.home_runs > actual.away_runs else "away"
        winner_pct = max(pred_home_wp, pred_away_wp)
        rows.append({
            "matchup": f"{pred['away']['abbr']} @ {pred['home']['abbr']}",
            "home_abbr": pred["home"]["abbr"],
            "away_abbr": pred["away"]["abbr"],
            "pred_winner_abbr": pred["home"]["abbr"] if pred_winner == "home" else pred["away"]["abbr"],
            "pred_score": f"{pred['expected']['away_runs']:.1f}–{pred['expected']['home_runs']:.1f}",
            "actual_score": f"{int(actual.away_runs)}–{int(actual.home_runs)}",
            "winner_called": pred_winner == actual_winner,
            "winner_pct": int(round(winner_pct * 100)),
        })
    return rows


def _build_segments(rows: list[dict], correct: int, total: int) -> list[dict]:
    segments = [{
        "kind": "intro",
        "text": f"Yesterday the model called {total} matchups. Let's see how we did.",
    }]
    for r in rows:
        text = (
            f"{r['away_abbr']} at {r['home_abbr']}. "
            f"Model favored {r['pred_winner_abbr']} at {r['winner_pct']} percent. "
            f"Final: {r['actual_score']}. "
            + ("Called it." if r["winner_called"] else "Miss.")
        )
        segments.append({"kind": "game", "text": text, "data": r})
    segments.append({
        "kind": "outro",
        "text": f"{correct} out of {total} winners called. "
                f"See today's picks at MLB sims dot com.",
        "data": {"correct": correct, "total": total},
    })
    return segments


async def _generate_tts(segments: list[dict], work_dir: Path) -> None:
    for i, seg in enumerate(segments):
        path = work_dir / f"seg_{i:03d}.mp3"
        await edge_tts.Communicate(seg["text"], VOICE, rate="+8%").save(str(path))
        seg["audio_path"] = path


def _draw_centered(draw, xy, text, fnt, fill):
    draw.text(xy, text, font=fnt, fill=fill, anchor="mm")


def _render_card(seg: dict, idx: int, target_date: dt.date, work_dir: Path) -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), color=COLOR_BG)
    draw = ImageDraw.Draw(img)
    cx = WIDTH // 2

    _draw_centered(draw, (cx, HEIGHT - 90), "mlbsims.com", _font(40), COLOR_MUTED)

    if seg["kind"] == "intro":
        _draw_centered(
            draw, (cx, HEIGHT // 2 - 220),
            target_date.strftime("%B %-d, %Y").upper(),
            _font(70, True), COLOR_MUTED,
        )
        _draw_centered(draw, (cx, HEIGHT // 2 - 60), "Predicted", _font(110, True), COLOR_FG)
        _draw_centered(draw, (cx, HEIGHT // 2 + 60), "vs", _font(80), COLOR_MUTED)
        _draw_centered(draw, (cx, HEIGHT // 2 + 180), "Actual", _font(110, True), COLOR_ACCENT)

    elif seg["kind"] == "game":
        r = seg["data"]
        _draw_centered(draw, (cx, 320), r["matchup"], _font(120, True), COLOR_FG)
        _draw_centered(draw, (cx, 700), "MODEL FAVORED", _font(46), COLOR_MUTED)
        _draw_centered(
            draw, (cx, 820),
            f"{r['pred_winner_abbr']} {r['winner_pct']}%",
            _font(140, True), COLOR_ACCENT,
        )
        _draw_centered(draw, (cx, 950), f"pred {r['pred_score']}", _font(56), COLOR_MUTED)
        _draw_centered(draw, (cx, 1200), "ACTUAL", _font(46), COLOR_MUTED)
        _draw_centered(draw, (cx, 1310), r["actual_score"], _font(180, True), COLOR_FG)
        verdict_color = COLOR_OK if r["winner_called"] else COLOR_MISS
        verdict_text = "CALLED IT" if r["winner_called"] else "MISS"
        _draw_centered(draw, (cx, 1600), verdict_text, _font(90, True), verdict_color)

    elif seg["kind"] == "outro":
        d = seg["data"]
        _draw_centered(draw, (cx, HEIGHT // 2 - 300), "DAILY SCORECARD", _font(60, True), COLOR_MUTED)
        _draw_centered(
            draw, (cx, HEIGHT // 2 - 100),
            f"{d['correct']}/{d['total']}", _font(280, True), COLOR_OK,
        )
        _draw_centered(draw, (cx, HEIGHT // 2 + 80), "winners called", _font(60), COLOR_FG)
        _draw_centered(draw, (cx, HEIGHT // 2 + 280), "tomorrow's picks at", _font(50), COLOR_MUTED)
        _draw_centered(draw, (cx, HEIGHT // 2 + 360), "mlbsims.com", _font(90, True), COLOR_ACCENT)

    path = work_dir / f"card_{idx:03d}.png"
    img.save(path)
    return path


def _build_segment_video(seg: dict, idx: int, card_path: Path, work_dir: Path) -> Path:
    out = work_dir / f"seg_{idx:03d}.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(card_path),
        "-i", str(seg["audio_path"]),
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-vf", f"scale={WIDTH}:{HEIGHT},fps=30",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    return out


def _concat(parts: list[Path], output: Path) -> None:
    # FFmpeg concat demuxer resolves relative paths against the concat file's
    # location, not the cwd — so we write absolute paths to avoid doubling.
    concat_list = parts[0].parent / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy",
        str(output),
    ], check=True)


def build_recap(target_date: dt.date, compilations_dir: Path) -> RecapResult | None:
    """Build the daily recap for target_date. Returns None if no usable data."""
    log.info("recap: building for %s", target_date)
    predictions = _load_predictions(target_date)
    if not predictions:
        log.warning("recap: no predictions found at %s; skipping",
                    PREDICTIONS_DIR / target_date.isoformat())
        return None

    rows = _build_rows(predictions, target_date)
    if not rows:
        log.warning("recap: no completed games match predictions for %s; skipping", target_date)
        return None

    correct = sum(r["winner_called"] for r in rows)
    total = len(rows)

    out_dir = compilations_dir / "recap" / target_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "recap.mp4"
    built = BuiltCompilation(
        kind="short", pitch_name="recap", output_path=output, clips=[],
    )

    if output.exists():
        log.info("recap: already built at %s; reusing", output)
        return RecapResult(built=built, correct=correct, total=total, rows=rows)

    work_dir = out_dir / "_work"
    work_dir.mkdir(exist_ok=True)

    segments = _build_segments(rows, correct, total)
    asyncio.run(_generate_tts(segments, work_dir))

    parts = []
    for i, seg in enumerate(segments):
        card_path = _render_card(seg, i, target_date, work_dir)
        parts.append(_build_segment_video(seg, i, card_path, work_dir))

    _concat(parts, output)

    log.info("recap: built %s (%d/%d correct, %d games)", output, correct, total, total)
    return RecapResult(built=built, correct=correct, total=total)
