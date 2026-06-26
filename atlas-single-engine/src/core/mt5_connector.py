"""
MT5 Connector - Interface para MetaTrader 5

NOTA: No Linux, MT5 requer configuração especial via Wine.
Este módulo implementa fallback para quando MT5 não estiver disponível.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd

logger = logging.getLogger(__name__)


class MT5Connector:
    """Conector para MetaTrader 5 com fallback para Linux."""
    
    def __init__(self, server: str = None, login: int = None, password: str = None):
        self.server = server
        self.login = login
        self.password = password
        self.connected = False
        self.mt5_available = False
        
        # Tentar importar biblioteca MT5
        try:
            import MetaTrader5 as mt5
            self.mt5 = mt5
            self.mt5_available = True
            logger.info("Biblioteca MetaTrader5 detectada")
        except ImportError:
            logger.warning(
                "MetaTrader5 não disponível. "
                "Funcionalidade MT5 desabilitada. "
                "Veja docs/MT5_SETUP.md para instruções."
            )
            self.mt5 = None
    
    def connect(self) -> bool:
        """Conecta ao terminal MT5."""
        if not self.mt5_available:
            logger.error("MT5 Python library não instalada")
            return False
        
        try:
            if not self.mt5.initialize():
                logger.error(f"MT5 initialize() falhou: {self.mt5.last_error()}")
                return False
            
            if self.login and self.password and self.server:
                authorized = self.mt5.login(
                    login=self.login,
                    password=self.password,
                    server=self.server
                )
                if not authorized:
                    logger.error(f"MT5 login falhou: {self.mt5.last_error()}")
                    return False
            
            self.connected = True
            logger.info("✅ MT5 conectado com sucesso")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar MT5: {e}")
            return False
    
    def disconnect(self):
        """Desconecta do MT5."""
        if self.mt5_available and self.connected:
            self.mt5.shutdown()
            self.connected = False
            logger.info("MT5 desconectado")
    
    def account_info(self) -> Optional[Dict]:
        """Retorna informações da conta."""
        if not self.connected:
            return None
        
        try:
            info = self.mt5.account_info()
            if info is None:
                return None
            
            return {
                'login': info.login,
                'server': info.server,
                'balance': info.balance,
                'equity': info.equity,
                'margin': info.margin,
                'profit': info.profit,
                'currency': info.currency,
            }
        except Exception as e:
            logger.error(f"Erro ao obter account_info: {e}")
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Retorna informações do símbolo."""
        if not self.connected:
            return None
        
        try:
            info = self.mt5.symbol_info(symbol)
            if info is None:
                logger.warning(f"Símbolo {symbol} não encontrado")
                return None
            
            return {
                'name': info.name,
                'bid': info.bid,
                'ask': info.ask,
                'spread': info.spread,
                'digits': info.digits,
                'trade_mode': info.trade_mode,
            }
        except Exception as e:
            logger.error(f"Erro ao obter symbol_info: {e}")
            return None

    def symbol_exists(self, symbol: str) -> bool:
        """Verifica se o símbolo existe no terminal MT5."""
        if not self.connected:
            return False

        try:
            return self.mt5.symbol_info(symbol) is not None
        except Exception:
            return False

    def ensure_symbol(self, symbol: str) -> bool:
        """Garante que o símbolo esteja selecionado no Market Watch."""
        if not self.connected:
            return False

        try:
            if self.mt5.symbol_select(symbol, True):
                return True
        except Exception:
            pass

        return self.symbol_exists(symbol)

    def list_symbols(self, search: str = None, limit: int = None) -> List[str]:
        """Lista símbolos disponíveis no terminal MT5."""
        if not self.connected:
            return []

        try:
            symbols = self.mt5.symbols_get()
            if symbols is None:
                return []

            names = []
            search_upper = search.upper() if search else None
            for item in symbols:
                name = str(getattr(item, 'name', '')).upper().strip()
                if not name:
                    continue
                if search_upper and search_upper not in name:
                    continue
                names.append(name)

            names = sorted(dict.fromkeys(names))
            if limit is not None:
                return names[:limit]
            return names
        except Exception as e:
            logger.error(f"Erro ao listar símbolos MT5: {e}")
            return []

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Retorna ticker padronizado no formato compatível com CCXT."""
        if not self.connected:
            return None

        try:
            self.ensure_symbol(symbol)
            tick = self.mt5.symbol_info_tick(symbol)
            if tick is None:
                return None

            bid = float(getattr(tick, 'bid', 0.0) or 0.0)
            ask = float(getattr(tick, 'ask', 0.0) or 0.0)
            last = float(getattr(tick, 'last', 0.0) or 0.0)
            if last <= 0 and bid > 0 and ask > 0:
                last = (bid + ask) / 2.0
            elif last <= 0:
                last = bid or ask or None

            raw_time = getattr(tick, 'time', None)
            timestamp = int(raw_time * 1000) if raw_time else None
            dt = datetime.utcfromtimestamp(raw_time).isoformat() if raw_time else None

            return {
                'symbol': symbol,
                'bid': bid or None,
                'ask': ask or None,
                'last': last,
                'timestamp': timestamp,
                'datetime': dt,
            }
        except Exception as e:
            logger.error(f"Erro ao obter ticker MT5: {e}")
            return None
    
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1m',
        limit: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        Busca dados OHLCV do MT5.
        
        Args:
            symbol: Símbolo (ex: 'CADJPY', 'XAUUSD', 'HK50')
            timeframe: '1m', '5m', '15m', '1h', '4h', '1d'
            limit: Quantidade de barras
            
        Returns:
            DataFrame com colunas [open, high, low, close, volume]
        """
        if not self.connected:
            logger.error("MT5 não conectado. Use connect() primeiro.")
            return None
        
        # Mapear timeframe
        tf_map = {
            '1m': self.mt5.TIMEFRAME_M1,
            '5m': self.mt5.TIMEFRAME_M5,
            '15m': self.mt5.TIMEFRAME_M15,
            '1h': self.mt5.TIMEFRAME_H1,
            '4h': self.mt5.TIMEFRAME_H4,
            '1d': self.mt5.TIMEFRAME_D1,
        }
        
        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            logger.error(f"Timeframe inválido: {timeframe}")
            return None
        
        try:
            self.ensure_symbol(symbol)
            rates = self.mt5.copy_rates_from_pos(symbol, mt5_tf, 0, limit)
            if rates is None or len(rates) == 0:
                logger.error(f"Nenhum dado retornado para {symbol} {timeframe}")
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Padronizar colunas
            df = df[['open', 'high', 'low', 'close', 'tick_volume']]
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
            logger.info(f"✅ {len(df)} candles carregados de {symbol} {timeframe}")
            return df
            
        except Exception as e:
            logger.error(f"Erro ao buscar OHLCV: {e}")
            return None
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Retorna preço atual (bid) do símbolo."""
        info = self.get_symbol_info(symbol)
        return info['bid'] if info else None
    
    def is_available(self) -> bool:
        """Verifica se MT5 está disponível e conectado."""
        return self.mt5_available and self.connected


def test_connection():
    """Testa conexão MT5 para debug."""
    print("🔍 Testando MT5 Connector...\n")
    
    mt5 = MT5Connector()
    
    if not mt5.mt5_available:
        print("❌ Biblioteca MetaTrader5 não disponível")
        print("   No Linux, veja docs/MT5_SETUP.md para instruções\n")
        return False
    
    print("✅ Biblioteca MT5 detectada")
    
    if mt5.connect():
        print("✅ Conexão estabelecida")
        
        account = mt5.account_info()
        if account:
            print(f"\n📊 Conta:")
            print(f"   Login: {account['login']}")
            print(f"   Servidor: {account['server']}")
            print(f"   Saldo: {account['balance']} {account['currency']}")
        
        # Testar símbolos
        test_symbols = ['CADJPY', 'XAUUSD', 'HK50']
        print(f"\n📈 Testando símbolos:")
        
        for symbol in test_symbols:
            info = mt5.get_symbol_info(symbol)
            if info:
                print(f"   ✅ {symbol}: Bid={info['bid']}, Ask={info['ask']}")
            else:
                print(f"   ❌ {symbol}: Não disponível")
        
        mt5.disconnect()
        return True
    else:
        print("❌ Falha na conexão")
        print("   Verifique se MT5 está rodando e logado")
        return False


if __name__ == '__main__':
    test_connection()
