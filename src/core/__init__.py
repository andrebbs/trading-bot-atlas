"""
Core trading modules
"""
from .indicators import TechnicalIndicators
from .analyzer import TradingAnalyzer
from .backtester import Backtester
from .exchange_connector import ExchangeConnector, PaperTradingConnector
from .strategy_catalog import StrategyCatalog
from .mt5_connector import MT5Connector
from .market_router import create_engine, normalize_market_type, supported_market_types

__all__ = [
    'TechnicalIndicators',
    'TradingAnalyzer',
    'Backtester',
    'ExchangeConnector',
    'PaperTradingConnector',
    'StrategyCatalog',
    'MT5Connector',
    'create_engine',
    'normalize_market_type',
    'supported_market_types'
]
