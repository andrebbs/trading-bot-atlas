# ATLAS — Fase 1 (correção de escala + observabilidade)

Pacote com os arquivos desta fase e ONDE colocar cada um.

## Onde colocar cada arquivo

| Arquivo | Destino no repo | Ação |
|---|---|---|
| `confluence_score.py` | `atlas-single-engine/src/core/confluence_score.py` | **SUBSTITUIR** o existente |
| `signal_guard.py`     | `atlas-single-engine/src/bot/signal_guard.py` (mesma pasta do telegram_bot.py) | **NOVO** arquivo |
| `calibrate_threshold.py` | `atlas-single-engine/scripts/calibrate_threshold.py` (ou raiz) | **NOVO** utilitário |
| `atlas.env.example`   | copie p/ `.env` e ajuste | referência de variáveis |

> Faça backup do `confluence_score.py` atual antes: `cp confluence_score.py confluence_score.py.bak`

## Ligação do signal_guard no telegram_bot.py

```python
from signal_guard import ADXGate, SignalThrottle, Heartbeat

adx_gate  = ADXGate()
throttle  = SignalThrottle()
heartbeat = Heartbeat(send_fn=self.send_telegram_message)

# para CADA candidato avaliado no loop de scan:
heartbeat.observe(symbol, direction, final_score_pct, confluence, block_reason)

if not adx_gate.ok(adx_value):
    heartbeat.observe(symbol, direction, final_score_pct, confluence, "ADX baixo")
    continue
if not throttle.allow(symbol):
    continue

# ... ao efetivamente disparar o sinal:
throttle.register(symbol)
heartbeat.mark_signal_fired()

# 1x ao fim de cada ciclo de scan de todos os ativos:
heartbeat.tick()
```

## Roteiro de deploy

**FASE 1 — coleta (48h, não muda decisões)**
```bash
cp atlas.env.example .env      # ATLAS_SHADOW_MODE=1 já vem ligado
# suba o confluence_score.py novo + signal_guard.py e rode o bot normal
```

**FASE 2 — calibrar com dados reais**
```bash
python calibrate_threshold.py /tmp/atlas_shadow.jsonl 80
```

**FASE 3 — produção**
```bash
# no .env:
ATLAS_SHADOW_MODE=0
ATLAS_MIN_SCORE=<P80 recomendado pelo script>
# e no telegram_bot: min_score=<mesmo valor>, min_confluence=3
```

## O que cada componente faz
- **confluence_score.py**: novo cálculo de score (convicção ativa → cobertura suave → bônus de concordância → curva logística), BOS/CHoCH deixa de ser veto (estrutura OU sweep OU tendência; rompimento vira bônus +5%), min_score 0.58→0.50, shadow logging embutido.
- **signal_guard.py**: `ADXGate` 12/15, `SignalThrottle` N sinais/hora por ativo, `Heartbeat` signal-or-explain.
- **calibrate_threshold.py**: mede a distribuição real de score e recomenda min_score no P80.
