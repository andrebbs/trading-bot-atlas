# ATLAS HOTPATCH — 2026-07-08 23:30

## PROBLEMA IDENTIFICADO

Heartbeats mostram que sinais com **scores 45-75% e confluência 4-5/5** estão sendo bloqueados como "Neutro" ou "Sinal fraco". A correção anterior não resolveu porque havia gates muito restritivos adicionados.

## CAUSA RAIZ

1. **Gate de "Mercado lateral (SMC ranging)"** bloqueava TODO sinal quando estrutura = ranging
2. **Gate de "Baixa volatilidade"** bloqueava sinais quando ATR/price < 0.003
3. **Bloqueio de WEAK sinais** impedia aprovação mesmo com confluência 3+

## CORREÇÕES APLICADAS (3 arquivos)

### 1. `src/core/confluence_score.py` — 3 mudanças críticas

**A) Remover gates de SMC ranging e volatilidade (linhas 417-449)**
- ✅ Removido: `if smc_analysis.get('structure') == 'ranging': return False`
- ✅ Removido: `if volatility < 0.003: return False`
- ✅ Mantém: Análise SMC/volatilidade apenas para debug, não bloqueia

**B) Reduzir thresholds de recomendação (linhas 61-66)**
```python
# ANTES:
STRONG_MIN_SCORE = 0.62
MIN_SCORE = 0.50
WEAK_MIN_SCORE = 0.42

# DEPOIS:
STRONG_MIN_SCORE = 0.65   # Aumentado (mais exigente)
MIN_SCORE = 0.45          # Reduzido 0.50 → 0.45 ⬇️
WEAK_MIN_SCORE = 0.35     # Reduzido 0.42 → 0.35 ⬇️
```

**C) Remover bloqueio de WEAK sinais (linhas 415-425)**
```python
# ANTES:
if recommendation.startswith('WEAK'):
    return False, analysis  # ❌ Bloqueava WEAK

# DEPOIS:
# NÃO BLOQUEAR WEAK - deixar passar se threshold disser sim
if recommendation == 'NEUTRAL':
    return False, analysis  # ✅ Apenas NEUTRAL é bloqueado
```

### 2. `src/bots/telegram_bot.py` — 1 mudança

**Mudar default min_score_threshold de 0.50 para 0.45 (linhas 4698, 4701)**
```python
# ANTES:
min_score_threshold = float(os.getenv('ATLAS_MIN_SCORE', '0.50'))
min_score_threshold = max(
    crypto_profile.get('min_score', 0.50),
    float(os.getenv('ATLAS_MIN_SCORE', '0.50'))
)

# DEPOIS:
min_score_threshold = float(os.getenv('ATLAS_MIN_SCORE', '0.45'))
min_score_threshold = max(
    crypto_profile.get('min_score', 0.45),
    float(os.getenv('ATLAS_MIN_SCORE', '0.45'))
)
```

## RESULTADO ESPERADO

Com as correções, os scores **45-75%** com **confluência 3-5/5** devem agora:

| Cenário | Antes | Depois |
|---------|-------|--------|
| Score 45%, conf 4/5 | ❌ BLOQUEADO "Sinal fraco" | ✅ BUY (54% após logística) |
| Score 50%, conf 4/5 | ❌ BLOQUEADO "Neutro" | ✅ BUY (61% após logística) |
| Score 61%, conf 4/5 | ❌ BLOQUEADO "Neutro" | ✅ BUY (75% após logística) |
| Score 75%, conf 5/5 | ❌ BLOQUEADO "Baixa volatilidade" | ✅ STRONG_BUY |
| Score 36%, conf 3/5 | ❌ BLOQUEADO "Neutro" | ⚠️ WEAK_BUY (41% após logística) |

## PARA EXECUTAR

### Opção 1: Restart rápido
```bash
bash run_bot_main.sh
```

### Opção 2: Com ambiente customizado
```bash
export ATLAS_MIN_SCORE=0.45
export ATLAS_MIN_CONFLUENCE=3
export ATLAS_WEAK_MIN_SCORE=0.35
bash run_bot_main.sh
```

## VALIDAÇÃO

- ✅ Compilação Python: OK (`py_compile` passou)
- ✅ Lógica matemática: OK (fórmula logística 0.45 → 54%, 0.50 → 61%, etc)
- ✅ Thresholds: OK (alinhados com confluence_score.py e telegram_bot.py)
- ⏳ Runtime: Aguarda restart do bot

## CHANGELOG

| Arquivo | Linhas | Mudança | Status |
|---------|--------|---------|--------|
| confluence_score.py | 61-66 | Thresholds reduzidos | ✅ |
| confluence_score.py | 415-449 | Gates SMC/volatilidade removidos | ✅ |
| confluence_score.py | 415-425 | Bloqueio WEAK removido | ✅ |
| telegram_bot.py | 4698, 4701 | min_score_threshold 0.50→0.45 | ✅ |

## PRÓXIMAS ETAPAS

1. **Hoje**: Restart do bot com novas correções
2. **Monitor**: Verificar heartbeats para confirmar aprovações
3. **Esperado**: "Sinais enviados" aumentar de 0/8 para 3-5/8 range
4. **Se problema**: Verificar logs em `logs/telegram_bot_<profile>.log`

---
**Data**: 2026-07-08 23:30  
**Status**: ✅ Pronto para deploy  
**Próximo**: Aguarda restart manual
