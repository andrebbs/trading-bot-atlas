import pandas as pd
import numpy as np
import requests
import time

from src.core.backtester import Backtester

# ==============================
# CONFIGURAÇÕES
# ==============================
SYMBOL = "SOLUSDT"
INTERVAL = "5"      # 5 minutos
LIMIT = 2000        # Quantidade de candles que vamos baixar (2000 = uma boa amostra)
INITIAL_BALANCE = 1000

print(f"🚀 Iniciando ATLAS Auto-Backtest")
print(f"📡 Baixando últimos {LIMIT} candles de {SYMBOL} ({INTERVAL}m)...")

# ==============================
# DOWNLOAD AUTOMÁTICO BYBIT
# ==============================
def get_bybit_data(symbol, interval, limit):
    # API pública Bybit (não bloqueia, não precisa de chave)
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    
    try:
        r = requests.get(url)
        data = r.json()
        
        if data['retCode'] != 0:
            raise Exception(f"Erro na API: {data['retMsg']}")
            
        klines = data['result']['list']
        # Bybit retorna do mais novo para o mais antigo, precisamos inverter
        klines.reverse()
        
        # O formato da Bybit: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        
        # Converter para float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
            
        print(f"✅ Download concluído: {len(df)} candles.")
        return df
        
    except Exception as e:
        print(f"❌ Erro ao baixar dados: {e}")
        return None

# ==============================
# DRAWDOWN CALC
# ==============================
def calculate_drawdown(equity_curve):
    peak = equity_curve[0]
    max_dd = 0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100

# ==============================
# RUN BACKTEST
# ==============================
def run():
    df = get_bybit_data(SYMBOL, INTERVAL, LIMIT)
    
    if df is None or len(df) < 200:
        print("Dados insuficientes para backtest.")
        return

    bt = Backtester(initial_balance=INITIAL_BALANCE)
    equity_curve = [INITIAL_BALANCE]

    print(f"\n📊 Processando estratégias SMC + Wyckoff + Analyzer...")
    print(f"⏳ Isso pode levar entre 30s a 2 minutos no Linux. Aguarde...\n")
    
    start_time = time.time()

    # O range começa no 150 pros indicadores SMC "aquecerem" os cálculos num histórico prévio
    for i in range(150, len(df)):
        data = df.iloc[:i].copy()
        
        # Pega a visão atual do seu bot real para aquele momento exato do passado
        result = bt.run(data)
        
        # Usamos o _current balance se ele retornou
        if result and "final_balance" in result:
            equity_curve.append(result["final_balance"])

        # Barra de progresso pra você saber que não travou
        if i % 100 == 0:
            print(f"   ... Escaneados {i}/{len(df)} candles")

    results = bt.results()
    drawdown = calculate_drawdown(equity_curve)
    
    duration = time.time() - start_time

    print("\n" + "="*50)
    print("🏆 RESULTADO FINAL DO SEU ROBÔ ATLAS v2")
    print("="*50)
    print(f"Ativo:         {SYMBOL} ({INTERVAL}m)")
    print(f"Período:       Últimos {LIMIT} candles")
    print(f"Tempo levado:  {duration:.1f} segundos")
    print("-" * 50)
    print(f"💰 Saldo inicial: ${results['initial_balance']:.2f}")
    if results['final_balance'] > results['initial_balance']:
        print(f"💰 Saldo final:   ${results['final_balance']:.2f} 🟢")
        print(f"🚀 Lucro Líquido: ${results['net_profit']:.2f}")
    else:
        print(f"💰 Saldo final:   ${results['final_balance']:.2f} 🔴")
        print(f"📉 Prejuízo:      ${results['net_profit']:.2f}")
    
    print(f"\n🎯 Trades Feitos: {results['trades']}")
    if results['trades'] > 0:
        print(f"✅ Vítorias (WIN): {results['wins']}")
        print(f"❌ Derrotas (LOSS): {results['losses']}")
        print(f"📊 Winrate (Acertos): {results['winrate']:.2f}%")
        print(f"📉 Drawdown máx:  {drawdown:.2f}%")

    print("="*50)

if __name__ == "__main__":
    run()
