"""Drain pending compilations to YouTube under daily quota.

Pulled out of upload_daily.py so daily_run.py can call it as part of the
single-cron pipeline. upload_daily.py is now a thin CLI shim around this.
"""

import json
import logging
from pathlib import Path

from googleapiclient.errors import HttpError

from automation.state import State
from automation.youtube import build_client, upload_video

log = logging.getLogger(__name__)


def _select_batch(state: State, max_long: int, max_short: int) -> list:
    already_long = state.uploads_today(kind="long")
    already_short = state.uploads_today(kind="short")
    long_budget = max(0, max_long - already_long)
    short_budget = max(0, max_short - already_short)
    longs = state.pending_uploads(kind="long")[:long_budget]
    shorts = state.pending_uploads(kind="short")[:short_budget]
    log.info(
        "upload budget: longs=%d/%d shorts=%d/%d  picked longs=%d shorts=%d",
        already_long, max_long, already_short, max_short, len(longs), len(shorts),
    )
    return list(longs) + list(shorts)


def drain_pending(cfg, state: State, dry_run: bool = False) -> int:
    """Upload pending compilations under today's quota.

    Returns number of successful uploads. Errors on individual uploads are
    logged and skipped; an unexpected exception aborts the batch.
    """
    batch = _select_batch(
        state,
        max_long=cfg.youtube.max_longs_per_day,
        max_short=cfg.youtube.max_shorts_per_day,
    )
    if not batch:
        log.info("no uploads to do (quota used or no pending compilations)")
        return 0

    log.info("will upload %d compilations", len(batch))
    for row in batch:
        log.info("  [%s] %s", row["kind"], row["id"])
    if dry_run:
        return 0

    youtube = build_client()
    uploaded = 0
    for row in batch:
        cid = row["id"]
        if not Path(row["output_path"]).exists():
            log.warning("file missing, skipping: %s -> %s", cid, row["output_path"])
            continue
        log.info("uploading: %s", cid)
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
            video_id = upload_video(
                youtube,
                file_path=row["output_path"],
                title=row["title"],
                description=row["description"],
                tags=tags,
                privacy_status=cfg.youtube.default_privacy,
                progress_cb=lambda pct, cid=cid: log.info("  %s: %d%%", cid, pct),
            )
        except HttpError:
            log.exception("upload failed: %s", cid)
            continue
        state.mark_uploaded(cid, video_id)
        uploaded += 1
        log.info("uploaded %s -> https://www.youtube.com/watch?v=%s", cid, video_id)
    return uploaded
