"""
Configurações do Bot de Trading
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações da Exchange
EXCHANGE = os.getenv('EXCHANGE', 'binance')  # binance, bybit, etc
API_KEY = os.getenv('API_KEY', '')
API_SECRET = os.getenv('API_SECRET', '')
TESTNET = True  # True para conta demo/testnet

# Configurações de Trading
SYMBOL = 'SOL/USDT'
TIMEFRAME = '5m'  # 1m, 5m, 15m, 1h, 4h, 1d
INITIAL_CAPITAL = 10000  # Capital inicial para backtesting

# Mercado (roteamento por motor)
MARKET_TYPE = os.getenv('MARKET_TYPE', 'crypto_binary')
SUPPORTED_MARKET_TYPES = ['crypto_binary', 'forex', 'stocks', 'commodities']

# Indicadores e seus parâmetros
INDICATORS_CONFIG = {
    'RSI': {'period': 14, 'overbought': 70, 'oversold': 30},
    'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
    'BOLLINGER': {'period': 20, 'std': 2},
    'EMA_SHORT': {'period': 9},
    'EMA_LONG': {'period': 21},
    'ATR': {'period': 14},
    'VOLUME': {'ma_period': 20}
}

# Pesos para cada indicador na decisão final (soma deve ser 1.0)
INDICATOR_WEIGHTS = {
    'RSI': 0.20,
    'MACD': 0.25,
    'BOLLINGER': 0.15,
    'EMA': 0.20,
    'VOLUME': 0.10,
    'ATR': 0.10
}

# Thresholds para decisão
BUY_THRESHOLD = 0.65  # Score acima de 0.65 = sinal de compra
SELL_THRESHOLD = 0.35  # Score abaixo de 0.35 = sinal de venda

# Risk Management
RISK_PER_TRADE = 0.02  # 2% do capital por trade
STOP_LOSS_PERCENT = 0.02  # 2% de stop loss
TAKE_PROFIT_PERCENT = 0.04  # 4% de take profit

# Logging
LOG_LEVEL = 'INFO'
LOG_FILE = 'trading_bot.log'

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Webhook TradingView
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8080'))
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')  # secret opcional para validar alertas
