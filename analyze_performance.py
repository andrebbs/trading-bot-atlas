#!/usr/bin/env python3
"""
Análise de Performance - Últimos 15 dias
Simulator Bitget
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Carregar trades
paper_trades_path = Path('logs/paper_trades.json')
trades = json.loads(paper_trades_path.read_text())

# Filtrar últimos 15 dias
cutoff = datetime.now() - timedelta(days=15)
recent_trades = []

for t in trades:
    try:
        ts = datetime.fromisoformat(t['ts'].replace('+00:00', ''))
        if ts >= cutoff:
            recent_trades.append(t)
    except:
        pass

# Métricas
total = len(recent_trades)
closed = [t for t in recent_trades if t.get('status') == 'CLOSED']
wins = [t for t in closed if t.get('result') == 'WIN']
losses = [t for t in closed if t.get('result') == 'LOSS']

win_rate = (len(wins) / len(closed) * 100) if closed else 0
total_pnl = sum(t.get('pnl', 0) for t in closed)

# Por ativo
by_asset = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0})
for t in closed:
    asset = t.get('asset', 'UNKNOWN')
    result = t.get('result')
    if result == 'WIN':
        by_asset[asset]['wins'] += 1
    elif result == 'LOSS':
        by_asset[asset]['losses'] += 1
    by_asset[asset]['pnl'] += t.get('pnl', 0)

# Por direção
by_side = {'BUY': {'wins': 0, 'losses': 0, 'pnl': 0}, 'SELL': {'wins': 0, 'losses': 0, 'pnl': 0}}
for t in closed:
    side = t.get('side', 'BUY')
    result = t.get('result')
    if result == 'WIN':
        by_side[side]['wins'] += 1
    elif result == 'LOSS':
        by_side[side]['losses'] += 1
    by_side[side]['pnl'] += t.get('pnl', 0)

# Drawdown
running_pnl = 0
max_pnl = 0
max_drawdown = 0
for t in sorted(closed, key=lambda x: x.get('ts', '')):
    running_pnl += t.get('pnl', 0)
    max_pnl = max(max_pnl, running_pnl)
    drawdown = max_pnl - running_pnl
    max_drawdown = max(max_drawdown, drawdown)

max_dd_pct = (max_drawdown / 500) * 100 if 500 > 0 else 0  # assumindo saldo inicial 500 SUSDT

# Melhor e pior streak
current_streak = 0
best_streak = 0
worst_streak = 0
for t in sorted(closed, key=lambda x: x.get('ts', '')):
    result = t.get('result')
    if result == 'WIN':
        current_streak = max(1, current_streak + 1)
        best_streak = max(best_streak, current_streak)
    elif result == 'LOSS':
        current_streak = min(-1, current_streak - 1)
        worst_streak = min(worst_streak, current_streak)
    else:
        current_streak = 0

# Avg win/loss
avg_win = sum(t.get('pnl', 0) for t in wins) / len(wins) if wins else 0
avg_loss = sum(t.get('pnl', 0) for t in losses) / len(losses) if losses else 0
profit_factor = abs(sum(t.get('pnl', 0) for t in wins) / sum(t.get('pnl', 0) for t in losses)) if losses and sum(t.get('pnl', 0) for t in losses) != 0 else 0

print('=' * 80)
print('📊 RELATÓRIO DE PERFORMANCE — ÚLTIMOS 15 DIAS (Simulator Bitget)')
print('=' * 80)
print()
print(f'📅 Período: {cutoff.strftime("%d/%m/%Y")} → {datetime.now().strftime("%d/%m/%Y")}')
print(f'💼 Ambiente: SUSDT-FUTURES (Simulator Bitget)')
print(f'⚙️  Config: Risk 1.0% | Leverage 5x')
print()
print('─' * 80)
print('🎯 MÉTRICAS GERAIS')
print('─' * 80)
print(f'Total de Trades: {total}')
print(f'Trades Fechados: {len(closed)}')
print(f'Trades Abertos: {total - len(closed)}')
print()
print(f'✅ Wins: {len(wins)}')
print(f'❌ Losses: {len(losses)}')
print(f'📈 Win Rate: {win_rate:.2f}%')
print()
print(f'💰 P&L Total: ${total_pnl:.2f} SUSDT')
print(f'💵 Média Win: ${avg_win:.2f}')
print(f'💸 Média Loss: ${avg_loss:.2f}')
print(f'🎲 Profit Factor: {profit_factor:.2f}')
print()
print(f'📉 Drawdown Máximo: ${max_drawdown:.2f} ({max_dd_pct:.2f}%)')
print(f'🔥 Melhor Streak: {best_streak} wins consecutivos')
print(f'❄️  Pior Streak: {abs(worst_streak)} losses consecutivos')
print()
print('─' * 80)
print('📊 PERFORMANCE POR ATIVO')
print('─' * 80)
for asset in sorted(by_asset.keys()):
    data = by_asset[asset]
    total_asset = data['wins'] + data['losses']
    wr = (data['wins'] / total_asset * 100) if total_asset else 0
    print(f'{asset:6s} | W:{data["wins"]:2d} L:{data["losses"]:2d} | WR:{wr:5.1f}% | P&L:${data["pnl"]:7.2f}')
print()
print('─' * 80)
print('🎲 PERFORMANCE POR DIREÇÃO')
print('─' * 80)
for side in ['BUY', 'SELL']:
    data = by_side[side]
    total_side = data['wins'] + data['losses']
    wr = (data['wins'] / total_side * 100) if total_side else 0
    print(f'{side:4s} | W:{data["wins"]:2d} L:{data["losses"]:2d} | WR:{wr:5.1f}% | P&L:${data["pnl"]:7.2f}')
print()
print('─' * 80)
print('✅ CRITÉRIOS PARA MIGRAR AO LIVE')
print('─' * 80)
criteria_1 = len(closed) >= 30
criteria_2 = win_rate >= 55
criteria_3 = max_dd_pct < 10

print(f'1. Mínimo 30 trades: {"✅ OK" if criteria_1 else "❌ FALTAM " + str(30 - len(closed))}')
print(f'2. Win Rate ≥ 55%: {"✅ OK" if criteria_2 else "❌ ATUAL " + f"{win_rate:.1f}%"}')
print(f'3. Drawdown < 10%: {"✅ OK" if criteria_3 else "❌ ATUAL " + f"{max_dd_pct:.1f}%"}')
print()

if criteria_1 and criteria_2 and criteria_3:
    print('🎉 APROVADO PARA LIVE! Sistema validado para conta real.')
else:
    print('⚠️  CONTINUAR NO SIMULATOR. Ajustar estratégia antes de migrar.')

print()
print('=' * 80)
