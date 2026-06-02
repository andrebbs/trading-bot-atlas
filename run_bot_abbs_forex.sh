#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export BOT_PROFILE="${BOT_PROFILE:-abbs-forex-bot}"
export BOT_INSTANCE_NAME="${BOT_INSTANCE_NAME:-abbs-forex-bot}"
export MARKET_TYPE="${MARKET_TYPE:-forex}"

exec ./run_bot_main.sh