---
applyTo: "src/core/market_router.py"
description: "Use when changing market type normalization, alias mapping, engine selection, or supported market list in market_router.py."
---

# Market Routing Rules

## Intent
- Keep market routing deterministic and backward compatible.
- Prevent regressions in alias handling and engine mapping.

## Required Invariants
- `normalize_market_type` must keep safe fallback to `crypto_binary` for empty input.
- Existing aliases must not break without explicit user approval:
  - `crypto`, `binary`, `crypto-binario`, `crypto_binario` -> `crypto_binary`
  - `fx` -> `forex`
  - `acoes`, `ações` -> `stocks`
- `create_engine` must continue raising clear `ValueError` for unsupported values.
- `supported_market_types()` output must reflect canonical keys from internal mapping.

## Change Workflow
1. Update canonical market map first (`_SUPPORTED_MARKET_TYPES`).
2. Update aliases in `normalize_market_type` only when needed.
3. Keep error messages explicit and user-facing.
4. Avoid hidden side effects in routing functions.

## Validation Checklist
- Confirm `run_bot_main.sh` still resolves a valid engine for default `MARKET_TYPE`.
- Confirm forex path remains valid with `run_bot_abbs_forex.sh`.
- If adding/removing market types, ensure docs and env examples are updated in the same task.

## Editing Guidance
- Prefer additive changes (new alias/key) over behavioral rewrites.
- Keep function signatures stable to avoid breaking bot call sites.
