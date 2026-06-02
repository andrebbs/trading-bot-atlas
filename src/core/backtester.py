"""
Módulo de Backtesting
Testa estratégias em dados históricos
"""
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
from .indicators import TechnicalIndicators
from .analyzer import TradingAnalyzer
from .exchange_connector import PaperTradingConnector
from config import config


class Backtester:
    """Classe para backtesting de estratégias"""
    
    def __init__(self, df, initial_capital=config.INITIAL_CAPITAL):
        """
        Inicializa backtester
        df: DataFrame com dados OHLCV
        """
        self.df = df.copy()
        self.initial_capital = initial_capital
        self.connector = PaperTradingConnector(initial_capital)
        self.trades = []
        self.equity_curve = []
        
    def run_backtest(self, buy_threshold=config.BUY_THRESHOLD, 
                     sell_threshold=config.SELL_THRESHOLD):
        """
        Executa backtest completo
        """
        print(f"\n{'='*60}")
        print(f"INICIANDO BACKTEST")
        print(f"{'='*60}")
        print(f"Capital Inicial: ${self.initial_capital:,.2f}")
        print(f"Período: {self.df.index[0]} até {self.df.index[-1]}")
        print(f"Total de candles: {len(self.df)}")
        print(f"{'='*60}\n")
        
        # Calcula indicadores
        tech_indicators = TechnicalIndicators(self.df)
        self.df = tech_indicators.calculate_all_indicators(config.INDICATORS_CONFIG)
        
        # Gera sinais
        analyzer = TradingAnalyzer(self.df)
        analyzer.generate_signals(buy_threshold, sell_threshold)
        signals_df = analyzer.get_signals_dataframe()
        
        # Adiciona sinais ao DataFrame principal
        self.df = self.df.join(signals_df)
        
        # Simula trading
        position = None  # None, 'long'
        entry_price = 0
        
        for idx, row in self.df.iterrows():
            current_price = row['close']
            signal = row['signal']
            score = row['composite_score']
            
            # Registra equity
            equity = self.connector.get_equity(current_price)
            self.equity_curve.append({
                'timestamp': idx,
                'equity': equity,
                'price': current_price
            })
            
            # Lógica de trading
            if position is None and signal == 1:
                # COMPRA
                buy_amount = (self.connector.balance['USDT'] * config.RISK_PER_TRADE) / current_price
                order = self.connector.create_market_order(
                    config.SYMBOL, 'buy', buy_amount, current_price
                )
                
                if order:
                    position = 'long'
                    entry_price = current_price
                    
                    trade = {
                        'entry_time': idx,
                        'entry_price': entry_price,
                        'entry_score': score,
                        'amount': buy_amount,
                        'type': 'long'
                    }
                    
            elif position == 'long':
                # Verifica condições de saída
                should_exit = False
                exit_reason = ''
                
                # Stop Loss
                if current_price <= entry_price * (1 - config.STOP_LOSS_PERCENT):
                    should_exit = True
                    exit_reason = 'Stop Loss'
                
                # Take Profit
                elif current_price >= entry_price * (1 + config.TAKE_PROFIT_PERCENT):
                    should_exit = True
                    exit_reason = 'Take Profit'
                
                # Sinal de venda
                elif signal == -1:
                    should_exit = True
                    exit_reason = 'Sinal de Venda'
                
                if should_exit:
                    sell_amount = self.connector.balance.get('BTC', 0)
                    order = self.connector.create_market_order(
                        config.SYMBOL, 'sell', sell_amount, current_price
                    )
                    
                    if order:
                        # Registra trade completo
                        trade['exit_time'] = idx
                        trade['exit_price'] = current_price
                        trade['exit_score'] = score
                        trade['exit_reason'] = exit_reason
                        trade['pnl'] = (current_price - entry_price) * sell_amount
                        trade['pnl_percent'] = ((current_price - entry_price) / entry_price) * 100
                        
                        self.trades.append(trade)
                        position = None
        
        # Se ainda tem posição aberta, fecha no último candle
        if position == 'long':
            last_price = self.df.iloc[-1]['close']
            sell_amount = self.connector.balance.get('BTC', 0)
            self.connector.create_market_order(config.SYMBOL, 'sell', sell_amount, last_price)
            
            trade['exit_time'] = self.df.index[-1]
            trade['exit_price'] = last_price
            trade['exit_score'] = self.df.iloc[-1]['composite_score']
            trade['exit_reason'] = 'Fim do período'
            trade['pnl'] = (last_price - entry_price) * sell_amount
            trade['pnl_percent'] = ((last_price - entry_price) / entry_price) * 100
            self.trades.append(trade)
        
        return self.generate_report()
    
    def generate_report(self):
        """Gera relatório completo do backtest"""
        trades_df = pd.DataFrame(self.trades)
        
        if len(trades_df) == 0:
            print("\n⚠ Nenhum trade foi executado no período")
            return None
        
        # Métricas gerais
        final_equity = self.equity_curve[-1]['equity']
        total_return = final_equity - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        
        # Métricas de trades
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        total_trades = len(trades_df)
        wins = len(winning_trades)
        losses = len(losing_trades)
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        avg_win = winning_trades['pnl'].mean() if wins > 0 else 0
        avg_loss = losing_trades['pnl'].mean() if losses > 0 else 0
        
        # Maior ganho e perda
        max_win = trades_df['pnl'].max()
        max_loss = trades_df['pnl'].min()
        
        # Profit Factor
        total_wins = winning_trades['pnl'].sum() if wins > 0 else 0
        total_losses = abs(losing_trades['pnl'].sum()) if losses > 0 else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Drawdown
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
        max_drawdown = equity_df['drawdown'].min()
        
        # Imprime relatório
        print(f"\n{'='*60}")
        print(f"RELATÓRIO DE BACKTEST")
        print(f"{'='*60}\n")
        
        print(f"📊 PERFORMANCE GERAL")
        print(f"  Capital Inicial:      ${self.initial_capital:,.2f}")
        print(f"  Capital Final:        ${final_equity:,.2f}")
        print(f"  Retorno Total:        ${total_return:,.2f} ({total_return_pct:+.2f}%)")
        print(f"  Max Drawdown:         {max_drawdown:.2f}%\n")
        
        print(f"📈 ESTATÍSTICAS DE TRADES")
        print(f"  Total de Trades:      {total_trades}")
        print(f"  Trades Vencedores:    {wins} ({win_rate:.1f}%)")
        print(f"  Trades Perdedores:    {losses} ({100-win_rate:.1f}%)")
        print(f"  Profit Factor:        {profit_factor:.2f}\n")
        
        print(f"💰 ANÁLISE DE GANHOS/PERDAS")
        print(f"  Ganho Médio:          ${avg_win:,.2f}")
        print(f"  Perda Média:          ${avg_loss:,.2f}")
        print(f"  Maior Ganho:          ${max_win:,.2f}")
        print(f"  Maior Perda:          ${max_loss:,.2f}\n")
        
        # Detalhes dos trades
        print(f"📋 DETALHES DOS TRADES")
        print("="*60)
        for i, trade in enumerate(trades_df.to_dict('records'), 1):
            emoji = "✅" if trade['pnl'] > 0 else "❌"
            print(f"{emoji} Trade #{i}")
            print(f"   Entrada:  {trade['entry_time']} @ ${trade['entry_price']:,.2f}")
            print(f"   Saída:    {trade['exit_time']} @ ${trade['exit_price']:,.2f}")
            print(f"   Motivo:   {trade['exit_reason']}")
            print(f"   P&L:      ${trade['pnl']:,.2f} ({trade['pnl_percent']:+.2f}%)")
            print()
        
        print(f"{'='*60}\n")
        
        # Retorna relatório estruturado
        report = {
            'initial_capital': self.initial_capital,
            'final_equity': final_equity,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'max_win': max_win,
            'max_loss': max_loss,
            'max_drawdown': max_drawdown,
            'trades': trades_df.to_dict('records'),
            'equity_curve': equity_df.to_dict('records')
        }
        
        return report
    
    def plot_results(self, report=None):
        """Plota gráficos dos resultados"""
        if report is None:
            print("Execute o backtest primeiro!")
            return
        
        equity_df = pd.DataFrame(report['equity_curve'])
        trades_df = pd.DataFrame(report['trades'])
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 10))
        
        # Gráfico 1: Preço e sinais
        ax1 = axes[0]
        ax1.plot(self.df.index, self.df['close'], label='Preço', linewidth=1)
        
        # Marca compras
        if len(trades_df) > 0:
            for _, trade in trades_df.iterrows():
                ax1.scatter(trade['entry_time'], trade['entry_price'], 
                           color='green', marker='^', s=100, zorder=5)
                ax1.scatter(trade['exit_time'], trade['exit_price'], 
                           color='red', marker='v', s=100, zorder=5)
        
        ax1.set_title('Preço e Sinais de Trading')
        ax1.set_ylabel('Preço (USDT)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Gráfico 2: Curva de Equity
        ax2 = axes[1]
        ax2.plot(equity_df['timestamp'], equity_df['equity'], 
                label='Equity', color='blue', linewidth=2)
        ax2.axhline(y=self.initial_capital, color='gray', 
                   linestyle='--', label='Capital Inicial')
        ax2.set_title('Curva de Equity')
        ax2.set_ylabel('Capital (USDT)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Gráfico 3: Drawdown
        ax3 = axes[2]
        ax3.fill_between(equity_df['timestamp'], equity_df['drawdown'], 0, 
                        color='red', alpha=0.3)
        ax3.set_title('Drawdown')
        ax3.set_ylabel('Drawdown (%)')
        ax3.set_xlabel('Data')
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('backtest_results.png', dpi=300, bbox_inches='tight')
        print("✓ Gráfico salvo: backtest_results.png")
        plt.show()
