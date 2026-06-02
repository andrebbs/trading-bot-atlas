---
mode: agent
description: "Triage Telegram/runtime incidents: inspect bot logs, profile/env routing, monitor state, and return root cause with minimal fix plan."
---

# Triage Telegram Incident

You are triaging a runtime incident in this repository.

## Use This Prompt
- This is the canonical Telegram/runtime triage prompt for the repository.
- Prefer this prompt over shorter variants unless the user explicitly asks for a reduced checklist.

## Goal
Produce a fast, evidence-based diagnosis for Telegram bot issues (no alerts, command failures, monitor loop anomalies, wrong market/profile behavior), then propose the smallest safe fix.

## Inputs To Ask/Infer
- Incident summary (symptom + when it started).
- Active startup path used by operator:
  - `bash run_bot_main.sh`
  - `bash run_bot_abbs_forex.sh`
  - `bash run_bot_otc.sh`
- Expected profile/market (`BOT_PROFILE`, `MARKET_TYPE`).

## Mandatory Triage Flow
1. Confirm runtime path and profile assumptions.
2. Inspect evidence first (before code edits):
   - `logs/telegram_bot_<profile>.log`
   - `logs/market_diagnostics_<profile>.log`
   - `logs/bot_state.json`
3. Verify env resolution model in `src/bots/telegram_bot.py` (`<KEY>_<PROFILE_SUFFIX>` then fallback key).
4. Check market routing consistency in `src/core/market_router.py`.
5. Reproduce with smallest command/action.

## High-Probability Checks
- Bot online but no alerts:
  - `TELEGRAM_CHAT_ID` missing or wrong.
  - `/monitor on` not active.
  - Profile mismatch selecting wrong env keys.
- Signals unexpected or market mismatch:
  - `MARKET_TYPE` misconfigured.
  - Alias normalization drift in market router.
- Duplicate/missing monitor signals:
  - cooldown/dedup behavior and persisted state in `logs/bot_state.json`.

## Output Format (always)
1. **Root Cause**: one sentence.
2. **Evidence**: 3-6 concrete observations (logs, config, code path).
3. **Minimal Fix**: exact files/commands to change.
4. **Validation**: exact commands executed and expected signal of success.
5. **Residual Risk**: what remains uncertain.

## Constraints
- Do not hardcode secrets/tokens in code.
- Keep scheduler cadence and command interfaces stable unless explicitly requested.
- Prefer local, minimal patches over refactors.
