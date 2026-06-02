# 🔧 GUIA DE INTEGRAÇÃO — SMC no Telegram Bot

**Data**: 29/05/2026  
**Objetivo**: Integrar SMC Detector no monitor_market do telegram_bot.py  
**Tempo estimado**: 30 minutos

---

## 📋 CHECKLIST PRÉ-INTEGRAÇÃO

- [x] SMC Detector implementado (`src/core/smc_detector.py`)
- [x] Testes validados (`test_smc_integration.py`)
- [ ] Backup do `telegram_bot.py` (segurança)
- [ ] Risk ajustado no `.env` (0.5%)
- [ ] Bot parado (para edição)

---

## 1️⃣ BACKUP DE SEGURANÇA

```bash
cd /home/abbs/trading-bot
cp src/bots/telegram_bot.py src/bots/telegram_bot.py.backup_$(date +%Y%m%d)
```

---

## 2️⃣ MODIFICAÇÕES NO CÓDIGO

### A. Adicionar Import (topo do arquivo)

**Localização**: Após os imports existentes de `src.core`

```python
from src.core.smc_detector import SMCDetector
```

### B. Instanciar SMC Detector (global)

**Localização**: Após as variáveis globais (ex: `monitoring_active`, `last_signal`)

```python
# Detector SMC global
smc_detector = SMCDetector(lookback_period=50)
```

### C. Modificar função `monitor_market()`

**Localização**: Dentro da função `monitor_market()`, ANTES de chamar `execute_trade`

**Buscar por**:
```python
def monitor_market():
    """Monitora mercado e envia alertas automáticos."""
```

**Adicionar filtro SMC** após calcular os indicadores e ANTES da decisão de trade:

```python
# ─── FILTRO SMC (NOVO) ───────────────────────────────────────────────────
try:
    smc_analysis = smc_detector.get_analysis(df)
    smc_structure = smc_analysis['structure']
    
    # Score SMC por direção
    smc_score_buy = smc_analysis['score_buy']
    smc_score_sell = smc_analysis['score_sell']
    
    # Filtrar por estrutura
    skip_reason = None
    
    if direction == 'BUY':
        if smc_structure not in ['bullish', 'transition']:
            skip_reason = f'SMC: estrutura {smc_structure} não suporta BUY'
        elif smc_score_buy < 0.40:
            skip_reason = f'SMC: score BUY baixo ({smc_score_buy:.2f} < 0.40)'
    
    elif direction == 'SELL':
        if smc_structure not in ['bearish', 'transition']:
            skip_reason = f'SMC: estrutura {smc_structure} não suporta SELL'
        elif smc_score_sell < 0.40:
            skip_reason = f'SMC: score SELL baixo ({smc_score_sell:.2f} < 0.40)'
    
    # Se ranging, sempre skip
    if smc_structure == 'ranging':
        skip_reason = 'SMC: mercado lateralizado (ranging)'
    
    if skip_reason:
        logger.info(f'[SMC FILTER] {symbol} | {direction} | BLOQUEADO: {skip_reason}')
        log_market_diagnostic(
            event='smc_filter_block',
            symbol=symbol,
            direction=direction,
            structure=smc_structure,
            smc_score_buy=smc_score_buy,
            smc_score_sell=smc_score_sell,
            reason=skip_reason
        )
        continue  # pular este sinal
    
    # Se passou o filtro, registrar
    logger.info(f'[SMC FILTER] {symbol} | {direction} | APROVADO | estrutura={smc_structure} | score={smc_score_buy if direction=="BUY" else smc_score_sell:.2f}')
    log_market_diagnostic(
        event='smc_filter_pass',
        symbol=symbol,
        direction=direction,
        structure=smc_structure,
        smc_score=smc_score_buy if direction == 'BUY' else smc_score_sell
    )

except Exception as smc_err:
    logger.warning(f'[SMC FILTER] Erro ao analisar {symbol}: {smc_err}')
    # Se SMC falhar, deixar passar (degradação graceful)
# ─────────────────────────────────────────────────────────────────────────
```

### D. (Opcional) Adicionar SMC info no alerta do Telegram

**Localização**: Onde monta a mensagem de alerta

