#!/usr/bin/env python3
from pathlib import Path

bot = Path("src/bots/telegram_bot.py")
patch = Path("atlas_scanner_patch.py")

if not bot.exists():
    raise SystemExit("ERRO: src/bots/telegram_bot.py não encontrado. Execute na raiz do projeto.")
if not patch.exists():
    raise SystemExit("ERRO: atlas_scanner_patch.py não encontrado no diretório atual.")

text = bot.read_text(encoding="utf-8")
patch_text = patch.read_text(encoding="utf-8")

marker = "# === ATLAS INTELLIGENT SCANNER PATCH ==="
if marker not in text:
    lines = text.splitlines()
    insert = 0
    for i, ln in enumerate(lines[:160]):
        if ln.startswith("import ") or ln.startswith("from ") or not ln.strip() or ln.strip().startswith("#"):
            insert = i + 1
        elif insert:
            break
    lines.insert(insert, "\n" + marker + "\n" + patch_text + "\n# === END ATLAS INTELLIGENT SCANNER PATCH ===\n")
    text = "\n".join(lines) + "\n"

if "register_atlas_scanner(application)" not in text:
    text += "\n# TODO: chame register_atlas_scanner(application) após criar o Application.\n"

bot.write_text(text, encoding="utf-8")
print("OK: patch inserido com sucesso!")
print("Lembre de adicionar: register_atlas_scanner(application) após criar o Application.")
