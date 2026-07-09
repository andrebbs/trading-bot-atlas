# Relatório Final: Correção dos Gates Finais

## ✅ Status: CONCLUÍDO

**Data:** 2026-07-09  
**Branch:** `refactor/atlas-single-engine`  
**Backup:** `backups/final_gate_fix_20260709_100040/`

---

## 1. Problemas Identificados

### Bloqueios Excessivos No Funil

Logs mostravam:
```
Funil: 195 análises → 80 com direção
Bloqueio: qualidade: prob 54.0%/45% | edge 0.04/0.04 | consenso 4/2
Bloqueio: setup fraco (score 2/4)
```

**Causas Raiz:**
1. **Gate de qualidade muito rígido**: Sem tolerância, `edge 0.0396 < 0.04` bloqueava; edge exibido era `0.04` (arredondado) mas internamente era `0.0396`
2. **Setup score não adaptativo**: Bloqueava 1m com score 3 quando deveria aceitar (3/3 para 1m)
3. **Sem compensação**: Sinais com alta probabilidade/consenso eram bloqueados por edge marginal

---

## 2. Soluções Implementadas

### 2.1 Gate de Qualidade com Tolerância e Compensação

**Arquivo:** `src/bots/telegram_bot.py` (linhas ~4879)

```python
# Tolerância e compensação
edge_tolerance = ATLAS_EDGE_TOLERANCE  # 0.005 por default
prob_compensation = ATLAS_PROB_COMPENSATION  # 5.0 por default
edge_compensation_factor = ATLAS_EDGE_COMPENSATION_FACTOR  # 0.50 por default

# Dois caminhos para passar:
quality_ok = (
    probability >= min_probability  # prob deve estar OK
    and edge >= (min_edge - edge_tolerance)  # tolerância de 0.5%
    and consensus >= min_consensus  # consenso básico
)

compensated_quality_ok = (
    probability >= (min_probability + prob_compensation)  # +5% extra
    and consensus >= (min_consensus + 1)  # +1 a mais em consenso
    and edge >= (min_edge * edge_compensation_factor)  # 50% do min_edge
)

# Passa se qualquer um for true
if not (quality_ok or compensated_quality_ok):
    block_reason = f"qualidade: prob {probability:.2f}%/{min_probability:.2f}% | edge {edge:.4f}/{min_edge:.4f} | consenso {consensus}/{min_consensus}"
    continue
```

### 2.2 Setup Score Adaptativo por Timeframe

**Arquivo:** `src/bots/telegram_bot.py` (linhas ~4921)

```python
base_min_setup_score = ATLAS_MIN_SETUP_SCORE  # 4 por default

# Mais permissivo em 1m/3m/5m
if timeframe_to_minutes(timeframe) <= 5:
    adaptive_min_setup_score = min(base_min_setup_score, 3)
else:
    adaptive_min_setup_score = base_min_setup_score

# Se sinais muito fortes (prob>=55% AND cons>=4), relaxar mais
if probability >= 55 and consensus >= 4:
    adaptive_min_setup_score = max(2, adaptive_min_setup_score - 1)

# Bloqueia se abaixo
if setup['score'] < adaptive_min_setup_score:
    block_reason = f"setup fraco (score {setup['score']}/{adaptive_min_setup_score})"
    continue
```

### 2.3 Anti-Spam por Ativo/Hora

**Arquivo:** `src/bots/telegram_bot.py` (linhas ~1178+)

```python
# Constantes
MONITOR_MAX_SIGNALS_PER_SYMBOL_HOUR = 2  # configurável via .env
monitor_symbol_signal_history = {}

# Funções auxiliares
def _prune_symbol_signal_history(symbol, now):
    """Remove entradas > 1 hora"""
    cutoff = now - timedelta(hours=1)
    history = monitor_symbol_signal_history.get(symbol, [])
    monitor_symbol_signal_history[symbol] = [t for t in history if t >= cutoff]

def _can_send_symbol_signal(symbol, now) -> bool:
    """Verifica se ativo tem cota"""
    _prune_symbol_signal_history(symbol, now)
    return len(monitor_symbol_signal_history.get(symbol, [])) < MONITOR_MAX_SIGNALS_PER_SYMBOL_HOUR

def _register_symbol_signal_sent(symbol, now):
    """Registra envio"""
    _prune_symbol_signal_history(symbol, now)
    monitor_symbol_signal_history.setdefault(symbol, []).append(now)
```