**Buscar por**:
```python
message = f"""
🚨 ALERTA DE SINAL!
```

**Adicionar** (após "Probabilidade"):
```python
📊 SMC: {smc_structure.upper()} (score: {smc_score_buy if direction=='BUY' else smc_score_sell:.2f})
```

**Exemplo completo**:
```python
message = f"""
🚨 ALERTA DE SINAL!

{'🟢 COMPRA' if direction == 'BUY' else '🔴 VENDA'} - {symbol}

💵 Preço: ${price:.2f}
📊 Score: {probability:.3f}
📈 Probabilidade: {probability*100:.1f}%
📊 SMC: {smc_structure.upper()} (score: {smc_score_buy if direction=='BUY' else smc_score_sell:.2f})

💡 Sugestões:
🛡 Stop Loss: ${stop_loss:.2f} (-2%)
🎯 Take Profit: ${take_profit:.2f} (+4%)
"""
```

---

## 3️⃣ AJUSTAR .env

```bash
nano /home/abbs/trading-bot/.env
```

**Modificar**:
```bash
# Risk conservador durante testes SMC
BITGET_RISK_PCT=0.5      # era 1.0
BITGET_LEVERAGE=3        # era 5

# Aumentar coleta de dados
MONITOR_MAX_SIGNALS=6    # era 4

# Garantir que está no simulator
BITGET_PRODUCT_TYPE=SUSDT-FUTURES
```

**Salvar**: `Ctrl+O` → `Enter` → `Ctrl+X`

---

## 4️⃣ TESTAR INTEGRAÇÃO

### A. Teste de sintaxe

```bash
cd /home/abbs/trading-bot
python3 -m py_compile src/bots/telegram_bot.py
```

**Se erro**: corrigir sintaxe  
**Se OK**: prosseguir

### B. Teste de import

```bash
python3 -c "from src.core.smc_detector import SMCDetector; print('✅ SMC import OK')"
```

### C. Teste completo (dry-run)

```bash
python3 src/bots/telegram_bot.py --dry-run
```

**Se erro**: verificar logs  
**Se OK**: prosseguir

---

## 5️⃣ REINICIAR BOT

```bash
# Parar bot antigo
pkill -f telegram_bot.py

# Aguardar 2s
sleep 2

# Iniciar com SMC
bash run_bot_main.sh &

# Verificar se subiu
ps aux | grep telegram_bot.py | grep -v grep
```

**Esperado**: Ver processo rodando

---

## 6️⃣ VALIDAÇÃO OPERACIONAL

### A. Verificar logs

```bash
tail -f logs/telegram_bot_main.log
```

**Buscar por**:
```
[SMC FILTER] BTC/USDT | BUY | BLOQUEADO: SMC: mercado lateralizado (ranging)
[SMC FILTER] ETH/USDT | SELL | APROVADO | estrutura=bearish | score=0.65
```

### B. Verificar diagnósticos

```bash
tail -f logs/market_diagnostics_main.log | grep smc_filter
```

**Esperado**:
```json
{"event": "smc_filter_block", "symbol": "BTC/USDT", "structure": "ranging", ...}
{"event": "smc_filter_pass", "symbol": "ETH/USDT", "structure": "bearish", ...}
```

### C. Comandos no Telegram

```
/monitor on
/stats
/bitget_status
```

**Observar**: Alertas com informação SMC incluída

---

## 7️⃣ MONITORAMENTO (Próximos 7 Dias)

### Métricas Diárias

```bash
# Win Rate atual
python3 analyze_performance.py | grep "Win Rate"

# Total de trades
grep -c '"status": "CLOSED"' logs/paper_trades.json

# Sinais bloqueados por SMC
grep -c 'smc_filter_block' logs/market_diagnostics_main.log

# Sinais aprovados por SMC
grep -c 'smc_filter_pass' logs/market_diagnostics_main.log
```

### Relatório Semanal (7 dias)

```bash
python3 analyze_performance.py > reports/smc_week1_$(date +%Y%m%d).txt
```

**Analisar**:
- WR subiu?
- Profit Factor melhorou?
- Estruturas mais lucrativas (bullish vs bearish)?

---

