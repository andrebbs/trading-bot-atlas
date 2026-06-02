"""
Exemplo de uso dos módulos do bot
Execute este arquivo para ver exemplos práticos
"""
from datetime import datetime
import pandas as pd
import numpy as np
from indicators import TechnicalIndicators
from analyzer import TradingAnalyzer

def generate_sample_data():
    """Gera dados de exemplo para demonstração"""
    # Simula 100 candles de preço
    np.random.seed(42)
    
    dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
    
    # Simula movimento de preço com tendência
    base_price = 50000
    price_changes = np.random.randn(100).cumsum() * 100
    close_prices = base_price + price_changes
    
    # Simula OHLC
    data = {
        'open': close_prices + np.random.randn(100) * 50,
        'high': close_prices + abs(np.random.randn(100) * 100),
        'low': close_prices - abs(np.random.randn(100) * 100),
        'close': close_prices,
        'volume': np.random.randint(1000, 10000, 100)
    }
    
    df = pd.DataFrame(data, index=dates)
    return df


def example_1_basic_indicators():
    """Exemplo 1: Calculando indicadores básicos"""
    print("\n" + "="*70)
    print("EXEMPLO 1: Calculando Indicadores Técnicos")
    print("="*70 + "\n")
    
    # Gera dados de exemplo
    df = generate_sample_data()
    print(f"✓ Dados gerados: {len(df)} candles")
    print(f"  Período: {df.index[0]} até {df.index[-1]}")
    print(f"  Preço inicial: ${df.iloc[0]['close']:.2f}")
    print(f"  Preço final: ${df.iloc[-1]['close']:.2f}\n")
    
    # Calcula indicadores
    tech = TechnicalIndicators(df)
    
    # RSI
    rsi = tech.calculate_rsi(14)
    print(f"📊 RSI (14): {rsi.iloc[-1]:.2f}")
    
    # MACD
    tech.calculate_macd(12, 26, 9)
    print(f"📊 MACD: {tech.df.iloc[-1]['macd']:.4f}")
    
    # Bollinger Bands
    tech.calculate_bollinger_bands(20, 2)
    print(f"📊 Bollinger Bands:")
    print(f"   Upper: ${tech.df.iloc[-1]['bb_upper']:.2f}")
    print(f"   Middle: ${tech.df.iloc[-1]['bb_middle']:.2f}")
    print(f"   Lower: ${tech.df.iloc[-1]['bb_lower']:.2f}")
    
    # EMA
    tech.calculate_ema(9)
    tech.calculate_ema(21)
    print(f"📊 EMA 9: ${tech.df.iloc[-1]['ema_9']:.2f}")
    print(f"📊 EMA 21: ${tech.df.iloc[-1]['ema_21']:.2f}")
    
    print("\n✓ Indicadores calculados com sucesso!\n")


def example_2_signal_generation():
    """Exemplo 2: Gerando sinais de trading"""
    print("\n" + "="*70)
    print("EXEMPLO 2: Gerando Sinais de Trading")
    print("="*70 + "\n")
    
    # Gera dados e calcula indicadores
    df = generate_sample_data()
    
    config = {
        'RSI': {'period': 14, 'overbought': 70, 'oversold': 30},
        'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
        'BOLLINGER': {'period': 20, 'std': 2},
        'EMA_SHORT': {'period': 9},
        'EMA_LONG': {'period': 21},
        'ATR': {'period': 14},
        'VOLUME': {'ma_period': 20}
    }
    
    tech = TechnicalIndicators(df)
    df = tech.calculate_all_indicators(config)
    
    # Analisa e gera sinais
    analyzer = TradingAnalyzer(df)
    signal_data = analyzer.get_current_signal()
    
    # Mostra resultado
    print(f"💰 Preço Atual: ${df.iloc[-1]['close']:.2f}\n")
    
    print(f"🎯 Score Composto: {signal_data['score']:.3f}")
    print(f"📊 Probabilidade: {signal_data['probability']:.1f}%\n")
    
    print("📋 Scores por Indicador:")
    print(f"  RSI:       {signal_data['rsi_score']:+.3f}")
    print(f"  MACD:      {signal_data['macd_score']:+.3f}")
    print(f"  Bollinger: {signal_data['bollinger_score']:+.3f}")
    print(f"  EMA:       {signal_data['ema_score']:+.3f}")
    print(f"  Volume:    {signal_data['volume_score']:+.3f}")
    print(f"  ATR:       {signal_data['atr_score']:+.3f}\n")
    
    signal = signal_data['signal']
    if signal == 1:
        emoji = "🟢"
        action = "COMPRA"
    elif signal == -1:
        emoji = "🔴"
        action = "VENDA"
    else:
        emoji = "🟡"
        action = "NEUTRO"
    
    print(f"{emoji} RECOMENDAÇÃO: {action}\n")


