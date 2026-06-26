"""
Bot de Trading - Análise Técnica e Tomada de Decisão  
Autor: Trading Bot System
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import (
    ExchangeConnector,
    PaperTradingConnector,
    TechnicalIndicators,
    TradingAnalyzer,
    Backtester,
)
from config import config


def print_banner():
    """Imprime banner do bot"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║         🤖 BOT DE TRADING - ANÁLISE TÉCNICA 📈            ║
    ║                  Sistema de Decisão Inteligente          ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def analyze_current_market(symbol: str = None, timeframe: str = None):
    """Analisa o mercado atual e fornece recomendação"""
    print("\n📊 ANALISANDO MERCADO ATUAL...\n")

    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    
    # Conecta à exchange
    exchange = ExchangeConnector(testnet=config.TESTNET)
    
    # Busca dados históricos
    print(f"Buscando dados de {symbol} ({timeframe})...")
    df = exchange.fetch_ohlcv(symbol, timeframe, limit=500)
    
    if df is None:
        print("❌ Erro ao buscar dados!")
        return
    
    # Calcula indicadores
    print("Calculando indicadores técnicos...")
    tech_indicators = TechnicalIndicators(df)
    df = tech_indicators.calculate_all_indicators(config.INDICATORS_CONFIG)
    
    # Analisa e gera sinal
    print("Analisando sinais...")
    analyzer = TradingAnalyzer(df)
    signal_data = analyzer.get_current_signal()
    
    # Busca preço atual
    ticker = exchange.get_ticker(symbol)
    current_price = ticker['last'] if ticker else df.iloc[-1]['close']
    
    # Imprime resultado
    print(f"\n{'='*70}")
    print(f"📈 ANÁLISE DE {symbol}")
    print(f"{'='*70}")
    print(f"🕐 Timestamp:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"💵 Preço Atual:      ${current_price:,.2f}")
    print(f"{'='*70}\n")
    
    # Score composto
    score = signal_data['score']
    probability = signal_data['probability']
    
    print(f"🎯 SCORE COMPOSTO:   {score:.3f}")
    print(f"📊 Probabilidade:    {probability:.1f}%\n")
    
    # Interpretação do sinal
    signal = signal_data['signal']
    if signal == 1:
        emoji = "🟢"
        action = "COMPRA"
        color_bar = "█" * int(score * 50)
    elif signal == -1:
        emoji = "🔴"
        action = "VENDA"
        color_bar = "█" * int((1 - score) * 50)
    else:
        emoji = "🟡"
        action = "NEUTRO / AGUARDAR"
        color_bar = "█" * 25
    
    print(f"{emoji} RECOMENDAÇÃO:      {action}")
    print(f"📊 Força do sinal:   [{color_bar}]\n")
    
    # Detalhes dos indicadores
    print(f"📋 DETALHAMENTO DOS INDICADORES")
    print(f"{'-'*70}")
    
    indicators_status = [
        ("RSI", signal_data['rsi_score'], config.INDICATOR_WEIGHTS['RSI']),
        ("MACD", signal_data['macd_score'], config.INDICATOR_WEIGHTS['MACD']),
        ("Bollinger", signal_data['bollinger_score'], config.INDICATOR_WEIGHTS['BOLLINGER']),
        ("EMA", signal_data['ema_score'], config.INDICATOR_WEIGHTS['EMA']),
        ("Volume", signal_data['volume_score'], config.INDICATOR_WEIGHTS['VOLUME']),
        ("ATR", signal_data['atr_score'], config.INDICATOR_WEIGHTS['ATR']),
    ]
    
    for name, score_val, weight in indicators_status:
        # Normaliza score para 0-1
        normalized = (score_val + 1) / 2
        bar = "█" * int(normalized * 30)
        
        if score_val > 0.3:
            sentiment = "🟢 COMPRA"
        elif score_val < -0.3:
            sentiment = "🔴 VENDA"
        else:
            sentiment = "🟡 NEUTRO"
        
        print(f"{name:12} [{bar:30}] {score_val:+.3f} (peso: {weight:.0%}) {sentiment}")
    
    print(f"{'-'*70}\n")
    
    # Valores técnicos atuais
    latest = df.iloc[-1]
    ema_short_period = config.INDICATORS_CONFIG['EMA_SHORT']['period']
    ema_long_period = config.INDICATORS_CONFIG['EMA_LONG']['period']
    ema_short_col = f"ema_{ema_short_period}"
    ema_long_col = f"ema_{ema_long_period}"
    
    print(f"📊 VALORES ATUAIS DOS INDICADORES")
    print(f"{'-'*70}")
    print(f"RSI:              {latest['rsi']:.2f}")
    print(f"MACD:             {latest['macd']:.4f}")
    print(f"MACD Signal:      {latest['macd_signal']:.4f}")
    print(f"BB Upper:         ${latest['bb_upper']:.2f}")
    print(f"BB Middle:        ${latest['bb_middle']:.2f}")
    print(f"BB Lower:         ${latest['bb_lower']:.2f}")
    print(f"EMA {ema_short_period}:            ${latest[ema_short_col]:.2f}")
    print(f"EMA {ema_long_period}:            ${latest[ema_long_col]:.2f}")
    print(f"ATR:              ${latest['atr']:.2f}")
    print(f"Volume:           {latest['volume']:,.0f}")
    print(f"{'-'*70}\n")
    
    # Recomendações adicionais
    if signal == 1:
        stop_loss = current_price * (1 - config.STOP_LOSS_PERCENT)
        take_profit = current_price * (1 + config.TAKE_PROFIT_PERCENT)
        print(f"💡 SUGESTÕES DE GERENCIAMENTO DE RISCO")
        print(f"   Stop Loss:     ${stop_loss:,.2f} (-{config.STOP_LOSS_PERCENT*100}%)")
        print(f"   Take Profit:   ${take_profit:,.2f} (+{config.TAKE_PROFIT_PERCENT*100}%)")
        print(f"   Tamanho:       {config.RISK_PER_TRADE*100}% do capital")
    
    print(f"\n{'='*70}\n")


def run_backtest(symbol: str = None, timeframe: str = None):
    """Executa backtesting da estratégia"""
    print("\n🔄 INICIANDO BACKTESTING...\n")

    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    
    # Conecta e busca dados históricos
    exchange = ExchangeConnector(testnet=config.TESTNET)
    print(f"Buscando dados históricos de {symbol}...")
    df = exchange.fetch_ohlcv(symbol, timeframe, limit=1000)
    
    if df is None:
        print("❌ Erro ao buscar dados!")
        return
    
    # Executa backtest
    backtester = Backtester(df, config.INITIAL_CAPITAL)
    report = backtester.run_backtest(config.BUY_THRESHOLD, config.SELL_THRESHOLD)
    
    if report:
        # Plota resultados
        try:
            backtester.plot_results(report)
        except Exception as e:
            print(f"⚠ Não foi possível gerar gráficos: {e}")
        
        # Salva relatório
        import json
        with open('reports/backtest_report.json', 'w') as f:
            # Converte timestamps para string
            report_copy = report.copy()
            for trade in report_copy['trades']:
                trade['entry_time'] = str(trade['entry_time'])
                trade['exit_time'] = str(trade['exit_time'])
            for equity in report_copy['equity_curve']:
                equity['timestamp'] = str(equity['timestamp'])
            
            json.dump(report_copy, f, indent=2)
        
        print("✓ Relatório salvo: reports/backtest_report.json")


def run_paper_trading(symbol: str = None, timeframe: str = None):
    """Executa paper trading em tempo real"""
    print("\n📄 MODO PAPER TRADING\n")
    print("Monitorando mercado e simulando trades...")
    print("(Pressione Ctrl+C para parar)\n")

    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    
    import time
    
    connector = PaperTradingConnector(config.INITIAL_CAPITAL)
    exchange = ExchangeConnector(testnet=config.TESTNET)
    
    position = None
    entry_price = 0
    
    try:
        while True:
            # Busca dados
            df = exchange.fetch_ohlcv(symbol, timeframe, limit=200)
            
            if df is None:
                print("Erro ao buscar dados, tentando novamente...")
                time.sleep(60)
                continue
            
            # Calcula indicadores e sinais
            tech_indicators = TechnicalIndicators(df)
            df = tech_indicators.calculate_all_indicators(config.INDICATORS_CONFIG)
            
            analyzer = TradingAnalyzer(df)
            signal_data = analyzer.get_current_signal()
            
            current_price = df.iloc[-1]['close']
            signal = signal_data['signal']
            score = signal_data['score']
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"[{timestamp}] Preço: ${current_price:,.2f} | Score: {score:.3f} | Signal: {signal}")
            
            # Lógica de trading
            if position is None and signal == 1:
                # COMPRA
                buy_amount = (connector.balance['USDT'] * config.RISK_PER_TRADE) / current_price
                order = connector.create_market_order(symbol, 'buy', buy_amount, current_price)
                
                if order:
                    position = 'long'
                    entry_price = current_price
                    equity = connector.get_equity(current_price)
                    print(f"  💰 Equity: ${equity:,.2f} | PnL: ${connector.get_pnl(current_price):+,.2f}")
                    
            elif position == 'long':
                # Verifica saída
                should_exit = False
                exit_reason = ''
                
                if current_price <= entry_price * (1 - config.STOP_LOSS_PERCENT):
                    should_exit = True
                    exit_reason = 'Stop Loss'
                elif current_price >= entry_price * (1 + config.TAKE_PROFIT_PERCENT):
                    should_exit = True
                    exit_reason = 'Take Profit'
                elif signal == -1:
                    should_exit = True
                    exit_reason = 'Sinal de Venda'
                
                if should_exit:
                    base_asset = symbol.split('/')[0]
                    sell_amount = connector.balance.get(base_asset, 0)
                    connector.create_market_order(symbol, 'sell', sell_amount, current_price)
                    
                    pnl = connector.get_pnl(current_price)
                    pnl_pct = connector.get_pnl_percent(current_price)
                    
                    print(f"  🏁 {exit_reason} | PnL: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
                    position = None
                else:
                    equity = connector.get_equity(current_price)
                    pnl = connector.get_pnl(current_price)
                    print(f"  💰 Equity: ${equity:,.2f} | PnL: ${pnl:+,.2f}")
            
            # Espera antes da próxima verificação
            time.sleep(60 if timeframe == '1m' else 300)
            
    except KeyboardInterrupt:
        print("\n\n⚠ Parando paper trading...\n")
        
        final_equity = connector.get_equity(current_price)
        final_pnl = connector.get_pnl(current_price)
        final_pnl_pct = connector.get_pnl_percent(current_price)
        
        print(f"{'='*60}")
        print(f"RESUMO DO PAPER TRADING")
        print(f"{'='*60}")
        print(f"Capital Inicial:  ${config.INITIAL_CAPITAL:,.2f}")
        print(f"Capital Final:    ${final_equity:,.2f}")
        print(f"PnL Total:        ${final_pnl:+,.2f} ({final_pnl_pct:+.2f}%)")
        print(f"Total de Orders:  {len(connector.orders)}")
        print(f"{'='*60}\n")


def main():
    """Função principal"""
    parser = argparse.ArgumentParser(description='Bot de Trading com Análise Técnica')
    parser.add_argument(
        'mode',
        choices=['analyze', 'backtest', 'paper'],
        help='Modo: analyze, backtest ou paper'
    )
    parser.add_argument('--symbol', default=config.SYMBOL, help='Símbolo (ex: SOL/USDT, XAU/USD)')
    parser.add_argument('--timeframe', default=config.TIMEFRAME, help='Timeframe (ex: 1m, 5m, 15m)')

    args = parser.parse_args()

    print_banner()

    if args.mode == 'analyze':
        analyze_current_market(args.symbol, args.timeframe)
    elif args.mode == 'backtest':
        run_backtest(args.symbol, args.timeframe)
    elif args.mode == 'paper':
        run_paper_trading(args.symbol, args.timeframe)


if __name__ == '__main__':
    main()

