#!/usr/bin/env python3
import argparse,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

# Carregar .env manualmente (remove comentários)
env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                # Remover comentário inline (tudo após #)
                if "#" in line:
                    line = line[:line.index("#")]
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"\'')
                if key not in os.environ:
                    os.environ[key] = val

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "core" / "novadexy_executor.py"
_spec = importlib.util.spec_from_file_location("novadexy_executor", _MODULE_PATH)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
NovaDexyExecutor = _module.NovaDexyExecutor
NovaDexySettings = _module.NovaDexySettings

p=argparse.ArgumentParser(description="NovaDexy demo smoke test; sem --execute é dry-run.")
p.add_argument("--symbol",default="BTC/USDT");p.add_argument("--direction",default="BUY");p.add_argument("--price",required=True,type=float);p.add_argument("--amount-cents",type=int);p.add_argument("--expiration",type=int);p.add_argument("--execute",action="store_true")
a=p.parse_args();s=NovaDexySettings.from_env()
if not a.execute: s=NovaDexySettings(False,"dry_run",s.base_url,s.token,s.account_id,s.default_amount_cents,s.default_expiration,s.timeout_seconds)
r=NovaDexyExecutor(s).place_order(a.symbol,a.direction,a.price,a.amount_cents,a.expiration);print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r["ok"] else 1)
