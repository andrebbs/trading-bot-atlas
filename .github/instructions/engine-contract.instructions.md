---
applyTo: "src/engines/**"
description: "Use when editing engine classes, EngineSignal/EngineContext contract, OTC proxy handling, or market-specific signal evaluation behavior."
---

# Engine Contract Rules

## Intent
- Preserve a stable contract across all engines (`crypto_binary`, `forex`, `otc`).
- Keep market-specific logic isolated per engine module.

## Core Contract
- Every engine must return `EngineSignal` with coherent values for:
  - `market_type`, `symbol`, `timeframe`, `direction`
  - `probability`, `score`, `edge`, `consensus`
- `direction` remains one of: `buy`, `sell`, `neutral`.
- `evaluate()` should consume `context.metadata["signal"]` defensively with defaults.

## Consistency Requirements
- Do not break `BaseEngine.evaluate(context)` interface.
- Keep per-engine responsibilities separate:
  - `CryptoBinaryEngine`: fixed-expiry behavior.
  - `ForexEngine`: spot/CFD style signal projection.
  - `OTCEngine`: OTC-specific proxy/regime/strategy behavior.
- If changing OTC proxy map or strategy constants, preserve existing keys unless the user asked to deprecate them.

## Safe Change Workflow
1. Implement minimal local change in target engine.
2. Verify no contract drift against `src/engines/base.py`.
3. Verify router compatibility in `src/core/market_router.py` if `market_type` semantics change.
4. Prefer extending `extra` payload over modifying required signal fields.

## Validation Checklist
- Start bot in default profile and ensure engine instantiation still succeeds.
- Validate at least one CLI command after engine edits:
  - `python3 main.py analyze`
- For OTC edits, check proxy resolution paths and strategy auto-selection behavior.

## Editing Guidance
- Avoid moving shared constants into unrelated modules.
- Avoid broad refactors in engine files unless explicitly requested.
- Add concise comments only for non-obvious market-specific logic.
