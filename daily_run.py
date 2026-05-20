"""Cron entry point: process every pitcher in config/pitchers.yaml.

Per pitcher:
  1. Fetch recent Statcast data and download new clips.
  2. Persist each new clip in the state DB.
  3. Build one long horizontal compilation of every new clip.
  4. Record the compilation + metadata in the state DB.

After all pitchers, build yesterday's Predicted-vs-Actual recap Short and
queue it for upload alongside the long compilations. The recap uses
predictions already written to sim_site/data/games/{yesterday}/ by the
sim_site cron 24h earlier.

Writes a per-run manifest JSON consumed by the YouTube uploader.
The script always exits 0 — pitcher-level failures are logged and
isolated so one bad pitcher never aborts the run.
"""

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from automation import (
    compiler, config as config_mod, manifest as manifest_mod, metadata,
    recap_compiler,
)
from automation.logging_setup import setup as setup_logging
from automation.state import State
from automation.uploader import drain_pending
from pitching_stats_getter import process_pitcher

log = logging.getLogger("daily_run")


def _build_for_pitcher(pcfg, paths, state: State, run_date: str):
    """Build compilations for one pitcher.

    Compilations are grouped by GAME DATE, not run date — viewers want clips
    tagged with when the game happened, not when we scraped. `run_date` is
    only used internally by the state-row "run_date" column for auditing.
    """

    def _persist(c):
        state.record_clip(
            play_id=c.play_id,
            game_pk=c.game_pk,
            game_date=c.game_date,
            pitcher_name=c.pitcher_name,
            pitch_name=c.pitch_name,
            call_type=c.call_type,
            landscape_path=c.landscape_path,
            portrait_path=c.portrait_path or "",
        )

    new_clips = process_pitcher(
        name=pcfg.name,
        team_brief_name=pcfg.team,
        lookback_days=pcfg.lookback_days,
        videos_dir=str(paths.videos_dir),
        seen_play_id=state.has_play,
        on_clip_recorded=_persist,
        skip_portrait_for_ball=pcfg.strikes_only_shorts,
    )
    log.info("pitcher=%s new_clips=%d", pcfg.name, len(new_clips))

    if not new_clips:
        return []

    manifest_entries = []

    def _record(entry):
        state.record_compilation(
            compilation_id=entry.compilation_id,
            pitcher_name=entry.pitcher_name,
            run_date=entry.run_date,
            kind=entry.kind,
            pitch_name=entry.pitch_name,
            output_path=entry.output_path,
            title=entry.title,
            description=entry.description,
            tags_json=json.dumps(entry.tags),
        )
        manifest_entries.append(entry)

    clips_by_game_date: dict[str, list] = {}
    for c in new_clips:
        clips_by_game_date.setdefault(c.game_date, []).append(c)

    for game_date, game_clips in sorted(clips_by_game_date.items()):
        try:
            long_built = compiler.build_long_horizontal(
                pitcher_name=pcfg.name,
                run_date=game_date,
                clips=game_clips,
                compilations_dir=paths.compilations_dir,
                min_clips=pcfg.long_min_clips,
            )
            if long_built is not None:
                meta = metadata.for_long(pcfg.name, game_date, long_built.clips)
                _record(manifest_mod.make_entry(pcfg.name, game_date, long_built, meta))
        except Exception:
            log.exception(
                "long horizontal failed for %s game_date=%s; continuing",
                pcfg.name, game_date,
            )

    return manifest_entries


def _build_daily_recap(paths, state: State, run_date: str):
    """Build yesterday's Predicted-vs-Actual recap as a Short.

    Uses sim_site predictions already written 24h ago by the sim_site cron.
    Returns the manifest entry (or None if recap couldn't be built — e.g.,
    missing predictions, no games on that date).
    """
    target_date = (datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=1)).date()
    try:
        result = recap_compiler.build_recap(
            target_date=target_date,
            compilations_dir=paths.compilations_dir,
        )
    except Exception:
        log.exception("recap build failed for %s", target_date)
        return None
    if result is None:
        return None

    meta = metadata.for_recap(target_date, result.correct, result.total, result.rows)
    entry = manifest_mod.make_entry(
        pitcher_name="MLB Sims",
        run_date=target_date.isoformat(),
        built=result.built,
        metadata=meta,
    )
    state.record_compilation(
        compilation_id=entry.compilation_id,
        pitcher_name=entry.pitcher_name,
        run_date=entry.run_date,
        kind=entry.kind,
        pitch_name=entry.pitch_name,
        output_path=entry.output_path,
        title=entry.title,
        description=entry.description,
        tags_json=json.dumps(entry.tags),
    )
    log.info("recap queued: %s (%d/%d winners)", entry.compilation_id, result.correct, result.total)
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily MLB pitcher compilation run.")
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Path to pitchers.yaml (default: config/pitchers.yaml)",
    )
    parser.add_argument(
        "--skip-upload", action="store_true",
        help="Build compilations but do not upload to YouTube.",
    )
    args = parser.parse_args()

    cfg = config_mod.load(args.config)
    cfg.paths.ensure()
    logfile = setup_logging(cfg.paths.logs_dir)
    log.info("starting daily run, log=%s", logfile)
    log.info("pitchers=%d", len(cfg.pitchers))

    state = State(cfg.paths.state_db)
    run_date = datetime.now().strftime("%Y-%m-%d")

    all_entries = []
    for pcfg in cfg.pitchers:
        try:
            all_entries.extend(_build_for_pitcher(pcfg, cfg.paths, state, run_date))
        except Exception:
            log.exception("pitcher run failed: %s", pcfg.name)

    recap_entry = _build_daily_recap(cfg.paths, state, run_date)
    if recap_entry is not None:
        all_entries.append(recap_entry)

    manifest_path = manifest_mod.write_run_manifest(
        cfg.paths.manifest_dir, run_date, all_entries
    )
    log.info("wrote manifest: %s (%d entries)", manifest_path, len(all_entries))

    if args.skip_upload:
        log.info("skipping upload (--skip-upload)")
    else:
        try:
            drain_pending(cfg, state)
        except Exception:
            log.exception("upload pass failed; build outputs are still on disk")
    log.info("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
