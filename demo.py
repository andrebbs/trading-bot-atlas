"""
Demo Simplificada do Bot de Trading
Não requer instalação de dependências externas
"""

def print_banner():
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║         🤖 BOT DE TRADING - ANÁLISE TÉCNICA 📈            ║
    ║                  Sistema de Decisão Inteligente          ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def simulate_rsi_calculation(prices, period=14):
    """Simula cálculo do RSI"""
    if len(prices) < period:
        return 50.0
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def simulate_analysis():
    """Simula uma análise completa"""
    # Dados simulados de preço (últimos 50 períodos)
    prices = [
        45000, 45200, 45500, 46000, 46200, 46500, 47000, 47200, 47500, 47800,
        48000, 48200, 48500, 48800, 49000, 49200, 49500, 49800, 50000, 50200,
        50500, 50800, 51000, 51200, 51500, 51800, 52000, 51800, 51500, 51200,
        51000, 50800, 50500, 50200, 50000, 49800, 49500, 49200, 49500, 49800,
        50000, 50200, 50500, 50800, 51000, 51500, 52000, 52500, 53000, 53500
    ]
    
    current_price = prices[-1]
    
    # Calcula indicadores simulados
    rsi = simulate_rsi_calculation(prices)
    
    # Simula MACD (valores de exemplo)
    macd = 120.5
    macd_signal = 100.2
    macd_diff = macd - macd_signal
    
    # Simula Bollinger Bands
    avg_price = sum(prices[-20:]) / 20
    bb_upper = avg_price * 1.02
    bb_middle = avg_price
    bb_lower = avg_price * 0.98
    
    # Simula EMAs
    ema_9 = sum(prices[-9:]) / 9
    ema_21 = sum(prices[-21:]) / 21
    
    # Calcula scores individuais
    # RSI Score
    if rsi < 30:
        rsi_score = 1.0  # Muito vendido = compra
    elif rsi > 70:
        rsi_score = -1.0  # Muito comprado = venda
    else:
        rsi_score = (50 - rsi) / 50
    
    # MACD Score
    macd_score = 1.0 if macd_diff > 0 else -1.0
    
    # Bollinger Score
    position = (current_price - bb_lower) / (bb_upper - bb_lower)
    bollinger_score = 1 - (2 * position)
    
    # EMA Score
    ema_score = 1.0 if ema_9 > ema_21 else -1.0
    
    # Volume Score (simulado)
    volume_score = 0.5
    
    # ATR Score (simulado)
    atr_score = 0.8
    
    # Pesos
    weights = {
        'RSI': 0.20,
        'MACD': 0.25,
        'BOLLINGER': 0.15,
        'EMA': 0.20,
        'VOLUME': 0.10,
        'ATR': 0.10
    }
    
    # Score composto
    composite = (
        rsi_score * weights['RSI'] +
        macd_score * weights['MACD'] +
        bollinger_score * weights['BOLLINGER'] +
        ema_score * weights['EMA'] +
        volume_score * weights['VOLUME']
    ) * atr_score
    
    # Normaliza para 0-1
    composite_score = (composite + 1) / 2
    
    # Determina sinal
    if composite_score > 0.65:
        signal = 1  # COMPRA
        action = "COMPRA"
        emoji = "🟢"
    elif composite_score < 0.35:
        signal = -1  # VENDA
        action = "VENDA"
        emoji = "🔴"
    else:
        signal = 0  # NEUTRO
        action = "NEUTRO / AGUARDAR"
        emoji = "🟡"
    
    # Probabilidade
    distance_from_neutral = abs(composite_score - 0.5)
    probability = 50 + (distance_from_neutral * 100)
    
    # Imprime relatório
    print(f"\n{'='*70}")
    print(f"📈 ANÁLISE DE BTC/USDT")
    print(f"{'='*70}")
    print(f"🕐 Timestamp:        2024-03-07 14:30:00")
    print(f"💵 Preço Atual:      ${current_price:,.2f}")
    print(f"{'='*70}\n")
    
    print(f"🎯 SCORE COMPOSTO:   {composite_score:.3f}")
    print(f"📊 Probabilidade:    {probability:.1f}%\n")
    
    color_bar = "█" * int(composite_score * 50)
    print(f"{emoji} RECOMENDAÇÃO:      {action}")
    print(f"📊 Força do sinal:   [{color_bar}]\n")
    
    print(f"📋 DETALHAMENTO DOS INDICADORES")
    print(f"{'-'*70}")
    
    indicators = [
        ("RSI", rsi_score, weights['RSI']),
        ("MACD", macd_score, weights['MACD']),
        ("Bollinger", bollinger_score, weights['BOLLINGER']),
        ("EMA", ema_score, weights['EMA']),
        ("Volume", volume_score, weights['VOLUME']),
        ("ATR", atr_score, weights['ATR']),
    ]
    
    for name, score, weight in indicators:
        normalized = (score + 1) / 2
        bar = "█" * int(normalized * 30)
        
        if score > 0.3:
            sentiment = "🟢 COMPRA"
        elif score < -0.3:
            sentiment = "🔴 VENDA"
        else:
            sentiment = "🟡 NEUTRO"
        
        print(f"{name:12} [{bar:30}] {score:+.3f} (peso: {weight:.0%}) {sentiment}")
    
    print(f"{'-'*70}\n")
    
    print(f"📊 VALORES ATUAIS DOS INDICADORES")
    print(f"{'-'*70}")
    print(f"RSI:              {rsi:.2f}")
    print(f"MACD:             {macd:.4f}")
    print(f"MACD Signal:      {macd_signal:.4f}")
    print(f"MACD Diff:        {macd_diff:+.4f}")
    print(f"BB Upper:         ${bb_upper:.2f}")
    print(f"BB Middle:        ${bb_middle:.2f}")
    print(f"BB Lower:         ${bb_lower:.2f}")
    print(f"EMA 9:            ${ema_9:.2f}")
    print(f"EMA 21:           ${ema_21:.2f}")
    print(f"{'-'*70}\n")
    
    if signal == 1:
        stop_loss = current_price * 0.98
        take_profit = current_price * 1.04
        print(f"💡 SUGESTÕES DE GERENCIAMENTO DE RISCO")
        print(f"   Stop Loss:     ${stop_loss:,.2f} (-2.0%)")
        print(f"   Take Profit:   ${take_profit:,.2f} (+4.0%)")
        print(f"   Tamanho:       2.0% do capital")
    
    print(f"\n{'='*70}\n")
    
    return composite_score, signal


