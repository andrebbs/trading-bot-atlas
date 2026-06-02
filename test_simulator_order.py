"""Teste de ordem no simulator SUSDT-FUTURES da Bitget."""
import ccxt, os
from dotenv import load_dotenv
load_dotenv()

ex = ccxt.bitget({
    'apiKey': os.getenv('API_KEY'),
    'secret': os.getenv('API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

PRODUCT_TYPE = 'SUSDT-FUTURES'

# Saldo
bal = ex.fetch_balance({'productType': PRODUCT_TYPE})
free = float(bal.get('SUSDT', {}).get('free', 0))
print(f'Saldo SUSDT: {free:.2f}')

# Mercados para ver contrato minimo BTC
markets = ex.load_markets()
btc_market = markets.get('BTC/USDT:USDT', {})
limits = btc_market.get('limits', {})
amount_limits = limits.get('amount', {})
min_qty = amount_limits.get('min', 0.001)
precision = btc_market.get('precision', {}).get('amount', 3)
print(f'BTC contrato min: {min_qty} | precisao: {precision}')
print(f'contract size: {btc_market.get("contractSize")}')

# Preco BTC
ticker = ex.fetch_ticker('BTC/USDT:USDT')
price = float(ticker['last'])
print(f'BTC price: {price:.2f}')

# Usando quantidade mínima
qty = min_qty
print(f'Qty: {qty} BTC  (notional ~${qty*price:.2f} | margem ~${qty*price/5:.2f})')

# Alavancagem
try:
    ex.set_leverage(5, 'BTC/USDT:USDT', {'productType': PRODUCT_TYPE})
    print('Alavancagem 5x OK')
except Exception as e:
    print(f'Alavancagem: {e}')

# Ordem LONG
print('Enviando ordem LONG no simulator...')
order = ex.create_market_order(
    'BTC/USDT:USDT', 'buy', qty,
    params={
        'productType': PRODUCT_TYPE,
        'marginCoin': 'USDT',
        'tradeSide': 'open',
    }
)
print(f'ORDEM OK: id={order.get("id")} | status={order.get("status")} | side={order.get("side")}')


ex = ccxt.bitget({
    'apiKey': os.getenv('API_KEY'),
    'secret': os.getenv('API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'options': {'defaultType': 'swap'},
    'enableRateLimit': True,
})

PRODUCT_TYPE = 'SUSDT-FUTURES'
MARGIN_COIN  = 'SUSDT'

# Saldo
bal = ex.fetch_balance({'productType': PRODUCT_TYPE})
free = float(bal.get(MARGIN_COIN, {}).get('free', 0))
print(f'Saldo {MARGIN_COIN}: {free:.2f}')

# Preco BTC
ticker = ex.fetch_ticker('BTC/USDT:USDT')
price = float(ticker['last'])
print(f'BTC price: {price:.2f}')

# Quantidade minima (risco 1%, alavancagem 5x)
qty = round((free * 0.01 * 5) / price, 3)
qty = max(qty, 0.001)
print(f'Qty: {qty} BTC  (notional ~${qty*price:.2f})')

# Alavancagem
try:
    ex.set_leverage(5, 'BTC/USDT:USDT', {'productType': PRODUCT_TYPE})
    print('Alavancagem 5x definida')
except Exception as e:
    print(f'Alavancagem: {e}')

# Ordem LONG
print('Enviando ordem LONG no simulator...')
order = ex.create_market_order(
    'BTC/USDT:USDT', 'buy', qty,
    params={
        'productType': PRODUCT_TYPE,
        'marginCoin': 'USDT',
        'tradeSide': 'open',       # abrir posição (one-way mode)
    }
)
print(f'ORDEM OK: id={order.get("id")} | status={order.get("status")} | side={order.get("side")}')
