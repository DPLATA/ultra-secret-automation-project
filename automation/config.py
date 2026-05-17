"""Typed loader for config/pitchers.yaml."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "pitchers.yaml"


@dataclass(frozen=True)
class PitcherConfig:
    name: str
    team: str  # team Brief Name, resolved against constants.MLB_TEAMS_INFO
    lookback_days: int
    long_min_clips: int
    short_min_clips: int
    short_max_clips: int
    strikes_only_shorts: bool


@dataclass(frozen=True)
class YouTubeConfig:
    max_uploads_per_day: int
    max_longs_per_day: int
    max_shorts_per_day: int
    default_privacy: str


@dataclass(frozen=True)
class Paths:
    videos_dir: Path
    compilations_dir: Path
    manifest_dir: Path
    state_db: Path
    logs_dir: Path

    def ensure(self) -> None:
        for p in (self.videos_dir, self.compilations_dir, self.manifest_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    pitchers: list[PitcherConfig] = field(default_factory=list)
    paths: Paths = None  # type: ignore[assignment]
    youtube: YouTubeConfig = None  # type: ignore[assignment]


def _abs(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else REPO_ROOT / p


def load(config_path: Optional[Path] = None) -> Config:
    path = config_path or DEFAULT_CONFIG_PATH
    with open(path) as f:
        raw = yaml.safe_load(f)

    defaults = raw.get("defaults", {}) or {}
    lookback_days = int(defaults.get("lookback_days", 7))
    long_min_clips = int(defaults.get("long_min_clips", 5))
    short_min_clips = int(defaults.get("short_min_clips", 3))
    short_max_clips = int(defaults.get("short_max_clips", 6))
    strikes_only_shorts = bool(defaults.get("strikes_only_shorts", True))

    pitchers = [
        PitcherConfig(
            name=p["name"],
            team=p["team"],
            lookback_days=int(p.get("lookback_days", lookback_days)),
            long_min_clips=int(p.get("long_min_clips", long_min_clips)),
            short_min_clips=int(p.get("short_min_clips", short_min_clips)),
            short_max_clips=int(p.get("short_max_clips", short_max_clips)),
            strikes_only_shorts=bool(p.get("strikes_only_shorts", strikes_only_shorts)),
        )
        for p in raw.get("pitchers", []) or []
    ]

    paths_raw = raw.get("paths", {}) or {}
    paths = Paths(
        videos_dir=_abs(paths_raw.get("videos_dir", "videos")),
        compilations_dir=_abs(paths_raw.get("compilations_dir", "compilations")),
        manifest_dir=_abs(paths_raw.get("manifest_dir", "compilations/manifests")),
        state_db=_abs(paths_raw.get("state_db", "state.db")),
        logs_dir=_abs(paths_raw.get("logs_dir", "logs")),
    )

    yt_raw = raw.get("youtube", {}) or {}
    youtube = YouTubeConfig(
        max_uploads_per_day=int(yt_raw.get("max_uploads_per_day", 6)),
        max_longs_per_day=int(yt_raw.get("max_longs_per_day", 3)),
        max_shorts_per_day=int(yt_raw.get("max_shorts_per_day", 3)),
        default_privacy=str(yt_raw.get("default_privacy", "private")),
    )
    return Config(pitchers=pitchers, paths=paths, youtube=youtube)
