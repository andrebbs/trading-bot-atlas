#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instalador automático do Scanner Inteligente ATLAS
===================================================
Execute na RAIZ do projeto:
    python apply_patch.py

O script:
  1. Localiza src/bots/telegram_bot.py
  2. Garante que from __future__ import annotations está no topo
  3. Injeta o import do scanner
  4. Adiciona register_atlas_scanner(application) se não existir
"""

import re
import sys
import shutil
from pathlib import Path

TARGET = Path("src/bots/telegram_bot.py")
PATCH  = Path("atlas_intelligent_scanner.py")
BACKUP = TARGET.with_suffix(".py.bak")

def abort(msg: str) -> None:
    print(f"ERRO: {msg}")
    sys.exit(1)

if not TARGET.exists():
    abort(f"{TARGET} não encontrado. Execute este script na raiz do projeto.")

if not PATCH.exists():
    abort(f"{PATCH} não encontrado. Certifique-se de que está no mesmo diretório.")

# Faz backup
shutil.copy2(TARGET, BACKUP)
print(f"Backup criado: {BACKUP}")

text = TARGET.read_text(encoding="utf-8")
lines = text.splitlines()

# ── 1. Garante from __future__ import annotations no topo ──────
FUTURE = "from __future__ import annotations"
if FUTURE not in text:
    # Insere após shebang/encoding se existirem
    insert_at = 0
    for i, ln in enumerate(lines[:5]):
        if ln.startswith("#"):
            insert_at = i + 1
        else:
            break
    lines.insert(insert_at, FUTURE)
    print("✓ 'from __future__ import annotations' adicionado.")
else:
    print("✓ 'from __future__ import annotations' já presente.")

# ── 2. Injeta import do scanner ─────────────────────────────────
IMPORT_LINE = "from atlas_intelligent_scanner import register_atlas_scanner"
if IMPORT_LINE not in "\n".join(lines):
    # Encontra último import
    last_import = 0
    for i, ln in enumerate(lines):
        if ln.startswith(("import ", "from ")) and "atlas_intelligent_scanner" not in ln:
            last_import = i
    lines.insert(last_import + 1, IMPORT_LINE)
    print("✓ Import do scanner adicionado.")
else:
    print("✓ Import do scanner já presente.")

# ── 3. Adiciona register_atlas_scanner(application) ─────────────
REGISTER_CALL = "register_atlas_scanner(application)"
joined = "\n".join(lines)

if REGISTER_CALL not in joined:
    # Procura padrão comum de criação do Application
    patterns = [
        r"(application\s*=\s*Application\.builder\(\)[^\n]+build\(\))",
        r"(app\s*=\s*Application\.builder\(\)[^\n]+build\(\))",
        r"(updater\s*=\s*Updater\([^\n]+\))",
    ]
    replaced = False
    for pat in patterns:
        m = re.search(pat, joined)
        if m:
            old = m.group(0)
            new = old + "\n" + REGISTER_CALL
            joined = joined.replace(old, new, 1)
            print("✓ register_atlas_scanner(application) inserido após criação do Application.")
            replaced = True
            break

    if not replaced:
        # Adiciona ao final como fallback com aviso
        joined += (
            "\n\n# TODO: chame register_atlas_scanner(application) "
            "logo após criar o Application do Telegram.\n"
            f"# {REGISTER_CALL}\n"
        )
        print(
            "⚠ Não foi possível localizar Application.builder() automaticamente.\n"
            "  Adicione manualmente:\n"
            f"  {REGISTER_CALL}"
        )
else:
    print("✓ register_atlas_scanner(application) já presente.")

TARGET.write_text(joined, encoding="utf-8")
print(f"\n✅ Patch aplicado com sucesso em {TARGET}")
print("   Para reverter: cp src/bots/telegram_bot.py.bak src/bots/telegram_bot.py")
