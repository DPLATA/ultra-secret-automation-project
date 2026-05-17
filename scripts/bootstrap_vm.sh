#!/usr/bin/env bash
# One-shot bootstrap for a fresh Ubuntu 24.04 Compute Engine VM.
# Run after SSH-ing in. Idempotent — safe to re-run.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/DPLATA/ultra-secret-automation-project/main/scripts/bootstrap_vm.sh | bash
# or copy this file up and:
#   bash scripts/bootstrap_vm.sh

set -euo pipefail

REPO_URL="https://github.com/DPLATA/ultra-secret-automation-project.git"
REPO_DIR="$HOME/ultra-secret-automation-project"
TIMEZONE="America/New_York"
CRON_TIME="0 3 * * *"  # 3 AM ET daily

echo "==> system packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ffmpeg git tzdata

echo "==> timezone -> $TIMEZONE"
sudo timedatectl set-timezone "$TIMEZONE"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "==> cloning repo"
    git clone "$REPO_URL" "$REPO_DIR"
else
    echo "==> pulling latest"
    git -C "$REPO_DIR" pull --ff-only
fi

cd "$REPO_DIR"

if [ ! -d ".venv" ]; then
    echo "==> creating venv"
    python3 -m venv .venv
fi

echo "==> installing python deps"
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install pybaseball requests beautifulsoup4 opencv-python PyYAML \
    google-api-python-client google-auth-oauthlib google-auth-httplib2

echo "==> creating data dirs"
mkdir -p videos compilations/manifests logs secrets

echo "==> wiring cron"
CRON_LINE="$CRON_TIME cd $REPO_DIR && $REPO_DIR/.venv/bin/python daily_run.py >> $REPO_DIR/logs/cron.log 2>&1"
# de-dupe: drop any prior daily_run cron lines, then append ours
( crontab -l 2>/dev/null | grep -v "daily_run.py" ; echo "$CRON_LINE" ) | crontab -
echo "==> installed cron line:"
crontab -l | grep daily_run.py

cat <<'EOF'

==> bootstrap done

Remaining manual step: copy your OAuth secrets up from your laptop:
    gcloud compute scp --recurse ~/path/to/repo/secrets/ INSTANCE_NAME:~/ultra-secret-automation-project/

Then smoke-test:
    cd ~/ultra-secret-automation-project
    .venv/bin/python daily_run.py --skip-upload

Cron will fire daily at 3:00 AM America/New_York. Inspect logs at:
    ~/ultra-secret-automation-project/logs/cron.log
EOF
