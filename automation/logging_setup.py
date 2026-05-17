"""Per-run logging: console + dated file under paths.logs_dir."""

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup(logs_dir: Path, level: int = logging.INFO) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / f"run-{datetime.now():%Y-%m-%d_%H-%M-%S}.log"
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    handlers = [logging.FileHandler(logfile), logging.StreamHandler(sys.stdout)]
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)
    return logfile