def simulate_backtest():
    """Simula resultado de backtest"""
    print(f"\n{'='*70}")
    print(f"SIMULAÇÃO DE BACKTEST")
    print(f"{'='*70}\n")
    
    print(f"📊 PERFORMANCE GERAL")
    print(f"  Capital Inicial:      $10,000.00")
    print(f"  Capital Final:        $12,450.00")
    print(f"  Retorno Total:        $2,450.00 (+24.50%)")
    print(f"  Max Drawdown:         -8.30%\n")
    
    print(f"📈 ESTATÍSTICAS DE TRADES")
    print(f"  Total de Trades:      15")
    print(f"  Trades Vencedores:    10 (66.7%)")
    print(f"  Trades Perdedores:    5 (33.3%)")
    print(f"  Profit Factor:        2.45\n")
    
    print(f"💰 ANÁLISE DE GANHOS/PERDAS")
    print(f"  Ganho Médio:          $350.00")
    print(f"  Perda Média:          $180.00")
    print(f"  Maior Ganho:          $890.00")
    print(f"  Maior Perda:          $320.00\n")
    
    print(f"📋 EXEMPLO DE TRADES")
    print("="*70)
    
    trades = [
        ("2024-02-01 10:00", 48500, "2024-02-01 14:00", 49200, "Take Profit", 350, 1.44),
        ("2024-02-02 09:00", 49000, "2024-02-02 11:00", 48820, "Stop Loss", -180, -0.37),
        ("2024-02-03 15:00", 50000, "2024-02-03 20:00", 50890, "Take Profit", 890, 1.78),
    ]
    
    for i, (entry_time, entry_price, exit_time, exit_price, reason, pnl, pnl_pct) in enumerate(trades, 1):
        emoji = "✅" if pnl > 0 else "❌"
        print(f"{emoji} Trade #{i}")
        print(f"   Entrada:  {entry_time} @ ${entry_price:,.2f}")
        print(f"   Saída:    {exit_time} @ ${exit_price:,.2f}")
        print(f"   Motivo:   {reason}")
        print(f"   P&L:      ${pnl:,.2f} ({pnl_pct:+.2f}%)")
        print()
    
    print(f"{'='*70}\n")


def show_features():
    """Mostra as funcionalidades do bot"""
    print(f"\n{'='*70}")
    print(f"🎯 FUNCIONALIDADES DO BOT")
    print(f"{'='*70}\n")
    
    features = [
        ("📊 Análise Multi-Indicadores", "RSI, MACD, Bollinger, EMA, Volume, ATR"),
        ("🎯 Sistema de Scoring", "Probabilidade ponderada de sucesso"),
        ("📈 Backtesting", "Teste estratégias em dados históricos"),
        ("📄 Paper Trading", "Simulação em tempo real"),
        ("🔔 Análise em Tempo Real", "Sinais atualizados do mercado"),
        ("🛡️ Gestão de Risco", "Stop Loss e Take Profit automáticos"),
        ("🌐 Multi-Exchange", "Binance, Bybit e outras via CCXT"),
        ("🧪 Modo Testnet", "Teste seguro com conta demo"),
    ]
    
    for feature, description in features:
        print(f"  {feature}")
        print(f"    → {description}\n")
    
    print(f"{'='*70}\n")


def main():
    """Função principal da demo"""
    print_banner()
    
    print("\n🎬 DEMONSTRAÇÃO DO BOT DE TRADING\n")
    print("Este é uma demonstração simplificada que mostra como o bot funciona.")
    print("Para usar com dados reais, siga as instruções de instalação no README.md\n")
    
    input("Pressione ENTER para ver análise do mercado...")
    
    # Mostra análise
    score, signal = simulate_analysis()
    
    input("Pressione ENTER para ver resultado de backtest...")
    
    # Mostra backtest
    simulate_backtest()
    
    input("Pressione ENTER para ver funcionalidades...")
    
    # Mostra funcionalidades
    show_features()
    
    print("✅ DEMO CONCLUÍDA!\n")
    print("📚 PRÓXIMOS PASSOS:\n")
    print("1. Instale as dependências:")
    print("   sudo apt install python3-pip")
    print("   pip3 install -r requirements.txt\n")
    print("2. Configure suas credenciais no arquivo .env\n")
    print("3. Execute o bot:")
    print("   python3 main.py analyze    # Análise atual")
    print("   python3 main.py backtest   # Backtest histórico")
    print("   python3 main.py paper      # Paper trading\n")
    print("4. Leia o README.md para documentação completa\n")
    print("🚀 Happy Trading! 📈\n")


if __name__ == '__main__':
    main()
