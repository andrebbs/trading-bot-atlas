# Patch ATLAS — Monitor "signal-or-explain" (Jul/2026)

Arquivo alterado: `atlas-single-engine/src/bots/telegram_bot.py`
(substituir o arquivo inteiro pelo `telegram_bot.py` deste pacote)

## O que muda

### 1. Heartbeat explicativo (principal)
O status "📡 Monitor ativo (sem novo sinal ainda)" agora inclui:
- **Funil**: quantas análises rodaram desde o último status e quantas tinham direção
- **Ciclos fora da janela**: quantos ciclos não analisaram nada por estar fora da janela de pré-alerta
- **Top 3 motivos de bloqueio** com contagem (ATLAS, qualidade, ADX, setup, filtro profissional...)
- **Melhor candidato rejeitado**: ativo, timeframe, direção (COMPRA/VENDA), horário e motivo

As estatísticas zeram após cada heartbeat (medem sempre a janela desde o último status).

### 2. Janela de pré-alerta ampliada (`get_pre_alert_window_seconds`)
- TF >= 15m: **120–15s** (antes 45–10s)
- TF 5m: **60–10s** (antes 45–10s)
- TF 1m: inalterado (20–10s)

### 3. ADX adaptativo
- Gate duro: **12** (antes 15)
- Gate "sem MACD acelerando": **15** (antes 18)

### 4. Latência
- `fetch_ohlcv` do monitor: `limit=300` (antes 500)

### 5. Descarte silencioso corrigido
Candidato aprovado que perde a janela durante a análise agora gera log
(`Candidato aprovado perdeu a janela de pre-alerta`) e entra na telemetria
do heartbeat, em vez de sumir sem rastro.

## O que NÃO muda
- Nenhum gate foi removido; nenhum sinal novo é emitido que antes não seria
  (exceto os liberados pelo ADX 12/15 e pela janela maior).
- Modo weekend, martingale, dedup e cooldowns: intactos.

## Como testar
1. Substitua o arquivo e reinicie o bot (`run_bot_main.sh`).
2. `/monitor on` e aguarde o primeiro heartbeat (10 min).
3. Verifique se o heartbeat mostra o funil. Se aparecer
   "Ciclos fora da janela" muito alto com 0 análises, o gargalo é a janela;
   se aparecerem bloqueios ATLAS/qualidade, o gargalo é calibração.
4. Nos logs, procure por `Candidato aprovado perdeu a janela` — se aparecer
   com frequência, aumente ainda mais a janela do TF correspondente.

## Rollback
Restaurar o `telegram_bot.py` original do branch.
