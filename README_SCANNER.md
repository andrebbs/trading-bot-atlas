# ATLAS Scanner Inteligente – Guia Completo

## O que está neste pacote

| Arquivo | Descrição |
|---|---|
| `atlas_intelligent_scanner.py` | Módulo principal do scanner (código-fonte completo) |
| `apply_patch.py` | Instalador automático que injeta o scanner no seu bot |
| `.env.example` | Exemplo de variáveis de ambiente |
| `README_SCANNER.md` | Este guia |

---

## Instalação rápida

```bash
# 1. Extraia na raiz do seu projeto
unzip ATLAS_SCANNER_INTELIGENTE.zip

# 2. Aplique o patch automático
python apply_patch.py

# 3. Copie e ajuste as variáveis de ambiente
cp .env.example .env
nano .env          # ajuste TELEGRAM_CHAT_ID, ativos, intervalos etc.

# 4. Inicie o bot normalmente
python src/bots/telegram_bot.py
```

---

## Instalação manual (se preferir)

No `telegram_bot.py`, adicione:

```python
from __future__ import annotations          # ← deve ser a 1ª linha de código
from atlas_intelligent_scanner import register_atlas_scanner
```

Logo após criar o `Application`:

```python
application = Application.builder().token(TOKEN).build()
register_atlas_scanner(application)         # ← adicione esta linha
```

---

## Comandos disponíveis no Telegram

| Comando | Ação |
|---|---|
| `/scanner on` | Ativa o scanner |
| `/scanner off` | Desativa o scanner |
| `/scanner status` | Exibe estado atual |
| `/scanner intervalo 5` | Define intervalo para 5 minutos |
| `/scanner ativos BTC/USDT,ETH/USDT` | Atualiza lista de ativos |
| `/scanner timeframe 15m` | Muda timeframe |
| `/scanner score 0.65` | Define score mínimo para alertas |

---

## Exemplo de alerta gerado

```
🔥 ATLAS SCANNER – ALERTA
🟢 Ativo: BTC/USDT
📊 Sinal: BUY
🏆 Score: 0.73
🎯 Confiança: 0.68
⏱ Timeframe: 5m
🕐 Horário: 2026-07-01 03:15:22 UTC
```

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `ATLAS_SCANNER_ENABLED` | `false` | Ligar ao iniciar |
| `ATLAS_SCANNER_INTERVAL_SECONDS` | `300` | Intervalo em segundos |
| `ATLAS_SCANNER_TIMEFRAME` | `5m` | Timeframe padrão |
| `ATLAS_SCANNER_SYMBOLS` | `BTC/USDT,ETH/USDT,SOL/USDT` | Ativos |
| `ATLAS_SCANNER_MIN_SCORE` | `0.58` | Score mínimo |
| `ATLAS_SCANNER_COOLDOWN_SECONDS` | `900` | Cooldown entre alertas |
| `TELEGRAM_CHAT_ID` | – | Chat ID para envio de alertas |

---

## Dependências necessárias

```
python-telegram-bot[job-queue]>=20.0
```

---

## Limitações conhecidas

- O scanner **depende da `ConfluenceScoreSystem`** do projeto.  
  Sem ela, o sinal retornado será `NO_ENGINE`.
- O `JobQueue` requer `python-telegram-bot[job-queue]` instalado.
- O cooldown é em memória: reiniciando o bot, os cooldowns são zerados.
- O `TELEGRAM_CHAT_ID` precisa estar definido para envio automático de alertas.

---

## Reversão do patch

```bash
cp src/bots/telegram_bot.py.bak src/bots/telegram_bot.py
```
