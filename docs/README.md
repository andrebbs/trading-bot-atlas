# 🤖 Bot de Trading - Análise Técnica Automatizada

Bot inteligente para análise de mercado e auxílio na tomada de decisões de trading. Utiliza múltiplos indicadores técnicos para gerar sinais de compra/venda com scores de probabilidade.

## 🎯 Características

- **Análise Multi-Indicadores**: RSI, MACD, Bollinger Bands, EMA, Volume, ATR
- **Sistema de Scoring**: Calcula probabilidade ponderada baseada em múltiplos indicadores
- **Backtesting**: Teste sua estratégia em dados históricos
- **Paper Trading**: Simule trades em tempo real sem arriscar capital
- **Análise em Tempo Real**: Obtenha sinais de trading atualizados
- **Gestão de Risco**: Stop Loss e Take Profit automáticos
- **Suporte Multi-Exchange**: Binance, Bybit, e outras (via CCXT)
- **Modo Testnet**: Teste com contas demo

## 📊 Indicadores Implementados

| Indicador | Descrição | Peso Padrão |
|-----------|-----------|-------------|
| **RSI** | Relative Strength Index - identifica sobrecompra/sobrevenda | 20% |
| **MACD** | Moving Average Convergence Divergence - momentum | 25% |
| **Bollinger Bands** | Volatilidade e extremos de preço | 15% |
| **EMA** | Exponential Moving Average - tendência | 20% |
| **Volume** | Confirmação de movimentos | 10% |
| **ATR** | Average True Range - gerenciamento de risco | 10% |

## 🚀 Instalação

### 1. Clone ou crie o projeto

```bash
mkdir trading-bot
cd trading-bot
```

### 2. Crie um ambiente virtual (recomendado)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as credenciais

Copie o arquivo de exemplo e preencha com suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:

```env
EXCHANGE=binance
API_KEY=sua_chave_api
API_SECRET=seu_secret
```

**⚠️ IMPORTANTE**: Para testes iniciais, deixe `TESTNET=True` no `config.py`!

## 📖 Como Usar

### 1. Análise de Mercado Atual

Analisa o mercado agora e fornece recomendação:

```bash
python main.py analyze
```

**Saída**:
- Score composto (0-1)
- Recomendação: COMPRA / VENDA / NEUTRO
- Probabilidade de sucesso
- Detalhamento de cada indicador
- Sugestões de Stop Loss e Take Profit

### 2. Backtesting

Teste a estratégia em dados históricos:

```bash
python main.py backtest
```

**Saída**:
- Performance geral (retorno, drawdown)
- Estatísticas de trades (win rate, profit factor)
- Detalhes de cada trade
- Gráficos visuais (salvo como `backtest_results.png`)
- Relatório JSON (`backtest_report.json`)

### 3. Paper Trading

Simule trading em tempo real:

```bash
python main.py paper
```

Monitora o mercado continuamente e simula trades automaticamente.
Pressione `Ctrl+C` para parar e ver o resumo.

## ⚙️ Configuração

Edite `config.py` para personalizar:

```python
# Par de trading
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'  # 1m, 5m, 15m, 1h, 4h, 1d

# Thresholds de decisão
BUY_THRESHOLD = 0.65   # Score > 0.65 = compra
SELL_THRESHOLD = 0.35  # Score < 0.35 = venda

# Gestão de risco
RISK_PER_TRADE = 0.02        # 2% do capital por trade
STOP_LOSS_PERCENT = 0.02     # 2% de stop loss
TAKE_PROFIT_PERCENT = 0.04   # 4% de take profit
```

### Ajustando Pesos dos Indicadores

```python
INDICATOR_WEIGHTS = {
    'RSI': 0.20,      # 20%
    'MACD': 0.25,     # 25%
    'BOLLINGER': 0.15,# 15%
    'EMA': 0.20,      # 20%
    'VOLUME': 0.10,   # 10%
    'ATR': 0.10       # 10%
}
# Soma deve ser 1.0
```

### Ajustando Parâmetros dos Indicadores

```python
INDICATORS_CONFIG = {
    'RSI': {'period': 14, 'overbought': 70, 'oversold': 30},
    'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
    'BOLLINGER': {'period': 20, 'std': 2},
    'EMA_SHORT': {'period': 9},
    'EMA_LONG': {'period': 21},
    'ATR': {'period': 14},
    'VOLUME': {'ma_period': 20}
}
```

## 📁 Estrutura do Projeto

```
trading-bot/
├── main.py                  # Script principal
├── config.py                # Configurações
├── indicators.py            # Cálculo de indicadores técnicos
├── analyzer.py              # Análise e geração de sinais
├── backtester.py            # Sistema de backtesting
├── exchange_connector.py    # Conexão com exchanges
├── requirements.txt         # Dependências
├── .env.example             # Exemplo de configuração
└── README.md                # Documentação
```

## 🔐 Segurança

- **Nunca compartilhe** suas chaves API
- Use **apenas permissões de leitura** para análise
- Para trading real, use contas com **capital limitado**
- Teste sempre em **ambiente testnet** primeiro
- Mantenha o arquivo `.env` no `.gitignore`

## 📈 Exemplos de Uso

### Exemplo 1: Análise Rápida

```bash
python main.py analyze
```

Resultado:
```
🎯 SCORE COMPOSTO:   0.723
📊 Probabilidade:    72.3%

🟢 RECOMENDAÇÃO:      COMPRA
```

### Exemplo 2: Backtest de 1000 Candles

```bash
python main.py backtest
```

Resultado:
```
📊 PERFORMANCE GERAL
  Capital Inicial:      $10,000.00
  Capital Final:        $12,450.00
  Retorno Total:        $2,450.00 (+24.50%)
  Max Drawdown:         -8.30%

📈 ESTATÍSTICAS DE TRADES
  Total de Trades:      15
  Trades Vencedores:    10 (66.7%)
  Profit Factor:        2.45
```

## 🎨 Versão Java

Se você preferir Java, posso criar uma versão equivalente usando:
- **Spring Boot** para estrutura
- **TA4J** para indicadores técnicos
- **XChange** para integração com exchanges
- **JUnit** para backtesting

## 🔧 Troubleshooting

### Erro de conexão com exchange

```python
# Verifique se está usando testnet
TESTNET = True  # em config.py
```

### Erro "Module not found"

```bash
pip install -r requirements.txt
```

### Gráficos não aparecem

Instale backend gráfico:
```bash
pip install PyQt5
```

## 📚 Próximos Passos

1. **Teste o bot** em modo `analyze` para entender os sinais
2. **Execute backtest** para avaliar a estratégia
3. **Ajuste os parâmetros** conforme necessário
4. **Use paper trading** para validar em tempo real
5. **Só então considere** trading real com capital limitado

## 🤝 Contribuindo

Este é um bot base que pode ser expandido com:
- Machine Learning para otimização de parâmetros
- Mais indicadores (Ichimoku, Fibonacci, etc)
- Notificações (Telegram, Email, Discord)
- Dashboard web
- Trading automatizado real
- Multi-timeframe analysis

## ⚠️ Disclaimer

Este bot é para fins educacionais e de pesquisa. Trading envolve risco de perda de capital. **Não sou responsável por perdas financeiras**. Sempre faça sua própria pesquisa (DYOR) e nunca invista mais do que pode perder.

## 📞 Suporte

Para dúvidas ou sugestões:
- Leia a documentação primeiro
- Verifique os logs de erro
- Teste em ambiente isolado

**Happy Trading! 🚀📈**
