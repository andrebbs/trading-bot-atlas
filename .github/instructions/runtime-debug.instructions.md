---
applyTo: "src/bots/**"
description: "Use when debugging runtime issues, monitor loops, Telegram command failures, scheduler behavior, or profile-specific startup problems in this repository."
---

# Runtime And Debug Workflow (Bots)

## Scope
- Applies to runtime triage and operational debugging for bot orchestration in `src/bots/`.
- Prioritize reproducible diagnosis before changing behavior.

## Fast Triage Order
1. Confirm startup path used by operator:
   - `bash run_bot_main.sh`
   - `bash run_bot_abbs_forex.sh`
   - `bash run_bot_otc.sh`
2. Confirm profile and market routing assumptions:
   - `BOT_PROFILE`
   - `MARKET_TYPE`
3. Inspect logs and state before editing code:
   - `logs/telegram_bot_<profile>.log`
   - `logs/market_diagnostics_<profile>.log`
   - `logs/bot_state.json`
4. Reproduce with smallest command possible, then patch minimally.

## Required Checks Before Any Runtime Edit
- Validate environment keys through profile-aware behavior in `src/bots/telegram_bot.py` (`<KEY>_<PROFILE_SUFFIX>` first, then fallback key).
- Verify routing aliases still map correctly in `src/core/market_router.py`.
- Keep scheduler cadence unchanged unless explicitly requested by user.
- Never hardcode Telegram tokens, API keys, or chat ids.

## Command Baseline
- Install dependencies: `python3 -m pip install -r requirements.txt`
- Main runtime: `bash run_bot_main.sh`
- Webhook runtime: `bash run_webhook.sh`
- Minimal CLI sanity checks:
  - `python3 main.py analyze`
  - `python3 main.py backtest`

## Incident Patterns To Check First
- Bot starts but no alerts:
  - Missing/incorrect `TELEGRAM_CHAT_ID`
  - Monitor not active (`/monitor on` flow)
  - Profile mismatch causing wrong env keys
- Unexpected market behavior:
  - `MARKET_TYPE` mismatch
  - Alias normalization regression in router
- Duplicate or missing signals:
  - Dedup and cooldown logic in monitor flow
  - State drift in `logs/bot_state.json`

## Edit Strategy
- Prefer local fix in existing function over refactor.
- Keep public command interface stable.
- If monitor logic is touched, validate both default and forex profile paths.
- Add concise comments only where logic is non-obvious.

## Handoff Notes Format
When finishing a runtime fix, report:
1. Root cause.
2. Exact file changed.
3. Validation commands executed.
4. Residual risk (if any).
