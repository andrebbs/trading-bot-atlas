# 🎯 Sistema de Tiers de Liquidez - ATLAS v1.1

**ATLAS** = Advanced Technical Liquidity Analysis System

**Data de Implementação**: 1 de junho de 2026  
**Versão**: 1.1  
**Objetivo**: Eliminar sinais falsos causados por dojis em ativos de baixa liquidez

---

## 📊 **Problema Identificado**

Durante operações com o sistema ATLAS, foi observado que:

- ✅ **BTC e ETH** mantêm comportamento técnico consistente 24/7
- ⚠️ **SOL, XRP, BNB** funcionam bem em horários de alta liquidez, mas ficam erráticos em madrugada asiática
- ❌ **ADA, LTC, DOGE, LINK** viram "máquinas de dojis" fora do overlap Londres+NY (12-16h UTC)

**Causa Raiz**:
- Volume baixo → spreads altos → movimentos erráticos
- Market makers ausentes → preço não reflete demanda real  
- Manipulação de bots → micro oscilações sem direção

**Resultado**: Sinais falsos, especialmente em finais de semana e madrugada asiática (21h-7h UTC).

---

## 🏗️ **Arquitetura do Sistema de Tiers**

### **TIER 1 - Major (BTC/ETH)**

**Ativos**: BTC, ETH

**Características**:
- ✅ Liquidez profunda 24/7
- ✅ Opera **qualquer horário** (sem restrições)
- ✅ Mantêm estrutura técnica mesmo fora de horário comercial

**Parâmetros de Entrada**:
```python
{
    'tier': 1,
    'tier_name': 'Major',
    'min_score': 0.55,           # Score mínimo: 55%
    'min_adx': 24.0,             # ADX mínimo: 24
    'liquidity_check': False,    # SEM validação de horário
}
```

**Quando Sinalizar**:
- Score ≥ 55% + ADX ≥ 24 + Confluência ≥ 3/5 técnicas

---

### **TIER 2 - Large Caps (SOL/XRP/BNB)**

**Ativos**: SOL, XRP, BNB

**Características**:
- ✅ Excelente liquidez em **horários principais**
- ⚠️ Requer **sessão ativa**: Londres (7-16h UTC) OU Nova York (12-21h UTC)
- ❌ **Bloqueado em finais de semana** (Sábado/Domingo)

**Parâmetros de Entrada**:
```python
{
    'tier': 2,
    'tier_name': 'Large Cap',
    'min_score': 0.55,           # Score mínimo: 55%
    'min_adx': 26.0,             # ADX mínimo: 26 (mais rigoroso que Tier 1)
    'liquidity_check': True,     # Valida horário
    'min_session_level': 'any',  # Londres OU NY (qualquer uma)
}
```

**Quando Sinalizar**:
- ✅ Segunda a Sexta
- ✅ 07-16h UTC (Londres) **OU** 12-21h UTC (Nova York)
- ✅ Score ≥ 55% + ADX ≥ 26 + Confluência ≥ 3/5 técnicas

**Quando Bloquear**:
- ❌ Sábado/Domingo (qualquer horário)
- ❌ Madrugada asiática (21h-7h UTC) em dias úteis

---

### **TIER 3 - Alt Coins (ADA/DOGE/LTC/LINK)**

**Ativos**: ADA, DOGE, LTC, LINK, DOT, MATIC

**Características**:
- ⚠️ Alta volatilidade, baixa liquidez fora de picos
- ⚠️ Requer **APENAS overlap Londres+NY** (12-16h UTC)
- ❌ **Bloqueio TOTAL** em finais de semana e madrugada

**Parâmetros de Entrada**:
```python
{
    'tier': 3,
    'tier_name': 'Alt Coin',
    'min_score': 0.60,            # Score mínimo: 60% (mais rigoroso)
    'min_adx': 30.0,              # ADX mínimo: 30 (tendência forte obrigatória)
    'liquidity_check': True,      # Valida horário
    'min_session_level': 'overlap', # APENAS overlap Londres+NY
    'require_mtf_for_all': True,  # Confirmação MTF obrigatória
}
```

**Quando Sinalizar**:
- ✅ Segunda a Sexta
- ✅ **APENAS 12-16h UTC** (overlap Londres+NY - melhor liquidez)
- ✅ Score ≥ 60% + ADX ≥ 30 + Confluência ≥ 3/5 técnicas + MTF confirmado

**Quando Bloquear**:
- ❌ Sábado/Domingo (qualquer horário)
- ❌ Fora do overlap (antes de 12h UTC ou após 16h UTC)
- ❌ Madrugada asiática (21h-7h UTC)

---

## 🛡️ **Comportamento do Sistema**

### **Análise Manual (/btc, /eth, /ada, etc)**

Quando você solicita análise de um ativo fora do horário permitido:

```
⏸ ADA/USDT - Filtro de Liquidez Ativo

❌ Tier 3 (Alt Coin) requer OVERLAP Londres+NY (12-16h UTC). 
Atual: 03:45 UTC (Asiática/Fechado). 
Alts de baixa liquidez geram dojis fora do overlap.

💡 Por quê?
Ativos Tier 3 (Alt Coin) geram muitos dojis e sinais falsos em horários 
de baixa liquidez. O sistema ATLAS bloqueia análise nestes períodos 
para proteger a qualidade dos sinais.

🕐 Quando operar ADA/USDT:
• Segunda a Sexta, 12-16h UTC (Overlap Londres+NY apenas)
```

