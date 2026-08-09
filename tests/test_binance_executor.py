from binance.client import Client
from binance.enums import *

# 1. Suas chaves da Binance TESTNET (substitua pelas suas)
API_KEY = 'SUA_API_KEY_DA_TESTNET'
SECRET_KEY = 'SUA_SECRET_KEY_DA_TESTNET'

# Inicializa o cliente apontando para a Testnet
client = Client(API_KEY, SECRET_KEY, testnet=True)

# Par e valor da operação
symbol = 'BTCUSDT'
quantidade_btc = 0.001  # Quantidade pequena para teste

try:
    # 2. Pega o preço atual do Bitcoin
    ticker = client.get_symbol_ticker(symbol=symbol)
    preco_atual = float(ticker['price'])
    print(f"Preço atual do BTC: US$ {preco_atual:.2f}")

    # 3. Define as metas (exemplo: 1% de lucro e 0.5% de perda aceitável)
    preco_take_profit = round(preco_atual * 1.01, 2) # +1%
    preco_stop_loss = round(preco_atual * 0.995, 2)  # -0.5%

    print(f"Definindo Take Profit em: US$ {preco_take_profit}")
    print(f"Definindo Stop Loss em: US$ {preco_stop_loss}")

    # 4. Executa a ordem de compra a preço de mercado (Entrada)
    ordem_compra = client.create_order(
        symbol=symbol,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=quantidade_btc
    )
    print("\n✅ Ordem de COMPRA executada com sucesso!")

    # 5. Cria a ordem OCO (One-Cancels-the-Other): Lucro e Proteção ao mesmo tempo
    # Se bater no Take Profit, cancela o Stop (e vice-versa)
    ordem_oco = client.create_oco_order(
        symbol=symbol,
        side=SIDE_SELL,
        quantity=quantidade_btc,
        price=str(preco_take_profit),       # Preço de Venda no Lucro
        stopPrice=str(preco_stop_loss),     # Preço de Disparo do Stop
        stopLimitPrice=str(preco_stop_loss * 0.999), # Preço limite de venda do Stop
        stopLimitTimeInForce=TIME_IN_FORCE_GTC
    )
    print("✅ Trava de Proteção (Stop Loss/Take Profit) posicionada!")

except Exception as e:
    print(f"❌ Erro ao executar a operação: {e}")