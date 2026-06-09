"""Upload a single game-chart MP4 to YouTube as a Short.

Reuses the existing OAuth + upload pipeline (automation.youtube). Defaults to
private so you can eyeball it in YouTube Studio before flipping public.

Usage:
    .venv/bin/python scripts/upload_game_chart.py \\
        --video ~/Desktop/game_chart_823453.mp4 \\
        --title "PHI vs CWS — every play, visualized | June 7, 2026 #MLB #Shorts"

If --title is omitted, generates a default from the file name.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from automation.youtube import build_client, upload_video  # noqa: E402

DEFAULT_DESCRIPTION = """\
Every event of the {date} {away} at {home} game, charted from Statcast data.

The arc shows cumulative bases advanced in each half-inning — multiple
revolutions are runs scored. The circles at the bottom track runs per inning.

This is a new visualization format we're testing on the channel. Let us know
what you think in the comments.

→ Ask any baseball question at mlbsims.com/ask
→ Daily predictions at mlbsims.com

#MLB #Shorts #DataViz #Statcast #Baseball #{away_tag} #{home_tag}
"""

DEFAULT_TAGS = [
    "MLB", "Statcast", "baseball", "MLB Sims",
    "data visualization", "Shorts", "baseball analytics",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", type=Path, required=True, help="path to MP4")
    ap.add_argument("--title", type=str, help="YouTube title (≤100 chars)")
    ap.add_argument("--description", type=str, help="YouTube description (override)")
    ap.add_argument("--tags", type=str, nargs="+", help="space-separated tag list")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"],
                    default="private")
    ap.add_argument("--away", type=str, default="White Sox")
    ap.add_argument("--home", type=str, default="Phillies")
    ap.add_argument("--away-tag", type=str, default="WhiteSox")
    ap.add_argument("--home-tag", type=str, default="Phillies")
    ap.add_argument("--date", type=str, default="June 7, 2026")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"video not found: {args.video}")

    title = args.title or f"{args.away} vs {args.home} — every play, visualized | {args.date} #Shorts"
    if len(title) > 100:
        print(f"WARN: title {len(title)} chars (max 100); truncating")
        title = title[:97] + "..."
    description = args.description or DEFAULT_DESCRIPTION.format(
        date=args.date, away=args.away, home=args.home,
        away_tag=args.away_tag, home_tag=args.home_tag,
    )
    tags = args.tags or DEFAULT_TAGS

    print(f"=== uploading {args.video.name} ===")
    print(f"  title:    {title}")
    print(f"  privacy:  {args.privacy}")
    print(f"  tags:     {tags}")
    print(f"  size:     {args.video.stat().st_size // 1024} KB")
    print(f"  → connecting to YouTube…")

    youtube = build_client()

    def cb(pct: int):
        print(f"  uploading… {pct}%", end="\r")

    video_id = upload_video(
        youtube,
        file_path=str(args.video),
        title=title,
        description=description,
        tags=tags,
        privacy_status=args.privacy,
        progress_cb=cb,
    )
    print()
    print(f"✓ uploaded: https://youtu.be/{video_id}")
    print(f"   studio:  https://studio.youtube.com/video/{video_id}/edit")


if __name__ == "__main__":
    main()
