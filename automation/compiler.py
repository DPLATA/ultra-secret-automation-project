"""Build daily compilations from downloaded clips.

Two outputs per pitcher per run:
  - One long horizontal video: every new landscape clip concatenated.
  - One vertical "Short" per pitch type: portrait clips of that pitch type
    (optionally strikes-only), provided enough clips exist.

Long uses ffmpeg's concat demuxer (fast). Shorts use the concat filter,
which fully decodes each input and rebuilds the timeline — slower, but
fixes intermittent PTS corruption we saw on the demuxer path (one clip
with bad timestamp metadata produced a 3-hour output).
"""

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from video_scraper.downloader import ClipRecord

log = logging.getLogger(__name__)

SHORT_TARGET_SECONDS = 55.0  # YouTube Shorts cap is 60s; leave 5s safety margin
SHORT_DURATION_WARN_THRESHOLD = 65.0


def _ffprobe_duration(path: str) -> float:
    """Return clip duration in seconds via ffprobe, 0.0 if unreadable."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


@dataclass(frozen=True)
class BuiltCompilation:
    kind: str  # "long" | "short"
    pitch_name: str | None  # None for "long"
    output_path: Path
    clips: list[ClipRecord]


def _safe_filename(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")


def _ffmpeg_concat_demuxer(clip_paths: Sequence[str], output_path: Path) -> None:
    """Concat for the long horizontal — tries stream-copy first, falls back to re-encode.

    Stream-copy is ~400x faster than re-encode on the e2-micro (seconds vs hours)
    but is vulnerable to PTS corruption when one input clip has bad timestamp
    metadata — historically that produced multi-hour bogus durations. We detect
    that case by comparing output duration against the sum of input durations,
    and fall back to the slow re-encode path if drift > 60s.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, dir=output_path.parent
    ) as f:
        concat_list = f.name
        for p in clip_paths:
            abspath = os.path.abspath(p).replace("'", r"'\''")
            f.write(f"file '{abspath}'\n")
    try:
        expected_duration = sum(_ffprobe_duration(p) for p in clip_paths)

        # Fast path: stream-copy with PTS regeneration safety flags.
        copy_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            "-fflags", "+genpts",
            "-avoid_negative_ts", "make_zero",
            str(output_path),
        ]
        copy_result = subprocess.run(copy_cmd, capture_output=True, text=True)
        if copy_result.returncode == 0:
            actual = _ffprobe_duration(str(output_path))
            drift = abs(actual - expected_duration)
            if drift <= 60.0:
                log.info(
                    "concat (stream-copy) ok: %s (%.0fs, drift=%.1fs)",
                    output_path, actual, drift,
                )
                return
            log.warning(
                "concat (stream-copy) drift %.1fs > 60s — likely PTS corruption; "
                "falling back to re-encode for %s", drift, output_path,
            )
        else:
            log.warning(
                "concat (stream-copy) failed (rc=%s) — falling back to re-encode for %s\n%s",
                copy_result.returncode, output_path, copy_result.stderr[-500:],
            )

        # Slow fallback path: full re-encode (the historical implementation).
        reencode_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        result = subprocess.run(reencode_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg failed (code %s):\n%s", result.returncode, result.stderr[-2000:])
            raise RuntimeError(f"ffmpeg concat failed for {output_path}")
        log.info("concat (re-encode fallback) ok: %s", output_path)
    finally:
        try:
            os.remove(concat_list)
        except OSError:
            pass


def _ffmpeg_concat_filter(clip_paths: Sequence[str], output_path: Path) -> None:
    """Slower but more reliable concat via the concat filter.

    Forces ffmpeg to decode each input and rebuild the timeline from scratch,
    which avoids PTS / duration corruption when one input has bad metadata.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd: list[str] = ["ffmpeg", "-y"]
    for p in clip_paths:
        cmd += ["-i", p]
    n = len(clip_paths)
    streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    filter_complex = f"{streams}concat=n={n}:v=1:a=1[v][a]"
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg failed (code %s):\n%s", result.returncode, result.stderr[-2000:])
        raise RuntimeError(f"ffmpeg concat failed for {output_path}")


def build_long_horizontal(
    pitcher_name: str,
    run_date: str,
    clips: list[ClipRecord],
    compilations_dir: Path,
    min_clips: int,
) -> BuiltCompilation | None:
    if len(clips) < min_clips:
        log.info(
            "skip long horizontal for %s: %d clips < min %d",
            pitcher_name, len(clips), min_clips,
        )
        return None
    out_dir = compilations_dir / _safe_filename(pitcher_name) / run_date
    out_path = out_dir / f"{_safe_filename(pitcher_name)}_{run_date}_long.mp4"
    _ffmpeg_concat_demuxer([c.landscape_path for c in clips], out_path)
    log.info("built long horizontal: %s (%d clips)", out_path, len(clips))
    return BuiltCompilation(kind="long", pitch_name=None, output_path=out_path, clips=clips)


def build_shorts_per_pitch_type(
    pitcher_name: str,
    run_date: str,
    clips: list[ClipRecord],
    compilations_dir: Path,
    min_clips: int,
    max_clips: int,
    strikes_only: bool,
) -> list[BuiltCompilation]:
    pool = [
        c for c in clips
        if (c.call_type == "strike" or not strikes_only) and c.portrait_path
    ]
    by_pitch: dict[str, list[ClipRecord]] = {}
    for c in pool:
        by_pitch.setdefault(c.pitch_name, []).append(c)
    # Pick clips for each pitch type: rank highest-velocity first, greedily
    # add until the cumulative duration approaches the YouTube-Shorts cap.
    # Capping by clip count alone is unreliable — Savant clip durations vary
    # 7-15s depending on outcome (whiff vs ball-in-play).
    for pitch_name, group in by_pitch.items():
        group.sort(key=lambda c: c.speed_mph, reverse=True)
        selected: list[ClipRecord] = []
        cumulative = 0.0
        for c in group:
            if len(selected) >= max_clips:
                break
            d = _ffprobe_duration(c.portrait_path)
            if d <= 0:
                continue
            if cumulative + d > SHORT_TARGET_SECONDS and len(selected) >= min_clips:
                break
            selected.append(c)
            cumulative += d
        by_pitch[pitch_name] = selected

    built: list[BuiltCompilation] = []
    for pitch_name, group in by_pitch.items():
        if len(group) < min_clips:
            log.info(
                "skip short for %s %s: %d clips < min %d",
                pitcher_name, pitch_name, len(group), min_clips,
            )
            continue
        out_dir = compilations_dir / _safe_filename(pitcher_name) / run_date
        out_path = (
            out_dir / f"{_safe_filename(pitcher_name)}_{run_date}_short_"
                      f"{_safe_filename(pitch_name)}.mp4"
        )
        try:
            _ffmpeg_concat_filter([c.portrait_path for c in group], out_path)
        except Exception:
            log.exception("short failed for %s %s; continuing", pitcher_name, pitch_name)
            continue
        actual_dur = _ffprobe_duration(str(out_path))
        if actual_dur > SHORT_DURATION_WARN_THRESHOLD:
            log.warning(
                "short %s came out %.1fs (target <%.1fs) — may not be detected as a Short",
                out_path.name, actual_dur, SHORT_TARGET_SECONDS,
            )
        log.info("built short: %s (%d clips, %.1fs)", out_path, len(group), actual_dur)
        built.append(
            BuiltCompilation(
                kind="short", pitch_name=pitch_name, output_path=out_path, clips=group
            )
        )
    return built