## 8️⃣ TROUBLESHOOTING

### Problema: SMC não está filtrando

**Verificar**:
1. Import foi adicionado?
2. `smc_detector` foi instanciado?
3. Filtro está ANTES de `execute_trade`?

**Debug**:
```bash
grep -n "smc_detector" src/bots/telegram_bot.py
```

### Problema: Erro ao analisar estrutura

**Logs**:
```bash
grep "SMC FILTER.*Erro" logs/telegram_bot_main.log
```

**Causa comum**: DataFrame vazio ou muito pequeno

**Solução**: Aumentar `limit` no fetch_ohlcv

### Problema: Bot não envia alertas

**Verificar**:
1. Todos os sinais estão sendo bloqueados por ranging?
2. Score SMC muito alto (>0.40)?

**Ajustar threshold temporariamente**:
```python
elif smc_score_buy < 0.30:  # era 0.40
```

---

## 9️⃣ ROLLBACK (Se Necessário)

```bash
# Restaurar backup
cp src/bots/telegram_bot.py.backup_20260529 src/bots/telegram_bot.py

# Reiniciar
pkill -f telegram_bot.py
bash run_bot_main.sh &
```

---

## 🎯 CRITÉRIOS DE SUCESSO (7 dias)

| Métrica | Valor Atual | Alvo Semana 1 | Como Medir |
|---------|-------------|---------------|------------|
| Win Rate | 28.57% | ≥45% | `analyze_performance.py` |
| Total Trades | 14 | ≥20 | Contar CLOSED em paper_trades.json |
| Sinais Bloqueados | 0 | ~40-60% | `grep -c smc_filter_block` |
| Sinais Aprovados | 0 | ~40-60% | `grep -c smc_filter_pass` |
| P&L | -$2.48 | ≥$0 | `analyze_performance.py` |

---

## 📊 EXEMPLO DE LOG ESPERADO

```
2026-05-29 15:32:10 - INFO - [SMC FILTER] BTC/USDT | BUY | BLOQUEADO: SMC: estrutura ranging não suporta BUY
2026-05-29 15:32:15 - INFO - [SMC FILTER] ETH/USDT | SELL | BLOQUEADO: SMC: mercado lateralizado (ranging)
2026-05-29 15:32:20 - INFO - [SMC FILTER] SOL/USDT | BUY | APROVADO | estrutura=transition | score=0.55
2026-05-29 15:32:20 - INFO - [MONITOR] Executando trade: SOL/USDT | BUY | $82.86
2026-05-29 15:32:21 - INFO - [PAPER] BUY SOL @ 82.8600 qty=0.601234 notional=$49.82 market=transition
```

**Interpretação**:
- BTC e ETH bloqueados (ranging)
- SOL aprovado (transition + score 0.55)
- Trade executado com sucesso

---

## ✅ CHECKLIST FINAL

- [ ] Backup criado
- [ ] Import SMC adicionado
- [ ] SMC Detector instanciado
- [ ] Filtro inserido em `monitor_market()`
- [ ] (Opcional) Info SMC na mensagem Telegram
- [ ] `.env` ajustado (risk 0.5%)
- [ ] Sintaxe validada
- [ ] Bot reiniciado
- [ ] Logs verificados
- [ ] `/monitor on` ativado no Telegram
- [ ] Monitoramento configurado

---

## 📞 PRÓXIMOS PASSOS

**Hoje**:
1. ✅ Integrar SMC (este guia)
2. ✅ Ativar `/monitor on`
3. ✅ Observar primeiros filtros

**Amanhã**:
- Verificar trades executados vs. bloqueados
- Ajustar threshold se necessário (0.40 → 0.35 se muito restritivo)

**Em 7 dias**:
- Gerar relatório completo
- Comparar WR antes/depois SMC
- Decidir: aprovar Fase 1 ou ajustar

**Em 30 dias**:
- Completar Fases 2-5
- Atingir WR ≥60%
- Migrar para LIVE

---

**Boa sorte, Trader! 🚀**

SMC é o primeiro passo para transformar 28% → 60%+ de Win Rate.

**Estrutura de mercado > Indicadores isolados.**

Vamos dominar isso juntos! 💎