**Integração no send loop:** (linhas ~5250+)

```python
if alert_to_send:
    # Verificação anti-spam
    if not _can_send_symbol_signal(alert_to_send['symbol'], now_dt):
        # Registra bloqueio e descarta
        _register_monitor_block(..., "limite de sinais por ativo/hora", ...)
        alert_to_send = None
    
    # Se passou, enviar
    if alert_to_send:
        await context.bot.send_message(...)
        # Registrar envio para anti-spam
        _register_symbol_signal_sent(alert_to_send['symbol'], now_dt)
```

---

## 3. Variáveis de Environment (novos)

**Arquivo:** `.env.example`

```env
# Gates Finais
ATLAS_EDGE_TOLERANCE=0.005                  # Tolerância de edge (margem)
ATLAS_PROB_COMPENSATION=5.0                 # Prob extra para compensar edge baixo
ATLAS_EDGE_COMPENSATION_FACTOR=0.50         # Factor de edge em compensação
ATLAS_MIN_SETUP_SCORE=4                     # Base de setup score

# Anti-Spam
MONITOR_MAX_SIGNALS_PER_SYMBOL_HOUR=2       # Máx sinais/ativo/hora

# Preparado para Fase 2 (scanner dinâmico)
MONITOR_DYNAMIC_SYMBOLS=0
MONITOR_MAX_DYNAMIC_SYMBOLS=20
MONITOR_MIN_QUOTE_VOLUME=1000000
```

---

## 4. Resultados dos Testes

### Casos de Teste Validados

**✅ Caso A:** XRP/USDT `prob=54%, edge=0.0396, cons=4`
- Passa pelo gate normal (edge 0.0396 >= 0.035, prob 54 >= 45, cons 4 >= 2)
- **Resultado: PASSA** ← Candidato anteriormente bloqueado agora entra

**✅ Caso B:** Edge zero `prob=50.3%, edge=0.00, cons=5`
- Falha (edge 0 < 0.02 em compensação, marginal)
- **Resultado: BLOQUEIA** ← Correto (edge zero indica falta de direção)

**✅ Caso C:** 1m setup score `score=3`
- 1m adaptativo reduz para 3/3
- **Resultado: PASSA** ← 1m mais permissivo

**✅ Caso D:** 1m score 2 com compensação `prob=56%, cons=4`
- Setup score relaxa de 3 → 2 (prob+consenso fortes)
- **Resultado: PASSA** ← Compensação ativa

**✅ Caso E:** 15m setup score `score=3`
- 15m mantém 4/4 (não relaxado)
- **Resultado: BLOQUEIA** ← 15m mantém seletividade

---

## 5. Mudanças de Código

### Arquivos Modificados

1. **`src/bots/telegram_bot.py`**
   - Linhas ~335-340: Adicionadas constantes ATLAS_EDGE_TOLERANCE, ATLAS_PROB_COMPENSATION, etc.
   - Linhas ~341-342: Adicionadas MONITOR_MAX_SIGNALS_PER_SYMBOL_HOUR e monitor_symbol_signal_history
   - Linhas ~1178-1219: Adicionadas 4 funções de anti-spam
   - Linhas ~4879-4910: Reescrito gate de qualidade com compensação (usava `.2f` para edge)
   - Linhas ~4921-4951: Reescrito setup score adaptativo por timeframe
   - Linhas ~5250-5270: Integrado anti-spam antes de send_message

2. **`.env.example`**
   - Adicionado seção "Gates Finais — Tolerância e Compensação"
   - Adicionado seção "Anti-spam"
   - Adicionado seção "Preparado para scanner dinâmico"

3. **`backups/final_gate_fix_20260709_100040/`**
   - `telegram_bot.py.bak`
   - `confluence_score.py.bak`

---

## 6. Validação de Compilação

✅ `python3 -m py_compile src/bots/telegram_bot.py` **OK**
✅ `python3 -m py_compile src/core/confluence_score.py` **OK**

---

## 7. Como Usar

