# AGENTS.md

Agent instructions for this repository.

## Project Identity
- Project root: `/home/abbs/trading-bot`
- Primary runtime entrypoint: `src/bots/telegram_bot.py` (started via shell scripts)
- Secondary CLI entrypoint: `main.py` (`analyze`, `backtest`, `paper`)
- Keep this project separate from `/home/abbs/forex-bot` (different codebase and ops flow).

## First Steps For Any Task
1. Read `README.md` and `docs/README.md` for feature overview.
2. Check market/profile startup scripts before changing runtime behavior:
   - `run_bot_main.sh`
   - `run_bot_abbs_forex.sh`
   - `run_bot_otc.sh`
3. Prefer minimal edits in existing modules; do not move files unless requested.

## Run And Validate
- Install deps: `python3 -m pip install -r requirements.txt`
- Main bot (default profile): `bash run_bot_main.sh`
- Forex profile inside this repo: `bash run_bot_abbs_forex.sh`
- OTC profile: `bash run_bot_otc.sh`
- Webhook mode: `bash run_webhook.sh`
- CLI checks:
  - `python3 main.py analyze`
  - `python3 main.py backtest`
  - `python3 main.py paper`

## Architecture Map
- Bot orchestration and Telegram commands: `src/bots/telegram_bot.py`
- Webhook receiver: `src/bots/webhook_server.py`
- Market routing: `src/core/market_router.py`
- Execution engines:
  - `src/engines/crypto_binary_engine.py`
  - `src/engines/forex_engine.py`
  - `src/engines/otc_engine.py`
- Analysis core:
  - `src/core/indicators.py`
  - `src/core/analyzer.py`
  - `src/core/backtester.py`
- Execution/connectors:
  - `src/core/exchange_connector.py`
  - `src/core/bitget_executor.py`
  - `src/core/mt5_connector.py`
- Global config: `config/config.py`

## Critical Conventions
- `MARKET_TYPE` controls engine selection through `src/core/market_router.py`.
- `BOT_PROFILE` changes env key lookup and log/state file names in `src/bots/telegram_bot.py`.
- Profile-aware env lookup uses `<KEY>_<PROFILE_SUFFIX>` first, then `<KEY>` fallback.
- Do not hardcode secrets/tokens; keep credentials in `.env` only.
- Preserve existing APScheduler behavior and monitor cadence unless user explicitly requests behavior changes.

## Files Agents Should Check During Debugging
- Bot logs: `logs/telegram_bot_<profile>.log`
- Market diagnostics: `logs/market_diagnostics_<profile>.log`
- Runtime state: `logs/bot_state.json`
- Runtime configs/artifacts: `logs/trade_config.json`, `logs/paper_trades.json`, `logs/eco_events.json`

## Documentation Links (Source Of Truth)
- Setup and install: [INSTALL.md](INSTALL.md), [QUICKSTART.md](QUICKSTART.md)
- Main overview: [README.md](README.md)
- Docs index: [docs/README.md](docs/README.md)
- Telegram behavior and commands: [docs/TELEGRAM_BOT.md](docs/TELEGRAM_BOT.md)
- MT5 integration notes: [docs/MT5_SETUP.md](docs/MT5_SETUP.md)
- Current roadmap/checklist: [docs/PROJECT_CHECKLIST.md](docs/PROJECT_CHECKLIST.md)

## Editing Guidance
- Prefer targeted fixes over broad refactors.
- Keep command names, env var names, and script interfaces backward compatible.
- If changing monitoring logic, validate both crypto and forex profile paths.
- If changing routing logic, confirm aliases still map correctly (`crypto`, `binary`, `fx`, etc.).

## Optional Next Customizations
- Add `.github/instructions/runtime.instructions.md` for run/debug workflow details scoped to `src/bots/**`.
- Add `.github/instructions/market-routing.instructions.md` scoped to `src/core/market_router.py` and `src/engines/**`.
- Add `.github/prompts/triage-telegram.prompt.md` for one-command log triage and incident summaries.