### **Monitoramento Automático (/monitor on)**

O sistema **pula automaticamente** ativos bloqueados, economizando processamento:

**Logs**:
```
[LIQUIDEZ] ⏸ ADA/USDT bloqueado - Tier 3 (Alt Coin) | 
Tier 3 (Alt Coin) requer OVERLAP Londres+NY (12-16h UTC). 
Atual: 03:45 UTC (Asiática/Fechado)
```

**Diagnóstico** (logs/market_diagnostics_<profile>.log):
```json
{
  "event": "monitor_liquidity_block",
  "profile": "main",
  "market_type": "crypto_binary",
  "requested_symbol": "ADA/USDT",
  "tier": 3,
  "tier_name": "Alt Coin",
  "reason": "❌ Tier 3 (Alt Coin) requer OVERLAP Londres+NY..."
}
```

---

## 📈 **Impacto Esperado**

### **Antes (ATLAS v1.0)**:
- 📊 ADA às 3h UTC → Doji → Sinal COMPRA (score 58%) → **❌ FALSO**
- 📊 LTC Domingo 15h UTC → Oscilação sem volume → Sinal VENDA (score 56%) → **❌ FALSO**

### **Depois (ATLAS v1.1)**:
- 📊 ADA às 3h UTC → **⏸ BLOQUEADO** (madrugada asiática)
- 📊 LTC Domingo 15h UTC → **⏸ BLOQUEADO** (final de semana)
- 📊 ADA às 14h UTC (Segunda-Feira) → Overlap L+NY → Sinal COMPRA (score 62%, ADX 32) → **✅ VÁLIDO**

### **Métricas Esperadas**:
- ⬇️ **-70% de sinais falsos** em alts (ADA/LTC/DOGE)
- ⬆️ **+15-20% Win Rate** geral (eliminação de dojis)
- 🎯 **Menos sinais, maior qualidade**

---

## 🔧 **Configuração por Perfil**

### **Perfil Main (Crypto Binary)**
Lista monitorada padrão:
```python
DEFAULT_CRYPTO_MONITORED_SYMBOLS = [
    'BTC/USDT',   # Tier 1 - 24/7
    'ETH/USDT',   # Tier 1 - 24/7
    'SOL/USDT',   # Tier 2 - Sessão ativa
    'BNB/USDT',   # Tier 2 - Sessão ativa
    'XRP/USDT',   # Tier 2 - Sessão ativa
    'ADA/USDT'    # Tier 3 - Overlap apenas
]
```

### **Customização via .env**
```bash
# Monitorar APENAS majors (conservador)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT

# Incluir large caps (balanceado)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT

# Lista completa com alts (agressivo - overlap apenas)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,BNB/USDT,ADA/USDT,DOGE/USDT,LTC/USDT
```

---

## 📝 **Checklist de Validação**

Para validar se o sistema está funcionando:

1. **Teste de Bloqueio - Tier 3 (ADA) em Madrugada Asiática**:
   ```bash
   # Simular horário: 3h UTC (Segunda-Feira)
   /ada
   # Esperado: ⏸ Filtro de Liquidez Ativo
   ```

2. **Teste de Liberação - Tier 3 (ADA) no Overlap**:
   ```bash
   # Simular horário: 14h UTC (Segunda-Feira)
   /ada
   # Esperado: Análise normal prossegue
   ```

3. **Teste de Bloqueio - Tier 2 (SOL) no Final de Semana**:
   ```bash
   # Simular horário: 14h UTC (Sábado)
   /sol
   # Esperado: ❌ Tier 2 bloqueado em finais de semana
   ```

4. **Teste Monitor - Rotação com Bloqueios**:
   ```bash
   /monitor on
   # Verificar logs: ativos Tier 2/3 devem ser pulados fora de horário
   ```

5. **Verificar Logs de Diagnóstico**:
   ```bash
   tail -f logs/market_diagnostics_main.log | grep liquidity_block
   ```

---

## 🚀 **Próximos Passos**

1. ✅ **Implementação completa** - Sistema ativo em produção
2. 🔄 **Monitoramento de Win Rate** - Acompanhar impacto ao longo de 2-4 semanas
3. 📊 **Análise de dados** - Comparar Win Rate antes/depois por tier
4. 🔧 **Ajuste fino** - Refinar horários baseado em dados reais
5. 📈 **Expansão** - Adicionar novos ativos com tier adequado (ex: AVAX, MATIC)

---

## 📞 **Suporte**

Documentação adicional:
- [README.md](../README.md) - Visão geral do sistema
- [SISTEMA_ATLAS_COMPLETO.md](../SISTEMA_ATLAS_COMPLETO.md) - Detalhes do ATLAS v1.1
- [TELEGRAM_BOT.md](TELEGRAM_BOT.md) - Comandos do bot

**Logs de diagnóstico**:
- `logs/telegram_bot_main.log` - Log principal do bot
- `logs/market_diagnostics_main.log` - Diagnósticos de mercado
- `logs/bot_state.json` - Estado atual do sistema

---

**Implementado por**: GitHub Copilot  
**Data**: 1 de junho de 2026  
**Versão**: ATLAS v1.1 - Sistema de Tiers de Liquidez