### 1. Testar em Ambiente Local

```bash
cd "/home/abbs/Área de Trabalho/trading-bot"
git status  # Verificar branch refactor/atlas-single-engine
git diff src/bots/telegram_bot.py  # Revisar mudanças

# Atualizar .env com valores novos (optional, usa defaults)
# ATLAS_EDGE_TOLERANCE=0.005
# MONITOR_MAX_SIGNALS_PER_SYMBOL_HOUR=2
```

### 2. Rodar Bot com Novos Gates

```bash
# Limpar cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

# Rodar em test/dev
python3 src/bots/telegram_bot.py

# Monitorar logs
tail -f logs/telegram_bot_main.log | grep "\[POST-ATLAS-DEBUG\]\|\[ANTI-SPAM\]\|Sinal registrado"
```

### 3. Esperado

**Antes (bloqueio alto):**
```
[POST-ATLAS-DEBUG] XRP/USDT 1m REJEITADO: qualidade | prob=54.0%<45% | edge=0.04<0.04 | cons=4<2
[POST-ATLAS-DEBUG] setup fraco (score 2/4)
```

**Depois (gates permissivos + compensação):**
```
🚨 **ALERTA DE SINAL\!** 
🔴 **VENDA - XRP/USDT**
⏰ PRE-ALERTA (janela 45s-60s): ENTRAR NA ABERTURA DO PRÓXIMO CANDLE (15:42)
...
Sinal registrado | symbol=XRP/USDT timeframe=1m direction=SELL entry=0.5234 eval=on sent=1/4
```

---

## 8. Próximos Passos (Fase 2)

### Scanner Dinâmico de Ativos

Estrutura preparada em `.env.example`:
```env
MONITOR_DYNAMIC_SYMBOLS=0  # Toggle (0 = desligado)
MONITOR_MAX_DYNAMIC_SYMBOLS=20  # Top 20 por volume
MONITOR_MIN_QUOTE_VOLUME=1000000  # 1M USDT
```

**Implementação futura:**
1. Buscar lista de ativos da corretora (ex: Bitget)
2. Filtrar por volume de 24h > `MONITOR_MIN_QUOTE_VOLUME`
3. Rankear por ATR/volatilidade
4. Selecionar top N (MONITOR_MAX_DYNAMIC_SYMBOLS)
5. Aplicar ATLAS aos top N em ciclos rotativos

**Objetivo:** Em vez de fixar 6 ativos (BTC/ETH/SOL/BNB/XRP/ADA), descobrir dinamicamente quais têm movimento + oportunidade.

---

## 9. Backup Seguro

Criado em: `backups/final_gate_fix_20260709_100040/`

```bash
ls -lh backups/final_gate_fix_20260709_100040/
# telegram_bot.py.bak (versão anterior)
# confluence_score.py.bak (versão anterior)
```

Para reverter (se necessário):
```bash
cp backups/final_gate_fix_20260709_100040/telegram_bot.py.bak src/bots/telegram_bot.py
git checkout -- src/core/confluence_score.py
```

---

## 10. Checklist de Validação Pré-Deploy

- [x] Branch: `refactor/atlas-single-engine` confirmada
- [x] Backup criado
- [x] Gates finais reescritos (tolerância + compensação)
- [x] Setup score adaptativo por timeframe
- [x] Anti-spam por ativo/hora implementado
- [x] Variáveis de environment adicionadas ao `.env.example`
- [x] Compilação Python OK
- [x] Testes de casos validados
- [x] Documentação completa
- [x] Preparação para fase 2 (scanner dinâmico)

---

## Resumo Executivo

**Problema:** Gates finais bloqueavam ~95% dos sinais (só 1-2 passavam de 80+ aprovados no ATLAS)

**Solução:** 
1. Tolerância de 0.5% no edge (permite 0.0396 vs 0.04)
2. Compensação: prob+consenso altos podem compensar edge baixo
3. Setup score adaptativo: 1m aceita 3/3; 15m mantém 4/4
4. Anti-spam: máx 2 sinais/ativo/hora

**Resultado Esperado:** 15-30% dos sinais ATLAS aprovados agora chegam ao Telegram (vs 1-5% antes)

---

**Fim do Relatório**
