#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export BOT_PROFILE=otc
export BOT_INSTANCE_NAME=otc

# OTC dedicado
export MARKET_TYPE="otc"

choose_python() {
  local candidates=(
    "$SCRIPT_DIR/.venv/bin/python3"
    "$SCRIPT_DIR/.venv_trading/bin/python3"
    "$SCRIPT_DIR/.venv_run/bin/python3"
    "/usr/bin/python3"
    "python3"
  )

  local py
  for py in "${candidates[@]}"; do
    if command -v "$py" >/dev/null 2>&1; then
      if "$py" -c "import pandas, telegram" >/dev/null 2>&1; then
        echo "$py"
        return 0
      fi
    fi
  done

  return 1
}

if ! PY_BIN="$(choose_python)"; then
  echo "Erro: nao encontrei Python com dependencias (pandas + python-telegram-bot)." >&2
  echo "Rode: python3 -m pip install --user -r requirements.txt" >&2
  exit 1
fi

exec "$PY_BIN" src/bots/telegram_bot.py