def example_3_multiple_signals():
    """Exemplo 3: Analisando múltiplos períodos"""
    print("\n" + "="*70)
    print("EXEMPLO 3: Análise de Múltiplos Períodos")
    print("="*70 + "\n")
    
    df = generate_sample_data()
    
    config = {
        'RSI': {'period': 14, 'overbought': 70, 'oversold': 30},
        'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
        'BOLLINGER': {'period': 20, 'std': 2},
        'EMA_SHORT': {'period': 9},
        'EMA_LONG': {'period': 21},
        'ATR': {'period': 14},
        'VOLUME': {'ma_period': 20}
    }
    
    tech = TechnicalIndicators(df)
    df = tech.calculate_all_indicators(config)
    
    analyzer = TradingAnalyzer(df)
    analyzer.generate_signals(buy_threshold=0.65, sell_threshold=0.35)
    
    signals_df = analyzer.get_signals_dataframe()
    
    # Conta sinais
    buy_signals = (signals_df['signal'] == 1).sum()
    sell_signals = (signals_df['signal'] == -1).sum()
    neutral_signals = (signals_df['signal'] == 0).sum()
    
    print(f"📊 Análise de {len(df)} períodos:\n")
    print(f"  🟢 Sinais de COMPRA:  {buy_signals} ({buy_signals/len(df)*100:.1f}%)")
    print(f"  🔴 Sinais de VENDA:   {sell_signals} ({sell_signals/len(df)*100:.1f}%)")
    print(f"  🟡 Sinais NEUTROS:    {neutral_signals} ({neutral_signals/len(df)*100:.1f}%)\n")
    
    # Últimos 5 sinais
    print("📋 Últimos 5 sinais:")
    print("-" * 70)
    
    for i in range(-5, 0):
        timestamp = df.index[i]
        price = df.iloc[i]['close']
        score = signals_df.iloc[i]['composite_score']
        signal = signals_df.iloc[i]['signal']
        
        if signal == 1:
            emoji = "🟢"
            action = "COMPRA"
        elif signal == -1:
            emoji = "🔴"
            action = "VENDA"
        else:
            emoji = "🟡"
            action = "NEUTRO"
        
        print(f"{timestamp.strftime('%Y-%m-%d %H:%M')} | ${price:,.2f} | "
              f"Score: {score:.3f} | {emoji} {action}")
    
    print()


def main():
    """Executa todos os exemplos"""
    print("\n")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║         📚 EXEMPLOS DE USO DO BOT DE TRADING             ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    
    try:
        example_1_basic_indicators()
        input("Pressione ENTER para continuar...")
        
        example_2_signal_generation()
        input("Pressione ENTER para continuar...")
        
        example_3_multiple_signals()
        
        print("\n" + "="*70)
        print("✓ Todos os exemplos executados com sucesso!")
        print("="*70 + "\n")
        
        print("📖 Próximos passos:")
        print("  1. Configure suas credenciais em .env")
        print("  2. Execute: python main.py analyze")
        print("  3. Execute: python main.py backtest")
        print("  4. Execute: python main.py paper\n")
        
    except Exception as e:
        print(f"\n❌ Erro ao executar exemplos: {e}\n")


if __name__ == '__main__':
    main()
