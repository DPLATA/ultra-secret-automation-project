"""Write a JSON manifest of compilations ready to upload.

The YouTube uploader (added in a later step) consumes this manifest.
Manifests are append-only per run: one file per daily run, plus a
rolling `pending.json` of everything not yet uploaded.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from automation.compiler import BuiltCompilation
from automation.metadata import Metadata


@dataclass
class ManifestEntry:
    compilation_id: str
    pitcher_name: str
    run_date: str
    kind: str
    pitch_name: str | None
    output_path: str
    title: str
    description: str
    tags: list[str]


def make_entry(
    pitcher_name: str,
    run_date: str,
    built: BuiltCompilation,
    metadata: Metadata,
) -> ManifestEntry:
    pid = built.pitch_name or "all"
    return ManifestEntry(
        compilation_id=f"{pitcher_name}|{run_date}|{built.kind}|{pid}",
        pitcher_name=pitcher_name,
        run_date=run_date,
        kind=built.kind,
        pitch_name=built.pitch_name,
        output_path=str(built.output_path),
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags,
    )


def write_run_manifest(
    manifest_dir: Path, run_date: str, entries: Iterable[ManifestEntry]
) -> Path:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"manifest-{run_date}.json"
    payload = {"run_date": run_date, "entries": [asdict(e) for e in entries]}
    path.write_text(json.dumps(payload, indent=2))
    return path
