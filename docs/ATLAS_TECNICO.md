# 🤖 ATLAS - Documentação Técnica Completa

**ATLAS** = **A**dvanced **T**echnical **L**iquidity **A**nalysis **S**ystem

**Versão**: 1.1 (Junho 2026)  
**Status**: Produção  
**Objetivo**: Sistema de análise técnica multi-dimensional com filtros de liquidez para trading de criptomoedas

---

## 📋 **Índice**

1. [Visão Geral](#visão-geral)
2. [Arquitetura do Sistema](#arquitetura-do-sistema)
3. [Módulos de Análise](#módulos-de-análise)
4. [Sistema de Confluence Score](#sistema-de-confluence-score)
5. [Filtros de Liquidez (v1.1)](#filtros-de-liquidez)
6. [Integração com Binance](#integração-com-binance)
7. [Fluxo de Decisão](#fluxo-de-decisão)
8. [Configuração e Parâmetros](#configuração-e-parâmetros)

---

## 🎯 **Visão Geral**

### **O Que é o ATLAS?**

ATLAS é um sistema de análise técnica avançado que combina **5 metodologias complementares** para gerar sinais de trading de alta qualidade:

1. **Smart Money Concepts (SMC)** - Detecta fluxo institucional
2. **Wyckoff** - Analisa volume e fases de mercado
3. **Price Action** - Identifica padrões de candles
4. **Indicadores Tradicionais** - RSI, MACD, Bollinger, EMA
5. **Elliott Wave** - Contagem de ondas e projeções

### **Por Que Múltiplas Metodologias?**

```
Problema Anterior:
├─ Sistema baseado APENAS em indicadores tradicionais (RSI, MACD, Bollinger)
├─ Win Rate: 28.57% ❌
└─ Sinais defasados, muitos falsos positivos

Solução ATLAS:
├─ Combina 5 técnicas com pesos calibrados
├─ Win Rate Esperado: 60%+ ✅
└─ Filtra sinais de baixa qualidade
```

### **Diferenciais v1.1**

- ✅ **Confluence Score**: Score ponderado 0-100% baseado em concordância de técnicas
- ✅ **Filtros de Liquidez**: Bloqueia ativos Alt em horários de baixa liquidez
- ✅ **Multi-timeframe**: Confirmação em timeframes superiores
- ✅ **Gestão de Risco**: Stop-loss e take-profit dinâmicos

---

## 🏗️ **Arquitetura do Sistema**

```
┌─────────────────────────────────────────────────────────────────┐
│                      ATLAS ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐
│ Binance API  │  ← Dados OHLCV em tempo real
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│              EXCHANGE CONNECTOR (ccxt)                       │
│  • Fetch OHLCV (limite 200-500 candles)                     │
│  • Get Ticker (preço atual)                                  │
│  • Orderbook, Trades                                         │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│           TECHNICAL INDICATORS CALCULATOR                    │
│  RSI(14), MACD(12,26,9), Bollinger(20,2), EMA(9,20,50,200)  │
│  ATR(14), Volume MA(20), ADX(14)                             │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                    ANALYZER LAYER                            │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│   SMC        │  Wyckoff     │ Price Action │ Elliott Wave    │
│  Detector    │  Detector    │   Detector   │   Detector      │
│              │              │              │                 │
│ • BOS/CHoCH  │ • Acumulação │ • Engulfing  │ • Impulso       │
│ • Order      │ • Markup     │ • Pin Bar    │ • Correção      │
│   Blocks     │ • Distrib.   │ • Doji       │ • Projeções     │
│ • FVG        │ • Markdown   │ • S/R        │                 │
│              │              │              │                 │
│ Score: 0-1   │ Score: 0-1   │ Score: 0-1   │ Score: 0-1      │
└──────────────┴──────────────┴──────────────┴─────────────────┘
               │              │              │                │
               └──────────────┴──────────────┴────────────────┘
                                    │
                                    ▼
           ┌────────────────────────────────────────────────┐
           │     CONFLUENCE SCORE SYSTEM (MASTER)           │
           │                                                │
           │  Weighted Combination:                         │
           │  • SMC:         30%                            │
           │  • Wyckoff:     25%                            │
           │  • Price Action:20%                            │
           │  • Traditional: 15%                            │
           │  • Elliott:     10%                            │
           │                ────                            │
           │  Total:        100% → Final Score (0-100%)     │
           │                                                │
           │  Confluence Count: 3/5 técnicas mínimo         │
           └────────────────┬───────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────────────────┐
           │      LIQUIDITY FILTERS (v1.1 - NEW)            │
           │                                                │
           │  Tier 1 (BTC/ETH):     24/7                    │
           │  Tier 2 (SOL/XRP/BNB): Sessão ativa            │
           │  Tier 3 (ADA/DOGE/LTC):Overlap apenas          │
           │                                                │
           │  Bloqueia alts em:                             │
           │  • Finais de semana                            │
           │  • Madrugada asiática (21-7h UTC)              │
           └────────────────┬───────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────────────────┐
           │           DECISION GATE                        │
           │                                                │
           │  ✅ APROVADO se:                               │
           │     • Score ≥ 55% (Tier 1/2) ou 60% (Tier 3)   │
           │     • ADX ≥ 24/26/30 (por tier)                │
           │     • Confluência ≥ 3/5 técnicas               │
           │     • Horário de liquidez OK                   │
           │                                                │
           │  ❌ BLOQUEADO caso contrário                   │
           └────────────────┬───────────────────────────────┘
                            │
                            ▼
           ┌────────────────────────────────────────────────┐
           │            SIGNAL OUTPUT                       │
           │                                                │
           │  • Telegram Alert (/monitor automático)        │
           │  • Análise Manual (/btc, /ada, etc)            │
           │  • Logs estruturados                           │
           │  • Diagnósticos de bloqueio                    │
           └────────────────────────────────────────────────┘
```

---

## 📊 **Módulos de Análise**

### **1. Smart Money Concepts (SMC) - 30%**

**Arquivo**: `src/core/smc_detector.py`

**O Que Detecta**:
- **BOS (Break of Structure)**: Rompimento de estrutura de mercado
- **CHoCH (Change of Character)**: Mudança de caráter (bullish ↔ bearish)
- **Order Blocks**: Zonas de ordens institucionais
- **FVG (Fair Value Gap)**: Gaps de liquidez não preenchidos

**Score Calculation**:
```python
score_smc = (
    bos_score * 0.4 +        # Estrutura de mercado (peso alto)
    order_block_score * 0.3 + # Zonas institucionais
    fvg_score * 0.3           # Gaps de valor justo
)
# Retorna: 0.0 - 1.0
```

**Quando Pontua Alto**:
- ✅ BOS bullish com Order Block testado = 0.8-1.0
- ✅ CHoCH recente + FVG alinhado = 0.7-0.9
- ❌ Sem estrutura clara = 0.0-0.3

---

### **2. Wyckoff - 25%**

**Arquivo**: `src/core/wyckoff_detector.py`

**O Que Detecta**:
- **Acumulação** (Phase A-E): Smart money comprando
- **Markup**: Impulsão bullish
- **Distribuição** (Phase A-E): Smart money vendendo
- **Markdown**: Impulsão bearish

**Score Calculation**:
```python
score_wyckoff = (
    phase_score * 0.5 +      # Fase atual do ciclo
    volume_score * 0.3 +     # Volume profile
    support_resistance * 0.2  # S/R de Wyckoff
)
# Retorna: 0.0 - 1.0
```

**Quando Pontua Alto**:
- ✅ Acumulação + Spring (Phase C) = 0.8-1.0 (setup de compra)
- ✅ Distribuição + UTAD (Phase D) = 0.8-1.0 (setup de venda)
- ❌ Fase indefinida ou transição = 0.2-0.4

---

### **3. Price Action - 20%**

**Arquivo**: `src/core/price_action_detector.py`

**O Que Detecta**:
- **Padrões de Candle**: Engulfing, Pin Bar, Doji, Hammer, Shooting Star
- **Suporte e Resistência**: Níveis testados múltiplas vezes
- **Rejection Wicks**: Rejeições de preço em zonas críticas

**Score Calculation**:
```python
score_pa = (
    candle_pattern_score * 0.5 +  # Padrões clássicos
    sr_score * 0.3 +               # Suporte/Resistência
    rejection_score * 0.2          # Rejeições de pavio
)
# Retorna: 0.0 - 1.0
```

**Quando Pontua Alto**:
- ✅ Engulfing bullish em suporte forte = 0.8-1.0
- ✅ Pin bar bullish com rejeição de mínima = 0.7-0.9
- ❌ Doji (indecisão) = 0.0-0.3

---

### **4. Indicadores Tradicionais - 15%**

**Arquivo**: `src/core/analyzer.py` (TradingAnalyzer)

**O Que Usa**:
- **RSI(14)**: Sobrecompra (>70) / Sobrevenda (<30)
- **MACD(12,26,9)**: Cruzamentos e divergências
- **Bollinger Bands(20,2)**: Volatilidade e extremos
- **EMA(9,20,50,200)**: Tendências multi-timeframe
- **Volume**: Comparação com média móvel
- **ATR(14)**: Volatilidade para stop-loss

**Score Calculation**:
```python
score_traditional = weighted_average([
    rsi_signal * 0.20,
    macd_signal * 0.25,
    bollinger_signal * 0.15,
    ema_signal * 0.20,
    volume_signal * 0.10,
    atr_signal * 0.10
])
# Retorna: 0.0 - 1.0
```

**Quando Pontua Alto**:
- ✅ RSI oversold + MACD cross bull + preço no Bollinger inferior = 0.7-1.0
- ✅ EMA9 > EMA20 > EMA50 (tendência clara) = 0.6-0.8
- ❌ Indicadores conflitantes = 0.3-0.5

---

### **5. Elliott Wave - 10%**

**Arquivo**: `src/core/elliott_wave_detector.py`

**O Que Detecta**:
- **Ondas de Impulso** (1,3,5): Movimento direcional forte
- **Ondas de Correção** (2,4,A,B,C): Pullbacks e reversões
- **Projeções de Fibonacci**: Alvos baseados em ondas anteriores

**Score Calculation**:
```python
score_elliott = (
    wave_count_confidence * 0.6 +  # Confiança na contagem
    fibonacci_alignment * 0.4       # Alinhamento com projeções
)
# Retorna: 0.0 - 1.0
```

**Quando Pontua Alto**:
- ✅ Onda 3 em desenvolvimento (impulso forte) = 0.7-1.0
- ✅ Onda 2 completada (entrada após correção) = 0.6-0.8
- ❌ Contagem ambígua ou onda 4 = 0.2-0.4

**Nota**: Elliott tem peso baixo (10%) pois é mais subjetivo que outras técnicas.

---

## 🎯 **Sistema de Confluence Score**

**Arquivo**: `src/core/confluence_score.py`

### **Como Funciona**

```python
# Cada técnica retorna score 0.0-1.0
score_smc = 0.75          # SMC detectou BOS + Order Block
score_wyckoff = 0.68      # Wyckoff em fase de Markup
score_price_action = 0.82 # Engulfing bullish em suporte
score_traditional = 0.60  # RSI oversold, MACD cross
score_elliott = 0.45      # Onda 2 possível (baixa confiança)

# Aplicação de pesos
final_score = (
    score_smc * 0.30 +           # 0.75 * 0.30 = 0.225
    score_wyckoff * 0.25 +       # 0.68 * 0.25 = 0.170
    score_price_action * 0.20 +  # 0.82 * 0.20 = 0.164
    score_traditional * 0.15 +   # 0.60 * 0.15 = 0.090
    score_elliott * 0.10         # 0.45 * 0.10 = 0.045
)
# = 0.694 (69.4%)

# Conta confluência (quantas técnicas concordam? >= 0.6)
techniques_agree = [
    score_smc >= 0.6,           # True
    score_wyckoff >= 0.6,       # True
    score_price_action >= 0.6,  # True
    score_traditional >= 0.6,   # True
    score_elliott >= 0.6        # False
]
confluence_count = 4/5  # 4 técnicas concordam

# DECISÃO
if final_score >= 0.55 and confluence_count >= 3:
    return "SINAL APROVADO ✅"
else:
    return "SINAL BLOQUEADO ❌"
```

### **Thresholds de Aprovação**

| Tier | Ativo | Score Mín | ADX Mín | Confluência Mín |
|------|-------|-----------|---------|-----------------|
| 1 | BTC, ETH | 55% | 24 | 3/5 |
| 2 | SOL, XRP, BNB | 55% | 26 | 3/5 |
| 3 | ADA, DOGE, LTC | 60% | 30 | 3/5 |

---

## 🛡️ **Filtros de Liquidez (v1.1)**

**Arquivos**: 
- `src/bots/telegram_bot.py` (funções `_check_crypto_liquidity_session`, `_get_crypto_signal_profile`)
- Docs: `docs/TIER_LIQUIDEZ.md`, `docs/GUIA_HORARIOS.md`

### **Por Que Existem?**

**Problema**: Ativos de baixa capitalização (ADA, LTC, DOGE) geram **dojis e sinais falsos** em horários de baixa liquidez:
- Madrugada asiática (21-7h UTC)
- Finais de semana
- Fora de sessões comerciais principais

**Solução**: Classificar ativos por tier e bloquear análise em horários inadequados.

### **Classificação de Ativos**

```python
TIER 1 - Major (BTC, ETH):
  - Liquidez profunda 24/7
  - Opera: Qualquer horário
  - Score min: 55%, ADX min: 24

TIER 2 - Large Caps (SOL, XRP, BNB):
  - Liquidez condicional
  - Opera: Segunda-Sexta, 07-21h UTC (Londres OU NY)
  - Bloqueado: Finais de semana, madrugada asiática
  - Score min: 55%, ADX min: 26

TIER 3 - Alt Coins (ADA, DOGE, LTC, LINK):
  - Alta volatilidade, baixa liquidez
  - Opera: Segunda-Sexta, 12-16h UTC (Overlap Londres+NY)
  - Bloqueado: Finais de semana, fora de overlap
  - Score min: 60%, ADX min: 30
```

### **Lógica de Validação**

```python
def _check_crypto_liquidity_session(asset: str) -> tuple[bool, str]:
    profile = _get_crypto_signal_profile(asset)
    
    # Tier 1: sem restrição
    if profile['tier'] == 1:
        return True, "Tier 1 - Opera 24/7"
    
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Segunda, 6=Domingo
    hour = now_utc.hour
    
    # Bloqueia finais de semana para Tier 2 e 3
    if weekday >= 5:
        return False, "Bloqueado em finais de semana"
    
    # Tier 2: aceita Londres OU NY
    if profile['tier'] == 2:
        if 7 <= hour < 16 or 12 <= hour < 21:
            return True, "Sessão ativa"
        return False, "Fora de sessão (madrugada asiática)"
    
    # Tier 3: APENAS overlap (12-16h UTC)
    if profile['tier'] == 3:
        if 12 <= hour < 16:
            return True, "Overlap Londres+NY"
        return False, "Fora de overlap (baixa liquidez)"
```

### **Impacto Esperado**

```
Antes (sem filtros):
├─ ADA às 03h UTC → Doji → Score 58% → ❌ Sinal FALSO
├─ LTC Domingo → Score 56% → ❌ Sinal FALSO
└─ 5-10 sinais/dia, Win Rate ~45%

Depois (com filtros):
├─ ADA às 03h UTC → ⏸ BLOQUEADO (sem sinal)
├─ LTC Domingo → ⏸ BLOQUEADO (sem sinal)
├─ ADA às 14h UTC → Score 62%, ADX 32 → ✅ Sinal VÁLIDO
└─ 2-4 sinais/dia, Win Rate esperado ~60%+
```

---

## 🔌 **Integração com Binance**

**Arquivo**: `src/core/exchange_connector.py`

### **Biblioteca Usada**: `ccxt` (CryptoCurrency eXchange Trading Library)

### **Configuração**

```python
# config/config.py
EXCHANGE = 'binance'  # Exchange principal
API_KEY = os.getenv('API_KEY', '')        # Chave API (opcional para leitura)
API_SECRET = os.getenv('API_SECRET', '')  # Secret (opcional para leitura)
TESTNET = True  # True = testnet, False = produção
```

### **Métodos Principais**

```python
class ExchangeConnector:
    def __init__(self, exchange_name='binance', testnet=True):
        self.exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,  # Respeita limites de API
            'options': {'defaultType': 'future'}  # Futuros
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)
    
    def fetch_ohlcv(self, symbol, timeframe='5m', limit=200):
        """Busca dados OHLCV (Open, High, Low, Close, Volume)"""
        # Retorna: DataFrame com colunas [timestamp, open, high, low, close, volume]
    
    def get_ticker(self, symbol):
        """Busca ticker em tempo real"""
        # Retorna: {'last': 67890.5, 'bid': 67889, 'ask': 67891, ...}
    
    def get_orderbook(self, symbol, limit=20):
        """Busca livro de ordens"""
        # Retorna: {'bids': [...], 'asks': [...]}
```

### **Ativos Suportados**

```python
# Mapeamento de comandos → símbolos Binance
SYMBOL_MAP = {
    'BTC': 'BTC/USDT',    # BINANCE:BTCUSDT
    'ETH': 'ETH/USDT',    # BINANCE:ETHUSDT
    'SOL': 'SOL/USDT',    # BINANCE:SOLUSDT
    'XRP': 'XRP/USDT',    # BINANCE:XRPUSDT
    'BNB': 'BNB/USDT',    # BINANCE:BNBUSDT
    'ADA': 'ADA/USDT',    # BINANCE:ADAUSDT
    'DOGE': 'DOGE/USDT',  # BINANCE:DOGEUSDT
    'LTC': 'LTC/USDT',    # BINANCE:LTCUSDT
}
```

### **Rate Limits**

Binance limita requisições por minuto:
- **Spot**: 1200 req/min
- **Futures**: 2400 req/min

O sistema usa:
- `enableRateLimit=True` (aguarda automaticamente)
- Cache de ticker (reutiliza por ciclo de monitor)
- Batch de análises (analisa múltiplos ativos por conexão)

---

## 🔄 **Fluxo de Decisão Completo**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. RECEBE REQUEST                                           │
│    /btc, /ada, /monitor on, etc                             │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. NORMALIZA SÍMBOLO                                        │
│    BTC → BTC/USDT                                           │
│    ADA → ADA/USDT                                           │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. VALIDA LIQUIDEZ (v1.1 - NOVO)                            │
│    ├─ Identifica Tier do ativo                              │
│    ├─ Verifica horário UTC                                  │
│    └─ BLOQUEIO SE:                                          │
│        • Tier 2/3 em fim de semana                          │
│        • Tier 2 em madrugada asiática                       │
│        • Tier 3 fora de overlap (12-16h UTC)                │
│                                                             │
│    ❌ BLOQUEADO → Retorna mensagem educativa                │
│    ✅ LIBERADO → Continua                                   │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. BUSCA DADOS BINANCE                                      │
│    └─ fetch_ohlcv(symbol, timeframe='5m', limit=200)        │
│       Retorna: DataFrame[timestamp, open, high, low, close, │
│                          volume]                            │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. CALCULA INDICADORES TRADICIONAIS                         │
│    TechnicalIndicators(df).calculate_all_indicators()       │
│    └─ RSI(14), MACD(12,26,9), Bollinger(20,2),              │
│       EMA(9,20,50,200), ATR(14), Volume MA                  │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. ANÁLISE MULTI-DIMENSIONAL (Paralelo)                     │
│                                                             │
│    ├─ SMCDetector.analyze(df)          → score_smc         │
│    ├─ WyckoffDetector.analyze(df)      → score_wyckoff     │
│    ├─ PriceActionDetector.analyze(df)  → score_pa          │
│    ├─ ElliottWaveDetector.analyze(df)  → score_elliott     │
│    └─ TradingAnalyzer.get_signal()     → score_traditional │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. CONFLUENCE SCORE SYSTEM                                  │
│                                                             │
│    final_score = (                                          │
│        score_smc * 0.30 +                                   │
│        score_wyckoff * 0.25 +                               │
│        score_pa * 0.20 +                                    │
│        score_traditional * 0.15 +                           │
│        score_elliott * 0.10                                 │
│    )                                                        │
│                                                             │
│    confluence_count = count(scores >= 0.6)                  │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. DECISION GATE                                            │
│                                                             │
│    Tier 1/2:                   Tier 3:                      │
│    • Score ≥ 55%               • Score ≥ 60%                │
│    • ADX ≥ 24/26               • ADX ≥ 30                   │
│    • Confluência ≥ 3/5         • Confluência ≥ 3/5         │
│                                • MTF confirmado             │
│                                                             │
│    ✅ APROVADO → Gera sinal                                 │
│    ❌ BLOQUEADO → Log de diagnóstico                        │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. OUTPUT                                                   │
│                                                             │
│    ├─ Telegram Alert (se /monitor ativo)                   │
│    ├─ Resposta de análise manual (se comando direto)       │
│    ├─ Logs estruturados (ATLAS ✅/❌)                        │
│    └─ Diagnósticos (market_diagnostics.log)                │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚙️ **Configuração e Parâmetros**

### **Arquivo Principal**: `config/config.py`

```python
# Exchange
EXCHANGE = 'binance'
API_KEY = os.getenv('API_KEY', '')
API_SECRET = os.getenv('API_SECRET', '')
TESTNET = True

# Trading
SYMBOL = 'SOL/USDT'  # Símbolo padrão
TIMEFRAME = '5m'     # Timeframe padrão
MARKET_TYPE = 'crypto_binary'

# Indicadores
INDICATORS_CONFIG = {
    'RSI': {'period': 14, 'overbought': 70, 'oversold': 30},
    'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
    'BOLLINGER': {'period': 20, 'std': 2},
    'EMA_SHORT': {'period': 9},
    'EMA_LONG': {'period': 21},
    'ATR': {'period': 14},
    'VOLUME': {'ma_period': 20}
}

# Risk Management
RISK_PER_TRADE = 0.02  # 2% do capital por trade
```

### **Variáveis de Ambiente** (`.env`)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=<seu_token>
TELEGRAM_CHAT_ID=<seu_chat_id>

# Binance (opcional para leitura pública)
API_KEY=
API_SECRET=

# Configuração do bot
MARKET_TYPE=crypto_binary
BOT_PROFILE=main  # ou abbs-forex-bot, otc-bot

# Ativos monitorados (custom)
CRYPTO_MONITORED_SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT,ADA/USDT

# Confluence thresholds
MONITOR_MAX_SIGNALS=6          # Máximo 6 sinais por sessão
MONITOR_INTERVAL_SECONDS=300   # Check a cada 5 min
```

### **Pesos do Confluence Score** (`src/core/confluence_score.py`)

```python
WEIGHTS = {
    'traditional': 0.15,   # Pode aumentar se indicadores forem precisos
    'smc': 0.30,           # Peso alto (estrutura institucional)
    'wyckoff': 0.25,       # Peso médio-alto (volume profile)
    'price_action': 0.20,  # Peso médio (padrões confiáveis)
    'elliott': 0.10        # Peso baixo (subjetivo)
}
```

**Como Ajustar**:
- Se SMC está gerando muitos falsos positivos → reduzir para 0.25
- Se Price Action está muito preciso → aumentar para 0.25
- **Sempre manter soma = 1.0**

---

## 📊 **Logs e Diagnósticos**

### **Arquivos de Log**

```
logs/
├── telegram_bot_main.log           # Log principal do bot
├── market_diagnostics_main.log     # Diagnósticos estruturados
├── bot_state.json                  # Estado persistente
├── trade_config.json               # Configurações ativas
└── paper_trades.json               # Trades em simulação
```

### **Formato de Log ATLAS**

```bash
# Sinal aprovado
[ATLAS] ✅ BTC/USDT (Tier1) | 5m | BUY | APROVADO | 
  score=67% (min=55%) | confluência=4/5 | 
  fatores=smc,wyckoff,price_action,traditional

# Sinal bloqueado
[ATLAS] ❌ ADA/USDT (Tier3) | 5m | BUY | BLOQUEADO: score insuficiente | 
  score=52% (min=60%) | confluência=2/5

# Bloqueio de liquidez
[LIQUIDEZ] ⏸ ADA/USDT bloqueado - Tier 3 (Alt Coin) | 
  Tier 3 requer OVERLAP Londres+NY (12-16h UTC). 
  Atual: 03:45 UTC (Asiática/Fechado)
```

### **Diagnóstico Estruturado** (`market_diagnostics.log`)

```json
{
  "event": "atlas_filter_approve",
  "timestamp": "2026-06-01T14:32:15Z",
  "symbol": "BTC/USDT",
  "timeframe": "5m",
  "direction": "BUY",
  "tier": 1,
  "final_score": 0.67,
  "final_score_pct": 67,
  "confluence_count": 4,
  "factors_agree": ["smc", "wyckoff", "price_action", "traditional"],
  "factors_disagree": ["elliott"],
  "scores": {
    "traditional": 0.62,
    "smc": 0.75,
    "wyckoff": 0.68,
    "price_action": 0.71,
    "elliott": 0.45
  },
  "recommendation": "FORTE"
}
```

---

## 🧪 **Como Testar**

### **1. Validar Conexão Binance**

```python
python3 -c "from src.core.exchange_connector import ExchangeConnector; \
  ex = ExchangeConnector(testnet=True); \
  print(ex.get_ticker('BTC/USDT'))"
```

Esperado: `{'last': 67890.5, 'bid': ..., 'ask': ...}`

### **2. Testar Confluence Score Standalone**

```python
cd /home/abbs/trading-bot
python3 src/core/confluence_score.py

# Esperado: Exemplo de análise com scores de cada técnica
```

### **3. Análise Manual via Telegram**

```bash
/btc    # Tier 1 - sempre funciona
/sol    # Tier 2 - funciona em horário comercial
/ada    # Tier 3 - funciona apenas 12-16h UTC
```

### **4. Monitor Automático**

```bash
/monitor on
# Aguardar 5 minutos, verificar logs:
tail -f logs/telegram_bot_main.log | grep ATLAS
```

---

## 📚 **Referências e Recursos**

### **Documentação do Projeto**

- [README.md](../README.md) - Visão geral do sistema
- [SISTEMA_ATLAS_COMPLETO.md](../SISTEMA_ATLAS_COMPLETO.md) - Guia operacional
- [docs/TIER_LIQUIDEZ.md](TIER_LIQUIDEZ.md) - Especificação de filtros de liquidez
- [docs/GUIA_HORARIOS.md](GUIA_HORARIOS.md) - Referência rápida de horários
- [docs/TELEGRAM_BOT.md](TELEGRAM_BOT.md) - Comandos do bot

### **Bibliotecas Utilizadas**

- **ccxt**: https://github.com/ccxt/ccxt (API de exchanges)
- **pandas**: Manipulação de dados OHLCV
- **numpy**: Cálculos matemáticos
- **python-telegram-bot**: Integração com Telegram
- **ta-lib** (opcional): Indicadores técnicos adicionais

### **Conceitos Teóricos**

- **Smart Money Concepts**: ICT (Inner Circle Trader) methodology
- **Wyckoff**: Richard Wyckoff - Market Analysis Method
- **Price Action**: Steve Nison - Japanese Candlestick Charting Techniques
- **Elliott Wave**: Ralph Nelson Elliott - The Wave Principle

---

## 🔧 **Troubleshooting**

### **Problema: Poucos sinais sendo gerados**

**Causa**: Filtros muito rigorosos (score alto ou confluência alta)

**Solução**:
```python
# Reduzir threshold temporariamente para teste
min_score = 0.50  # de 0.55
min_confluence = 2  # de 3
```

### **Problema: Muitos sinais falsos em ADA/LTC**

**Causa**: Filtros de liquidez não ativados ou horário errado

**Solução**:
- Verificar se está operando 12-16h UTC
- Confirmar que filtros estão ativos nos logs

### **Problema: Binance API retorna erro**

**Causas Possíveis**:
- Rate limit excedido
- Símbolos inválidos
- Testnet fora do ar

**Solução**:
```bash
# Ver logs detalhados
tail -f logs/telegram_bot_main.log | grep -i error

# Testar manualmente
python3 -c "from src.core.exchange_connector import ExchangeConnector; \
  ex = ExchangeConnector(); ex.fetch_ohlcv('BTC/USDT')"
```

---

**Última atualização**: 1 de junho de 2026  
**Versão ATLAS**: 1.1  
**Autor**: Sistema ATLAS Development Team
