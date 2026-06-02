# 🚀 Guia Rápido de Instalação

## ⚡ Instalação Express (5 minutos)

### 1. Instalar Python e Pip

```bash
sudo apt update
sudo apt install python3 python3-pip -y
```

### 2. Instalar Dependências

```bash
cd trading-bot
pip3 install -r requirements.txt
```

Se tiver erro de permissão, use:
```bash
pip3 install --user -r requirements.txt
```

### 3. Configurar Credenciais (Opcional para análise)

```bash
cp .env.example .env
nano .env
```

Preencha:
```env
EXCHANGE=binance
API_KEY=sua_chave_aqui
API_SECRET=seu_secret_aqui
```

**⚠️ IMPORTANTE**: 
- Para apenas **analisar** o mercado, você NÃO precisa de credenciais!
- Para **paper trading** ou **trading real**, você precisa de uma conta na exchange

### 4. Testar Instalação

```bash
python3 demo.py
```

## 🎯 Uso Básico

### Análise de Mercado (sem credenciais necessárias)

```bash
python3 main.py analyze
```

Retorna:
- ✅ Score composto (0-1)
- ✅ Recomendação (COMPRA/VENDA/NEUTRO)
- ✅ Probabilidade de sucesso
- ✅ Detalhamento de todos os indicadores
- ✅ Sugestões de Stop Loss e Take Profit

### Backtest (sem credenciais necessárias)

```bash
python3 main.py backtest
```

Testa a estratégia em dados históricos e gera:
- ✅ Relatório completo de performance
- ✅ Gráficos visuais (`backtest_results.png`)
- ✅ Relatório JSON (`backtest_report.json`)

### Paper Trading (requer credenciais)

```bash
python3 main.py paper
```

Monitora o mercado em tempo real e simula trades.

## 🔧 Configuração Personalizada

### Editar Indicadores

Abra `config.py` e modifique:

```python
# Par de trading
SYMBOL = 'BTC/USDT'  # Pode ser ETH/USDT, SOL/USDT, etc

# Timeframe
TIMEFRAME = '1h'  # Opções: 1m, 5m, 15m, 1h, 4h, 1d

# Thresholds
BUY_THRESHOLD = 0.65   # Quanto maior, mais conservador
SELL_THRESHOLD = 0.35  # Quanto menor, mais conservador
```

### Ajustar Pesos dos Indicadores

```python
INDICATOR_WEIGHTS = {
    'RSI': 0.25,       # Aumentar para dar mais peso ao RSI
    'MACD': 0.25,
    'BOLLINGER': 0.15,
    'EMA': 0.15,
    'VOLUME': 0.10,
    'ATR': 0.10
}
```

### Modificar Gestão de Risco

```python
RISK_PER_TRADE = 0.02        # 2% do capital por trade
STOP_LOSS_PERCENT = 0.02     # 2% de stop loss
TAKE_PROFIT_PERCENT = 0.04   # 4% de take profit
```

## 📊 Exemplos Práticos

### Exemplo 1: Análise Rápida do Bitcoin

```bash
python3 main.py analyze
```

Você verá algo como:

```
🎯 SCORE COMPOSTO:   0.723
📊 Probabilidade:    72.3%

🟢 RECOMENDAÇÃO:      COMPRA

💡 SUGESTÕES DE GERENCIAMENTO DE RISCO
   Stop Loss:     $51,940.00 (-2%)
   Take Profit:   $55,120.00 (+4%)
```

### Exemplo 2: Testar Estratégia em 1000 Candles

```bash
python3 main.py backtest
```

Resultado:

```
📊 PERFORMANCE GERAL
  Capital Final:        $12,450.00
  Retorno Total:        +24.50%
  Max Drawdown:         -8.30%

📈 ESTATÍSTICAS
  Win Rate:             66.7%
  Profit Factor:        2.45
```

### Exemplo 3: Analisar Ethereum em 15 minutos

Edite `config.py`:
```python
SYMBOL = 'ETH/USDT'
TIMEFRAME = '15m'
```

Execute:
```bash
python3 main.py analyze
```

## 🔐 Obtendo Credenciais de API

### Binance Testnet (Grátis)

1. Acesse: https://testnet.binancefuture.com/
2. Faça login com email
3. Vá em: Account → API Management
4. Crie nova API Key
5. Copie API Key e Secret para `.env`

### Binance Real (para trading real)

1. Acesse: https://www.binance.com/
2. Conta → API Management
3. Crie API Key
4. **IMPORTANTE**: Ative apenas permissões de leitura para análise!

## 🐛 Troubleshooting

### Erro: "Module not found"

```bash
pip3 install --user -r requirements.txt
```

### Erro: "No module named 'tkinter'"

Para gráficos no Linux:
```bash
sudo apt install python3-tk
```

### Erro de conexão com exchange

Verifique:
1. Suas credenciais estão corretas no `.env`
2. Você está usando `TESTNET=True` em `config.py`
3. Sua internet está funcionando

### Bot muito conservador (nunca compra)

Reduza o threshold em `config.py`:
```python
BUY_THRESHOLD = 0.55  # Era 0.65
```

### Bot muito agressivo (compra sempre)

Aumente o threshold:
```python
BUY_THRESHOLD = 0.75  # Era 0.65
```

## 📈 Dicas de Uso

### ✅ Boas Práticas

1. **Sempre teste primeiro** com `analyze` e `backtest`
2. **Use testnet** antes de trading real
3. **Comece com capital pequeno** (1-2% do total)
4. **Não confie cegamente** no bot - analise os sinais
5. **Ajuste os parâmetros** para seu estilo de trading
6. **Monitore regularmente** a performance

### ❌ O que NÃO fazer

1. ❌ Não use todo seu capital imediatamente
2. ❌ Não ignore os sinais de stop loss
3. ❌ Não opere sem entender os indicadores
4. ❌ Não modifique o código sem fazer backup
5. ❌ Não compartilhe suas API keys

## 🔄 Atualizações e Melhorias

Para adicionar mais funcionalidades:

### Adicionar Telegram Notifications

```bash
pip3 install python-telegram-bot
```

### Adicionar mais indicadores (Ichimoku, Fibonacci)

Edite `indicators.py` e adicione novos métodos.

### Dashboard Web

```bash
pip3 install flask plotly
```

## 📞 Suporte

Se tiver problemas:

1. Verifique o arquivo `trading_bot.log` para erros
2. Leia o README.md completo
3. Execute `python3 demo.py` para testar sem dependências externas
4. Verifique se todas as dependências estão instaladas

## 🎓 Próximos Passos

1. ✅ Execute `python3 demo.py` - Demonstração básica
2. ✅ Execute `python3 main.py analyze` - Análise real
3. ✅ Ajuste parâmetros em `config.py`
4. ✅ Execute `python3 main.py backtest` - Teste histórico
5. ✅ Configure `.env` com suas credenciais
6. ✅ Teste em conta testnet
7. ✅ Considere trading real (com cautela!)

---

**⚠️ DISCLAIMER**: Trading envolve risco. Use por sua conta e risco!

**🚀 Bom trading! 📈**
