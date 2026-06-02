"""
Módulo de Conexão com Exchange
Gerencia conexão e operações com exchanges (Binance, Bybit, etc)
"""
import ccxt
import pandas as pd
from datetime import datetime
from config import config


class ExchangeConnector:
    """Classe para conectar e operar com exchanges"""
    
    def __init__(self, exchange_name=config.EXCHANGE, testnet=config.TESTNET):
        """
        Inicializa conexão com a exchange
        exchange_name: nome da exchange (binance, bybit, etc)
        testnet: True para usar ambiente de teste
        """
        self.exchange_name = exchange_name
        self.testnet = testnet
        self.exchange = self._initialize_exchange()
        
    def _initialize_exchange(self):
        """Inicializa a exchange"""
        exchange_class = getattr(ccxt, self.exchange_name)
        
        exchange_config = {
            'apiKey': config.API_KEY,
            'secret': config.API_SECRET,
            'enableRateLimit': True,
        }
        
        # Configuração de tipo de mercado (sempre Spot para dados públicos de preço)
        if self.exchange_name == 'binance':
            exchange_config['options'] = {'defaultType': 'spot'}
            # Usa API de produção Spot (pública, sem auth para OHLCV)
            # Preços idênticos ao TradingView
        elif self.exchange_name == 'bybit' and self.testnet:
            exchange_config['urls'] = {
                'api': 'https://api-testnet.bybit.com'
            }
        
        exchange = exchange_class(exchange_config)
        
        try:
            exchange.load_markets()
            print(f"✓ Conectado à {self.exchange_name} ({'TESTNET' if self.testnet else 'LIVE'})")
        except Exception as e:
            print(f"✗ Erro ao conectar: {e}")
        
        return exchange

    def list_markets(self, quote: str = None, active_only: bool = True, spot_only: bool = False):
        """Lista símbolos disponíveis já carregados pela exchange."""
        try:
            markets = getattr(self.exchange, 'markets', None) or self.exchange.load_markets()
        except Exception as e:
            print(f"Erro ao listar mercados: {e}")
            return []

        symbols = []
        for symbol, details in markets.items():
            if active_only and details.get('active') is False:
                continue
            if spot_only and not details.get('spot', False):
                continue
            if quote and str(details.get('quote', '')).upper() != str(quote).upper():
                continue
            symbols.append(symbol)

        return sorted(set(symbols))
    
    def fetch_ohlcv(self, symbol=config.SYMBOL, timeframe=config.TIMEFRAME, limit=500):
        """
        Busca dados OHLCV (Open, High, Low, Close, Volume)
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            print(f"Erro ao buscar dados OHLCV: {e}")
            return None
    
    def get_ticker(self, symbol=config.SYMBOL):
        """Busca informações do ticker (preço atual, volume, etc)"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Erro ao buscar ticker: {e}")
            return None

    def has_market(self, symbol: str) -> bool:
        """Indica se o símbolo existe nos mercados carregados da exchange."""
        try:
            return symbol in (self.exchange.markets or {})
        except Exception:
            return False
    
    def get_balance(self):
        """Retorna o saldo da conta"""
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            print(f"Erro ao buscar saldo: {e}")
            return None
    
    def create_market_order(self, symbol, side, amount):
        """
        Cria ordem a mercado
        side: 'buy' ou 'sell'
        amount: quantidade a comprar/vender
        """
        try:
            order = self.exchange.create_market_order(symbol, side, amount)
            print(f"✓ Ordem {side.upper()} criada: {amount} {symbol}")
            return order
        except Exception as e:
            print(f"✗ Erro ao criar ordem: {e}")
            return None
    
    def create_limit_order(self, symbol, side, amount, price):
        """
        Cria ordem limitada
        """
        try:
            order = self.exchange.create_limit_order(symbol, side, amount, price)
            print(f"✓ Ordem LIMIT {side.upper()} criada: {amount} {symbol} @ {price}")
            return order
        except Exception as e:
            print(f"✗ Erro ao criar ordem limitada: {e}")
            return None
    
    def create_stop_loss_order(self, symbol, side, amount, stop_price):
        """Cria ordem de stop loss"""
        try:
            params = {'stopPrice': stop_price}
            order = self.exchange.create_order(
                symbol, 'stop_market', side, amount, None, params
            )
            print(f"✓ Stop Loss criado: {amount} {symbol} @ {stop_price}")
            return order
        except Exception as e:
            print(f"✗ Erro ao criar stop loss: {e}")
            return None
    
    def get_open_orders(self, symbol=None):
        """Retorna ordens abertas"""
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            print(f"Erro ao buscar ordens abertas: {e}")
            return []
    
    def cancel_order(self, order_id, symbol):
        """Cancela uma ordem"""
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            print(f"✓ Ordem {order_id} cancelada")
            return result
        except Exception as e:
            print(f"✗ Erro ao cancelar ordem: {e}")
            return None
    
    def get_position(self, symbol=None):
        """Retorna posições abertas (para futuros)"""
        try:
            positions = self.exchange.fetch_positions(symbol)
            return positions
        except Exception as e:
            print(f"Erro ao buscar posições: {e}")
            return []


class PaperTradingConnector:
    """
    Simulador de trading para backtesting e paper trading
    Não executa ordens reais
    """
    
    def __init__(self, initial_capital=config.INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.balance = {'USDT': initial_capital, 'BTC': 0}
        self.positions = []
        self.orders = []
        self.trades = []
        
    def get_balance(self):
        """Retorna saldo simulado"""
        return {
            'free': self.balance,
            'used': {},
            'total': self.balance
        }
    
    def create_market_order(self, symbol, side, amount, current_price):
        """Simula ordem a mercado"""
        base, quote = symbol.split('/')
        
        order = {
            'id': len(self.orders) + 1,
            'timestamp': datetime.now(),
            'symbol': symbol,
            'type': 'market',
            'side': side,
            'amount': amount,
            'price': current_price,
            'cost': amount * current_price,
            'status': 'closed'
        }
        
        if side == 'buy':
            cost = amount * current_price
            if self.balance[quote] >= cost:
                self.balance[quote] -= cost
                self.balance[base] = self.balance.get(base, 0) + amount
                self.orders.append(order)
                print(f"✓ [PAPER] Compra: {amount} {base} @ {current_price}")
                return order
            else:
                print(f"✗ [PAPER] Saldo insuficiente para compra")
                return None
        
        elif side == 'sell':
            if self.balance.get(base, 0) >= amount:
                self.balance[base] -= amount
                self.balance[quote] += amount * current_price
                self.orders.append(order)
                print(f"✓ [PAPER] Venda: {amount} {base} @ {current_price}")
                return order
            else:
                print(f"✗ [PAPER] Quantidade insuficiente para venda")
                return None
    
    def get_equity(self, current_price, symbol='BTC/USDT'):
        """Calcula patrimônio total atual"""
        base, quote = symbol.split('/')
        btc_value = self.balance.get(base, 0) * current_price
        usdt_value = self.balance.get(quote, 0)
        return btc_value + usdt_value
    
    def get_pnl(self, current_price, symbol='BTC/USDT'):
        """Calcula lucro/prejuízo"""
        equity = self.get_equity(current_price, symbol)
        return equity - self.initial_capital
    
    def get_pnl_percent(self, current_price, symbol='BTC/USDT'):
        """Calcula lucro/prejuízo percentual"""
        pnl = self.get_pnl(current_price, symbol)
        return (pnl / self.initial_capital) * 100
