#!/usr/bin/env bash
# Sync the rendered static site into a sibling git checkout of the public
# Cloudflare-Pages-connected repo, then commit + push. On push to main,
# Cloudflare Pages auto-rebuilds and serves the new content.
#
# One-time setup:
#   1. Create a public GitHub repo (suggested name: mlb-sims-site)
#   2. On the host running cron, clone it to SIM_SITE_REPO (default ~/mlb-sims-site)
#      using an SSH deploy key with write access.
#   3. In the Cloudflare dashboard, create a Pages project connected to that
#      repo; pick "no build" — the repo already contains rendered HTML.
#   4. Make sure `git push` works non-interactively from the cron host.
#
# Override the checkout path by exporting SIM_SITE_REPO before invoking.

set -euo pipefail

SITE_REPO="${SIM_SITE_REPO:-$HOME/mlb-sims-site}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RENDERED="$REPO_ROOT/sim_site/site"

if [ ! -d "$SITE_REPO/.git" ]; then
  echo "FATAL: $SITE_REPO is not a git checkout." >&2
  echo "       Set SIM_SITE_REPO or clone the public site repo there." >&2
  exit 1
fi
if [ ! -d "$RENDERED" ]; then
  echo "FATAL: rendered site not found at $RENDERED. Run daily_run.py first." >&2
  exit 1
fi

# Sync local mirror with remote first — the e2-micro cron and the Mac can both
# push to this repo, so the local checkout may be stale.
git -C "$SITE_REPO" pull --rebase --quiet origin main

# Mirror rendered output into the public checkout. --delete removes stale files
# (e.g. yesterday's slate pages once they're no longer current). Exclude .git so
# we don't clobber the public repo's own history.
rsync -a --delete --exclude=".git" "$RENDERED/" "$SITE_REPO/"

cd "$SITE_REPO"
git add -A

if git diff --quiet --cached; then
  echo "deploy: no changes to push"
  exit 0
fi

git commit -m "Daily build $(date -u +%Y-%m-%dT%H:%MZ)"
git push origin main
echo "deploy: pushed to origin/main; Cloudflare Pages will rebuild"
