# 📊 Guia Rápido - Horários de Operação por Ativo

**Sistema ATLAS v1.1** - Filtros de Liquidez Ativos

**ATLAS** = Advanced Technical Liquidity Analysis System

---

## ⏰ **Horários em UTC (Brasil = UTC-3)**

```
Londres:      07:00 - 16:00 UTC  (04:00 - 13:00 Brasília)
Nova York:    12:00 - 21:00 UTC  (09:00 - 18:00 Brasília)
Overlap L+NY: 12:00 - 16:00 UTC  (09:00 - 13:00 Brasília) ⭐ MELHOR
Asiática:     21:00 - 07:00 UTC  (18:00 - 04:00 Brasília) ⚠️ EVITAR
```

---

## 🟢 **TIER 1 - Major (Opera 24/7)**

| Ativo | Comandos | Horário | Score Min | ADX Min |
|-------|----------|---------|-----------|---------|
| **BTC** | `/btc` `/bitcoin` | ✅ 24/7 | 55% | 24 |
| **ETH** | `/eth` `/ethereum` | ✅ 24/7 | 55% | 24 |

**✅ Pode operar**: Qualquer horário, qualquer dia  
**❌ Nunca bloqueado**: Liquidez profunda sempre

---

## 🟡 **TIER 2 - Large Caps (Sessão Ativa)**

| Ativo | Comandos | Horário | Score Min | ADX Min |
|-------|----------|---------|-----------|---------|
| **SOL** | `/sol` | 🕐 Seg-Sex, 07-21h UTC | 55% | 26 |
| **XRP** | `/xrp` | 🕐 Seg-Sex, 07-21h UTC | 55% | 26 |
| **BNB** | `/bnb` | 🕐 Seg-Sex, 07-21h UTC | 55% | 26 |

**✅ Pode operar**:
- Segunda a Sexta
- 07:00 - 16:00 UTC (Londres) OU 12:00 - 21:00 UTC (Nova York)

**❌ Bloqueado em**:
- Sábado/Domingo (qualquer horário)
- Madrugada asiática (21:00 - 07:00 UTC) em dias úteis

---

## 🔴 **TIER 3 - Alt Coins (Overlap Apenas)**

| Ativo | Comandos | Horário | Score Min | ADX Min |
|-------|----------|---------|-----------|---------|
| **ADA** | `/ada` | ⭐ Seg-Sex, 12-16h UTC | 60% | 30 |
| **DOGE** | - | ⭐ Seg-Sex, 12-16h UTC | 60% | 30 |
| **LTC** | `/ltc` | ⭐ Seg-Sex, 12-16h UTC | 60% | 30 |
| **LINK** | - | ⭐ Seg-Sex, 12-16h UTC | 60% | 30 |

**✅ Pode operar**:
- Segunda a Sexta
- **APENAS 12:00 - 16:00 UTC** (overlap Londres+NY)
- Em Brasília: 09:00 - 13:00 (horário comercial da manhã)

**❌ Bloqueado em**:
- Sábado/Domingo (qualquer horário)
- Antes de 12:00 UTC ou após 16:00 UTC (mesmo em dias úteis)
- Toda madrugada asiática

---

## 💡 **Por Que Esses Horários?**

### **Problema**: Dojis em Baixa Liquidez
Ativos como ADA, LTC e DOGE **viram "máquinas de dojis"** quando:
- ❌ Volume baixo (madrugada, finais de semana)
- ❌ Spreads altos (poucos market makers)
- ❌ Manipulação de bots (oscilações sem direção)

### **Solução**: Filtrar por Horário
- ✅ BTC/ETH têm liquidez 24/7 → **TIER 1**
- ⚠️ SOL/XRP/BNB funcionam em sessões ativas → **TIER 2**
- 🚨 ADA/LTC/DOGE precisam de overlap para funcionar → **TIER 3**

---

## 🎯 **Exemplos Práticos**

### **Cenário 1: Segunda-Feira, 10:00 UTC (07:00 Brasília)**
```
✅ /btc   → APROVADO (Tier 1 - 24/7)
✅ /eth   → APROVADO (Tier 1 - 24/7)
✅ /sol   → APROVADO (Tier 2 - Londres ativa)
❌ /ada   → BLOQUEADO (Tier 3 - fora do overlap, precisa ser após 12h UTC)
```

### **Cenário 2: Quarta-Feira, 14:00 UTC (11:00 Brasília)**
```
✅ /btc   → APROVADO (Tier 1 - 24/7)
✅ /eth   → APROVADO (Tier 1 - 24/7)
✅ /sol   → APROVADO (Tier 2 - Overlap L+NY)
✅ /ada   → APROVADO (Tier 3 - Overlap ativo!)
```

