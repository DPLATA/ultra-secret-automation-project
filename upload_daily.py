"""CLI shim: drain pending YouTube uploads under daily quota.

For most cases just run `daily_run.py` — it builds compilations and then
calls this same logic. This script is for upload-only runs (e.g. retry
after a daily_run build failure).
"""

import argparse
from pathlib import Path

from automation import config as config_mod
from automation.logging_setup import setup as setup_logging
from automation.state import State
from automation.uploader import drain_pending


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--config", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    cfg = config_mod.load(args.config)
    cfg.paths.ensure()
    setup_logging(cfg.paths.logs_dir)
    state = State(cfg.paths.state_db)
    drain_pending(cfg, state, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
