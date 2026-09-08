#!/usr/bin/env python3
"""Smoke test for the Stockity/Binomo (Crypto IDX) executor.

Without --execute this only validates the payload/settings, it never
opens a WebSocket connection. Use STOCKITY_ENABLED=true and valid
credentials plus --execute to actually place a demo/live order.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env manually (mirrors scripts/novadexy_demo_smoke.py)
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                if "#" in line:
                    line = line[: line.index("#")]
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"\'')
                if key not in os.environ:
                    os.environ[key] = val

from src.core.stockity_executor import StockityExecutor, StockitySettings  # noqa: E402

p = argparse.ArgumentParser(description="Stockity smoke test; sem --execute é apenas validação de payload.")
p.add_argument("--symbol", default="Z-CRY/IDX")
p.add_argument("--direction", default="BUY")
p.add_argument("--amount-cents", type=int)
p.add_argument("--expiration-minutes", type=int)
p.add_argument("--execute", action="store_true")
a = p.parse_args()

settings = StockitySettings.from_env()
if not a.execute:
    print("Dry validation only (no WebSocket connection opened). Settings:")
    print(json.dumps({
        "mode": settings.mode,
        "platform": settings.platform,
        "default_asset_ric": settings.default_asset_ric,
        "wallet_type": settings.wallet_type,
    }, indent=2))
    raise SystemExit(0)

executor = StockityExecutor(settings)
result = executor.place_order(
    symbol=a.symbol,
    direction=a.direction,
    amount_cents=a.amount_cents,
    expiration_minutes=a.expiration_minutes,
)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result.get("ok") else 1)
