# MLB Pitcher Compilation Automation

Daily pipeline: for every pitcher you list, fetch the last week of Baseball Savant data, download new clips, and build:

- one **long horizontal** compilation of every new clip (YouTube long-form), and
- one **vertical 9:16 Short** per pitch type (YouTube Shorts), strikes-only by default.

YouTube upload is intentionally out of scope for this iteration — the pipeline writes a manifest of pending uploads to be consumed by the uploader added later.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg   # required by the compiler
```

Edit [config/pitchers.yaml](config/pitchers.yaml) — add the pitchers you want processed every run. Each entry needs `name` (as it appears on Baseball Savant) and `team` (matches a `Brief Name` in [constants.py](constants.py), e.g. `Cubs`, `Yankees`, `Padres`).

## Run

```bash
python daily_run.py
```

Outputs:

- `videos/<pitcher>/<game_pk>/{landscape,portrait}/<call_type>/<pitch>/*.mp4` — per-clip downloads (dedup'd via [state.db](state.db)).
- `compilations/<pitcher>/<YYYY-MM-DD>/<pitcher>_<date>_long.mp4` — long horizontal video.
- `compilations/<pitcher>/<YYYY-MM-DD>/<pitcher>_<date>_short_<pitch>.mp4` — one per qualifying pitch type.
- `compilations/manifests/manifest-<YYYY-MM-DD>.json` — ready-to-upload entries (title, description, tags, path).
- `logs/run-<timestamp>.log` — per-run log.

Re-running on the same day is safe: clips already in `state.db` are skipped.

## Schedule daily

See [crontab.example](crontab.example). Short version:

```cron
0 9 * * * cd /abs/path/to/repo && /abs/path/to/venv/bin/python daily_run.py >> logs/cron.log 2>&1
```

## Layout

- [daily_run.py](daily_run.py) — cron entry point; orchestrates one run.
- [automation/config.py](automation/config.py) — loads `pitchers.yaml`.
- [automation/state.py](automation/state.py) — SQLite dedup for clips + compilations.
- [automation/compiler.py](automation/compiler.py) — ffmpeg concat for long horizontal + vertical Shorts.
- [automation/metadata.py](automation/metadata.py) — title/description/tags generation.
- [automation/manifest.py](automation/manifest.py) — writes the per-run upload manifest.
- [pitching_stats_getter.py](pitching_stats_getter.py) — pybaseball lookup + per-game scrape (also runs interactively if invoked directly).
- [video_scraper/](video_scraper) — fetch clip URLs and convert to 9:16.
- [clip_paster.py](clip_paster.py) — legacy one-off compiler; superseded by [automation/compiler.py](automation/compiler.py).

## Known limitations

- Pitcher names must be `First Last` (or `First Middle … Last` — the script takes the first and last tokens). Multi-word surnames (e.g. "De La Rosa") need a manual override that isn't implemented yet.
- `start_speed` is sometimes `None` in the Savant payload; treated as `0` in captions.
- The compiler always re-encodes (no `-c copy`) because clips across games can have divergent codec params. Slower, but reliable.
