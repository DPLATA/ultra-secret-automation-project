"""Manual YouTube uploader for a single compilation entry or arbitrary file.

For one-off testing and ad-hoc uploads. The cron path is upload_daily.py.

Usage:
    # From the most recent manifest:
    python upload_manual.py --list
    python upload_manual.py --compilation-id "Paul Skenes|2026-05-12|short|Sinker"
    python upload_manual.py --compilation-id "..." --privacy unlisted

    # Arbitrary file (e.g. one-off recap, experimental video):
    python upload_manual.py --file path/to/video.mp4 \\
        --title "Title here" --description "Body here" \\
        --tags "mlb,baseball,...",
        --privacy unlisted
"""

import argparse
import json
import os
import sys
from pathlib import Path

from googleapiclient.errors import HttpError

from automation.youtube import build_client, upload_video


def _latest_manifest() -> Path:
    candidates = sorted(Path("compilations/manifests").glob("manifest-*.json"))
    if not candidates:
        sys.exit("No manifests found in compilations/manifests/")
    return candidates[-1]


def _load_entries(manifest_path: Path) -> list[dict]:
    return json.loads(manifest_path.read_text())["entries"]


def _upload(file_path: str, title: str, description: str, tags: list[str], privacy: str) -> int:
    print(f"uploading: {file_path}")
    print(f"  title  : {title}")
    print(f"  privacy: {privacy}")
    try:
        video_id = upload_video(
            build_client(),
            file_path=file_path,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy,
            progress_cb=lambda pct: print(f"  upload progress: {pct}%"),
        )
    except HttpError as e:
        print(f"YouTube API error: {e}", file=sys.stderr)
        return 1
    print(f"\ndone: https://www.youtube.com/watch?v={video_id}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument("--list", action="store_true")
    p.add_argument("--compilation-id", type=str, default=None)
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")

    # Arbitrary-file mode
    p.add_argument("--file", type=str, default=None,
                   help="Upload an arbitrary video file (bypasses the manifest).")
    p.add_argument("--title", type=str, default=None)
    p.add_argument("--description", type=str, default=None)
    p.add_argument("--tags", type=str, default="",
                   help="Comma-separated tags.")

    args = p.parse_args()

    # Arbitrary-file path
    if args.file:
        if not os.path.exists(args.file):
            sys.exit(f"file missing: {args.file}")
        if not args.title or not args.description:
            sys.exit("--title and --description required with --file")
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        return _upload(args.file, args.title, args.description, tags, args.privacy)

    # Manifest-driven path
    manifest_path = args.manifest or _latest_manifest()
    entries = _load_entries(manifest_path)
    print(f"manifest: {manifest_path}  ({len(entries)} entries)")

    if args.list:
        for e in entries:
            size_mb = os.path.getsize(e["output_path"]) / 1024 / 1024 if os.path.exists(e["output_path"]) else 0
            print(f"  [{e['kind']:5}] {e['compilation_id']}")
            print(f"          title: {e['title']}")
            print(f"          file : {e['output_path']}  ({size_mb:.1f} MB)")
        return 0

    if not args.compilation_id:
        sys.exit("--compilation-id required (or use --list, or --file)")
    entry = next((e for e in entries if e["compilation_id"] == args.compilation_id), None)
    if entry is None:
        sys.exit(f"no entry with id {args.compilation_id!r}")
    if not os.path.exists(entry["output_path"]):
        sys.exit(f"file missing: {entry['output_path']}")

    return _upload(
        entry["output_path"], entry["title"], entry["description"],
        entry["tags"], args.privacy,
    )


if __name__ == "__main__":
    raise SystemExit(main())