### **Cenário 3: Sábado, 14:00 UTC (11:00 Brasília)**
```
✅ /btc   → APROVADO (Tier 1 - 24/7)
✅ /eth   → APROVADO (Tier 1 - 24/7)
❌ /sol   → BLOQUEADO (Tier 2 - finais de semana bloqueados)
❌ /ada   → BLOQUEADO (Tier 3 - finais de semana bloqueados)
```

### **Cenário 4: Terça-Feira, 03:00 UTC (00:00 Brasília - Madrugada)**
```
✅ /btc   → APROVADO (Tier 1 - 24/7)
✅ /eth   → APROVADO (Tier 1 - 24/7)
❌ /sol   → BLOQUEADO (Tier 2 - madrugada asiática)
❌ /ada   → BLOQUEADO (Tier 3 - madrugada asiática)
```

---

## 🔧 **Como Saber Se Foi Bloqueado?**

Quando você tenta analisar um ativo fora de horário:

```
⏸ ADA/USDT - Filtro de Liquidez Ativo

❌ Tier 3 (Alt Coin) requer OVERLAP Londres+NY (12-16h UTC). 
Atual: 03:45 UTC (Asiática/Fechado). 
Alts de baixa liquidez geram dojis fora do overlap.

💡 Por quê?
Ativos Tier 3 geram muitos dojis e sinais falsos em horários 
de baixa liquidez. O sistema bloqueia análise para proteger 
a qualidade dos sinais.

🕐 Quando operar ADA/USDT:
• Segunda a Sexta, 12-16h UTC (Overlap Londres+NY apenas)
```

---

## 📝 **Estratégias Recomendadas**

### **Operação Conservadora (Iniciantes)**
```bash
# Monitorar APENAS Tier 1 (24/7, sempre seguro)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT
```
- ✅ Menos sinais, maior qualidade
- ✅ Pode operar qualquer horário
- ✅ Win Rate mais estável

### **Operação Balanceada (Intermediário)**
```bash
# Tier 1 + Tier 2 (bom equilíbrio)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT
```
- ✅ Mais oportunidades em horários principais
- ⚠️ Evitar madrugada e finais de semana

### **Operação Agressiva (Avançado)**
```bash
# Tier 1 + 2 + 3 (todos os ativos)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,ADA/USDT,LTC/USDT
```
- ✅ Máximo de oportunidades
- ⚠️ Requer disciplina de horário
- 🎯 **Overlap 12-16h UTC é ESSENCIAL para alts**

---

## ⏱️ **Melhor Horário para Operar (Brasil)**

```
🥇 OURO: 09:00 - 13:00 (Brasília) = 12:00 - 16:00 UTC
   → Overlap Londres+NY
   → TODOS os ativos (Tier 1, 2 e 3) operando
   → Maior volume e liquidez

🥈 PRATA: 04:00 - 09:00 (Brasília) = 07:00 - 12:00 UTC
   → Londres ativa, NY ainda não abriu
   → Tier 1 e 2 operando (sem Tier 3)

🥉 BRONZE: 13:00 - 18:00 (Brasília) = 16:00 - 21:00 UTC
   → Londres fechou, só Nova York
   → Tier 1 e 2 operando (sem Tier 3)

⚠️ EVITAR: 18:00 - 04:00 (Brasília) = 21:00 - 07:00 UTC
   → Madrugada asiática
   → Apenas Tier 1 (BTC/ETH)
   → Baixo volume global
```

---

## 📞 **Comandos Úteis**

```bash
/monitor on              # Ativa monitor automático (respeita filtros de liquidez)
/monitor off             # Desativa monitor
/config                  # Ver configuração atual
/ativos                  # Ver lista de ativos monitorados

# Análise manual (valida liquidez antes de analisar)
/btc                     # Bitcoin (Tier 1 - sempre funciona)
/eth                     # Ethereum (Tier 1 - sempre funciona)
/sol                     # Solana (Tier 2 - sessão ativa)
/ada                     # Cardano (Tier 3 - overlap apenas)
```

---

## 📊 **Logs de Diagnóstico**

Para ver quando ativos foram bloqueados:

```bash
# Ver bloqueios de liquidez
tail -f logs/market_diagnostics_main.log | grep liquidity_block

# Ver sinais aprovados pelo ATLAS
tail -f logs/telegram_bot_main.log | grep "ATLAS.*APROVADO"

# Ver sinais bloqueados pelo ATLAS
tail -f logs/telegram_bot_main.log | grep "ATLAS.*BLOQUEADO"
```

---

**Versão**: 1.1 (Jun 2026)  
**Documentação completa**: [docs/TIER_LIQUIDEZ.md](TIER_LIQUIDEZ.md)
