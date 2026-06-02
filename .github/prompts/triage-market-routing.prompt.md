---
mode: agent
description: "Triage market-routing incidents: validate market type normalization, alias mapping, engine selection, and engine signal contract with minimal-risk fixes."
---

# Triage Market Routing Incident

You are triaging a market-routing incident in this repository.

## Goal
Produce a fast, evidence-based diagnosis for routing and engine-selection issues, then propose the smallest safe fix.

## Inputs To Ask/Infer
- Reported symptom (wrong market behavior, wrong engine selected, unsupported market_type error, missing/invalid signal fields).
- Runtime path used by operator:
  - `bash run_bot_main.sh`
  - `bash run_bot_abbs_forex.sh`
  - `bash run_bot_otc.sh`
- Expected `MARKET_TYPE` and expected engine behavior.

## Mandatory Triage Flow
1. Confirm expected market path from incident report.
2. Inspect routing code first:
   - `src/core/market_router.py`
   - `_SUPPORTED_MARKET_TYPES`
   - `normalize_market_type`
3. Validate actual engine contract and behavior:
   - `src/engines/base.py`
   - `src/engines/crypto_binary_engine.py`
   - `src/engines/forex_engine.py`
   - `src/engines/otc_engine.py`
4. Reproduce with smallest possible command/action.
5. Patch minimally, preserving backward compatibility.

## High-Probability Checks
- `MARKET_TYPE` resolves to unexpected canonical value.
- Alias removed or changed unexpectedly (`crypto`, `binary`, `fx`, `acoes`, `ações`).
- Canonical key exists but maps to wrong engine class.
- Engine returns malformed/incomplete signal fields (`direction`, `probability`, `score`, `edge`, `consensus`).
- OTC proxy/strategy behavior drift after constants or mapping changes.

## Output Format (always)
1. **Root Cause**: one sentence.
2. **Evidence**: 3-6 concrete findings from code/logs/runtime behavior.
3. **Minimal Fix**: exact files and edits required.
4. **Validation**: exact commands and expected success signal.
5. **Residual Risk**: what remains uncertain.

## Validation Commands
- `python3 main.py analyze`
- `bash run_bot_main.sh` (default route)
- `bash run_bot_abbs_forex.sh` (forex route)
- `bash run_bot_otc.sh` (otc route)

## Constraints
- Preserve fallback behavior for empty market type (`crypto_binary`).
- Keep router and engine interfaces stable unless explicitly requested.
- Avoid broad refactors; prefer local targeted fixes.
- If aliases or supported markets are changed, include docs/config update in the same task.
