from __future__ import annotations

"""
Bot de Trading para Telegram
Envia notificações automáticas de sinais e responde comandos
"""
import sys
import os
import json
import logging
import time
import re
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple
import atexit
import fcntl
import numpy as np
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import ExchangeConnector, TechnicalIndicators, TradingAnalyzer
from src.core.market_router import normalize_market_type
from src.core import economic_calendar
from src.core.smc_detector import SMCDetector
from src.core.confluence_score import ConfluenceScoreSystem
from src.utils.pocket_signal_parser import PocketSignalParser, TradingSignal
from config import config

# Perfil da instância do bot: main | abbs-forex-bot etc.
BOT_PROFILE = os.getenv('BOT_PROFILE', 'main').strip().lower() or 'main'


def get_profile_env(base_key: str):
    """Busca variavel por perfil e fallback para chave global."""
    profile_suffix = re.sub(r'[^A-Z0-9]+', '_', BOT_PROFILE.upper()).strip('_')
    candidate_keys = []
    if profile_suffix:
        candidate_keys.append(f"{base_key}_{profile_suffix}")
    candidate_keys.append(base_key)

    for key in candidate_keys:
        value = os.getenv(key)
        if value:
            return value
    return None


def _env_int(name: str, default: int, min_value: int = 1) -> int:
    """Le inteiro de ambiente com fallback e limite minimo."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Valor invalido para %s=%r. Usando padrao %s.", name, raw, default)
        return default
    return max(min_value, value)


_BOT_STATE_FILE = str(PROJECT_ROOT / 'logs' / 'bot_state.json')


def _load_bot_state() -> dict:
    """Carrega estado persistido do bot (timeframe, etc.)."""
    try:
        with open(_BOT_STATE_FILE, 'r') as _f:
            return json.load(_f)
    except Exception:
        return {}


def _get_scan_expiry_candle_close(pending: dict) -> tuple[float | None, str]:
    """Obtém o fechamento do candle 5m da EXPIRAÇÃO para avaliar WIN/LOSS real."""
    market_symbol = pending.get('market_symbol')
    if not market_symbol:
        market_symbol, _ = resolve_market_symbol(pending.get('asset', ''))
    if not market_symbol:
        return None, 'sem feed de candle'

    try:
        exchange = ExchangeConnector(testnet=config.TESTNET)
        ohlcv_df = exchange.fetch_ohlcv(market_symbol, '5m', limit=12)
    except Exception as exc:
        logger.warning('[scan] falha ao buscar OHLCV para avaliacao | %s: %s', market_symbol, exc)
        return None, 'ohlcv indisponivel'

    if ohlcv_df is None or len(ohlcv_df) < 2:
        return None, 'ohlcv insuficiente'

    # Busca o candle de EXPIRAÇÃO (não de entrada) para avaliar resultado
    expiry_ts = float(pending.get('expiry_ts', 0))
    expiry_dt = datetime.utcfromtimestamp(expiry_ts)
    expiry_candles = ohlcv_df[ohlcv_df.index <= expiry_dt]
    if expiry_candles.empty:
        return None, 'candle de expiracao nao encontrado'

    expiry_candle = expiry_candles.iloc[-1]
    return float(expiry_candle['close']), f'candle 5m expiração ({market_symbol})'


def _save_bot_state(key: str, value) -> None:
    """Persiste uma chave no estado do bot."""
    try:
        state = _load_bot_state()
        state[key] = value
        with open(_BOT_STATE_FILE, 'w') as _f:
            json.dump(state, _f)
    except Exception as _e:
        logger.warning('Nao foi possivel salvar estado do bot: %s', _e)


def _resolve_analysis_timeframe(requested: str | None = None) -> str:
    """Resolve timeframe da analise avulsa com fallback robusto."""
    req = (requested or '').strip().lower()
    if req in SUPPORTED_TIMEFRAMES:
        return req

    saved = str(_load_bot_state().get('analysis_timeframe') or '').strip().lower()
    if saved in SUPPORTED_TIMEFRAMES:
        return saved

    cfg_tf = str(getattr(config, 'TIMEFRAME', '') or '').strip().lower()
    if cfg_tf in SUPPORTED_TIMEFRAMES:
        return cfg_tf

    return '5m'


def _env_flag(raw_value: str | None, default: bool = False) -> bool:
    """Normaliza flags booleanas vindas do ambiente."""
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {'1', 'true', 'yes', 'on'}


# Configuração de logging
LOGS_DIR = PROJECT_ROOT / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOGS_DIR / f'telegram_bot_{BOT_PROFILE}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DIAGNOSTICS_LOG_PATH = LOGS_DIR / f'market_diagnostics_{BOT_PROFILE}.log'
diagnostics_logger = logging.getLogger(f'{__name__}.market_diagnostics')
if not diagnostics_logger.handlers:
    diagnostics_handler = logging.FileHandler(DIAGNOSTICS_LOG_PATH)
    diagnostics_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
    diagnostics_logger.addHandler(diagnostics_handler)
    diagnostics_logger.setLevel(logging.INFO)
    diagnostics_logger.propagate = False


def log_market_diagnostic(event: str, **payload):
    """Registra diagnosticos estruturados sobre fonte e resolucao de mercado."""
    diagnostics_logger.info(
        json.dumps({'event': event, **payload}, ensure_ascii=True, default=str)
    )


# Variáveis globais
last_signal = {}
monitoring_active = False
monitor_end_time = None
pending_signal_evaluations = []
pending_martingale_decisions = []
last_pre_alert_key = {}
last_direction_alert_at = {}
weekend_reentry_tracker = {}
monitor_session_results = []
last_fresh_alert_at = None
signal_stats = {
    'total': 0,
    'good': 0,
    'bad': 0
}
instance_lock_file = None

# SMC Detector para filtragem de estrutura de mercado
smc_detector = SMCDetector(lookback_period=50)

# Sistema de Confluência ATLAS - Combina TODOS os detectores
confluence_system = ConfluenceScoreSystem()

# Lista de ativos monitorados inicial por perfil
DEFAULT_CRYPTO_MONITORED_SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT']
DEFAULT_FOREX_MONITORED_SYMBOLS = ['XAU/USD', 'US500']
_crypto_monitored_symbols_raw = os.getenv(
    'CRYPTO_MONITORED_SYMBOLS',
    ','.join(DEFAULT_CRYPTO_MONITORED_SYMBOLS)
)
crypto_monitored_symbols = [
    symbol.strip().upper()
    for symbol in _crypto_monitored_symbols_raw.split(',')
    if symbol.strip()
]
if not crypto_monitored_symbols:
    crypto_monitored_symbols = list(DEFAULT_CRYPTO_MONITORED_SYMBOLS)

_profile_monitored_symbols_raw = get_profile_env('MONITORED_SYMBOLS')
profile_monitored_symbols = [
    symbol.strip().upper()
    for symbol in (_profile_monitored_symbols_raw or '').split(',')
    if symbol.strip()
]

monitored_symbols = list(
    profile_monitored_symbols
    or (DEFAULT_FOREX_MONITORED_SYMBOLS if BOT_PROFILE == 'abbs-forex-bot' else crypto_monitored_symbols)
)

# Controle de rotação para evitar sobrecarga
current_rotation_index = 0
monitor_signals_sent = 0
SUPPORTED_TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']
if BOT_PROFILE == 'abbs-forex-bot':
    forex_default_timeframe = os.getenv('FOREX_DEFAULT_TIMEFRAME', '1h').strip().lower() or '1h'
    config.TIMEFRAME = forex_default_timeframe if forex_default_timeframe in SUPPORTED_TIMEFRAMES else '1h'
    DEFAULT_DYNAMIC_TIMEFRAMES = ['15m', '1h', '4h', '1d']
    DEFAULT_WEEKEND_DYNAMIC_TIMEFRAMES = ['1h', '4h']
else:
    DEFAULT_DYNAMIC_TIMEFRAMES = ['1m', '5m', '15m', '30m']
    DEFAULT_WEEKEND_DYNAMIC_TIMEFRAMES = ['1m', '5m']

_dynamic_timeframes_raw = os.getenv('MONITOR_DYNAMIC_TIMEFRAMES', ','.join(DEFAULT_DYNAMIC_TIMEFRAMES))
monitor_dynamic_timeframes = [
    tf for tf in (item.strip() for item in _dynamic_timeframes_raw.split(','))
    if tf in SUPPORTED_TIMEFRAMES
]
if not monitor_dynamic_timeframes:
    monitor_dynamic_timeframes = list(DEFAULT_DYNAMIC_TIMEFRAMES)
_weekend_dynamic_timeframes_raw = os.getenv(
    'WEEKEND_MONITOR_DYNAMIC_TIMEFRAMES',
    ','.join(DEFAULT_WEEKEND_DYNAMIC_TIMEFRAMES)
)
weekend_dynamic_timeframes = [
    tf for tf in (item.strip() for item in _weekend_dynamic_timeframes_raw.split(','))
    if tf in SUPPORTED_TIMEFRAMES
]
if not weekend_dynamic_timeframes:
    weekend_dynamic_timeframes = list(DEFAULT_WEEKEND_DYNAMIC_TIMEFRAMES)
monitor_timeframe_mode = os.getenv(
    'MONITOR_TIMEFRAME_MODE',
    'dynamic'
).strip().lower()
if monitor_timeframe_mode not in {'fixed', 'dynamic'}:
    monitor_timeframe_mode = 'dynamic'

# Restaura timeframe salvo pelo usuário (persiste reinicializações)
_saved_tf = _load_bot_state().get('analysis_timeframe')
if _saved_tf and _saved_tf in SUPPORTED_TIMEFRAMES:
    config.TIMEFRAME = _saved_tf
    monitor_timeframe_mode = 'fixed'

# Config do monitoramento automático
# Verifica com maior frequência para conseguir alertar na janela 20s-10s antes da virada.
MONITOR_INTERVAL_SECONDS = 5
MONITOR_DURATION_MINUTES = _env_int('MONITOR_DURATION_MINUTES', 60, min_value=5)
MONITOR_MAX_SIGNALS = _env_int('MONITOR_MAX_SIGNALS', 4)
MONITOR_NEW_SIGNAL_CYCLE_MINUTES = _env_int('MONITOR_NEW_SIGNAL_CYCLE_MINUTES', 5)
MONITOR_PRE_ALERT_MAX_SECONDS = 20
MONITOR_PRE_ALERT_MIN_SECONDS = 10
# Tenta revisitar cada ativo em no máximo 20s para não perder a janela 20s-10s.
MONITOR_TARGET_SYMBOL_REVISIT_SECONDS = 20
MONITOR_DIRECTION_COOLDOWN_CANDLES = 3
WEEKEND_MAX_REENTRIES = _env_int('WEEKEND_MAX_REENTRIES', 2)
WEEKEND_1M_CONTINUATION_MIN_SCORE = _env_int('WEEKEND_1M_CONTINUATION_MIN_SCORE', 5)
WEEKEND_1M_CONTINUATION_MIN_PROBABILITY = float(os.getenv('WEEKEND_1M_CONTINUATION_MIN_PROBABILITY', '56.0'))
MAX_PENDING_EVALUATIONS = 2
MARTINGALE_REENTRY_MAX_SECONDS = _env_int('MARTINGALE_REENTRY_MAX_SECONDS', 10)
MARTINGALE_REENTRY_MIN_SECONDS = _env_int('MARTINGALE_REENTRY_MIN_SECONDS', 3)
monitor_duration_minutes = MONITOR_DURATION_MINUTES
MONITOR_HEARTBEAT_SECONDS = _env_int('MONITOR_HEARTBEAT_SECONDS', 600)
MONITOR_AUTO_START = _env_flag(get_profile_env('MONITOR_AUTO_START'))
SCAN_AUTO_START   = _env_flag(get_profile_env('SCAN_AUTO_START'))

# Chat e telemetria da sessao atual de monitoramento
monitor_target_chat_id = None
monitor_started_at = None
monitor_last_alert_at = None
monitor_last_heartbeat_at = None

# Scanner automático de externos
_auto_scan_active = False
_auto_scan_last_alerted: dict = {}   # key: "ATIVO_DIR" -> timestamp do último alerta
_AUTO_SCAN_COOLDOWN = 1800           # segundos entre alertas repetidos do mesmo ativo+dir

# Fluxo de sinal único: envia o melhor sinal, aguarda expiração, reporta resultado, cooldown
_scan_pending_signal: dict = {}      # sinal aguardando expiração para checagem de resultado
_scan_last_signal_ts: float = 0.0   # timestamp do último sinal enviado
_SCAN_SIGNAL_INTERVAL = int(os.getenv('SCAN_SIGNAL_INTERVAL', '1800'))  # cooldown entre sinais (s), padrão 30min
SCAN_POLL_SECONDS = _env_int('SCAN_POLL_SECONDS', 60, min_value=15)
SCAN_MIN_ENTRY_LEAD_SECONDS = _env_int('SCAN_MIN_ENTRY_LEAD_SECONDS', 60, min_value=10)
SCAN_STRICT_NOISE_FILTER = _env_flag(get_profile_env('SCAN_STRICT_NOISE_FILTER'), default=True)
SCAN_STRICT_MAX_WEAK_FACTORS = _env_int('SCAN_STRICT_MAX_WEAK_FACTORS', 2, min_value=1)

# Filtros de qualidade otimizados (reduzem falsos positivos)
MIN_ALERT_PROBABILITY = 60.0  # Perfil equilibrado para 5m
MIN_ALERT_EDGE = 0.10  # Distância mínima de 0.5 (score 0.60 ou 0.40)
MIN_SIGNAL_CONSENSUS = 3  # Pelo menos 3 dos 4 indicadores principais devem concordar

# Ajuste para 1m: ainda seletivo, mas sem zerar completamente a frequência.
MIN_ALERT_PROBABILITY_1M = 58.0
MIN_ALERT_EDGE_1M = 0.08
MIN_SIGNAL_CONSENSUS_1M = 3
MIN_SETUP_SCORE = 4     # score minimo 4/8 para 5m+ (elimina setups sem estrutura)
MIN_SETUP_SCORE_1M = 6

MONITOR_INDICATORS_CONFIG = {
    **config.INDICATORS_CONFIG,
    'ADX': {'period': 14},
    'STOCHASTIC': {'k_period': 14, 'd_period': 3, 'smooth': 3},
    'FRACTALS': True,
}

CURRENT_MARKET_TYPE = normalize_market_type(getattr(config, 'MARKET_TYPE', 'crypto_binary'))

log_market_diagnostic(
    'bot_bootstrap',
    profile=BOT_PROFILE,
    market_type=CURRENT_MARKET_TYPE,
    diagnostics_log=str(DIAGNOSTICS_LOG_PATH),
)

# Parser para sinais externos (PocketOption, outros bots, canais)
signal_parser = PocketSignalParser()

DEFAULT_EXTERNAL_US_STOCKS = [
    'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'TSLA', 'NVDA', 'NFLX', 'AMD', 'INTC',
    'JPM', 'BAC', 'WMT', 'KO', 'DIS', 'NKE', 'MCD', 'PFE', 'XOM', 'CVX'
]
DEFAULT_EXTERNAL_COMMODITIES = [
    'XAUUSD', 'GOLD', 'OURO',
    'XAGUSD', 'SILVER', 'PRATA',
    'COPPER', 'HG', 'COBRE',
    'USOIL', 'WTI', 'BRENT', 'UKOIL', 'CL', 'PETROLEO'
]
DEFAULT_EXTERNAL_FOREX = [
    'GBP/JPY', 'GBPJPY',
    'EUR/USD', 'EURUSD',
    'GBP/USD', 'GBPUSD',
    'USD/JPY', 'USDJPY',
    'EUR/JPY', 'EURJPY',
    'AUD/JPY', 'AUDJPY',
    'AUD/USD', 'AUDUSD',
    'EUR/GBP', 'EURGBP',
    'USD/CAD', 'USDCAD',
    'USD/CHF', 'USDCHF',
    'NZD/USD', 'NZDUSD',
    'EUR/CHF', 'EURCHF',
    'EUR/NZD', 'EURNZD',
    'AUD/CAD', 'AUDCAD',
    'AUD/NZD', 'AUDNZD',
    'AUD/CHF', 'AUDCHF',
    'GBP/CHF', 'GBPCHF',
    'GBP/CAD', 'GBPCAD',
    'GBP/NZD', 'GBPNZD',
    'GBP/AUD', 'GBPAUD',
    'CAD/JPY', 'CADJPY',
    'CHF/JPY', 'CHFJPY',
    'NZD/JPY', 'NZDJPY',
]


def _parse_external_allowlist(env_name: str, defaults: list[str]) -> list[str]:
    raw = os.getenv(env_name, '').strip()
    if not raw:
        return [item.upper() for item in defaults]
    parsed = [item.strip().upper() for item in raw.split(',') if item.strip()]
    return parsed or [item.upper() for item in defaults]


EXTERNAL_US_STOCKS = _parse_external_allowlist('EXTERNAL_US_STOCKS', DEFAULT_EXTERNAL_US_STOCKS)
EXTERNAL_COMMODITIES = _parse_external_allowlist('EXTERNAL_COMMODITIES', DEFAULT_EXTERNAL_COMMODITIES)
EXTERNAL_FOREX = _parse_external_allowlist('EXTERNAL_FOREX', DEFAULT_EXTERNAL_FOREX)
EXTERNAL_ASSET_SET = set(EXTERNAL_US_STOCKS + EXTERNAL_COMMODITIES + EXTERNAL_FOREX)

# Mapeamento de símbolos Forex/Índices para proxies disponíveis na Binance.
FOREX_PROXY_MAP = {
    'XAU/USD': 'PAXG/USDT',
    'XAUUSD': 'PAXG/USDT',
    'GOLD': 'PAXG/USDT',
    'OURO': 'PAXG/USDT',
    'AUD/JPY': 'AUD/USDT',
    'AUDJPY': 'AUD/USDT',
    'GBP/JPY': 'GBP/USDT',
    'GBPJPY': 'GBP/USDT',
    'AUD/CAD': 'AUD/USDT',
    'AUDCAD': 'AUD/USDT',
    'GBP/USD': 'GBP/USDT',
    'GBPUSD': 'GBP/USDT',
    'EUR/GBP': 'EUR/USDT',
    'EURGBP': 'EUR/USDT',
    'EUR/CHF': 'EUR/USDT',
    'EURCHF': 'EUR/USDT',
    'EUR/HUF': 'EUR/USDT',
    'EURHUF': 'EUR/USDT',
    'EUR/RUB': 'EUR/USDT',
    'EURRUB': 'EUR/USDT',
    'EUR/NZD': 'EUR/USDT',
    'EURNZD': 'EUR/USDT',
    'EUR/TRY': 'EUR/USDT',
    'EURTRY': 'EUR/USDT',
    'EUR/JPY': 'EUR/USDT',
    'EURJPY': 'EUR/USDT',
    'AUD/NZD': 'AUD/USDT',
    'AUDNZD': 'AUD/USDT',
    'AUD/CHF': 'AUD/USDT',
    'AUDCHF': 'AUD/USDT',
    'AUD/USD': 'AUD/USDT',
    'AUDUSD': 'AUD/USDT',
    'USD/JPY': 'USDC/USDT',
    'USDJPY': 'USDC/USDT',
}

# Mapeamento de ativos externos para o scanner público do TradingView.
# Tupla: (screener, 'EXCHANGE:SYMBOL')
# Dados verificados e funcionais sem necessidade de API key.
TV_TICKER_MAP = {
    # ── Crypto (BINANCE via TradingView) ──────────────────────────────────────
    'BTC':      ('crypto', 'BINANCE:BTCUSDT'),
    'BITCOIN':  ('crypto', 'BINANCE:BTCUSDT'),
    'ETH':      ('crypto', 'BINANCE:ETHUSDT'),
    'ETHEREUM': ('crypto', 'BINANCE:ETHUSDT'),
    'BNB':      ('crypto', 'BINANCE:BNBUSDT'),
    'SOL':      ('crypto', 'BINANCE:SOLUSDT'),
    'SOLANA':   ('crypto', 'BINANCE:SOLUSDT'),
    'SUI':      ('crypto', 'BINANCE:SUIUSDT'),
    'LTC':      ('crypto', 'BINANCE:LTCUSDT'),
    'LITECOIN': ('crypto', 'BINANCE:LTCUSDT'),
    'ADA':      ('crypto', 'BINANCE:ADAUSDT'),
    'CARDANO':  ('crypto', 'BINANCE:ADAUSDT'),
    'XRP':      ('crypto', 'BINANCE:XRPUSDT'),
    'DOGE':     ('crypto', 'BINANCE:DOGEUSDT'),
    'DOGECOIN': ('crypto', 'BINANCE:DOGEUSDT'),
    # ── Ações NASDAQ ─────────────────────────────────────────────────────────
    'AAPL': ('america', 'NASDAQ:AAPL'),
    'MSFT': ('america', 'NASDAQ:MSFT'),
    'AMZN': ('america', 'NASDAQ:AMZN'),
    'GOOGL': ('america', 'NASDAQ:GOOGL'),
    'META': ('america', 'NASDAQ:META'),
    'TSLA': ('america', 'NASDAQ:TSLA'),
    'NVDA': ('america', 'NASDAQ:NVDA'),
    'NFLX': ('america', 'NASDAQ:NFLX'),
    'AMD':  ('america', 'NASDAQ:AMD'),
    'INTC': ('america', 'NASDAQ:INTC'),
    'WMT':  ('america', 'NASDAQ:WMT'),
    # Ações NYSE
    'JPM': ('america', 'NYSE:JPM'),
    'BAC': ('america', 'NYSE:BAC'),
    'KO':  ('america', 'NYSE:KO'),
    'DIS': ('america', 'NYSE:DIS'),
    'NKE': ('america', 'NYSE:NKE'),
    'MCD': ('america', 'NYSE:MCD'),
    'PFE': ('america', 'NYSE:PFE'),
    'XOM': ('america', 'NYSE:XOM'),
    'CVX': ('america', 'NYSE:CVX'),
    # ── Forex (FX via TradingView) ─────────────────────────────────────────
    'GBP/JPY':  ('global', 'FX:GBPJPY'),
    'GBPJPY':   ('global', 'FX:GBPJPY'),
    'EUR/USD':  ('global', 'FX:EURUSD'),
    'EURUSD':   ('global', 'FX:EURUSD'),
    'GBP/USD':  ('global', 'FX:GBPUSD'),
    'GBPUSD':   ('global', 'FX:GBPUSD'),
    'USD/JPY':  ('global', 'FX:USDJPY'),
    'USDJPY':   ('global', 'FX:USDJPY'),
    'EUR/JPY':  ('global', 'FX:EURJPY'),
    'EURJPY':   ('global', 'FX:EURJPY'),
    'AUD/JPY':  ('global', 'FX:AUDJPY'),
    'AUDJPY':   ('global', 'FX:AUDJPY'),
    'AUD/USD':  ('global', 'FX:AUDUSD'),
    'AUDUSD':   ('global', 'FX:AUDUSD'),
    'EUR/GBP':  ('global', 'FX:EURGBP'),
    'EURGBP':   ('global', 'FX:EURGBP'),
    'USD/CAD':  ('global', 'FX:USDCAD'),
    'USDCAD':   ('global', 'FX:USDCAD'),
    'USD/CHF':  ('global', 'FX:USDCHF'),
    'USDCHF':   ('global', 'FX:USDCHF'),
    'NZD/USD':  ('global', 'FX:NZDUSD'),
    'NZDUSD':   ('global', 'FX:NZDUSD'),
    'EUR/CHF':  ('global', 'FX:EURCHF'),
    'EURCHF':   ('global', 'FX:EURCHF'),
    'EUR/NZD':  ('global', 'FX:EURNZD'),
    'EURNZD':   ('global', 'FX:EURNZD'),
    'AUD/CAD':  ('global', 'FX:AUDCAD'),
    'AUDCAD':   ('global', 'FX:AUDCAD'),
    'AUD/NZD':  ('global', 'FX:AUDNZD'),
    'AUDNZD':   ('global', 'FX:AUDNZD'),
    'AUD/CHF':  ('global', 'FX:AUDCHF'),
    'AUDCHF':   ('global', 'FX:AUDCHF'),
    'GBP/CHF':  ('global', 'FX:GBPCHF'),
    'GBPCHF':   ('global', 'FX:GBPCHF'),
    'GBP/CAD':  ('global', 'FX:GBPCAD'),
    'GBPCAD':   ('global', 'FX:GBPCAD'),
    'GBP/NZD':  ('global', 'FX:GBPNZD'),
    'GBPNZD':   ('global', 'FX:GBPNZD'),
    'GBP/AUD':  ('global', 'FX:GBPAUD'),
    'GBPAUD':   ('global', 'FX:GBPAUD'),
    'CAD/JPY':  ('global', 'FX:CADJPY'),
    'CADJPY':   ('global', 'FX:CADJPY'),
    'CHF/JPY':  ('global', 'FX:CHFJPY'),
    'CHFJPY':   ('global', 'FX:CHFJPY'),
    'NZD/JPY':  ('global', 'FX:NZDJPY'),
    'NZDJPY':   ('global', 'FX:NZDJPY'),
    # Commodities
    'XAUUSD': ('global', 'OANDA:XAUUSD'),
    'GOLD':   ('global', 'TVC:GOLD'),
    'OURO':   ('global', 'TVC:GOLD'),
    'XAGUSD': ('global', 'TVC:SILVER'),
    'SILVER': ('global', 'TVC:SILVER'),
    'PRATA':  ('global', 'TVC:SILVER'),
    'COPPER': ('global', 'COMEX:HG1!'),
    'HG':     ('global', 'COMEX:HG1!'),
    'COBRE':  ('global', 'COMEX:HG1!'),
    'USOIL':  ('global', 'FX:USOIL'),
    'WTI':    ('global', 'FX:USOIL'),
    'CL':     ('global', 'FX:USOIL'),
    'PETROLEO': ('global', 'FX:USOIL'),
    'BRENT':  ('global', 'FX:UKOIL'),
    'UKOIL':  ('global', 'FX:UKOIL'),
}

# Mapa de símbolos para BitGet Futures (linear perpetual USDT)
BITGET_FUTURES_MAP = {
    'BTC':  'BTCUSDT',
    'ETH':  'ETHUSDT',
    'BNB':  'BNBUSDT',
    'SOL':  'SOLUSDT',
    'SUI':  'SUIUSDT',
    'LTC':  'LTCUSDT',
    'ADA':  'ADAUSDT',
    'XRP':  'XRPUSDT',
    'DOGE': 'DOGEUSDT',
}
# Assets que o scanner automático pode executar via BitGet
BITGET_SCANNABLE = set(BITGET_FUTURES_MAP.keys())


def _to_float(value: str, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_naive_utc(dt_value):
    """Normaliza datetime para UTC sem timezone para comparacoes simples."""
    if dt_value is None:
        return None
    try:
        # Alguns feeds retornam epoch numérico; inferimos segundos/ms explicitamente.
        if isinstance(dt_value, (int, float, np.integer, np.floating)):
            raw = float(dt_value)
            if raw > 1e12:  # epoch em milissegundos
                return datetime.utcfromtimestamp(raw / 1000.0)
            if raw > 1e9:   # epoch em segundos
                return datetime.utcfromtimestamp(raw)

        ts = pd.Timestamp(dt_value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert('UTC').tz_localize(None)
        return ts.to_pydatetime()
    except Exception:
        return None


def _extract_ticker_timestamp(ticker: dict):
    """Extrai timestamp do ticker CCXT em UTC (naive), quando disponivel."""
    if not ticker:
        return None

    raw_ts = ticker.get('timestamp')
    if raw_ts is not None:
        try:
            # CCXT usa milissegundos.
            return datetime.utcfromtimestamp(float(raw_ts) / 1000.0)
        except Exception:
            pass

    raw_dt = ticker.get('datetime')
    return _to_naive_utc(raw_dt)


def _normalize_otc_symbol(symbol: str) -> str:
    """Normaliza simbolo OTC para formato BASE/QUOTE sem sufixo OTC."""
    raw = (symbol or '').upper().replace(' OTC', '').replace('OTC', '').strip()
    if '/' in raw:
        base, quote = raw.split('/', 1)
        return f"{base.strip()}/{quote.strip()}"
    return raw


def _is_price_parity_compatible(requested_symbol: str, market_symbol: str) -> bool:
    """Indica se o proxy pode representar preco absoluto do ativo solicitado."""
    req = _normalize_otc_symbol(requested_symbol)
    mkt = (market_symbol or '').upper().strip()

    # Mesmo simbolo (ou similar) é seguro para exibir preco.
    if req == mkt or req.replace('/', '') == mkt.replace('/', ''):
        return True

    # Casos especiais conhecidos com boa paridade aproximada.
    special_pairs = {
        ('XAU/USD', 'PAXG/USDT'),
    }
    if (req, mkt) in special_pairs:
        return True

    # Para FX OTC, só tratamos como comparavel quando é XXX/USD via XXX/USDT.
    if '/' in req and '/' in mkt:
        req_base, req_quote = req.split('/', 1)
        mkt_base, mkt_quote = mkt.split('/', 1)
        if req_base == mkt_base and req_quote in {'USD', 'USDT'} and mkt_quote == 'USDT':
            return True

    return False


def resolve_reference_price(
    exchange: ExchangeConnector,
    requested_symbol: str,
    market_symbol: str,
    closed_df: pd.DataFrame,
    timeframe: str,
):
    """Resolve preco de referencia com protecao contra ticker desatualizado."""
    if not _is_price_parity_compatible(requested_symbol, market_symbol):
        return None, f"proxy sem paridade ({market_symbol})"

    # Para OTC proxy, rejeitamos ticker velho para evitar valores congelados.
    max_ticker_age_seconds = 15 * 60
    now_utc = datetime.utcnow()

    ticker = exchange.get_ticker(market_symbol)
    if ticker and ticker.get('last') is not None:
        ticker_ts = _extract_ticker_timestamp(ticker)
        if ticker_ts is not None:
            age_seconds = (now_utc - ticker_ts).total_seconds()
            if 0 <= age_seconds <= max_ticker_age_seconds:
                return float(ticker['last']), f"ticker ({int(age_seconds)}s)"
            logger.warning(
                "Ticker desatualizado para %s (idade=%ss). Usando candle fechado.",
                market_symbol,
                int(age_seconds),
            )
        else:
            # Sem timestamp: usa ticker apenas se ele estiver proximo do ultimo close.
            try:
                close_price = float(closed_df.iloc[-1]['close'])
                last_price = float(ticker['last'])
                drift = abs(last_price - close_price) / max(abs(close_price), 1e-9)
                if drift <= 0.02:
                    return last_price, "ticker (sem timestamp)"
            except Exception:
                pass

    # Fallback robusto: ultimo candle fechado com idade visivel na mensagem.
    close_price = float(closed_df.iloc[-1]['close'])
    candle_ts = _to_naive_utc(closed_df.index[-1])
    candle_age_seconds = int((now_utc - candle_ts).total_seconds()) if candle_ts else -1
    # Evita exibir idade absurda por timestamp mal interpretado.
    max_reasonable_age = max(6 * timeframe_to_minutes(timeframe) * 60, 30 * 60)
    if 0 <= candle_age_seconds <= max_reasonable_age:
        return close_price, f"candle fechado ({candle_age_seconds}s)"
    return close_price, "candle fechado (idade indisponivel)"


WEEKEND_RANGE_LOOKBACK = 24
WEEKEND_RANGE_TOUCH_TOLERANCE = 0.12
WEEKEND_EXTREME_ZONE_THRESHOLD = _to_float(
    os.getenv('WEEKEND_EXTREME_ZONE_THRESHOLD', '0.30'),
    0.30,
)
WEEKEND_MAX_ADX = _to_float(os.getenv('WEEKEND_MAX_ADX', '30.0'), 30.0)


def is_weekend_binary_mode(reference_time: datetime | None = None) -> bool:
    """Ativa operacional de fim de semana apenas para crypto binário."""
    if CURRENT_MARKET_TYPE != 'crypto_binary':
        return False
    current = reference_time or datetime.utcnow()
    return current.weekday() >= 5


def get_active_dynamic_timeframes(reference_time: datetime | None = None) -> list[str]:
    """Retorna o pool dinâmico ativo conforme o contexto operacional."""
    if is_weekend_binary_mode(reference_time):
        return list(weekend_dynamic_timeframes)
    return list(monitor_dynamic_timeframes)


def get_operation_mode_snapshot(reference_time: datetime | None = None) -> dict:
    """Resume o modo operacional atual do bot."""
    current = reference_time or datetime.utcnow()
    weekend_mode = is_weekend_binary_mode(current)
    dynamic_pool = get_active_dynamic_timeframes(current)

    if weekend_mode:
        return {
            'mode': 'weekend',
            'label': 'Fim de Semana',
            'summary': 'Range, rejeição e falsa quebra nos extremos.',
            'timeframes': dynamic_pool if monitor_timeframe_mode == 'dynamic' else [config.TIMEFRAME],
            'expires': '2 a 3 velas',
        }

    return {
        'mode': 'normal',
        'label': 'Normal',
        'summary': 'Operacional padrão com filtros de tendência e continuidade.',
        'timeframes': dynamic_pool if monitor_timeframe_mode == 'dynamic' else [config.TIMEFRAME],
        'expires': '1 vela',
    }


def get_monitor_mode_label() -> str:
    """Retorna o rótulo do modo de monitoramento visível ao usuário."""
    if CURRENT_MARKET_TYPE == 'crypto_binary':
        return 'Crypto'
    if CURRENT_MARKET_TYPE == 'forex':
        return 'Forex'
    return 'Crypto/Forex'


def _count_range_touches(values: pd.Series, level: float, tolerance: float) -> int:
    """Conta toques em uma zona para validar range operacional."""
    if values.empty:
        return 0
    return int(((values.astype(float) - float(level)).abs() <= tolerance).sum())


def evaluate_weekend_binary_setup(
    df: pd.DataFrame,
    timeframe: str,
    signal_data: dict | None = None,
) -> dict:
    """Detecta setup de fim de semana baseado em range, rejeição e falsa quebra."""
    neutral_response = {
        'signal': 0,
        'score': 0,
        'probability': 50.0,
        'setup_type': 'aguardando extremo do range',
        'confirmations': [],
        'warnings': ['sem setup de fim de semana no candle atual'],
        'expiry_candles': 2,
        'range_high': None,
        'range_low': None,
        'adx': 0.0,
        'close_position': 0.5,
        'score_source': 'range',
    }

    if len(df) < WEEKEND_RANGE_LOOKBACK + 5:
        neutral_response['warnings'] = ['historico insuficiente para range de fim de semana']
        return neutral_response

    window = df.iloc[-(WEEKEND_RANGE_LOOKBACK + 1):-1].copy()
    last_closed = df.iloc[-1]
    prev_closed = df.iloc[-2]

    range_high = float(window['high'].max())
    range_low = float(window['low'].min())
    range_size = max(range_high - range_low, 1e-9)
    close = float(last_closed['close'])
    open_price = float(last_closed['open'])
    high = float(last_closed['high'])
    low = float(last_closed['low'])
    candle_range = max(high - low, 1e-9)
    body_ratio = abs(close - open_price) / candle_range
    upper_wick_ratio = (high - max(open_price, close)) / candle_range
    lower_wick_ratio = (min(open_price, close) - low) / candle_range
    close_position = min(max((close - range_low) / range_size, 0.0), 1.0)
    atr = float(last_closed.get('atr', range_size / 8.0))
    adx = float(last_closed.get('adx', 0.0))
    rsi = float(last_closed.get('rsi', 50.0))
    bb_upper = float(last_closed.get('bb_upper', range_high))
    bb_lower = float(last_closed.get('bb_lower', range_low))
    bb_middle = float(last_closed.get('bb_middle', close))
    stoch_k = float(last_closed.get('stoch_k', 50.0))
    stoch_d = float(last_closed.get('stoch_d', 50.0))
    macd_diff = float(last_closed.get('macd_diff', 0.0))
    prev_macd_diff = float(prev_closed.get('macd_diff', macd_diff))

    tolerance = max(range_size * WEEKEND_RANGE_TOUCH_TOLERANCE, atr * 0.8)
    top_touches = _count_range_touches(window['high'], range_high, tolerance)
    bottom_touches = _count_range_touches(window['low'], range_low, tolerance)
    range_pct = _safe_ratio(range_size, close, default=0.0) * 100.0
    is_range = top_touches >= 2 and bottom_touches >= 2 and adx <= WEEKEND_MAX_ADX

    bullish_engulf = (
        float(prev_closed['close']) < float(prev_closed['open'])
        and close > open_price
        and close >= float(prev_closed['open'])
        and open_price <= float(prev_closed['close'])
    )
    bearish_engulf = (
        float(prev_closed['close']) > float(prev_closed['open'])
        and close < open_price
        and close <= float(prev_closed['open'])
        and open_price >= float(prev_closed['close'])
    )

    false_break_buy = (
        low < range_low
        and close > range_low
        and lower_wick_ratio >= 0.35
        and close_position <= 0.38
    )
    false_break_sell = (
        high > range_high
        and close < range_high
        and upper_wick_ratio >= 0.35
        and close_position >= 0.62
    )
    rejection_buy = (
        close_position <= WEEKEND_EXTREME_ZONE_THRESHOLD
        and lower_wick_ratio >= 0.35
        and close >= bb_lower
        and (close >= open_price or bullish_engulf)
    )
    rejection_sell = (
        close_position >= 1.0 - WEEKEND_EXTREME_ZONE_THRESHOLD
        and upper_wick_ratio >= 0.35
        and close <= bb_upper
        and (close <= open_price or bearish_engulf)
    )

    signal = 0
    setup_type = 'aguardando extremo do range'
    confirmations = []
    warnings = []
    score = 0
    expiry_candles = 2 if timeframe_to_minutes(timeframe) <= 1 else 3
    score_source = 'range'

    if not is_range:
        warnings.append(
            f'contexto sem range limpo (ADX {adx:.1f}, toques topo/fundo {top_touches}/{bottom_touches})'
        )
    else:
        score += 2
        confirmations.append(f'range validado com {top_touches} toques no topo e {bottom_touches} no fundo')
        confirmations.append(f'ADX comportado para reversao ({adx:.1f})')

    if is_range and false_break_buy:
        signal = 1
        setup_type = 'falsa quebra + rejeicao no suporte'
        score += 4
        confirmations.append('furou o fundo e fechou de volta para dentro do range')
        confirmations.append('pavio inferior confirma captura de liquidez')
    elif is_range and false_break_sell:
        signal = -1
        setup_type = 'falsa quebra + rejeicao na resistencia'
        score += 4
        confirmations.append('furou o topo e fechou de volta para dentro do range')
        confirmations.append('pavio superior confirma captura de liquidez')
    elif is_range and rejection_buy:
        signal = 1
        setup_type = 'rejeicao no fundo do range'
        score += 3
        confirmations.append('suporte defendido com rejeicao clara')
    elif is_range and rejection_sell:
        signal = -1
        setup_type = 'rejeicao no topo do range'
        score += 3
        confirmations.append('resistencia defendida com rejeicao clara')

    anticipation_zone_threshold = min(0.38, WEEKEND_EXTREME_ZONE_THRESHOLD + 0.08)
    anticipation_buy = (
        is_range
        and signal == 0
        and close_position <= anticipation_zone_threshold
        and (stoch_k <= 12 or (stoch_k >= stoch_d and stoch_k <= 35))
        and (rsi <= 44 or lower_wick_ratio >= 0.25)
        and macd_diff >= prev_macd_diff
    )
    anticipation_sell = (
        is_range
        and signal == 0
        and close_position >= 1.0 - anticipation_zone_threshold
        and (stoch_k >= 88 or (stoch_k <= stoch_d and stoch_k >= 65))
        and (rsi >= 56 or upper_wick_ratio >= 0.30)
        and macd_diff <= prev_macd_diff
    )

    if anticipation_buy:
        signal = 1
        setup_type = 'exaustao no fundo do range'
        score += 3
        confirmations.append('preco esticado no suporte com perda de pressao vendedora')
        confirmations.append('estocastico/RSI sugerem reversao antecipada no extremo')
    elif anticipation_sell:
        signal = -1
        setup_type = 'exaustao no topo do range'
        score += 3
        confirmations.append('preco esticado na resistencia com perda de pressao compradora')
        confirmations.append('estocastico/RSI sugerem reversao antecipada no extremo')

    if signal == 1:
        if bullish_engulf:
            score += 1
            confirmations.append('engolfo de alta na zona extrema')
        if rsi <= 45:
            score += 1
            confirmations.append(f'RSI comprimido para reversao ({rsi:.1f})')
        if stoch_k >= stoch_d and stoch_k <= 35:
            score += 1
            confirmations.append('estocastico virou para cima na sobrevenda')
        if close > bb_middle and false_break_buy:
            score += 1
            confirmations.append('retorno rapido acima da media do range')
        if close_position > 0.45:
            warnings.append('retorno ja avancou demais; entrada pode ficar tardia')
    elif signal == -1:
        if bearish_engulf:
            score += 1
            confirmations.append('engolfo de baixa na zona extrema')
        if rsi >= 55:
            score += 1
            confirmations.append(f'RSI esticado para reversao ({rsi:.1f})')
        if stoch_k <= stoch_d and stoch_k >= 65:
            score += 1
            confirmations.append('estocastico virou para baixo na sobrecompra')
        if close < bb_middle and false_break_sell:
            score += 1
            confirmations.append('retorno rapido abaixo da media do range')
        if close_position < 0.55:
            warnings.append('retorno ja avancou demais; entrada pode ficar tardia')

    if range_pct < 0.35:
        warnings.append(f'range curto demais ({range_pct:.2f}%); payoff pode ficar apertado')
        score -= 1
    if body_ratio > 0.70 and signal != 0:
        warnings.append('candle de gatilho grande demais; risco de entrada atrasada')
        score -= 1
    if 0.35 <= close_position <= 0.65 and signal == 0:
        warnings.append('preco no meio do range; sem vantagem estatistica')

    tf_minutes = timeframe_to_minutes(timeframe)

    if signal == 0 and signal_data is not None and tf_minutes <= 1:
        continuation_signal = int(signal_data.get('signal', 0))
        continuation_score_hint = float(signal_data.get('score', 0.5))

        if continuation_signal == 0:
            if continuation_score_hint >= 0.55:
                continuation_signal = 1
            elif continuation_score_hint <= 0.45:
                continuation_signal = -1

        if continuation_signal != 0:
            continuation_setup = evaluate_signal_setup(df, continuation_signal, signal_data, timeframe)
            confirmations_blob = ' '.join(continuation_setup.get('confirmations', []))
            setup_type_hint = continuation_setup.get('setup_type', '')
            if (
                continuation_setup['score'] >= WEEKEND_1M_CONTINUATION_MIN_SCORE
                and float(continuation_setup.get('adx', adx)) >= max(20.0, WEEKEND_MAX_ADX - 8.0)
                and float(signal_data.get('probability', 50.0)) >= WEEKEND_1M_CONTINUATION_MIN_PROBABILITY
                and (
                    'pullback' in setup_type_hint
                    or 'rompimento' in setup_type_hint
                    or 'MACD acelerando' in confirmations_blob
                    or 'estocastico confirma' in confirmations_blob
                )
            ):
                signal = continuation_signal
                score = max(score, int(continuation_setup['score']))
                score_source = 'micro_continuation'
                setup_type = f"micro continuidade ({continuation_setup['setup_type']})"
                confirmations = list(continuation_setup['confirmations'][:4])
                warnings = list(continuation_setup['warnings'][:2])
                warnings.append('scalp weekend: setup de continuidade curta, aceitar no maximo 2 martingales')

    if signal == 0 and signal_data is not None and tf_minutes >= 5:
        continuation_signal = int(signal_data.get('signal', 0))
        continuation_score_hint = float(signal_data.get('score', 0.5))

        if continuation_signal == 0:
            if continuation_score_hint >= 0.58:
                continuation_signal = 1
            elif continuation_score_hint <= 0.42:
                continuation_signal = -1

        if continuation_signal != 0:
            continuation_setup = evaluate_signal_setup(df, continuation_signal, signal_data, timeframe)
            continuation_min_score = 6 if abs(continuation_score_hint - 0.5) >= 0.10 else 8
            if (
                continuation_setup['score'] >= continuation_min_score
                and float(continuation_setup.get('adx', adx)) >= max(28.0, WEEKEND_MAX_ADX - 2.0)
                and float(signal_data.get('probability', 50.0)) >= 58.0
            ):
                signal = continuation_signal
                score = max(score, int(continuation_setup['score']))
                score_source = 'continuation'
                setup_type = f"continuidade excepcional ({continuation_setup['setup_type']})"
                confirmations = list(continuation_setup['confirmations'][:4])
                warnings = [
                    warning
                    for warning in continuation_setup['warnings'][:3]
                    if 'sem alinhamento limpo das EMAs' not in warning
                ]
                warnings.append('fim de semana fora de range: operar apenas com contexto premium')

    score = max(score, 0)
    probability = min(86.0, 50.0 + score * 4.0)

    return {
        'signal': signal,
        'score': int(score),
        'probability': float(probability),
        'setup_type': setup_type,
        'confirmations': confirmations[:4],
        'warnings': warnings[:3],
        'expiry_candles': expiry_candles,
        'range_high': range_high,
        'range_low': range_low,
        'adx': adx,
        'close_position': close_position,
        'score_source': score_source,
    }


def resolve_market_symbol(symbol: str):
    """Resolve símbolo solicitado para um símbolo de mercado disponível."""
    if not symbol:
        return None, None

    raw = symbol.strip().upper()
    mapped = FOREX_PROXY_MAP.get(raw)
    if mapped:
        return mapped, f"proxy: {mapped}"

    # Símbolos nativos já compatíveis com Binance.
    if '/' in raw and raw.endswith('USDT'):
        return raw, None

    if raw.startswith('HK'):
        return None, "sem feed Binance para HK (use MT5/TradingView como fonte)"

    if raw in {'SP500', 'US500', 'SPX500', 'SPX', 'S&P500', 'S&P 500'}:
        return None, "sem feed Binance para S&P 500 (use MT5/Fundscap ou TradingView como fonte)"

    # Se não houver mapeamento explícito, tenta usar como veio.
    return raw, None


def timeframe_to_minutes(timeframe: str) -> int:
    """Converte timeframe para minutos."""
    mapping = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }
    return mapping.get(timeframe, 1)


def get_pre_alert_window_seconds(timeframe: str) -> Tuple[int, int]:
    """Retorna janela de pre-alerta (max_s, min_s) por timeframe."""
    tf_minutes = timeframe_to_minutes(timeframe)
    if tf_minutes >= 5:
        # Janela reduzida para sinal mais proximo da abertura do candle.
        return 45, 10
    return MONITOR_PRE_ALERT_MAX_SECONDS, MONITOR_PRE_ALERT_MIN_SECONDS


def get_higher_timeframe(timeframe: str) -> str:
    """Retorna timeframe superior para analise de tendencia primaria."""
    tf_map = {
        '1m': '5m', '3m': '15m', '5m': '15m',
        '15m': '30m', '30m': '1h', '1h': '4h', '4h': '1d',
    }
    return tf_map.get(timeframe, '1h')


def get_monitor_timeframe_label() -> str:
    """Texto do modo de timeframe ativo no monitor."""
    if monitor_timeframe_mode == 'dynamic':
        active_timeframes = get_active_dynamic_timeframes()
        suffix = ' (auto fim de semana)' if is_weekend_binary_mode() else ' (auto)'
        return ', '.join(active_timeframes) + suffix
    return config.TIMEFRAME


def get_monitor_signal_scope_key(symbol: str, timeframe: str) -> str:
    """Define a chave de deduplicacao do monitor para o ativo/timeframe."""
    if monitor_timeframe_mode == 'dynamic':
        return symbol
    return f"{symbol}|{timeframe}"


def get_actionable_monitor_timeframes(now: datetime) -> list[str]:
    """Retorna timeframes operaveis na janela atual do monitor."""
    if monitor_timeframe_mode != 'dynamic':
        return [config.TIMEFRAME]

    actionable = []
    for timeframe in get_active_dynamic_timeframes(now):
        pre_alert_max_seconds, pre_alert_min_seconds = get_pre_alert_window_seconds(timeframe)
        next_candle = get_next_candle_start(now, timeframe)
        seconds_to_next = (next_candle - now).total_seconds()
        if pre_alert_min_seconds <= seconds_to_next <= pre_alert_max_seconds:
            actionable.append(timeframe)
    return actionable


def score_monitor_candidate(
    timeframe: str,
    probability: float,
    setup_score: int,
    consensus: int,
    adx_value: float,
    primary_trend: int,
    signal: int,
) -> float:
    """Rankeia candidatos do monitor por qualidade para binaria."""
    rank = probability + (setup_score * 6.0) + (consensus * 4.0) + min(adx_value, 35.0) * 0.5
    rank += min(timeframe_to_minutes(timeframe), 30) * 0.1
    if primary_trend == signal:
        rank += 10.0
    elif primary_trend != 0:
        rank -= 8.0
    return rank


def classify_binary_entry(
    timeframe: str,
    signal: int,
    probability: float,
    setup: dict,
    consensus: int,
    primary_trend: int,
    confirm_signal: int = 0,
    confirm_primary_trend: int = 0,
) -> dict:
    """Classifica o sinal binario como direto, 1 protecao ou descarte."""
    adx_value = float(setup.get('adx', 0.0))
    setup_score = int(setup.get('score', 0))
    warnings = setup.get('warnings', [])
    has_ema_warning = any('EMAs' in warning for warning in warnings)
    has_adx_warning = any('ADX' in warning for warning in warnings)

    if primary_trend != 0 and primary_trend != signal:
        return {
            'allowed': False,
            'profile': 'descartar',
            'reason': 'contra tendencia primaria',
        }

    if timeframe == '1m':
        if confirm_signal != signal:
            return {
                'allowed': False,
                'profile': 'descartar',
                'reason': 'M1 sem confirmacao operacional no M5',
            }

        if confirm_primary_trend not in (0, signal):
            return {
                'allowed': False,
                'profile': 'descartar',
                'reason': 'M5 sem alinhamento de contexto',
            }

        if (
            probability >= 64.0
            and setup_score >= 6
            and consensus >= 4
            and adx_value >= 18.0
            and not has_ema_warning
            and not has_adx_warning
            and confirm_primary_trend == signal
        ):
            return {
                'allowed': True,
                'profile': 'entrada direta',
                'reason': 'M1 forte com confirmacao do M5',
            }

        if (
            probability >= 58.0
            and setup_score >= 5
            and consensus >= 3
            and adx_value >= 16.0
        ):
            return {
                'allowed': True,
                'profile': 'aceita 1 protecao',
                'reason': 'M1 valido, mas ainda exige gestao conservadora',
            }

        return {
            'allowed': False,
            'profile': 'descartar',
            'reason': 'M1 sem qualidade suficiente para binaria profissional',
        }

    if (
        probability >= 65.0
        and setup_score >= 6
        and consensus >= 4
        and adx_value >= 18.0
        and not has_ema_warning
        and not has_adx_warning
    ):
        return {
            'allowed': True,
            'profile': 'entrada direta',
            'reason': 'setup forte e alinhado',
        }

    if (
        probability >= 60.0
        and setup_score >= 5
        and consensus >= 3
        and adx_value >= 16.0
    ):
        return {
            'allowed': True,
            'profile': 'aceita 1 protecao',
            'reason': 'setup bom, mas nao premium',
        }

    return {
        'allowed': False,
        'profile': 'descartar',
        'reason': 'setup abaixo do padrao profissional',
    }


def get_primary_trend(exchange: ExchangeConnector, symbol: str, timeframe: str) -> int:
    """
    Verifica tendencia primaria no timeframe superior usando EMA 9/21.
    Retorna: +1 (alta), -1 (baixa), 0 (indefinido/lateral).
    """
    higher_tf = get_higher_timeframe(timeframe)
    try:
        df_higher = exchange.fetch_ohlcv(symbol, higher_tf, limit=30)
        if df_higher is None or len(df_higher) < 21:
            return 0
        closes = df_higher['close'].values.astype(float)
        ema9 = pd.Series(closes).ewm(span=9, adjust=False).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21, adjust=False).mean().iloc[-1]
        last_close = float(closes[-1])
        if last_close > ema9 > ema21:
            return 1
        if last_close < ema9 < ema21:
            return -1
        return 0
    except Exception:
        return 0


def parse_monitor_duration_to_minutes(raw: str):
    """Converte argumento de duracao para minutos (ex: 60, 60m, 1h)."""
    value = (raw or '').strip().lower()
    if not value:
        return None

    try:
        if value.endswith('h'):
            return int(value[:-1]) * 60
        if value.endswith('m'):
            return int(value[:-1])
        return int(value)
    except ValueError:
        return None


def get_symbols_per_cycle(total_symbols: int, actionable_timeframes: list[str] | None = None) -> int:
    """Calcula quantos ativos devem ser verificados por ciclo."""
    if total_symbols <= 0:
        return 1

    symbols_per_cycle = max(
        1,
        (total_symbols * MONITOR_INTERVAL_SECONDS + MONITOR_TARGET_SYMBOL_REVISIT_SECONDS - 1)
        // MONITOR_TARGET_SYMBOL_REVISIT_SECONDS,
    )

    if actionable_timeframes:
        narrowest_cycles = None
        for timeframe in actionable_timeframes:
            pre_alert_max_seconds, pre_alert_min_seconds = get_pre_alert_window_seconds(timeframe)
            window_seconds = max(1, pre_alert_max_seconds - pre_alert_min_seconds)
            cycles_available = max(1, -(-window_seconds // MONITOR_INTERVAL_SECONDS))
            if narrowest_cycles is None or cycles_available < narrowest_cycles:
                narrowest_cycles = cycles_available

        if narrowest_cycles:
            symbols_needed = max(1, -(-total_symbols // narrowest_cycles))
            symbols_per_cycle = max(symbols_per_cycle, symbols_needed)

    return min(symbols_per_cycle, total_symbols)


def get_quality_gates(timeframe: str):
    """Retorna gates de qualidade por timeframe."""
    if is_weekend_binary_mode():
        return 58.0, 0.06, 0
    tf_minutes = timeframe_to_minutes(timeframe)
    if tf_minutes <= 1:
        return MIN_ALERT_PROBABILITY_1M, MIN_ALERT_EDGE_1M, MIN_SIGNAL_CONSENSUS_1M
    return MIN_ALERT_PROBABILITY, MIN_ALERT_EDGE, MIN_SIGNAL_CONSENSUS


def get_setup_min_score(timeframe: str) -> int:
    """Retorna score minimo de setup por timeframe."""
    if is_weekend_binary_mode():
        return 5 if timeframe_to_minutes(timeframe) <= 1 else 4
    if timeframe_to_minutes(timeframe) <= 1:
        return MIN_SETUP_SCORE_1M
    return MIN_SETUP_SCORE


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Evita divisao por zero em calculos de setup."""
    try:
        if denominator in (0, None) or pd.isna(denominator):
            return default
        return float(numerator) / float(denominator)
    except Exception:
        return default


def _last_fractal_level(df: pd.DataFrame, direction: str):
    """Retorna o ultimo topo/fundo fractal confirmado."""
    column = 'fractal_high' if direction == 'high' else 'fractal_low'
    price_column = 'high' if direction == 'high' else 'low'
    if column not in df.columns:
        return None

    fractals = df[df[column] == True]
    if fractals.empty:
        return None
    return float(fractals.iloc[-1][price_column])


def _three_candle_confirmation(df: pd.DataFrame, signal: int) -> tuple:
    """
    Padrão dos 3 candles (Dow / price action):
      bull: [exaustao/doji] → [sweep de minima ou pullback] → [confirmacao bullish forte]
      bear: [exaustao/doji] → [sweep de maxima ou pullback] → [confirmacao bearish forte]
    Retorna (matched: bool, descricao: str)
    """
    if len(df) < 3:
        return False, ''

    c3 = df.iloc[-3]  # hesitacao / exaustao
    c2 = df.iloc[-2]  # negacao / sweep
    c1 = df.iloc[-1]  # confirmacao

    def _br(c):
        r = max(float(c['high']) - float(c['low']), 1e-9)
        return abs(float(c['close']) - float(c['open'])) / r

    c3_br = _br(c3)
    c1_br = _br(c1)
    c1_bullish = float(c1['close']) > float(c1['open'])
    c1_bearish = float(c1['close']) < float(c1['open'])
    c2_bearish = float(c2['close']) < float(c2['open'])
    c2_bullish = float(c2['close']) > float(c2['open'])
    c3_doji = c3_br < 0.35
    c1_strong = c1_br >= 0.50

    if signal == 1:
        # Reversao: exaustao → sweep de minima → confirmacao bullish
        sweep_reversal = (
            c3_doji
            and c2_bearish
            and float(c2['low']) <= float(c3['low'])
            and c1_bullish and c1_strong
            and float(c1['close']) > max(float(c2['open']), float(c2['close']))
        )
        # Continuacao: impulso → pullback curto → retomada
        continuation = (
            float(c3['close']) > float(c3['open'])  # c3 bullish
            and c2_bearish
            and float(c2['low']) > float(c3['low'])  # pullback nao viola c3
            and c1_bullish and c1_strong
            and float(c1['close']) > float(c2['high'])
        )
        if sweep_reversal:
            return True, 'exaustao + sweep de minima + confirmacao bullish'
        if continuation:
            return True, 'impulso + pullback + continuacao bullish'

    elif signal == -1:
        # Reversao: exaustao → sweep de maxima → confirmacao bearish
        sweep_reversal = (
            c3_doji
            and c2_bullish
            and float(c2['high']) >= float(c3['high'])
            and c1_bearish and c1_strong
            and float(c1['close']) < min(float(c2['open']), float(c2['close']))
        )
        # Continuacao: impulso → pullback curto → retomada
        continuation = (
            float(c3['close']) < float(c3['open'])  # c3 bearish
            and c2_bullish
            and float(c2['high']) < float(c3['high'])  # pullback nao viola c3
            and c1_bearish and c1_strong
            and float(c1['close']) < float(c2['low'])
        )
        if sweep_reversal:
            return True, 'exaustao + sweep de maxima + confirmacao bearish'
        if continuation:
            return True, 'impulso + pullback + continuacao bearish'

    return False, ''


def _detect_sweep(df: pd.DataFrame, signal: int, lookback: int = 10) -> tuple:
    """
    Detecta candle de sweep: furou extremo recente com sombra longa e fechou de volta.
    Indica captura de liquidez / armadilha antes de movimento real.
    """
    if len(df) < lookback + 2:
        return False, ''

    c1 = df.iloc[-1]
    window = df.iloc[-(lookback + 1):-1]
    h = float(c1['high'])
    l = float(c1['low'])
    o = float(c1['open'])
    c = float(c1['close'])
    rng = max(h - l, 1e-9)
    upper_wick = (h - max(o, c)) / rng
    lower_wick = (min(o, c) - l) / rng
    recent_high = float(window['high'].max())
    recent_low = float(window['low'].min())

    if signal == 1:
        swept = l < recent_low and c > recent_low
        if swept and lower_wick >= 0.40:
            return True, 'sweep de minima recente com rejeicao forte (liquidity grab)'

    elif signal == -1:
        swept = h > recent_high and c < recent_high
        if swept and upper_wick >= 0.40:
            return True, 'sweep de maxima recente com rejeicao forte (liquidity grab)'

    return False, ''


def evaluate_signal_setup(df: pd.DataFrame, signal: int, signal_data: dict, timeframe: str) -> dict:
    """Avalia a qualidade estrutural do setup para filtrar sinais fracos."""
    if len(df) < 30:
        return {
            'score': 0,
            'setup_type': 'indefinido',
            'confirmations': [],
            'warnings': ['historico insuficiente'],
        }

    last_closed = df.iloc[-1]
    prev_closed = df.iloc[-2]
    recent_window = df.tail(21)
    close = float(last_closed['close'])
    open_price = float(last_closed['open'])
    high = float(last_closed['high'])
    low = float(last_closed['low'])
    prev_high = float(prev_closed['high'])
    prev_low = float(prev_closed['low'])
    candle_range = max(high - low, 1e-9)
    body_ratio = abs(close - open_price) / candle_range
    upper_wick_ratio = (high - max(open_price, close)) / candle_range
    lower_wick_ratio = (min(open_price, close) - low) / candle_range

    ema_short = float(last_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_SHORT']['period']}", close))
    ema_long = float(last_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_LONG']['period']}", close))
    prev_ema_short = float(prev_closed.get(f"ema_{config.INDICATORS_CONFIG['EMA_SHORT']['period']}", ema_short))
    bb_middle = float(last_closed.get('bb_middle', close))
    macd = float(last_closed.get('macd', 0.0))
    macd_signal = float(last_closed.get('macd_signal', 0.0))
    macd_diff = float(last_closed.get('macd_diff', 0.0))
    prev_macd_diff = float(prev_closed.get('macd_diff', macd_diff))
    rsi = float(last_closed.get('rsi', 50.0))
    adx = float(last_closed.get('adx', 0.0))
    adx_pos = float(last_closed.get('adx_pos', 0.0))
    adx_neg = float(last_closed.get('adx_neg', 0.0))
    stoch_k = float(last_closed.get('stoch_k', 50.0))
    stoch_d = float(last_closed.get('stoch_d', 50.0))
    volume = float(last_closed.get('volume', 0.0))
    volume_ma = float(last_closed.get('volume_ma', volume))
    volume_ratio = _safe_ratio(volume, volume_ma, default=1.0)

    recent_breakout_high = float(recent_window['high'].iloc[:-1].max()) if len(recent_window) > 1 else high
    recent_breakout_low = float(recent_window['low'].iloc[:-1].min()) if len(recent_window) > 1 else low
    recent_low_now = float(df['low'].tail(6).min())
    previous_low_block = float(df['low'].iloc[-12:-6].min()) if len(df) >= 12 else recent_low_now
    recent_high_now = float(df['high'].tail(6).max())
    previous_high_block = float(df['high'].iloc[-12:-6].max()) if len(df) >= 12 else recent_high_now
    last_fractal_high = _last_fractal_level(df.iloc[:-1], 'high') if len(df) > 5 else None
    last_fractal_low = _last_fractal_level(df.iloc[:-1], 'low') if len(df) > 5 else None

    three_candle_match, three_candle_desc = _three_candle_confirmation(df, signal)
    sweep_match, sweep_desc = _detect_sweep(df, signal)

    setup_score = 0
    confirmations = []
    warnings = []
    setup_tags = []

    if signal == 1:
        trend_ok = close > ema_short > ema_long and ema_short >= prev_ema_short
        momentum_ok = macd > macd_signal and macd_diff >= prev_macd_diff
        regime_ok = adx >= 18 and adx_pos >= adx_neg
        volume_ok = volume_ratio >= 1.10
        rsi_ok = 48 <= rsi <= 68
        stoch_ok = stoch_k >= stoch_d and stoch_k <= 88
        higher_lows = recent_low_now > previous_low_block
        broke_recent_top = close > recent_breakout_high and body_ratio >= 0.55 and upper_wick_ratio <= 0.25
        broke_fractal_top = last_fractal_high is not None and close > last_fractal_high
        pulled_back_to_mean = (
            close > ema_short
            and low <= max(ema_short, bb_middle) * 1.002
            and lower_wick_ratio >= 0.25
        )

        if trend_ok:
            setup_score += 2
            confirmations.append('tendencia acima das EMAs 9/21')
        else:
            warnings.append('sem alinhamento limpo das EMAs')

        if regime_ok:
            setup_score += 1
            confirmations.append(f'ADX forte ({adx:.1f}) com DI+ dominante')
        else:
            warnings.append('tendencia fraca no ADX')

        if momentum_ok:
            setup_score += 2
            confirmations.append('MACD acelerando a favor da compra')
        else:
            warnings.append('MACD sem expansao suficiente')

        if volume_ok:
            setup_score += 1
            confirmations.append(f'volume acima da media ({volume_ratio:.2f}x)')

        if rsi_ok:
            setup_score += 1
            confirmations.append(f'RSI equilibrado para continuidade ({rsi:.1f})')
        else:
            warnings.append(f'RSI fora da faixa ideal ({rsi:.1f})')

        if stoch_ok:
            setup_score += 1
            confirmations.append('estocastico confirma impulso comprador')

        if higher_lows:
            setup_score += 1
            confirmations.append('fundos ascendentes no curto prazo')

        if broke_recent_top or broke_fractal_top:
            setup_score += 2
            setup_tags.append('rompimento')
            confirmations.append('rompimento confirmado de topo/resistencia')
        elif pulled_back_to_mean:
            setup_score += 2
            setup_tags.append('pullback')
            confirmations.append('pullback defendido na media curta')
        else:
            warnings.append('sem rompimento ou pullback tecnico claro')

        if sweep_match:
            setup_score += 2
            setup_tags.append('sweep')
            confirmations.append(sweep_desc)

        if three_candle_match:
            setup_score += 2
            setup_tags.append('3-candles')
            confirmations.append(f'padrao 3 candles: {three_candle_desc}')

        if upper_wick_ratio > 0.35 and close > recent_breakout_high:
            warnings.append('risco de falso rompimento por rejeicao superior')
            setup_score -= 2

    elif signal == -1:
        trend_ok = close < ema_short < ema_long and ema_short <= prev_ema_short
        momentum_ok = macd < macd_signal and macd_diff <= prev_macd_diff
        regime_ok = adx >= 18 and adx_neg >= adx_pos
        volume_ok = volume_ratio >= 1.10
        rsi_ok = 32 <= rsi <= 52
        stoch_ok = stoch_k <= stoch_d and stoch_k >= 12
        lower_highs = recent_high_now < previous_high_block
        broke_recent_bottom = close < recent_breakout_low and body_ratio >= 0.55 and lower_wick_ratio <= 0.25
        broke_fractal_bottom = last_fractal_low is not None and close < last_fractal_low
        pulled_back_to_mean = (
            close < ema_short
            and high >= min(ema_short, bb_middle) * 0.998
            and upper_wick_ratio >= 0.25
        )

        if trend_ok:
            setup_score += 2
            confirmations.append('tendencia abaixo das EMAs 9/21')
        else:
            warnings.append('sem alinhamento limpo das EMAs')

        if regime_ok:
            setup_score += 1
            confirmations.append(f'ADX forte ({adx:.1f}) com DI- dominante')
        else:
            warnings.append('tendencia fraca no ADX')

        if momentum_ok:
            setup_score += 2
            confirmations.append('MACD acelerando a favor da venda')
        else:
            warnings.append('MACD sem expansao suficiente')

        if volume_ok:
            setup_score += 1
            confirmations.append(f'volume acima da media ({volume_ratio:.2f}x)')

        if rsi_ok:
            setup_score += 1
            confirmations.append(f'RSI equilibrado para continuidade ({rsi:.1f})')
        else:
            warnings.append(f'RSI fora da faixa ideal ({rsi:.1f})')

        if stoch_ok:
            setup_score += 1
            confirmations.append('estocastico confirma impulso vendedor')

        if lower_highs:
            setup_score += 1
            confirmations.append('topos descendentes no curto prazo')

        if broke_recent_bottom or broke_fractal_bottom:
            setup_score += 2
            setup_tags.append('rompimento')
            confirmations.append('rompimento confirmado de fundo/suporte')
        elif pulled_back_to_mean:
            setup_score += 2
            setup_tags.append('pullback')
            confirmations.append('pullback rejeitado na media curta')
        else:
            warnings.append('sem rompimento ou pullback tecnico claro')

        if sweep_match:
            setup_score += 2
            setup_tags.append('sweep')
            confirmations.append(sweep_desc)

        if three_candle_match:
            setup_score += 2
            setup_tags.append('3-candles')
            confirmations.append(f'padrao 3 candles: {three_candle_desc}')

        if lower_wick_ratio > 0.35 and close < recent_breakout_low:
            warnings.append('risco de falso rompimento por rejeicao inferior')
            setup_score -= 2

    setup_type = ' / '.join(setup_tags) if setup_tags else 'continuidade'
    setup_score = max(setup_score, 0)

    return {
        'score': int(setup_score),
        'setup_type': setup_type,
        'confirmations': confirmations[:4],
        'warnings': warnings[:3],
        'volume_ratio': volume_ratio,
        'adx': adx,
        'rsi': rsi,
        'body_ratio': body_ratio,
        'signal_probability': float(signal_data.get('probability', 0.0)),
    }


def is_false_breakout_risk(df: pd.DataFrame, signal: int, timeframe: str) -> bool:
    """Filtro simples para evitar entrada em possivel falso rompimento no M5+."""
    if timeframe_to_minutes(timeframe) < 5 or len(df) < 4:
        return False

    # Usa candles fechados para reduzir ruído.
    last_closed = df.iloc[-2]
    prev_closed = df.iloc[-3]

    o = float(last_closed['open'])
    h = float(last_closed['high'])
    l = float(last_closed['low'])
    c = float(last_closed['close'])

    candle_range = max(h - l, 1e-9)
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_ratio = body / candle_range
    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    # Rompimento recente do candle anterior.
    broke_up = c > float(prev_closed['high'])
    broke_down = c < float(prev_closed['low'])

    if signal == 1:
        # Compra apos rompimento com corpo fraco ou forte rejeicao superior tende a falhar.
        if (broke_up and body_ratio < 0.45) or upper_wick_ratio > 0.45:
            return True
    elif signal == -1:
        # Venda apos rompimento com corpo fraco ou forte rejeicao inferior tende a falhar.
        if (broke_down and body_ratio < 0.45) or lower_wick_ratio > 0.45:
            return True

    return False


def get_next_candle_start(now: datetime, timeframe: str) -> datetime:
    """Retorna o início do próximo candle para o timeframe."""
    tf_minutes = timeframe_to_minutes(timeframe)

    if tf_minutes >= 1440:
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=0, minute=0, second=0, microsecond=0)

    base = now.replace(second=0, microsecond=0)
    minute_block = (base.minute // tf_minutes) * tf_minutes
    current_block_start = base.replace(minute=minute_block)
    return current_block_start + timedelta(minutes=tf_minutes)


def direction_cooldown_elapsed(symbol: str, signal: int, now: datetime, timeframe: str) -> bool:
    """Permite repetir sinal na mesma direção após cooldown de candles."""
    key = f"{symbol}:{signal}"
    last_at = last_direction_alert_at.get(key)
    if last_at is None:
        return True

    cooldown_minutes = timeframe_to_minutes(timeframe) * MONITOR_DIRECTION_COOLDOWN_CANDLES
    return (now - last_at) >= timedelta(minutes=cooldown_minutes)


def reset_weekend_reentry_state(symbol_key: str):
    """Limpa rastreio de reentradas scalp para o ativo/timeframe."""
    for tracked_signal in (1, -1):
        weekend_reentry_tracker.pop(f"{symbol_key}:{tracked_signal}", None)


def has_pending_martingale_decision(symbol_key: str, signal: int) -> bool:
    """Evita alerta duplicado enquanto uma decisao de martingale ainda nao foi emitida."""
    decision_key = f"{symbol_key}:{signal}"
    return any(item.get('decision_key') == decision_key for item in pending_martingale_decisions)


def build_monitor_session_summary(reason: str | None = None) -> str:
    """Monta resumo final da sessao atual de monitoramento."""
    total = len(monitor_session_results)
    wins = sum(1 for item in monitor_session_results if item.get('is_good'))
    losses = sum(1 for item in monitor_session_results if not item.get('is_good'))
    martingale_alerts = sum(1 for item in monitor_session_results if item.get('martingale_alert'))
    pending_count = len(pending_signal_evaluations)

    summary = "⏹ **Resumo final da sessão**\n\n"
    if reason:
        summary += f"Motivo: {reason}\n"
    summary += (
        f"📊 Operações avaliadas: {total}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"🚦 Alertas de martingale: {martingale_alerts}\n"
    )
    if total > 0:
        summary += f"🎯 Win rate: {(wins / total) * 100:.1f}%\n"
    if pending_count > 0:
        summary += f"⏳ Pendentes não fechadas: {pending_count}\n"

    recent_items = monitor_session_results[-4:]
    if recent_items:
        summary += "\nÚltimas operações:\n"
        for item in recent_items:
            direction = 'COMPRA' if item.get('signal') == 1 else 'VENDA'
            quality = 'WIN' if item.get('is_good') else 'LOSS'
            mg_suffix = ' | MG' if item.get('martingale_alert') else ''
            summary += (
                f"• {item.get('symbol')} {direction} {item.get('timeframe')}"
                f" | {quality} {item.get('result_pct', 0.0):+.3f}%{mg_suffix}\n"
            )

    return summary.strip()


def allow_weekend_reentry(symbol_key: str, signal: int, now: datetime, timeframe: str) -> bool:
    """Permite reemitir setup scalp no fim de semana ate 2 martingales."""
    if timeframe_to_minutes(timeframe) > 1:
        return False

    state_key = f"{symbol_key}:{signal}"
    state = weekend_reentry_tracker.get(state_key)
    if state is None:
        return False

    last_at = state.get('last_at')
    if last_at is None:
        return False

    max_gap = timedelta(minutes=timeframe_to_minutes(timeframe) * (WEEKEND_MAX_REENTRIES + 1))
    if now - last_at > max_gap:
        weekend_reentry_tracker.pop(state_key, None)
        return False

    return int(state.get('alerts_sent', 1)) < (WEEKEND_MAX_REENTRIES + 1)


def get_telegram_chat_id():
    """Retorna chat_id do ambiente ou config."""
    return get_profile_env('TELEGRAM_CHAT_ID') or getattr(config, 'TELEGRAM_CHAT_ID', None)


def get_telegram_bot_token():
    """Retorna token do bot conforme perfil ativo."""
    return get_profile_env('TELEGRAM_BOT_TOKEN') or getattr(config, 'TELEGRAM_BOT_TOKEN', None)


def bootstrap_auto_monitoring() -> tuple[bool, str | None]:
    """Ativa o monitoramento no boot quando solicitado por ambiente."""
    global monitoring_active, monitor_end_time, monitor_signals_sent, current_rotation_index
    global pending_signal_evaluations, pending_martingale_decisions, last_pre_alert_key, last_direction_alert_at
    global monitor_target_chat_id, monitor_started_at, monitor_last_alert_at, monitor_last_heartbeat_at
    global monitor_session_results, last_fresh_alert_at, monitor_duration_minutes

    if not MONITOR_AUTO_START:
        return False, None

    chat_id = get_telegram_chat_id()
    if not chat_id:
        return False, 'TELEGRAM_CHAT_ID ausente'

    if not monitored_symbols:
        return False, 'nenhum ativo configurado para monitoramento'

    monitor_duration_minutes = MONITOR_DURATION_MINUTES
    monitoring_active = True
    monitor_end_time = datetime.now() + timedelta(minutes=monitor_duration_minutes)
    monitor_signals_sent = 0
    current_rotation_index = 0
    monitor_target_chat_id = chat_id
    monitor_started_at = datetime.now()
    monitor_last_alert_at = None
    monitor_last_heartbeat_at = datetime.now()
    pending_signal_evaluations = []
    pending_martingale_decisions = []
    monitor_session_results = []
    last_fresh_alert_at = None
    last_pre_alert_key.clear()
    last_direction_alert_at.clear()
    weekend_reentry_tracker.clear()
    return True, None


async def notify_auto_monitor_started(context: ContextTypes.DEFAULT_TYPE):
    """Envia confirmação de auto-start para o chat alvo."""
    if not _auto_scan_active:
        return

    chat_id = monitor_target_chat_id or get_telegram_chat_id()
    if not chat_id:
        return

    assets_crypto = [a for a in TV_TICKER_MAP if a.upper() not in EXTERNAL_FOREX]
    assets_forex  = [a for a in TV_TICKER_MAP if a.upper() in EXTERNAL_FOREX]
    forex_session_ok, forex_label = _is_forex_session_active()
    forex_status = f'✅ {forex_label}' if forex_session_ok else f'🔒 Fora de sessão ({forex_label})'
    interval_min = _SCAN_SIGNAL_INTERVAL // 60

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🤖 *abbsCrypto iniciado*\n\n"
            "📡 *Scanner automático ATIVO*\n"
            f"🔬 Engine: TradingView API — 5m + 15m\n"
            f"📊 9 critérios: EMA9/20, RSI, S/R, Dow, Fibo, Day range, ADX, PA\n"
            f"🚦 FORTE ≥ 6/9 | ADX gate: crypto ≥ 20 | forex ≥ 25\n"
            f"🔄 Pré-análise P1: 4 min após cada entrada\n\n"
            f"💹 Crypto: {len(assets_crypto)} ativos — sempre ativo\n"
            f"💱 Forex: {len(assets_forex)} ativos — {forex_status}\n\n"
            f"⏱ Varredura a cada 5 min | Cooldown {interval_min} min entre sinais\n\n"
            "_Use /monitor para ver status detalhado_"
        ),
        parse_mode='Markdown'
    )


def release_instance_lock():
    """Libera lock de instância ao encerrar o processo."""
    global instance_lock_file
    try:
        if instance_lock_file:
            fcntl.flock(instance_lock_file, fcntl.LOCK_UN)
            instance_lock_file.close()
            instance_lock_file = None
    except Exception:
        pass


def acquire_instance_lock() -> bool:
    """Garante que apenas uma instância do bot rode por vez."""
    global instance_lock_file

    # Permite rodar instâncias paralelas (ex.: binarios e forex) sem conflito.
    instance_name = os.getenv('BOT_INSTANCE_NAME', 'default').strip().lower()
    safe_instance = re.sub(r'[^a-z0-9_-]+', '_', instance_name) or 'default'
    lock_path = f'/tmp/trading_bot_telegram_{safe_instance}.lock'
    instance_lock_file = open(lock_path, 'w')

    try:
        fcntl.flock(instance_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        instance_lock_file.write(str(os.getpid()))
        instance_lock_file.flush()
        atexit.register(release_instance_lock)
        return True
    except BlockingIOError:
        return False


async def _reply_text(update: Update, text: str, **kwargs):
    """Responde pelo effective_message e cai para o chat quando necessario."""
    message = update.effective_message
    if message is not None:
        return await message.reply_text(text, **kwargs)

    chat = update.effective_chat
    if chat is None:
        logger.error("Nao foi possivel responder: update sem effective_message/effective_chat.")
        return None

    return await chat.send_message(text, **kwargs)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start."""
    mode_snapshot = get_operation_mode_snapshot()

    main_section = """
📊 **Análise:**
/analise - Análise completa do ativo atual
/btc - Análise do Bitcoin (BTC/USDT)
/eth - Análise do Ethereum (ETH/USDT)
/sol - Análise do Solana (SOL/USDT)
/bnb - Análise do BNB (BNB/USDT)
/ada - Análise do Cardano (ADA/USDT)
/xrp - Análise do Ripple (XRP/USDT)
/ltc - Análise do Litecoin (LTC/USDT)

🔔 **Monitora:**
/monitor on - Ativar monitoramento automático
/monitor off - Desativar monitoramento
/ativos - Gerenciar ativos monitorados
/stats - Ver qualidade dos sinais (bom/ruim)
/externo - Publicar sinal externo (ações/commodities) no chat
    """.strip()

    profile_section = main_section

    welcome_message = """
🤖 **Bot de Trading - Análise Técnica**

Mercado ativo: **{market_type}**
Perfil: **{profile}**
Modo operacional: **{mode_label}**
Resumo: {mode_summary}

Comandos disponíveis:

{profile_section}

⚙️ **Configuração:**
/config - Ver configuração atual
/modo - Ver modo operacional atual
/timeframe [auto|1m|5m|15m|30m|1h|4h|1d] - Mudar timeframe
/ativo [SYMBOL] - Mudar ativo (ex: /ativo BTC/USDT)

ℹ️ **Info:**
/help - Mostrar esta mensagem
/ping - Testar se o bot está online

Desenvolvido com 💙 para análise técnica profissional
    """
    await _reply_text(
        update,
        welcome_message.format(
            market_type=CURRENT_MARKET_TYPE,
            profile=BOT_PROFILE,
            mode_label=mode_snapshot['label'],
            mode_summary=mode_snapshot['summary'],
            profile_section=profile_section,
        )
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    await start(update, context)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ping"""
    await _reply_text(update, "🟢 Bot online e funcionando!")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats para assertividade dos sinais."""
    total = signal_stats['total']
    good = signal_stats['good']
    bad = signal_stats['bad']

    if total == 0:
        await update.message.reply_text(
            "📊 Ainda não há sinais avaliados.\n"
            "Ative com /monitor on e aguarde o fechamento do próximo candle."
        )
        return

    hit_rate = (good / total) * 100
    await update.message.reply_text(
        f"📊 **Desempenho dos Sinais**\n\n"
        f"Total avaliados: {total}\n"
        f"✅ Bons: {good}\n"
        f"❌ Ruins: {bad}\n"
        f"🎯 Assertividade: {hit_rate:.1f}%",
        parse_mode='Markdown'
    )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, symbol=None, timeframe=None):
    """Análise avulsa usando engine TradingView (9 critérios profissionais)."""
    import math as _math

    current_symbol = (symbol or config.SYMBOL).upper()
    current_timeframe = _resolve_analysis_timeframe(timeframe)
    config.TIMEFRAME = current_timeframe
    confirm_timeframe = get_higher_timeframe(current_timeframe)

    # Normaliza para chave do TV_TICKER_MAP
    # Ex: "BTC/USDT" → "BTC", "ETH/USDT" → "ETH", "US500" → "US500"
    tv_key = current_symbol.split('/')[0]

    await update.message.reply_text("📊 Analisando via TradingView... ⏳")

    # Verifica se o ativo é suportado
    if tv_key not in TV_TICKER_MAP:
        await update.message.reply_text(
            f"❌ `{current_symbol}` não está no mapa de ativos suportados.\n"
            f"Use um dos ativos listados no /scan.",
            parse_mode='Markdown',
        )
        return

    # ═══════════════════════════════════════════════════════════════════════════════
    # VALIDAÇÃO DE TIER DE LIQUIDEZ (ATLAS v1.1 - Jun 2026)
    # ═══════════════════════════════════════════════════════════════════════════════
    # Bloqueia análise de alts (ADA/DOGE/LTC) em horários de baixa liquidez.
    # Evita sinais falsos causados por dojis em madrugada asiática e finais de semana.
    # ═══════════════════════════════════════════════════════════════════════════════
    av_type = 'forex' if tv_key.upper() in EXTERNAL_FOREX else 'crypto'
    
    # Validação de liquidez para ativos cripto
    if av_type == 'crypto':
        can_trade, liquidity_msg = _check_crypto_liquidity_session(tv_key)
        profile = _get_crypto_signal_profile(tv_key)
        
        if not can_trade:
            await update.message.reply_text(
                f"⏸ **{current_symbol}** - Filtro de Liquidez Ativo\n\n"
                f"{liquidity_msg}\n\n"
                f"💡 **Por quê?**\n"
                f"Ativos Tier {profile['tier']} ({profile['tier_name']}) geram muitos dojis e sinais falsos "
                f"em horários de baixa liquidez. O sistema ATLAS bloqueia análise nestes períodos "
                f"para proteger a qualidade dos sinais.\n\n"
                f"🕐 **Quando operar {current_symbol}:**\n" +
                (f"• Qualquer horário (liquidez 24/7)" if profile['tier'] == 1 else
                 f"• Segunda a Sexta, 07-16h UTC (Londres) ou 12-21h UTC (NY)" if profile['tier'] == 2 else
                 f"• Segunda a Sexta, 12-16h UTC (Overlap Londres+NY apenas)"),
                parse_mode='Markdown',
            )
            return

    try:
        # Busca dados no timeframe configurado e no superior para confirmação
        analysis_5m = _get_tv_analysis(tv_key, timeframe=current_timeframe)
        if not analysis_5m:
            await update.message.reply_text(f"❌ Sem dados TradingView para `{current_symbol}`.", parse_mode='Markdown')
            return

        analysis_15m = _get_tv_analysis(tv_key, timeframe=confirm_timeframe)

        # Determina tipo do ativo para thresholds corretos
        av_type = 'forex' if tv_key.upper() in EXTERNAL_FOREX else 'crypto'

        # Verifica sessão forex
        if av_type == 'forex':
            sess_ok, sess_label = _is_forex_session_active()
            if not sess_ok:
                await update.message.reply_text(
                    f"⏸ *{current_symbol}* é um par Forex.\n"
                    f"Sessão ativa: _{sess_label}_\n"
                    f"Sinais forex só são confiáveis na sessão de Londres (08–16h UTC) ou Nova York (12–21h UTC).",
                    parse_mode='Markdown',
                )
                return

        # Avalia BUY e SELL — escolhe o de maior pontuação
        best_direction = None
        best_score = -1
        best_quality = ''
        best_reasons = []
        for direction in ('BUY', 'SELL'):
            quality, reasons = _assess_signal_quality(analysis_5m, direction, asset_type=av_type)
            score = sum(1 for r in reasons if r.startswith('✅'))
            if score > best_score:
                best_score = score
                best_quality = quality
                best_reasons = reasons
                best_direction = direction

        # Se ADX gate bloqueou ambas as direções (score=0), tenta sem gate p/ mostrar diagnóstico
        if best_score == 0 and best_direction:
            for direction in ('BUY', 'SELL'):
                quality_ng, reasons_ng = _assess_signal_quality(
                    analysis_5m, direction, asset_type=av_type, skip_adx_gate=True)
                score_ng = sum(1 for r in reasons_ng if r.startswith('✅'))
                if score_ng > best_score:
                    best_score = score_ng
                    best_quality = quality_ng
                    best_reasons = reasons_ng
                    best_direction = direction

        # Confirmação 15m
        mtf_confirmed = False
        if analysis_15m and best_direction:
            q15, _ = _assess_signal_quality(analysis_15m, best_direction, asset_type=av_type)
            mtf_confirmed = 'FORTE' in q15 or 'MODERADO' in q15

        close = analysis_5m.get('close')
        rsi   = analysis_5m.get('RSI')
        adx   = analysis_5m.get('ADX')
        close_str = f'{close:.4g}' if close is not None else 'N/A'
        rsi_str   = f'{rsi:.1f}'   if rsi   is not None else 'N/A'
        adx_str   = f'{adx:.1f}'   if adx   is not None else 'N/A'
        group = _external_asset_group(tv_key)

        # Decide recomendação — 3 níveis para análise avulsa
        dir_label = 'COMPRA' if best_direction == 'BUY' else 'VENDA'
        safety_blocks = []
        crypto_profile = _get_crypto_signal_profile(tv_key) if av_type == 'crypto' else None

        if crypto_profile and best_direction:
            if adx is None or adx < crypto_profile['min_adx']:
                safety_blocks.append(
                    f"ADX {adx_str} abaixo do minimo para {crypto_profile['tier']} ({crypto_profile['min_adx']:.0f})"
                )
            if rsi is not None:
                if best_direction == 'BUY' and rsi >= crypto_profile['buy_rsi_block']:
                    safety_blocks.append(
                        f"RSI {rsi:.1f} esticado para compra (limite {crypto_profile['buy_rsi_block']:.0f})"
                    )
                if best_direction == 'SELL' and rsi <= crypto_profile['sell_rsi_block']:
                    safety_blocks.append(
                        f"RSI {rsi:.1f} esticado para venda (limite {crypto_profile['sell_rsi_block']:.0f})"
                    )

        # Gate de contra-tendência: Dow macro oposto → exige 5+/9 para MODERADO
        dow_counter = any('contratendencia' in r or 'contra tendencia' in r for r in best_reasons)
        moderado_min = 5 if dow_counter else 4

        # LÓGICA CORRIGIDA: NEUTRO só quando ADX baixo (sem tendência clara)
        # RSI extremo NÃO força NEUTRO, apenas ajusta direção/força
        adx_too_low = False
        rsi_reversal_signal = None
        
        if crypto_profile:
            # ADX abaixo do mínimo = mercado lateral, SIM é NEUTRO
            if adx is None or adx < crypto_profile['min_adx']:
                adx_too_low = True
            
            # RSI extremo sugere REVERSÃO, não neutralidade
            if rsi is not None and best_direction:
                if best_direction == 'BUY' and rsi >= 70:
                    # Sobrecomprado: sinal de reversão para VENDA
                    rsi_reversal_signal = 'SELL'
                elif best_direction == 'SELL' and rsi <= 30:
                    # Sobrevendido: sinal de reversão para COMPRA
                    rsi_reversal_signal = 'BUY'
        
        # Aplicar reversão se RSI extremo
        if rsi_reversal_signal:
            best_direction = rsi_reversal_signal
            dir_label = 'COMPRA' if rsi_reversal_signal == 'BUY' else 'VENDA'
            # Reduzir score porque é contra-indicador
            best_score = max(best_score - 2, 3)
        
        # Decisão final
        if adx_too_low or best_score < 3:
            # NEUTRO só quando ADX baixo OU score muito fraco
            rec_emoji, rec_label, rec_strength = '⚪', 'NEUTRO', ''
        elif 'FORTE' in best_quality and best_score >= 6:
            rec_emoji = '🟢' if best_direction == 'BUY' else '🔴'
            rec_label = dir_label
            rec_strength = 'FORTE'
        elif best_score >= moderado_min:
            rec_emoji = '🟡'
            rec_label = dir_label
            rec_strength = 'MODERADO'
        else:
            rec_emoji, rec_label, rec_strength = '⚪', 'NEUTRO', ''

        # Próxima fronteira do timeframe configurado para entrada
        tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
        tf_min = tf_minutes.get(current_timeframe, 5)
        now_local = datetime.now()
        if tf_min < 60:
            total_min = now_local.minute + now_local.second / 60 + 0.02
            next_tf_min = _math.ceil(total_min / tf_min) * tf_min
            if next_tf_min >= 60:
                entry_dt = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            else:
                entry_dt = now_local.replace(minute=int(next_tf_min), second=0, microsecond=0)
        else:
            entry_dt = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=tf_min // 60)
        entry_str = entry_dt.strftime('%H:%M')
        expiry_label = f'{tf_min} min' if tf_min < 60 else f'{tf_min // 60}h'

        mtf_tag = f'✅ {current_timeframe} + {confirm_timeframe} alinhados' if mtf_confirmed else f'⚠️ Apenas {current_timeframe} avaliado'
        reasons_text = '\n'.join(f'  {r}' for r in best_reasons)

        # Construir mensagem de ação
        if rec_label == 'NEUTRO':
            if adx_too_low:
                action_line = (
                    f"⚪ *RECOMENDAÇÃO: NEUTRO*\n"
                    f"📊 ADX {adx_str} — mercado sem tendência clara (lateral).\n"
                    f"⏸ Aguarde movimento direcional mais forte."
                )
            else:
                action_line = (
                    f"⚪ *RECOMENDAÇÃO: NEUTRO*\n"
                    f"⏸ Sinal fraco ({best_score}/9 critérios). Aguarde melhor configuração."
                )
            if safety_blocks:
                action_line += '\n⚠️ Observações:\n' + '\n'.join(f'  • {item}' for item in safety_blocks)
        elif rec_strength == 'FORTE':
            action_line = (
                f"{rec_emoji} *RECOMENDAÇÃO: {rec_label} — FORTE*\n"
                f"❗️ Entrada sugerida: `{entry_str}` (UTC-3) | Expiração: {expiry_label}"
            )
            if rsi_reversal_signal:
                action_line += f"\n🔄 Reversão esperada: RSI {rsi_str} extremo"
        else:
            action_line = (
                f"{rec_emoji} *RECOMENDAÇÃO: {rec_label} — MODERADO*\n"
                f"⚠️ Sinal presente mas não FORTE ({best_score}/9). Use com cautela.\n"
                f"❗️ Entrada sugerida: `{entry_str}` (UTC-3) | Expiração: {expiry_label}"
            )
            if rsi_reversal_signal:
                action_line += f"\n🔄 Reversão esperada: RSI {rsi_str} extremo"

        message = (
            f"📊 *ANÁLISE — {current_symbol}* ({group})\n"
            f"📅 {now_local.strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"⏱ Timeframe: `{current_timeframe}` (confirmação: `{confirm_timeframe}`)\n"
            f"💵 Preço: `{close_str}` | RSI: `{rsi_str}` | ADX: `{adx_str}`\n\n"
            f"{action_line}\n"
            f"_{mtf_tag}_\n\n"
            f"📋 *Critérios ({best_score}/9):*\n"
            f"{reasons_text}\n\n"
            f"_Qualidade: {best_quality}_"
        )
        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erro na análise avulsa: {e}")
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def analise_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /analise"""
    symbol = None
    timeframe = None

    if context.args:
        raw_symbol = (context.args[0] or '').strip().upper().replace('-', '/').replace(' ', '')
        alias_map = {
            'BTC': 'BTC/USDT',
            'ETH': 'ETH/USDT',
            'SOL': 'SOL/USDT',
            'BNB': 'BNB/USDT',
            'ADA': 'ADA/USDT',
            'XRP': 'XRP/USDT',
            'LTC': 'LTC/USDT',
            'XAU': 'XAU/USD',
            'GOLD': 'XAU/USD',
            'SP500': 'US500',
            'US500': 'US500',
        }
        symbol = alias_map.get(raw_symbol)
        if symbol is None:
            symbol = raw_symbol if '/' in raw_symbol else f'{raw_symbol}/USDT'

        if len(context.args) > 1:
            timeframe = (context.args[1] or '').strip().lower()

    await analyze(update, context, symbol=symbol, timeframe=timeframe)


async def _analyze_quick_symbol(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    symbol: str,
):
    """Atalhos de ativo aceitam timeframe opcional: /eth 1m, /btc 5m, etc."""
    timeframe = None
    if context.args:
        candidate_tf = (context.args[0] or '').strip().lower()
        if candidate_tf in SUPPORTED_TIMEFRAMES:
            timeframe = candidate_tf
        else:
            await update.message.reply_text(
                f"❌ Timeframe inválido para análise avulsa: {candidate_tf}. "
                f"Use: {', '.join(SUPPORTED_TIMEFRAMES)}"
            )
            return

    await analyze(update, context, symbol=symbol, timeframe=timeframe)


async def btc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /btc"""
    await _analyze_quick_symbol(update, context, symbol='BTC/USDT')


async def eth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /eth"""
    await _analyze_quick_symbol(update, context, symbol='ETH/USDT')


async def sol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /sol"""
    await _analyze_quick_symbol(update, context, symbol='SOL/USDT')


async def bnb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /bnb"""
    await _analyze_quick_symbol(update, context, symbol='BNB/USDT')


async def ada_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ada"""
    await _analyze_quick_symbol(update, context, symbol='ADA/USDT')


async def xrp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /xrp"""
    await _analyze_quick_symbol(update, context, symbol='XRP/USDT')


async def ltc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ltc"""
    await _analyze_quick_symbol(update, context, symbol='LTC/USDT')


async def ouro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ouro (proxy via PAXG/USDT na Binance)."""
    await _analyze_quick_symbol(update, context, symbol='PAXG/USDT')


async def xau_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias /xau para analise do ouro (proxy PAXG/USDT)."""
    await _analyze_quick_symbol(update, context, symbol='PAXG/USDT')


async def sp500_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atalho /sp500 para analise do S&P 500 via fonte Fundscap/MT5 quando disponivel."""
    await _analyze_quick_symbol(update, context, symbol='US500')


async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /config"""
    mode_snapshot = get_operation_mode_snapshot()
    message = f"""
⚙️ **Configuração Atual:**

📊 Ativo: `{config.SYMBOL}`
⏱ Timeframe: `{get_monitor_timeframe_label()}`
🧭 Modo operacional: `{mode_snapshot['label']}`
📝 Leitura atual: {mode_snapshot['summary']}
🕒 Pool ativo: `{', '.join(mode_snapshot['timeframes'])}`
⏳ Expiração base: `{mode_snapshot['expires']}`
💰 Capital Inicial: ${config.INITIAL_CAPITAL:,.2f}

**Thresholds:**
🟢 Compra: {config.BUY_THRESHOLD}
🔴 Venda: {config.SELL_THRESHOLD}

**Risk Management:**
🛡 Stop Loss: {config.STOP_LOSS_PERCENT*100}%
🎯 Take Profit: {config.TAKE_PROFIT_PERCENT*100}%
📦 Risk per Trade: {config.RISK_PER_TRADE*100}%

Para mudar use:
/timeframe [auto|1m|5m|15m|30m|1h|4h|1d]
/ativo [SYMBOL]
/modo
    """
    await update.message.reply_text(message, parse_mode='Markdown')


async def modo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /modo para mostrar o modo operacional atual."""
    mode_snapshot = get_operation_mode_snapshot()
    message = (
        "🧭 Modo Operacional Atual\n\n"
        f"• Mercado: {CURRENT_MARKET_TYPE}\n"
        f"• Perfil: {BOT_PROFILE}\n"
        f"• Modo: {mode_snapshot['label']}\n"
        f"• Resumo: {mode_snapshot['summary']}\n"
        f"• Timeframes ativos: {', '.join(mode_snapshot['timeframes'])}\n"
        f"• Expiração base: {mode_snapshot['expires']}"
    )
    await _reply_text(update, message)


async def timeframe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /timeframe"""
    global monitor_timeframe_mode

    if not context.args:
        await update.message.reply_text(
            "⏱ **Escolha o Timeframe:**\n\n"
            "📊 Atalhos rápidos:\n"
            "/timeframe auto - Seleção profissional automática (1m, 5m, 15m, 30m)\n"
            "/timeframe 1m - Scalping (1 minuto)\n"
            "/timeframe 5m - Day Trade rápido\n"
            "/timeframe 15m - Day Trade\n"
            "/timeframe 30m - Intraday seletivo\n"
            "/timeframe 1h - Swing curto\n"
            "/timeframe 4h - Swing médio\n"
            "/timeframe 1d - Position\n\n"
            f"✅ Atual: **{get_monitor_timeframe_label()}**",
            parse_mode='Markdown'
        )
        return
    
    tf = (context.args[0] or '').strip().lower()

    if tf == 'auto':
        monitor_timeframe_mode = 'dynamic'
        _save_bot_state('analysis_timeframe', None)
        await update.message.reply_text(
            "✅ Timeframe dinâmico profissional ativado.\n\n"
            f"🧠 Pool profissional: {', '.join(monitor_dynamic_timeframes)}\n"
            "O monitor vai priorizar a melhor entrada entre os tempos elegíveis e usar filtro operacional mais rígido.",
            parse_mode='Markdown'
        )
        return

    valid_tfs = list(SUPPORTED_TIMEFRAMES)
    
    if tf not in valid_tfs:
        await update.message.reply_text(f"❌ Timeframe inválido. Use: {', '.join(valid_tfs)}")
        return
    
    monitor_timeframe_mode = 'fixed'
    config.TIMEFRAME = tf
    _save_bot_state('analysis_timeframe', tf)
    
    # Mensagem específica por timeframe
    style_msg = {
        '1m': '⚡️ Scalping ativado! Sinais rápidos.',
        '5m': '🎯 Day Trade rápido! Bom para sinais intraday.',
        '15m': '📊 Day Trade! Ideal para operações do dia.',
        '30m': '🧭 Intraday seletivo! Menos ruído e mais contexto.',
        '1h': '📈 Swing curto! Operações de algumas horas.',
        '4h': '🔄 Swing médio! Operações de dias.',
        '1d': '💎 Position! Operações de semanas/meses.'
    }
    
    await update.message.reply_text(
        f"✅ Timeframe alterado para: **{tf}**\n\n"
        f"{style_msg.get(tf, '')}\n\n"
        "💡 Dica: Use /monitor on para alertas automáticos",
        parse_mode='Markdown'
    )


async def ativo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ativo"""
    if not context.args:
        await update.message.reply_text(
            "❌ Use: /ativo [SYMBOL]\n"
            f"📊 Ativo atual: {config.SYMBOL}\n\n"
            "Exemplos:\n"
            "/ativo BTC/USDT\n"
            "/ativo ETH/USDT\n"
            "/ativo SOL/USDT"
        )
        return
    
    symbol = context.args[0].upper()
    config.SYMBOL = symbol
    await update.message.reply_text(f"✅ Ativo alterado para: {symbol}")


async def ativos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ativos - gerencia lista de ativos monitorados"""
    global monitored_symbols
    
    if not context.args:
        top5_label = 'Top 5 cryptos'
        top10_label = 'Top 10 cryptos'
        symbols_list = '\n'.join([f"• {s}" for s in monitored_symbols])
        await update.message.reply_text(
            f"📊 **Ativos Monitorados** ({len(monitored_symbols)}):\n\n"
            f"{symbols_list}\n\n"
            "**Comandos:**\n"
            "/ativos add BTC/USDT - Adicionar ativo\n"
            "/ativos remove SOL/USDT - Remover ativo\n"
            "/ativos clear - Limpar lista\n"
            f"/ativos preset top5 - {top5_label}\n"
            f"/ativos preset top10 - {top10_label}\n"
            "/ativos preset ouro - Ouro (PAXG proxy)\n"
            "/ativos preset forex - XAU/USD, AUD/JPY, HK50\n"
            "/ativos preset fundscap - XAU/USD, US500\n"
            "/ativos preset all - Todos disponíveis",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'add' and len(context.args) > 1:
        symbol = context.args[1].upper()
        if symbol not in monitored_symbols:
            monitored_symbols.append(symbol)
            await update.message.reply_text(f"✅ {symbol} adicionado! Total: {len(monitored_symbols)}")
        else:
            await update.message.reply_text(f"⚠️ {symbol} já está na lista")
    
    elif action == 'remove' and len(context.args) > 1:
        symbol = context.args[1].upper()
        if symbol in monitored_symbols:
            monitored_symbols.remove(symbol)
            await update.message.reply_text(f"✅ {symbol} removido! Restam: {len(monitored_symbols)}")
        else:
            await update.message.reply_text(f"⚠️ {symbol} não está na lista")
    
    elif action == 'clear':
        monitored_symbols.clear()
        await update.message.reply_text("✅ Lista limpa! Use /ativos add para adicionar")
    
    elif action == 'preset' and len(context.args) > 1:
        preset = ''.join(context.args[1:]).lower()
        if preset == 'top5':
            monitored_symbols.clear()
            monitored_symbols.extend(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT'])
            await update.message.reply_text("✅ Preset Top 5 ativado!\n📊 Monitorando: BTC, ETH, SOL, BNB, XRP")
        elif preset == 'top10':
            monitored_symbols.clear()
            monitored_symbols.extend([
                'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
                'ADA/USDT', 'DOGE/USDT', 'LINK/USDT', 'AVAX/USDT', 'LTC/USDT'
            ])
            await update.message.reply_text(
                "✅ Preset Top 10 ativado!\n"
                "📊 Monitorando: BTC, ETH, SOL, BNB, XRP, ADA, DOGE, LINK, AVAX, LTC"
            )
        elif preset == 'ouro':
            monitored_symbols.clear()
            monitored_symbols.extend(['PAXG/USDT'])
            await update.message.reply_text(
                "✅ Preset OURO ativado!\n"
                "📊 Monitorando: PAXG/USDT (proxy XAUUSD)"
            )
        elif preset == 'forex':
            monitored_symbols.clear()
            monitored_symbols.extend(['XAU/USD', 'AUD/JPY', 'HK50'])
            await update.message.reply_text(
                "✅ Preset FOREX ativado!\n"
                "📊 Monitorando: XAU/USD, AUD/JPY, HK50\n"
                "ℹ️ XAU/USD e AUD/JPY usam proxy de mercado quando necessário; HK50 requer fonte MT5/TradingView."
            )
        elif preset == 'fundscap':
            monitored_symbols.clear()
            monitored_symbols.extend(['XAU/USD', 'US500'])
            await update.message.reply_text(
                "✅ Preset FUNDSCAP ativado!\n"
                "📊 Monitorando: XAU/USD, US500\n"
                "ℹ️ XAU/USD usa proxy quando necessário; US500 depende de feed MT5/Fundscap ou TradingView."
            )
        elif preset == 'all':
            monitored_symbols.clear()
            monitored_symbols.extend(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'LTC/USDT'])
            await update.message.reply_text("✅ Preset completo ativado!\n📊 Monitorando todos os 7 ativos disponíveis")
        else:
            await update.message.reply_text("❌ Presets: top5, top10, ouro, forex, fundscap ou all")
    else:
        await update.message.reply_text("❌ Use: /ativos [add|remove|clear|preset] [SYMBOL]")


async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /monitor — controla o scanner automático (novo engine TradingView)."""
    global _auto_scan_active

    arg = (context.args[0].lower() if context.args else '').strip()

    # ── STATUS ────────────────────────────────────────────────────────────
    if not arg:
        status_icon = '🟢 ATIVO' if _auto_scan_active else '🔴 INATIVO'
        cooldown_info = ''
        if _auto_scan_active and _scan_last_signal_ts:
            elapsed = int(time.time() - _scan_last_signal_ts)
            remaining_cd = max(0, _SCAN_SIGNAL_INTERVAL - elapsed)
            if remaining_cd > 0:
                cooldown_info = f'\n⏳ Próximo sinal em: ~{remaining_cd // 60}m {remaining_cd % 60}s'
        pending_info = ''
        if _scan_pending_signal:
            p = _scan_pending_signal
            remaining_exp = max(0, int(p['expiry_ts'] - time.time()))
            pending_info = f"\n📌 Sinal pendente: {p['asset']} {p['direction']} — expira em {remaining_exp}s"

        assets_crypto = [a for a in TV_TICKER_MAP if a.upper() not in EXTERNAL_FOREX]
        assets_forex  = [a for a in TV_TICKER_MAP if a.upper() in EXTERNAL_FOREX]
        forex_session_ok, forex_label = _is_forex_session_active()
        forex_status = f'✅ {forex_label}' if forex_session_ok else f'🔒 Bloqueado ({forex_label})'

        await _reply_text(
            update,
            f"📡 *Scanner automático: {status_icon}*{cooldown_info}{pending_info}\n\n"
            f"🔬 *Engine:* TradingView API (5m + 15m)\n"
            f"📊 *Critérios:* 9 pontos — EMA, RSI, Dow, Fibo, ADX, PA, S/R, Day range\n"
            f"🚦 *FORTE:* ≥ 6/9 critérios em 5m, confirmado em 15m\n"
            f"🛡 *ADX gate:* crypto ≥ 20 | forex ≥ 25\n\n"
            f"💹 *Crypto ({len(assets_crypto)}):* {', '.join(assets_crypto)}\n"
            f"💱 *Forex ({len(assets_forex)}):* {', '.join(assets_forex[:6])}...\n"
            f"🌐 *Sessão forex:* {forex_status}\n\n"
            f"⏱ *Varredura:* a cada 5 min | Cooldown: {_SCAN_SIGNAL_INTERVAL // 60} min entre sinais\n"
            f"🔄 *Pré-análise P1:* ativa (4 min após entrada)\n\n"
            "Comandos: `/monitor on` | `/monitor off`"
        )
        return

    # ── LIGAR ─────────────────────────────────────────────────────────────
    if arg in ('on', 'ativar', 'ligar', '1'):
        _auto_scan_active = True
        assets_crypto = [a for a in TV_TICKER_MAP if a.upper() not in EXTERNAL_FOREX]
        assets_forex  = [a for a in TV_TICKER_MAP if a.upper() in EXTERNAL_FOREX]
        forex_session_ok, forex_label = _is_forex_session_active()
        forex_status = f'✅ {forex_label}' if forex_session_ok else f'🔒 Fora de sessão ({forex_label})'
        interval_min = _SCAN_SIGNAL_INTERVAL // 60
        await _reply_text(
            update,
            "✅ *Scanner ATIVADO*\n\n"
            f"🔬 Engine: TradingView — 5m + 15m confirmação\n"
            f"📊 9 critérios: EMA9/20, RSI, S/R, Dow, Fibo, Day range, ADX, Price Action\n"
            f"🚦 Sinal enviado apenas se FORTE (≥ 6/9) em 5m + confirmação 15m\n"
            f"🛡 ADX gate: crypto ≥ 20 | forex ≥ 25\n"
            f"🔄 Pré-análise P1: sim (4 min após entrada)\n\n"
            f"💹 Crypto ({len(assets_crypto)} ativos) — sempre ativo\n"
            f"💱 Forex ({len(assets_forex)} ativos) — {forex_status}\n\n"
            f"⏱ Varredura: cada 5 min | Cooldown: {interval_min} min entre sinais\n\n"
            "_O bot avisará automaticamente quando encontrar sinal qualificado._"
        )

    # ── DESLIGAR ──────────────────────────────────────────────────────────
    elif arg in ('off', 'desativar', 'desligar', '0'):
        _auto_scan_active = False
        await _reply_text(update, "⏹ *Scanner DESATIVADO.*\nUse `/monitor on` para reativar.")

    else:
        await _reply_text(update, "❌ Use: `/monitor on` | `/monitor off` | `/monitor` (status)")


def _signal_quality_consensus(signal_data: dict, signal: int) -> int:
    """Conta quantos indicadores direcionais concordam com o sinal."""
    directional_scores = [
        float(signal_data.get('rsi_score', 0.0)),
        float(signal_data.get('macd_score', 0.0)),
        float(signal_data.get('ema_score', 0.0)),
        float(signal_data.get('bollinger_score', 0.0)),
    ]
    if signal == 1:
        return sum(1 for s in directional_scores if s > 0)
    if signal == -1:
        return sum(1 for s in directional_scores if s < 0)
    return 0


async def pocket_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adiciona sinal manualmente ou de mensagem encaminhada."""
    try:
        if not context.args:
            await update.message.reply_text(
                "📝 Como usar:\n\n"
                "/pocket_add EUR/USD CALL 5m\n"
                "/pocket_add 🟢 GBPUSD BUY M5 - Alta confiança\n\n"
                "Ou encaminhe uma mensagem de sinal de outro canal/bot."
            )
            return
        
        # Juntar todos os args em uma mensagem
        message_text = ' '.join(context.args)
        
        # Tentar parsear
        signal = signal_parser.parse(message_text, source='manual')
        
        if signal:
            await update.message.reply_text(
                f"✅ Sinal registrado!\n\n"
                f"📊 {signal.asset} {signal.signal} {signal.timeframe}\n"
                f"⏰ {signal.timestamp.strftime('%H:%M:%S')}\n"
                + (f"🎯 Confiança: {signal.confidence}" if signal.confidence else "")
            )
        else:
            await update.message.reply_text(
                "❌ Não consegui identificar o sinal.\n\n"
                "Formato esperado:\n"
                "EUR/USD CALL 5m\n"
                "ou\n"
                "🟢 GBPUSD BUY M5"
            )
    
    except Exception as e:
        logger.error(f"Erro /pocket_add: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def pocket_recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra sinais recentes capturados."""
    try:
        minutes = 60  # padrão 1 hora
        
        if context.args and context.args[0].isdigit():
            minutes = int(context.args[0])
        
        recent_signals = signal_parser.get_recent_signals(minutes=minutes)
        
        if not recent_signals:
            await update.message.reply_text(
                f"📭 Nenhum sinal registrado nos últimos {minutes} minutos.\n\n"
                "Use /pocket_add para adicionar sinais manualmente ou "
                "encaminhe mensagens de canais de sinais."
            )
            return
        
        msg = f"📊 Sinais recentes ({len(recent_signals)} nos últimos {minutes}min):\n\n"
        
        for signal in recent_signals[-10:]:  # últimos 10
            emoji = '🟢' if signal.signal == 'CALL' else '🔴'
            confidence_str = f" ({signal.confidence})" if signal.confidence else ""
            msg += (
                f"{emoji} {signal.asset} {signal.signal} {signal.timeframe}{confidence_str}\n"
                f"   ⏰ {signal.timestamp.strftime('%H:%M')} | Fonte: {signal.source}\n\n"
            )
        
        await update.message.reply_text(msg)
    
    except Exception as e:
        logger.error(f"Erro /pocket_recent: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


async def pocket_compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compara sinal externo com estratégias validadas."""
    try:
        if not context.args:
            await update.message.reply_text(
                "🔍 Como usar:\n\n"
                "/pocket_compare EUR/USD\n"
                "/pocket_compare AUD/CAD OTC\n\n"
                "Busca sinais recentes do ativo e compara com backtests."
            )
            return
        
        asset = ' '.join(context.args).upper()
        
        # Buscar sinais recentes desse ativo
        recent_signals = signal_parser.get_signals_by_asset(asset, minutes=30)
        
        if not recent_signals:
            await update.message.reply_text(
                f"📭 Nenhum sinal recente para {asset}.\n\n"
                "Use /pocket_add para adicionar sinais primeiro."
            )
            return
        
        latest_signal = recent_signals[-1]
        
        msg = (
            f"🔍 COMPARAÇÃO DE SINAL - {asset}\n\n"
            f"📥 **Sinal Externo** ({latest_signal.source}):\n"
            f"   {latest_signal.signal} {latest_signal.timeframe}\n"
            f"   ⏰ Recebido: {latest_signal.timestamp.strftime('%H:%M:%S')}\n"
        )
        
        if latest_signal.confidence:
            msg += f"   🎯 Confiança: {latest_signal.confidence}\n"
        
        msg += "\n📊 **Estratégias Validadas**:\n\n"
        
        # Testar com estratégias principais
        strategies = ['ema_adx_ao_trend_filter', 'macd_profitunity', 'fidelity_envelopes_sma']
        
        # Simular análise rápida (se possível)
        msg += (
            "⚠️ Análise completa requer:\n"
            "1. Dados históricos atualizados\n"
            "2. Backtest com /otcbacktest\n"
            "3. Validação de ADX e sessão\n\n"
            f"💡 **Recomendação**: Use estratégia `ema_adx_ao_trend_filter` "
            f"(melhor win rate no histórico)\n\n"
            f"Rode: /otcbacktest {asset}|{latest_signal.timeframe}|ema_adx_ao_trend_filter"
        )
        
        await update.message.reply_text(msg)
    
    except Exception as e:
        logger.error(f"Erro /pocket_compare: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erro: {str(e)}")


def _normalize_external_direction(raw_direction: str) -> str | None:
    direction = (raw_direction or '').strip().lower()
    mapping = {
        'buy': 'BUY',
        'call': 'BUY',
        'compra': 'BUY',
        'sell': 'SELL',
        'put': 'SELL',
        'venda': 'SELL',
    }
    return mapping.get(direction)


def _external_asset_group(asset: str) -> str:
    if asset in EXTERNAL_US_STOCKS:
        return 'Acao EUA'
    if asset in EXTERNAL_COMMODITIES:
        return 'Commodity'
    if asset in EXTERNAL_FOREX:
        return 'Forex'
    return 'Ativo externo'


# ═══════════════════════════════════════════════════════════════════════════════
# SISTEMA DE TIERS DE LIQUIDEZ CRIPTO (ATLAS v1.1 - Jun 2026)
# ═══════════════════════════════════════════════════════════════════════════════
# Resolve problema de dojis em horários de baixa liquidez em alts (ADA, LTC, DOGE).
# 
# TIER 1 (Major - BTC/ETH):
#   - Liquidez profunda 24/7, opera qualquer horário
#   - Score ≥ 55%, ADX ≥ 24
#
# TIER 2 (Large Caps - SOL/XRP/BNB):
#   - Liquidez condicional, requer sessão ativa (Londres 7-16h ou NY 12-21h UTC)
#   - Bloqueado em finais de semana
#   - Score ≥ 55%, ADX ≥ 26
#
# TIER 3 (Alt Coins - ADA/DOGE/LTC/LINK):
#   - Alta volatilidade, APENAS overlap Londres+NY (12-16h UTC)
#   - Bloqueio TOTAL em finais de semana e madrugada asiática
#   - Score ≥ 60%, ADX ≥ 30
# ═══════════════════════════════════════════════════════════════════════════════

CRYPTO_TIER1_SYMBOLS = {'BTC', 'ETH'}  # Major - 24/7
CRYPTO_TIER2_SYMBOLS = {'SOL', 'XRP', 'BNB'}  # Large Caps - Sessão ativa
CRYPTO_TIER3_SYMBOLS = {'ADA', 'DOGE', 'LTC', 'LINK', 'DOT', 'MATIC'}  # Alts - Overlap apenas

CRYPTO_ALIAS_MAP = {
    'BITCOIN': 'BTC',
    'ETHEREUM': 'ETH',
    'DOGECOIN': 'DOGE',
    'LITECOIN': 'LTC',
    'CARDANO': 'ADA',
    'SOLANA': 'SOL',
    'RIPPLE': 'XRP',
    'BINANCECOIN': 'BNB',
    'POLKADOT': 'DOT',
    'POLYGON': 'MATIC',
    'CHAINLINK': 'LINK',
}


def _normalize_crypto_symbol(asset: str) -> str:
    """Normaliza símbolo cripto para base (ex: BTC/USDT → BTC)."""
    raw = (asset or '').strip().upper().replace('-', '/').replace(' ', '')
    if '/' in raw:
        raw = raw.split('/', 1)[0]
    return CRYPTO_ALIAS_MAP.get(raw, raw)


def _get_crypto_signal_profile(asset: str) -> dict:
    """Retorna perfil de sinal baseado no tier de liquidez do ativo."""
    symbol = _normalize_crypto_symbol(asset)
    
    # TIER 1: BTC/ETH - Majors com liquidez 24/7
    if symbol in CRYPTO_TIER1_SYMBOLS:
        return {
            'tier': 1,
            'tier_name': 'Major',
            'min_score': 0.55,           # Score 55%
            'min_adx': 24.0,
            'buy_rsi_block': 70.0,
            'sell_rsi_block': 30.0,
            'require_mtf_for_all': False,
            'min_score_without_mtf': 5,
            'liquidity_check': False,    # Opera 24/7
        }
    
    # TIER 2: SOL/XRP/BNB - Large Caps com liquidez condicional
    elif symbol in CRYPTO_TIER2_SYMBOLS:
        return {
            'tier': 2,
            'tier_name': 'Large Cap',
            'min_score': 0.55,           # Score 55%
            'min_adx': 26.0,             # ADX mais alto que Tier 1
            'buy_rsi_block': 68.0,
            'sell_rsi_block': 32.0,
            'require_mtf_for_all': False,
            'min_score_without_mtf': 5,
            'liquidity_check': True,     # Requer sessão ativa
            'min_session_level': 'any',  # Londres OU NY (não precisa overlap)
        }
    
    # TIER 3: ADA/DOGE/LTC - Alts com alta volatilidade
    elif symbol in CRYPTO_TIER3_SYMBOLS:
        return {
            'tier': 3,
            'tier_name': 'Alt Coin',
            'min_score': 0.60,           # Score 60% (mais rigoroso)
            'min_adx': 30.0,             # ADX 30+ (tendência forte obrigatória)
            'buy_rsi_block': 64.0,
            'sell_rsi_block': 36.0,
            'require_mtf_for_all': True, # Confirmação MTF obrigatória
            'min_score_without_mtf': 7,  # Pontuação alta sem MTF
            'liquidity_check': True,     # Requer sessão ativa
            'min_session_level': 'overlap',  # APENAS overlap Londres+NY (12-16h UTC)
        }
    
    # Default: trata como Tier 3 (mais conservador)
    else:
        return {
            'tier': 3,
            'tier_name': 'Desconhecido',
            'min_score': 0.60,
            'min_adx': 30.0,
            'buy_rsi_block': 64.0,
            'sell_rsi_block': 36.0,
            'require_mtf_for_all': True,
            'min_score_without_mtf': 7,
            'liquidity_check': True,
            'min_session_level': 'overlap',
        }


def _check_crypto_liquidity_session(asset: str) -> tuple[bool, str]:
    """
    Valida se o ativo cripto pode operar no horário atual baseado no tier de liquidez.
    
    Retorna:
        (pode_operar: bool, motivo: str)
        
    Regras:
        - TIER 1 (BTC/ETH): Opera 24/7 (sempre retorna True)
        - TIER 2 (SOL/XRP/BNB): Requer sessão Londres OU NY, bloqueia finais de semana
        - TIER 3 (ADA/DOGE/LTC): APENAS overlap Londres+NY (12-16h UTC), bloqueia finais de semana
    """
    from datetime import timezone
    
    profile = _get_crypto_signal_profile(asset)
    
    # TIER 1: sem restrição de horário
    if not profile.get('liquidity_check', False):
        return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Opera 24/7"
    
    utc = datetime.now(timezone.utc)
    weekday = utc.weekday()  # 0=Segunda, 6=Domingo
    h = utc.hour + utc.minute / 60
    
    # Bloqueio de finais de semana para TIER 2 e TIER 3
    # Sábado (5) e Domingo (6)
    if weekday >= 5:
        return (
            False,
            f"❌ Tier {profile['tier']} ({profile['tier_name']}) bloqueado em finais de semana "
            f"(atual: {'Sábado' if weekday == 5 else 'Domingo'} {utc.hour:02d}:{utc.minute:02d} UTC). "
            f"Alts geram muitos dojis sem liquidez."
        )
    
    # Sessões
    london_session = 7.0 <= h < 16.0
    ny_session = 12.0 <= h < 21.0
    overlap_session = 12.0 <= h < 16.0
    
    min_session = profile.get('min_session_level', 'any')
    
    # TIER 2: aceita qualquer sessão ativa (Londres OU NY)
    if min_session == 'any':
        if london_session or ny_session:
            session_label = 'Overlap Londres+NY' if overlap_session else ('Londres' if london_session else 'Nova York')
            return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Sessão ativa: {session_label}"
        else:
            return (
                False,
                f"❌ Tier {profile['tier']} ({profile['tier_name']}) requer sessão ativa. "
                f"Atual: {utc.hour:02d}:{utc.minute:02d} UTC (Asiática/Fechado). "
                f"Opere entre 07-16h UTC (Londres) ou 12-21h UTC (NY)."
            )
    
    # TIER 3: APENAS overlap Londres+NY (12-16h UTC)
    elif min_session == 'overlap':
        if overlap_session:
            return True, f"Tier {profile['tier']} ({profile['tier_name']}) - Overlap Londres+NY (melhor liquidez)"
        else:
            session_now = 'Londres' if london_session else ('Nova York' if ny_session else 'Asiática/Fechado')
            return (
                False,
                f"❌ Tier {profile['tier']} ({profile['tier_name']}) requer OVERLAP Londres+NY (12-16h UTC). "
                f"Atual: {utc.hour:02d}:{utc.minute:02d} UTC ({session_now}). "
                f"Alts de baixa liquidez geram dojis fora do overlap."
            )
    
    # Fallback: bloqueia se não conhece a regra
    return False, f"⚠️ Tier {profile['tier']} - Configuração de sessão desconhecida: {min_session}"


def _is_forex_session_active() -> tuple:
    """Retorna (ativo: bool, label: str) indicando se há sessão forex líquida aberta.
    Sessões consideradas (UTC):
      Londres : 07:00 – 16:00
      Nova York: 12:00 – 21:00
    Overlap London+NY (12:00-16:00) = melhor momento.
    Asiática (21:00 – 07:00) = evitar para binários de 5 min.
    """
    from datetime import timezone
    utc = datetime.now(timezone.utc)
    # Forex spot fica fechado no fim de semana; evita alertas falsos em sábado/domingo.
    if utc.weekday() >= 5:
        return False, f'Mercado fechado (fim de semana {utc.hour:02d}:{utc.minute:02d} UTC)'

    h = utc.hour + utc.minute / 60
    london   = 7.0 <= h < 16.0
    new_york = 12.0 <= h < 21.0
    if london and new_york:
        return True, 'London+NY overlap'
    if london:
        return True, 'Londres'
    if new_york:
        return True, 'Nova York'
    return False, f'Sessão asiática/fechado ({utc.hour:02d}:{utc.minute:02d} UTC)'


_TV_INTERVAL_MAP = {
    '1m': '1', '3m': '3', '5m': '5', '10m': '10', '15m': '15',
    '30m': '30', '45m': '45', '1h': '60', '2h': '120', '4h': '240',
    '1d': '', 'D': '', 'diario': '',
}

def _get_tv_analysis(asset: str, timeframe: str = '5m') -> dict:
    """Busca dados técnicos do ativo via scanner público do TradingView (sem API key).
    timeframe: '1m','5m','15m','1h','4h','1d' — padrão 5m
    """
    entry = TV_TICKER_MAP.get(asset.upper())
    if not entry:
        return {}
    screener, tv_ticker = entry
    url = f'https://scanner.tradingview.com/{screener}/scan'

    interval = _TV_INTERVAL_MAP.get(timeframe, '5')
    suffix = ('|' + interval) if interval else ''

    # Colunas com timeframe dinâmico (OHLC + indicadores + estrutura macro)
    tf_cols_base = ['RSI', 'EMA9', 'EMA20', 'EMA50', 'EMA200', 'close', 'open', 'high', 'low', 'ADX']
    tf_cols = [c + suffix for c in tf_cols_base]
    # Colunas fixas: pivôs mensais + máx/mín diário e semanal (para Fibonacci e contexto de sessão)
    fixed_cols = [
        'Pivot.M.Classic.R1', 'Pivot.M.Classic.S1',
        'Pivot.M.Classic.R2', 'Pivot.M.Classic.S2',
        'high|1D', 'low|1D',
        'high|1W', 'low|1W',
    ]
    all_cols = tf_cols + fixed_cols
    try:
        resp = requests.post(url, json={
            'symbols': {'tickers': [tv_ticker], 'query': {'types': []}},
            'columns': all_cols,
        }, timeout=8)
        resp.raise_for_status()
        data = resp.json().get('data', [])
        if not data:
            return {}
        raw = dict(zip(all_cols, data[0]['d']))
        result = {}
        for base, col in zip(tf_cols_base, tf_cols):
            result[base] = raw.get(col)
        for col in fixed_cols:
            result[col] = raw.get(col)
        result['_timeframe'] = timeframe
        return result
    except Exception as _tv_err:
        import logging as _log
        _log.getLogger(__name__).warning('_get_tv_analysis(%s,%s) falhou: %s', asset, timeframe, _tv_err)
        return {}


def _assess_signal_quality(analysis: dict, direction: str, asset_type: str = 'crypto', skip_adx_gate: bool = False):
    """
    Avalia qualidade do sinal com 9 critérios profissionais.
    asset_type: 'forex' | 'crypto' | 'stock' | 'commodity'

    Regras de bloqueio (retorno imediato como FRACO):
      - ADX < 20 (crypto/stock/commodity) ou < 25 (forex): mercado lateral.

    Critérios com pesos:
      1. EMA9   — tendência curta   (+1 somente se separação ≥ 0.05% do preço)
      2. EMA20  — tendência média   (+1 somente se separação ≥ 0.05% do preço)
      3. RSI    — espaço para mover
      4. S/R    — nível pivot próximo
      5. Dow    — estrutura macro (EMA50/200) — também veta Fibonacci contra-tendência
      6. Fibo   — retração semanal, SÓ conta se Dow confirma mesma direção
      7. Dia    — posição no range diário
      8. ADX    — força da tendência (≥25 conta, ≥30 conta com bonus implícito)
      9. PA     — price action do candle atual

    Thresholds:
      FORTE TOTAL (7+/9) | FORTE (6/9) | MODERADO (4-5/9) | FRACO (<4/9)
    """
    score = 0
    lines = []

    close  = analysis.get('close')
    open_  = analysis.get('open')
    high   = analysis.get('high')
    low    = analysis.get('low')
    ema9   = analysis.get('EMA9')
    ema20  = analysis.get('EMA20')
    ema50  = analysis.get('EMA50')
    ema200 = analysis.get('EMA200')
    rsi    = analysis.get('RSI')
    adx    = analysis.get('ADX')
    r1 = analysis.get('Pivot.M.Classic.R1')
    s1 = analysis.get('Pivot.M.Classic.S1')
    r2 = analysis.get('Pivot.M.Classic.R2')
    s2 = analysis.get('Pivot.M.Classic.S2')
    day_high  = analysis.get('high|1D')
    day_low   = analysis.get('low|1D')
    week_high = analysis.get('high|1W')
    week_low  = analysis.get('low|1W')

    # ── GATE: ADX — mercado lateral = bloqueio total ────────────────────────
    # Forex precisa de ADX ≥ 25 (pares se movem menos e têm mais ruído de sessão).
    # Demais ativos: ADX ≥ 20.
    # skip_adx_gate=True: usado na análise avulsa p/ mostrar diagnóstico mesmo em lateral.
    adx_min = 25 if asset_type == 'forex' else 20
    if not skip_adx_gate and adx is not None and adx < adx_min:
        adx_label = 'forex' if asset_type == 'forex' else 'lateral'
        return (
            'FRACO ⚠️',
            [f'🚫 ADX {adx:.1f} < {adx_min} ({adx_label}) — mercado sem tendência: sinal bloqueado']
        )

    # ── Verificar se Dow confirma a direção (usado no critério 6/Fibo) ─────
    dow_confirmed = False
    if close is not None and ema50 is not None and ema200 is not None and ema50 > 0 and ema200 > 0:
        if direction == 'BUY':
            dow_confirmed = close > ema50 > ema200
        else:
            dow_confirmed = close < ema50 < ema200

    # ── 1: EMA9 (tendência curta) — exige separação mínima de 0.05% ───────
    if close is not None and ema9 is not None and close > 0:
        sep_pct = abs(close - ema9) / close * 100
        if sep_pct < 0.05:
            lines.append(f'➖ EMA9: colada ao preco ({ema9:.4g}, sep {sep_pct:.3f}%) — sem pressao direcional')
        elif direction == 'BUY':
            if close > ema9:
                score += 1
                lines.append(f'✅ EMA9: preco {sep_pct:.2f}% acima ({ema9:.4g}) — pressao compradora curta')
            else:
                lines.append(f'⚠️ EMA9: preco abaixo ({ema9:.4g}) — contra tendencia curta')
        else:
            if close < ema9:
                score += 1
                lines.append(f'✅ EMA9: preco {sep_pct:.2f}% abaixo ({ema9:.4g}) — pressao vendedora curta')
            else:
                lines.append(f'⚠️ EMA9: preco acima ({ema9:.4g}) — contra tendencia curta')

    # ── 2: EMA20 (tendência média) — exige separação mínima de 0.05% ──────
    if close is not None and ema20 is not None and ema20 > 0 and close > 0:
        sep_pct = abs(close - ema20) / close * 100
        if sep_pct < 0.05:
            lines.append(f'➖ EMA20: colada ao preco ({ema20:.4g}, sep {sep_pct:.3f}%) — sem confirmacao media')
        elif direction == 'BUY':
            if close > ema20:
                score += 1
                lines.append(f'✅ EMA20: preco {sep_pct:.2f}% acima ({ema20:.4g}) — tendencia media de alta')
            else:
                lines.append(f'⚠️ EMA20: preco abaixo ({ema20:.4g}) — contra tendencia media')
        else:
            if close < ema20:
                score += 1
                lines.append(f'✅ EMA20: preco {sep_pct:.2f}% abaixo ({ema20:.4g}) — tendencia media de baixa')
            else:
                lines.append(f'⚠️ EMA20: preco acima ({ema20:.4g}) — contra tendencia media')

    # ── 3: RSI — espaço para mover ─────────────────────────────────────────
    # Forex: exige leituras mais extremas (BUY ≤ 45, SELL ≥ 55) pois
    # RSI 50-55 em forex num 5m é puro ruído de sessão.
    rsi_buy_max  = 45 if asset_type == 'forex' else 50
    rsi_sell_min = 55 if asset_type == 'forex' else 50
    if rsi is not None:
        if direction == 'BUY':
            if rsi > 68:
                score -= 1
                lines.append(f'🚫 RSI {rsi:.0f} — sobrecomprado, risco de reversao')
            elif rsi <= rsi_buy_max:
                score += 1
                lines.append(f'✅ RSI {rsi:.0f} — espaco para subir (≤{rsi_buy_max})')
            elif rsi <= 58:
                lines.append(f'➖ RSI {rsi:.0f} — espaco moderado')
            else:
                lines.append(f'⚠️ RSI {rsi:.0f} — espaco limitado')
        else:
            if rsi < 32:
                score -= 1
                lines.append(f'🚫 RSI {rsi:.0f} — sobrevendido, risco de reversao')
            elif rsi >= rsi_sell_min:
                score += 1
                lines.append(f'✅ RSI {rsi:.0f} — espaco para cair (≥{rsi_sell_min})')
            elif rsi >= 42:
                lines.append(f'➖ RSI {rsi:.0f} — espaco moderado')
            else:
                lines.append(f'⚠️ RSI {rsi:.0f} — espaco limitado')

    # ── 4: Nível S/R pivot mais próximo ────────────────────────────────────
    if close is not None and all(v is not None for v in [r1, s1]):
        levels = [(abs(close - r1), 'R1', r1), (abs(close - s1), 'S1', s1)]
        if r2 is not None:
            levels.append((abs(close - r2), 'R2', r2))
        if s2 is not None:
            levels.append((abs(close - s2), 'S2', s2))
        levels.sort()
        nearest_dist, nearest_name, nearest_val = levels[0]
        dist_pct = nearest_dist / close * 100
        if dist_pct <= 0.5:
            score += 1
            lines.append(f'✅ S/R: {nearest_name} em {nearest_val:.4g} ({dist_pct:.1f}% — alta relevancia)')
        elif dist_pct <= 1.5:
            lines.append(f'➖ S/R: {nearest_name} em {nearest_val:.4g} ({dist_pct:.1f}% de distancia)')
        else:
            lines.append(f'➖ S/R: sem nivel pivot proximo (S1={s1:.4g} | R1={r1:.4g})')

    # ── 5: Teoria de Dow — estrutura macro (EMA50 / EMA200) ───────────────
    if close is not None and ema50 is not None and ema200 is not None and ema50 > 0 and ema200 > 0:
        if direction == 'BUY':
            if dow_confirmed:
                score += 1
                lines.append(f'✅ Dow: HH/HL — preco > EMA50 ({ema50:.4g}) > EMA200 ({ema200:.4g})')
            elif close > ema50 and ema50 < ema200:
                lines.append(f'⚠️ Dow: EMA50 < EMA200 — macro bearish, compra contratendencia')
            else:
                lines.append(f'⚠️ Dow: preco < EMA50 ({ema50:.4g}) — sem confirmacao macro de alta')
        else:
            if dow_confirmed:
                score += 1
                lines.append(f'✅ Dow: LH/LL — preco < EMA50 ({ema50:.4g}) < EMA200 ({ema200:.4g})')
            elif close < ema50 and ema50 > ema200:
                lines.append(f'⚠️ Dow: EMA50 > EMA200 — macro bullish, venda contratendencia')
            else:
                lines.append(f'⚠️ Dow: preco > EMA50 ({ema50:.4g}) — sem confirmacao macro de baixa')

    # ── 6: Fibonacci (swing semanal) — SÓ conta se Dow confirma ───────────
    # Fibonacci sozinho produz sinal simétrico (50% = suporte E resistência).
    # Só pontua se a estrutura macro (Dow) confirma a mesma direção.
    if close is not None and week_high is not None and week_low is not None and week_high > week_low:
        sw_range = week_high - week_low
        fib_levels = {
            '23.6%': week_high - 0.236 * sw_range,
            '38.2%': week_high - 0.382 * sw_range,
            '50.0%': week_high - 0.500 * sw_range,
            '61.8%': week_high - 0.618 * sw_range,
            '78.6%': week_high - 0.786 * sw_range,
        }
        nearest_fib = min(fib_levels.items(), key=lambda x: abs(close - x[1]))
        fib_name, fib_val = nearest_fib
        dist_pct = abs(close - fib_val) / close * 100
        key_fibs = ('38.2%', '50.0%', '61.8%')
        if dist_pct <= 0.5 and fib_name in key_fibs:
            if dow_confirmed:
                score += 1
                action_fib = 'suporte — oportunidade de compra' if direction == 'BUY' else 'resistencia — oportunidade de venda'
                lines.append(f'✅ Fibo: {fib_name} ({fib_val:.4g}) + Dow alinhado — {action_fib}')
            else:
                lines.append(f'➖ Fibo: {fib_name} ({fib_val:.4g}) mas Dow contra-tendencia — sem pontuacao')
        elif dist_pct <= 1.2:
            lines.append(f'➖ Fibo: proximo ao {fib_name} ({fib_val:.4g}, {dist_pct:.1f}% dist) — fora da zona')
        else:
            lines.append(f'➖ Fibo: sem nivel relevante proximo (range: {week_low:.4g}–{week_high:.4g})')

    # ── 7: Pullback — rejeição da EMA20 (suporte/resistência dinâmico) ─────
    # Setup mais clássico de opções binárias: impulso → pullback à EMA20 → rejeição.
    # BUY : mínima do candle tocou EMA20 (±0.3%) e fechou acima → rejeição bullish.
    # SELL: máxima do candle tocou EMA20 (±0.3%) e fechou abaixo → rejeição bearish.
    if all(v is not None for v in [close, low, high, ema20]) and ema20 > 0:
        tolerance = 0.003  # 0.3% para considerar "toque" na EMA20
        if direction == 'BUY':
            touched = low <= ema20 * (1 + tolerance)
            closed_above = close > ema20
            dist_pct = (close - ema20) / close * 100
            if touched and closed_above:
                score += 1
                lines.append(f'✅ Pullback: rejeicao bullish da EMA20 ({ema20:.4g}) — entrada classica confirmada')
            elif closed_above and dist_pct < 0.5:
                lines.append(f'➖ Pullback: preco proximo da EMA20 ({ema20:.4g}, {dist_pct:.2f}%) — sem toque confirmado')
            elif not closed_above:
                lines.append(f'⚠️ Pullback: preco abaixo da EMA20 ({ema20:.4g}) — sem suporte dinamico para compra')
            else:
                lines.append(f'➖ Pullback: sem recuo a EMA20 (dist {dist_pct:.2f}%) — entrada agressiva')
        else:
            touched = high >= ema20 * (1 - tolerance)
            closed_below = close < ema20
            dist_pct = (ema20 - close) / close * 100
            if touched and closed_below:
                score += 1
                lines.append(f'✅ Pullback: rejeicao bearish da EMA20 ({ema20:.4g}) — entrada classica confirmada')
            elif closed_below and dist_pct < 0.5:
                lines.append(f'➖ Pullback: preco proximo da EMA20 ({ema20:.4g}, {dist_pct:.2f}%) — sem toque confirmado')
            elif not closed_below:
                lines.append(f'⚠️ Pullback: preco acima da EMA20 ({ema20:.4g}) — sem resistencia dinamica para venda')
            else:
                lines.append(f'➖ Pullback: sem recuo a EMA20 (dist {dist_pct:.2f}%) — entrada agressiva')

    # ── 8: ADX — força da tendência (acima do gate ≥ 20) ──────────────────
    if adx is not None:
        if adx >= 30:
            score += 1
            lines.append(f'✅ ADX {adx:.0f} — tendencia forte, movimento direcional solido')
        elif adx >= 25:
            lines.append(f'➖ ADX {adx:.0f} — tendencia emergindo, monitorar')
        else:
            lines.append(f'➖ ADX {adx:.0f} — tendencia incipiente (20-24), sinal condicionado')

    # ── 9: Price Action — padrão do candle atual ───────────────────────────
    if all(v is not None for v in [close, open_, high, low]) and high > low:
        candle_range = high - low
        body = abs(close - open_)
        body_pct       = body / candle_range
        upper_wick     = high - max(close, open_)
        lower_wick     = min(close, open_) - low
        upper_wick_pct = upper_wick / candle_range
        lower_wick_pct = lower_wick / candle_range

        if body_pct < 0.1:
            lines.append(f'⚠️ PA: Doji — indecisao, aguardar confirmacao')
        elif direction == 'BUY':
            if lower_wick_pct >= 0.55 and body_pct < 0.35:
                score += 1
                lines.append(f'✅ PA: Pin bar bullish (sombra inf {lower_wick_pct:.0%}) — rejeicao de precos baixos')
            elif close > open_ and body_pct >= 0.6:
                score += 1
                lines.append(f'✅ PA: Marubozu bullish (corpo {body_pct:.0%}) — pressao compradora dominante')
            elif upper_wick_pct >= 0.55:
                lines.append(f'⚠️ PA: Sombra superior ({upper_wick_pct:.0%}) — rejeicao da alta, cautela')
            else:
                lines.append(f'➖ PA: Candle misto (corpo {body_pct:.0%}) — sem padrao definido')
        else:
            if upper_wick_pct >= 0.55 and body_pct < 0.35:
                score += 1
                lines.append(f'✅ PA: Pin bar bearish (sombra sup {upper_wick_pct:.0%}) — rejeicao de precos altos')
            elif close < open_ and body_pct >= 0.6:
                score += 1
                lines.append(f'✅ PA: Marubozu bearish (corpo {body_pct:.0%}) — pressao vendedora dominante')
            elif lower_wick_pct >= 0.55:
                lines.append(f'⚠️ PA: Sombra inferior ({lower_wick_pct:.0%}) — rejeicao da queda, cautela')
            else:
                lines.append(f'➖ PA: Candle misto (corpo {body_pct:.0%}) — sem padrao definido')

    # ── Qualidade final ────────────────────────────────────────────────────
    # FORTE TOTAL (7+/9): confluencia maxima
    # FORTE     (6/9)  : confluencia solida — sinal valido
    # MODERADO  (4-5/9): confluencia parcial — somente alerta informativo
    # FRACO     (<4/9) : baixa confluencia — ignorado
    if score >= 7:
        quality = 'FORTE TOTAL 🎯🎯'
    elif score >= 6:
        quality = 'FORTE 🎯'
    elif score >= 4:
        quality = 'MODERADO ⚡'
    else:
        quality = 'FRACO ⚠️'

    return quality, lines


def _is_noise_scan_candidate(reasons: list[str], score: int, mtf_confirmed: bool) -> tuple[bool, list[str]]:
    """Bloqueia sinais com confluência fraca para reduzir alertas de baixa qualidade."""
    weak_flags = []

    if any('⚠️ RSI' in r and 'espaco limitado' in r for r in reasons):
        weak_flags.append('rsi_limitado')
    if any(r.startswith('➖ S/R: sem nivel pivot proximo') for r in reasons):
        weak_flags.append('sr_sem_pivo_proximo')
    if any(r.startswith('➖ Fibo:') and ('fora da zona' in r or 'sem nivel relevante' in r) for r in reasons):
        weak_flags.append('fibo_fraco')
    if any(r.startswith('⚠️ PA: Doji') or r.startswith('➖ PA: Candle misto') for r in reasons):
        weak_flags.append('pa_indeciso')

    structural_ok = any(r.startswith('✅ S/R:') or r.startswith('✅ Fibo:') for r in reasons)

    # Filtro principal: combinação de fraquezas técnicas no mesmo setup.
    if len(weak_flags) >= SCAN_STRICT_MAX_WEAK_FACTORS:
        return True, weak_flags

    # Filtro complementar: sinal no limiar mínimo sem estrutura de nível clara.
    if score <= 6 and not structural_ok and not mtf_confirmed:
        weak_flags.append('score_limiar_sem_estrutura')
        return True, weak_flags

    return False, weak_flags


async def externo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra e publica sinal externo com análise técnica via TradingView."""
    if not context.args or len(context.args) < 2:
        await _reply_text(
            update,
            "📝 Uso: /externo ATIVO DIRECAO [HH:MM] [obs...]\n"
            "Ex.: /externo NFLX SELL 13:40\n"
            "Ex.: /externo GOLD BUY confirmacao manual\n"
            "\n💡 Você faz a análise técnica, o bot registra o sinal."
        )
        return

    asset = context.args[0].strip().upper()
    direction = _normalize_external_direction(context.args[1])

    if asset not in EXTERNAL_ASSET_SET:
        top_stocks = ', '.join(EXTERNAL_US_STOCKS[:6])
        top_comms = ', '.join(EXTERNAL_COMMODITIES[:4])
        top_forex = 'GBP/JPY, EUR/USD, GBP/USD, USD/JPY, EUR/JPY, AUD/JPY'
        await _reply_text(
            update,
            "❌ Ativo externo nao permitido neste perfil.\n"
            f"Forex (exemplos): {top_forex}\n"
            f"Acoes EUA (exemplos): {top_stocks}\n"
            f"Commodities (exemplos): {top_comms}\n"
            "Dica: use /listar_externos para ver todos os ativos."
        )
        return

    if direction is None:
        await _reply_text(update, "❌ Direcao invalida. Use: BUY, CALL, COMPRA, SELL, PUT, VENDA")
        return

    # Extrai horário e timeframe se fornecidos
    signal_time = datetime.now().strftime('%H:%M')
    tf_arg = '5m'  # padrão
    details_start = 2
    remaining = list(context.args[2:])
    new_remaining = []
    for tok in remaining:
        if tok.lower() in _TV_INTERVAL_MAP:
            tf_arg = tok.lower()
        elif re.match(r'^\d{1,2}:\d{2}$', tok) and details_start == 2:
            signal_time = tok
            details_start = 3
        else:
            new_remaining.append(tok)

    # Observações do usuário
    notes = ' '.join(new_remaining).strip()
    group = _external_asset_group(asset)
    direction_label = 'COMPRA ↗' if direction == 'BUY' else 'VENDA ↘'
    direction_arrow = '🟢' if direction == 'BUY' else '🔴'

    # Análise técnica via TradingView scanner
    analysis = _get_tv_analysis(asset, timeframe=tf_arg)

    # Montar bloco técnico
    tech_block = ''
    if analysis:
        close = analysis.get('close')
        ema9 = analysis.get('EMA9')
        rsi = analysis.get('RSI')
        close_str = f'{close:.4g}' if close is not None else 'N/A'
        ema9_str = f'{ema9:.4g}' if ema9 is not None else 'N/A'

        ext_type = 'forex' if asset.upper() in EXTERNAL_FOREX else 'crypto'
        quality, reasons = _assess_signal_quality(analysis, direction, asset_type=ext_type)
        reasons_text = '\n'.join(f'  {r}' for r in reasons)
        rsi_str2 = f'{rsi:.0f}' if rsi is not None else 'N/A'

        tf_label = analysis.get('_timeframe', tf_arg)
        tech_block = (
            f'\n\n📊 *Contexto tecnico ({tf_label}):*\n'
            f'Preco: `{close_str}` | EMA9: `{ema9_str}` | RSI: `{rsi_str2}`\n'
            f'\n*Qualidade do sinal: {quality}*\n'
            f'{reasons_text}'
        )
    else:
        tech_block = '\n\n📊 _Analise tecnica indisponivel (TV offline)_'

    # Montar mensagem de sinal
    msg = (
        f"📢 *SINAL EXTERNO*\n\n"
        f"{direction_arrow} *{asset}* ({group})\n"
        f"Direcao: *{direction_label}*\n"
        f"Horario: *{signal_time}*"
        f"{tech_block}\n\n"
        f"_Registrado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
    )
    if notes:
        msg += f"\n💬 _{notes}_"

    target_chat_id = monitor_target_chat_id or get_telegram_chat_id() or (update.effective_chat.id if update.effective_chat else None)
    if target_chat_id is None:
        await _reply_text(update, "❌ Nao encontrei chat alvo para envio.")
        return

    await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode='Markdown')

    if update.effective_chat and str(update.effective_chat.id) != str(target_chat_id):
        await _reply_text(update, f"✅ Sinal externo registrado e enviado.")


async def listar_externos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista todos os ativos suportados para sinais externos."""
    stocks_grouped = [EXTERNAL_US_STOCKS[i:i+5] for i in range(0, len(EXTERNAL_US_STOCKS), 5)]
    comms_grouped = [EXTERNAL_COMMODITIES[i:i+5] for i in range(0, len(EXTERNAL_COMMODITIES), 5)]
    
    msg = "📋 *ATIVOS SUPORTADOS PARA SINAIS EXTERNOS*\n\n"
    
    msg += "🇺🇸 *ACOES USA:*\n"
    for group in stocks_grouped:
        msg += "  " + " • ".join(group) + "\n"
    
    msg += "\n🌾 *COMMODITIES:*\n"
    for group in comms_grouped:
        msg += "  " + " • ".join(group) + "\n"
    
    msg += "\n💡 *COMO USAR:*\n"
    msg += "`/externo ATIVO DIRECAO [HH:MM] [obs...]`\n\n"
    msg += "*Exemplos:*\n"
    msg += "• `/externo NFLX SELL 13:40` - Vender Netflix às 13:40\n"
    msg += "• `/externo OURO BUY` - Comprar Ouro agora\n"
    msg += "• `/externo AAPL COMPRA 14:00 confirmação 5m` - Comprar AAPL com nota\n"
    msg += "• `/externo PETROLEO VENDA` - Vender Petróleo\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')


async def pocket_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ajuda para comandos de sinais externos."""
    msg = (
        "🤖 COMANDOS DE SINAIS EXTERNOS\n\n"
        "Capture sinais de outros bots/canais e compare com suas estratégias validadas.\n\n"
        "📝 **/pocket_add [mensagem]**\n"
        "   Adiciona sinal manualmente ou analisa mensagem encaminhada\n"
        "   Exemplo: /pocket_add EUR/USD CALL 5m\n\n"
        "📊 **/pocket_recent [minutos]**\n"
        "   Lista sinais recentes (padrão 60min)\n"
        "   Exemplo: /pocket_recent 30\n\n"
        "🔍 **/pocket_compare [ativo]**\n"
        "   Compara sinal externo com estratégias validadas\n"
        "   Exemplo: /pocket_compare EUR/USD OTC\n\n"
        "💡 **Dica**: Encaminhe mensagens do bot da PocketOption diretamente "
        "para mim e usarei /pocket_add automaticamente!"
    )
    await update.message.reply_text(msg)


async def check_paper_trades(context: ContextTypes.DEFAULT_TYPE):
    """Job agendado: fecha paper trades que atingiram TP, SL ou timeout."""
    try:
        from src.core import bitget_executor as _bx
        if not _bx.is_paper_mode():
            return
        closed = _bx.update_open_paper_trades()
        if not closed:
            return
        chat_id = monitor_target_chat_id or get_telegram_chat_id()
        if not chat_id:
            return
        for t in closed:
            result_emoji = '✅' if t.get('result') == 'WIN' else '❌'
            pnl = t.get('pnl', 0) or 0
            pnl_str = f"+${pnl:.4f}" if pnl >= 0 else f"-${abs(pnl):.4f}"
            msg = (
                f"📋 *PAPER TRADE FECHADO*\n"
                f"{result_emoji} *{t['result']}* | {t['side']} {t['asset']}\n"
                f"Entry: `{t['price']:.4g}` → Exit: `{t.get('exit_price', 0):.4g}`\n"
                f"PnL: `{pnl_str}` | Motivo: `{t.get('close_reason','?')}`"
            )
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
    except Exception as e:
        logger.warning('[check_paper_trades] erro: %s', e)


async def auto_scan_externos(context: ContextTypes.DEFAULT_TYPE):
    """Job agendado: envia o MELHOR sinal disponível (1 por ciclo).
    Fluxo: detecta → envia sinal → aguarda expiração → reporta resultado (WIN/LOSS) → cooldown → repete.
    """
    global _auto_scan_active, _auto_scan_last_alerted, _scan_pending_signal, _scan_last_signal_ts
    if not _auto_scan_active:
        return

    chat_id = monitor_target_chat_id or get_telegram_chat_id()
    if not chat_id:
        return

    from src.core import bitget_executor as _bx
    try:
        from src.core import economic_calendar as _eco
    except ImportError:
        _eco = None

    import math as _math
    now_ts = time.time()

    # ── PASSO 1: verificar resultado do sinal pendente ─────────────────────
    if _scan_pending_signal:
        pend = _scan_pending_signal
        # ── PRÉ-ANÁLISE: verificar PRIMEIRO (garante envio mesmo se expirou no intervalo)
        if not pend.get('pre_analysis_sent') and now_ts >= pend.get('pre_analysis_ts', float('inf')):
            pend['pre_analysis_sent'] = True
            try:
                pa = _get_tv_analysis(pend['asset'], '5m')
                direction  = pend['direction']
                op_label = 'COMPRA' if direction == 'BUY' else 'VENDA'
                p1_time = datetime.fromtimestamp(pend['expiry_ts']).strftime('%H:%M')

                if pa:
                    asset_type = 'forex' if pend['asset'].upper() in EXTERNAL_FOREX else 'crypto'
                    adx_min    = 25 if asset_type == 'forex' else 20
                    close  = pa.get('close', 0)
                    ema20  = pa.get('EMA20', 0)
                    rsi    = pa.get('RSI', 50)
                    adx    = pa.get('ADX', 0)
                    entry_price = float(pend.get('entry_price') or 0.0)
                    epsilon = max(entry_price * 0.00002, 1e-6) if entry_price > 0 else 1e-6
                    # Checa WIN independente de expiração: se já moveu a favor, não reentrar
                    already_won = False
                    if entry_price > 0:
                        if direction == 'BUY':
                            already_won = close > (entry_price + epsilon)
                        else:
                            already_won = close < (entry_price - epsilon)

                    if already_won:
                        move_pct = (close - entry_price) / entry_price * 100 if entry_price else 0.0
                        if direction == 'SELL':
                            move_pct = -move_pct
                        pre_msg = (
                            f"🔄 *PRÉ-ANÁLISE — {pend['asset']} P1 ({p1_time})*\n\n"
                            f"❌ *NÃO REENTRAR*\n"
                            f"  • Entrada principal já confirmou *WIN* ({move_pct:+.2f}%)\n"
                            f"  • Prioridade: preservar resultado e evitar overtrading"
                        )
                    else:
                        # Condicoes de re-entrada: evita falso "rompeu EMA20" quando preco segue
                        # no mesmo lado, mas muito colado na media.
                        ema_buffer = ema20 * 0.0001 if ema20 else 0.0  # 0.01%
                        if direction == 'BUY':
                            price_ok = close >= (ema20 + ema_buffer)
                        else:
                            price_ok = close <= (ema20 - ema_buffer)
                        rsi_ok   = (rsi < 65) if direction == 'BUY' else (rsi > 35)
                        adx_ok   = adx >= adx_min
                        valid    = price_ok and rsi_ok and adx_ok

                        if valid:
                            reasons_pa = []
                            if price_ok:
                                reasons_pa.append(f"Preco {'acima' if direction=='BUY' else 'abaixo'} EMA20 ({ema20:.4g})")
                            reasons_pa.append(f"RSI {rsi:.0f} {'ok' if rsi_ok else 'limite'}")
                            reasons_pa.append(f"ADX {adx:.1f} ({'ok' if adx_ok else 'fraco'})")
                            pre_msg = (
                                f"🔄 *PRÉ-ANÁLISE — {pend['asset']} P1 ({p1_time})*\n\n"
                                f"✅ *RE-ENTRADA {op_label} VÁLIDA*\n"
                                + '\n'.join(f'  • {r}' for r in reasons_pa)
                            )
                        else:
                            fail_reasons = []
                            if not price_ok:
                                if ema20 <= 0:
                                    fail_reasons.append("EMA20 indisponivel no momento")
                                elif (direction == 'BUY' and close <= ema20) or (direction == 'SELL' and close >= ema20):
                                    fail_reasons.append(f"Preco no lado oposto da EMA20 ({ema20:.4g}) — possivel reversao")
                                else:
                                    fail_reasons.append(f"Preco colado na EMA20 ({ema20:.4g}) — sem distancia de seguranca")
                            if not rsi_ok:
                                fail_reasons.append(f"RSI {rsi:.0f} — {'sobrecomprado' if direction=='BUY' else 'sobrevendido'}")
                            if not adx_ok:
                                fail_reasons.append(f"ADX {adx:.1f} < {adx_min} — momentum perdido")
                            pre_msg = (
                                f"🔄 *PRÉ-ANÁLISE — {pend['asset']} P1 ({p1_time})*\n\n"
                                f"❌ *NÃO REENTRAR*\n"
                                + '\n'.join(f'  • {r}' for r in fail_reasons)
                            )
                else:
                    pre_msg = (
                        f"🔄 *PRÉ-ANÁLISE — {pend['asset']} P1 ({p1_time})*\n\n"
                        f"⚠️ *Dados temporariamente indisponíveis*\n"
                        f"❌ *NÃO REENTRAR {op_label} sem confirmação*"
                    )

                await context.bot.send_message(chat_id=chat_id, text=pre_msg, parse_mode='Markdown')
            except Exception as _pe:
                logger.warning('[scan] pre_analysis erro: %s', _pe)
            if now_ts < pend['expiry_ts']:
                return  # não expirou ainda — aguarda próximo ciclo
            # já expirou durante o intervalo → segue direto para o resultado
        if now_ts >= pend['expiry_ts']:
            # Expirou — avalia pelo candle 5m da operação (fallback: spot TV)
            try:
                cur_price, price_source = _get_scan_expiry_candle_close(pend)
                if cur_price is None:
                    cur = _get_tv_analysis(pend['asset'], '5m')
                    cur_price = cur.get('close') if cur else None
                    price_source = 'spot TradingView (fallback)'
                if cur_price:
                    entry_price = pend['entry_price']
                    direction   = pend['direction']
                    # Ignora micro-diferenças para reduzir falso LOSS/WIN por ruído de cotação.
                    epsilon = max(float(entry_price) * 0.00002, 1e-6)
                    if direction == 'BUY':
                        if cur_price > entry_price + epsilon:
                            outcome = 'WIN'
                        elif cur_price < entry_price - epsilon:
                            outcome = 'LOSS'
                        else:
                            outcome = 'TIE'
                    else:
                        if cur_price < entry_price - epsilon:
                            outcome = 'WIN'
                        elif cur_price > entry_price + epsilon:
                            outcome = 'LOSS'
                        else:
                            outcome = 'TIE'

                    won = outcome == 'WIN'
                    move_pct = (cur_price - entry_price) / entry_price * 100
                    if direction == 'SELL':
                        move_pct = -move_pct
                    op_label = 'COMPRA' if direction == 'BUY' else 'VENDA'
                    if not pend.get('executed', True):
                        theoretical = 'WIN teórico' if outcome == 'WIN' else ('LOSS teórico' if outcome == 'LOSS' else 'empate técnico')
                        result_line = '📌 *RESULTADO TEÓRICO*'
                    elif outcome == 'WIN':
                        result_line = '✅ *VITÓRIA*'
                    elif outcome == 'LOSS':
                        result_line = '❌ *PERDA*'
                    else:
                        result_line = '⚪️ *EMPATE TÉCNICO*'
                    interval_min = _SCAN_SIGNAL_INTERVAL // 60
                    no_position_note = (
                        f'\n⚠️ _Sem posição real — execução falhou ou pausada ({theoretical})_'
                        if not pend.get('executed', True) else ''
                    )
                    result_msg = (
                        f"{result_line} — {pend['asset']} {op_label}\n\n"
                        f"Entrada: `{entry_price:.4g}` → Atual: `{cur_price:.4g}`\n"
                        f"Fonte de resultado: `{price_source}`\n"
                        f"Variação: `{move_pct:+.2f}%`\n"
                        f"Qualidade do sinal: _{pend['quality']}_"
                        f"{no_position_note}\n\n"
                        f"_Próximo sinal em ~{interval_min} min_"
                    )
                    await context.bot.send_message(chat_id=chat_id, text=result_msg, parse_mode='Markdown')
            except Exception:
                pass
            _scan_pending_signal = {}
            # Cooldown começa a partir do resultado (não do sinal)
            _scan_last_signal_ts = now_ts
        else:
            # Sinal ainda não expirou — aguarda
            remaining = int(pend['expiry_ts'] - now_ts)
            logger.debug('[scan] sinal pendente %s %s — expira em %ds', pend['asset'], pend['direction'], remaining)
            return

    # ── PASSO 2: verificar cooldown entre sinais ───────────────────────────
    if now_ts - _scan_last_signal_ts < _SCAN_SIGNAL_INTERVAL:
        remaining_cd = int(_SCAN_SIGNAL_INTERVAL - (now_ts - _scan_last_signal_ts))
        logger.debug('[scan] cooldown ativo — próximo sinal em %ds', remaining_cd)
        return

    # ── PASSO 3: pré-check de eventos macro ───────────────────────────────
    upcoming_events = []
    if _eco:
        try:
            upcoming_events = _eco.get_upcoming_high_impact(minutes_ahead=30)
        except Exception:
            upcoming_events = []

    # ── PASSO 4: varrer ativos e rankear por pontuação ────────────────────
    candidates = []
    # Sessão forex ativa? (bloqueia pares fora de London/NY)
    forex_session_ok, forex_session_label = _is_forex_session_active()

    seen_tv = set()
    rejection_stats = {
        'rsi_stretched': 0,
        'mtf_required': 0,
        'profile_block': 0,
        'noise_block': 0,
        'not_strong': 0,
        'no_analysis': 0,
    }

    for asset, (screener, tv_ticker) in TV_TICKER_MAP.items():
        if tv_ticker in seen_tv:
            continue
        seen_tv.add(tv_ticker)

        is_forex = asset.upper() in EXTERNAL_FOREX
        asset_type = 'forex' if is_forex else 'crypto'
        crypto_profile = _get_crypto_signal_profile(asset) if asset_type == 'crypto' else None

        # Bloqueia forex fora de sessão ativa
        if is_forex and not forex_session_ok:
            logger.debug('[scan] Forex %s ignorado — %s', asset, forex_session_label)
            continue

        for direction in ('BUY', 'SELL'):
            try:
                analysis = _get_tv_analysis(asset, timeframe='5m')
                if not analysis:
                    rejection_stats['no_analysis'] += 1
                    continue
                quality, reasons = _assess_signal_quality(analysis, direction, asset_type=asset_type)
                if 'FORTE' not in quality:
                    rejection_stats['not_strong'] += 1
                    continue
                score = sum(1 for r in reasons if r.startswith('✅'))
                rsi_5m = analysis.get('RSI')
                adx_5m = analysis.get('ADX')
                close_5m = analysis.get('close')
                ema50_5m = analysis.get('EMA50')
                ema200_5m = analysis.get('EMA200')

                trend_aligned = True
                if close_5m is not None and ema50_5m is not None and ema200_5m is not None:
                    if direction == 'BUY':
                        trend_aligned = close_5m > ema50_5m > ema200_5m
                    else:
                        trend_aligned = close_5m < ema50_5m < ema200_5m

                if crypto_profile:
                    adx_value = float(adx_5m) if adx_5m is not None else 0.0
                    if adx_value < crypto_profile['min_adx']:
                        logger.info(
                            '[scan] bloqueado perfil cripto | %s %s adx=%.1f min=%.1f tier=%s',
                            asset,
                            direction,
                            adx_value,
                            crypto_profile['min_adx'],
                            crypto_profile['tier'],
                        )
                        rejection_stats['profile_block'] += 1
                        continue
                    if score < crypto_profile['min_score_without_mtf']:
                        logger.info(
                            '[scan] bloqueado score perfil cripto | %s %s score=%s min=%s tier=%s',
                            asset,
                            direction,
                            score,
                            crypto_profile['min_score_without_mtf'],
                            crypto_profile['tier'],
                        )
                        rejection_stats['profile_block'] += 1
                        continue

                # Evita entradas esticadas que costumam falhar em sequencia de protecoes.
                if rsi_5m is not None:
                    # Mais tolerante quando a tendencia está alinhada; mais rígido em contratendencia.
                    if crypto_profile:
                        buy_base = float(crypto_profile['buy_rsi_block'])
                        sell_base = float(crypto_profile['sell_rsi_block'])
                        buy_max = buy_base if trend_aligned else max(58.0, buy_base - 2.0)
                        sell_min = sell_base if trend_aligned else min(42.0, sell_base + 2.0)
                    else:
                        buy_max = 68 if trend_aligned else 66
                        sell_min = 32 if trend_aligned else 34
                    if direction == 'BUY' and rsi_5m >= buy_max:
                        logger.info('[scan] bloqueado RSI esticado | %s BUY RSI=%.1f', asset, rsi_5m)
                        rejection_stats['rsi_stretched'] += 1
                        continue
                    if direction == 'SELL' and rsi_5m <= sell_min:
                        logger.info('[scan] bloqueado RSI esticado | %s SELL RSI=%.1f', asset, rsi_5m)
                        rejection_stats['rsi_stretched'] += 1
                        continue

                # Confirmação 15m
                mtf_confirmed = False
                try:
                    a15 = _get_tv_analysis(asset, timeframe='15m')
                    if a15:
                        q15, _ = _assess_signal_quality(a15, direction, asset_type=asset_type)
                        mtf_confirmed = 'FORTE' in q15 or 'MODERADO' in q15
                except Exception:
                    pass

                if crypto_profile and crypto_profile['require_mtf_for_all'] and not mtf_confirmed:
                    logger.info(
                        '[scan] bloqueado perfil cripto sem confirmacao 15m | %s %s tier=%s',
                        asset,
                        direction,
                        crypto_profile['tier'],
                    )
                    rejection_stats['mtf_required'] += 1
                    continue

                # Exige confirmação 15m para sinais fracos (<=5) e para qualquer contratendência.
                min_score_without_mtf = 5
                if crypto_profile:
                    min_score_without_mtf = int(crypto_profile['min_score_without_mtf'])
                if (score <= min_score_without_mtf or not trend_aligned) and not mtf_confirmed:
                    logger.info('[scan] bloqueado sem confirmacao 15m | %s %s score=%s', asset, direction, score)
                    rejection_stats['mtf_required'] += 1
                    continue

                if SCAN_STRICT_NOISE_FILTER:
                    is_noise, weak_flags = _is_noise_scan_candidate(reasons, score, mtf_confirmed)
                    if is_noise:
                        logger.info(
                            '[scan] bloqueado ruido | %s %s score=%s weak=%s',
                            asset,
                            direction,
                            score,
                            ','.join(weak_flags) if weak_flags else 'n/a',
                        )
                        rejection_stats['noise_block'] += 1
                        continue

                sort_score = score + (0.5 if mtf_confirmed else 0)
                candidates.append((sort_score, score, asset, direction, analysis, quality, reasons, mtf_confirmed))
            except Exception:
                continue

    if not candidates:
        logger.info(
            '[scan] sem candidatos | no_analysis=%s not_strong=%s rsi_block=%s mtf_block=%s profile_block=%s noise_block=%s',
            rejection_stats['no_analysis'],
            rejection_stats['not_strong'],
            rejection_stats['rsi_stretched'],
            rejection_stats['mtf_required'],
            rejection_stats['profile_block'],
            rejection_stats['noise_block'],
        )
        return

    # Seleciona o melhor candidato respeitando cooldown por ativo+direção.
    candidates.sort(reverse=True)
    selected_candidate = None
    for candidate in candidates:
        _, cand_score, cand_asset, cand_direction, cand_analysis, cand_quality, cand_reasons, cand_mtf_confirmed = candidate
        alert_key = f'{cand_asset}_{cand_direction}'
        last_alert_ts = _auto_scan_last_alerted.get(alert_key, 0.0)
        if now_ts - last_alert_ts < _AUTO_SCAN_COOLDOWN:
            continue
        selected_candidate = (
            cand_score,
            cand_asset,
            cand_direction,
            cand_analysis,
            cand_quality,
            cand_reasons,
            cand_mtf_confirmed,
            alert_key,
        )
        break

    if selected_candidate is None:
        logger.info('[scan] candidatos em cooldown por ativo/direcao | total=%s cooldown_s=%s', len(candidates), _AUTO_SCAN_COOLDOWN)
        return

    score, asset, direction, analysis, quality, reasons, mtf_confirmed, selected_alert_key = selected_candidate

    # ── PASSO 5: construir e enviar o sinal ───────────────────────────────
    market_symbol, _market_note = resolve_market_symbol(asset)

    close = analysis.get('close')
    rsi   = analysis.get('RSI')
    group = _external_asset_group(asset)
    direction_label = 'COMPRA' if direction == 'BUY' else 'VENDA'
    direction_arrow = '🟢' if direction == 'BUY' else '🔴'
    op_emoji = '📈' if direction == 'BUY' else '📉'
    close_str = f'{close:.4g}' if close is not None else 'N/A'
    rsi_str   = f'{rsi:.0f}'   if rsi   is not None else 'N/A'
    reasons_text = '\n'.join(f'  {r}' for r in reasons)
    mtf_tag = '✅ 5m + 15m confirmados' if mtf_confirmed else '⚠️ Apenas 5m confirmado'

    # Próxima fronteira de 5 minutos
    now_local = datetime.now()
    total_min = now_local.minute + now_local.second / 60 + 0.02
    next_5m_min = _math.ceil(total_min / 5) * 5
    if next_5m_min >= 60:
        entry_dt = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        entry_dt = now_local.replace(minute=next_5m_min, second=0, microsecond=0)

    # Evita alertas tardios: exige janela mínima para o operador agir antes da entrada.
    lead_seconds = (entry_dt - now_local).total_seconds()
    if lead_seconds < SCAN_MIN_ENTRY_LEAD_SECONDS:
        entry_dt = entry_dt + timedelta(minutes=5)

    prot1_dt = entry_dt + timedelta(minutes=5)
    prot2_dt = entry_dt + timedelta(minutes=10)
    entry_str = entry_dt.strftime('%H:%M')
    prot1_str = prot1_dt.strftime('%H:%M')
    prot2_str = prot2_dt.strftime('%H:%M')

    eco_block = ''
    if upcoming_events:
        evt_lines = '\n'.join(
            f"  ⏰ {e.get('time','?')} — {e.get('event','?')} ({e.get('country','?')})"
            for e in upcoming_events[:3]
        )
        eco_block = f"\n\n🚨 *ATENÇÃO — Evento macro em ≤ 30min:*\n{evt_lines}"

    exec_block = ''
    canonical = asset.upper()
    bitget_symbol = BITGET_FUTURES_MAP.get(canonical)
    trade_executed = False
    if bitget_symbol and close:
        can_execute = not upcoming_events  # MTF é informativo; não bloqueia simulador
        if not can_execute:
            exec_block = "\n\n⏸ _Execução pausada: evento macro ≤ 30min_"
        else:
            result = _bx.execute_trade(
                asset=canonical,
                bitget_symbol=bitget_symbol,
                direction=direction,
                price=close,
                rsi=rsi or 0.0,
                quality=quality,
            )
            if result.get('ok'):
                trade_executed = True
                mode = result.get('mode', 'PAPER')
                trade = result.get('trade', {})
                qty   = trade.get('qty', result.get('qty', 0))
                logger.info('[scan] execute_trade OK: %s %s %s qty=%.6g mode=%s', canonical, direction, bitget_symbol, qty, mode)
                exec_block = (
                    f"\n\n{'📋' if mode == 'PAPER' else '✅'} *Bitget {mode}:* "
                    f"`{direction} {qty:.6g} {canonical}` @ `{close_str}`"
                )
            else:
                logger.warning('[scan] execute_trade FALHOU: %s %s erro=%s', canonical, direction, result.get('error', 'erro'))
                exec_block = f"\n\n⚠️ _Execução falhou: {result.get('error', 'erro')}_"

    interval_min = _SCAN_SIGNAL_INTERVAL // 60
    msg = (
        f"{direction_arrow} *SINAL DETECTADO — {quality}*\n\n"
        f"📊 *ATIVO:* {asset} ({group})\n"
        f"❗️ *ENTRADA:* `{entry_str}` (UTC-3)\n"
        f"⏰ *TEMPO:* 5 MINUTOS\n"
        f"{op_emoji} *OPERAÇÃO:* {direction_label}\n"
        f"_{mtf_tag}_\n\n"
        f"🚦 *PROTEÇÕES (se necessário):*\n"
        f"  1ª: `{prot1_str}` | 2ª: `{prot2_str}`\n\n"
        f"📋 *Análise ({score}/9 critérios):*\n"
        f"Preco: `{close_str}` | RSI: `{rsi_str}`\n"
        f"{reasons_text}"
        f"{eco_block}"
        f"{exec_block}\n\n"
        f"_Resultado em ~5min | Próximo sinal em ~{interval_min}min após resultado_"
    )
    try:
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
    except Exception:
        return

    # ── PASSO 6: registrar sinal pendente para checagem de resultado ──────
    entry_ts = entry_dt.timestamp()
    _scan_pending_signal = {
        'asset': asset,
        'market_symbol': market_symbol,
        'direction': direction,
        'entry_price': close,
        'entry_ts': entry_ts,
        'expiry_ts': entry_ts + 300,       # 5 min após ENTRADA para checar resultado
        'pre_analysis_ts': entry_ts + 240, # 4 min após entrada → pré-análise P1
        'pre_analysis_sent': False,
        'quality': quality,
        'executed': trade_executed,        # False = sem posição real na Bitget
    }
    _auto_scan_last_alerted[selected_alert_key] = now_ts


async def bitget_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra resumo das operações paper/live da BitGet."""
    from src.core import bitget_executor as _bx
    s = _bx.get_paper_summary()
    mode_str = '📋 PAPER (simulado)' if s['mode'] == 'PAPER' else '🔴 LIVE (dinheiro real)'
    balance_str = f"${s['balance']:.2f}" if s['mode'] == 'PAPER' else '(saldo real via API)'
    pnl_str = f"${s['total_pnl']:+.2f}" if s['mode'] == 'PAPER' else '—'

    lines = [
        f"📊 *BitGet Futures — {mode_str}*\n",
        f"Saldo paper: `{balance_str}`",
        f"Posições abertas: `{s['open']}`",
        f"Fechadas: `{s['closed']}` | P&L total: `{pnl_str}`",
    ]
    if s['open_trades']:
        lines.append('\n*Posições abertas:*')
        for t in s['open_trades']:
            side_arrow = '🟢' if t['side'] == 'BUY' else '🔴'
            lines.append(
                f"  {side_arrow} {t['asset']} {t['side']} "
                f"`{t['qty']:.6g}` @ `{t['price']:.4g}` "
                f"— ${t['notional']:.2f}"
            )
    if not _bx.is_configured():
        lines.append('\n⚠️ _Passphrase não configurada — somente paper disponível_')
        lines.append('Configure BITGET\\_PASSPHRASE no .env para live trading')

    await _reply_text(update, '\n'.join(lines))


async def bitget_toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liga/desliga o modo live da BitGet. Uso: /bitget_toggle live | paper"""
    from src.core import bitget_executor as _bx
    arg = (context.args[0].lower() if context.args else '').strip()
    if arg == 'live':
        if not _bx.is_configured():
            await _reply_text(update,
                '❌ Não é possível ativar live: BITGET\\_PASSPHRASE não configurada no .env')
            return
        os.environ['BITGET_PAPER_TRADING'] = 'false'
        _bx.PAPER_TRADING = False
        await _reply_text(update,
            '🔴 *Modo LIVE ativado!*\n'
            'Próximas ordens serão executadas com dinheiro real.\n'
            'Para voltar ao paper: /bitget\\_toggle paper')
    elif arg == 'paper':
        os.environ['BITGET_PAPER_TRADING'] = 'true'
        _bx.PAPER_TRADING = True
        await _reply_text(update, '📋 *Modo PAPER ativado.* Ordens são apenas simuladas.')
    else:
        mode = 'PAPER 📋' if _bx.PAPER_TRADING else 'LIVE 🔴'
        await _reply_text(update,
            f'BitGet modo atual: *{mode}*\n'
            'Uso: `/bitget_toggle paper` ou `/bitget_toggle live`')


async def bitget_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra configuração de limites de trades. Uso: /bitget_config"""
    from src.core import trade_config
    stats = trade_config.get_daily_stats()
    cfg = trade_config.get_config()
    
    msg = (
        "*⚙️ BitGet — Configuração de Limites*\n\n"
        f"*Max trades/dia:* `{cfg['max_trades_per_day']}`\n"
        f"*Risk por trade:* `{cfg['risk_pct']:.1f}%` (do saldo)\n"
        f"*Alavancagem:* `{cfg['leverage']}x`\n"
        f"*Limite perda/dia:* `{cfg['daily_loss_limit_pct']:.1f}%`\n"
        f"*Requer mercado bom:* `{'Sim' if cfg['require_market_good'] else 'Não'}`\n\n"
        f"*Hoje (19/05/2026):*\n"
        f"Trades executados: `{stats['trades_today']}/{stats['max_trades']}`\n"
        f"P&L diário: `${stats['daily_pnl']:+.2f}`\n\n"
        "Usar: `/bitget_limits trades=5 risk=1.0 leverage=5`"
    )
    await _reply_text(update, msg)


async def bitget_limits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modifica limites. Uso: /bitget_limits trades=5 risk=1.0 leverage=5 loss=3.0"""
    from src.core import trade_config
    
    if not context.args:
        await _reply_text(update,
            "Uso: `/bitget_limits trades=5 risk=1.0 leverage=5 loss=3.0`\n\n"
            "Exemplos:\n"
            "  `/bitget_limits trades=10` — máx 10 trades/dia\n"
            "  `/bitget_limits risk=0.5` — 0.5% risco/trade\n"
            "  `/bitget_limits leverage=10` — alavancagem 10x\n"
            "  `/bitget_limits loss=5` — parar se perder 5% do dia"
        )
        return
    
    updates = {}
    for arg in context.args:
        try:
            k, v = arg.split('=')
            k = k.strip().lower()
            if k == 'trades':
                updates['max_trades_per_day'] = int(v)
            elif k == 'risk':
                updates['risk_pct'] = float(v)
            elif k == 'leverage':
                updates['leverage'] = int(v)
            elif k == 'loss':
                updates['daily_loss_limit_pct'] = float(v)
        except Exception:
            pass
    
    if not updates:
        await _reply_text(update, "❌ Nenhum parâmetro válido fornecido")
        return
    
    new_cfg = trade_config.update_config(updates)
    msg = (
        "✅ *Configuração atualizada!*\n\n"
        f"Max trades/dia: `{new_cfg['max_trades_per_day']}`\n"
        f"Risk: `{new_cfg['risk_pct']:.1f}%`\n"
        f"Leverage: `{new_cfg['leverage']}x`\n"
        f"Loss limit: `{new_cfg['daily_loss_limit_pct']:.1f}%`"
    )
    await _reply_text(update, msg)


async def scan_auto_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liga/desliga o scanner automático de externos. Uso: /scan_auto on | off"""
    global _auto_scan_active
    arg = (context.args[0].lower() if context.args else '').strip()
    if arg in ('on', 'ativar', 'ligar', '1'):
        _auto_scan_active = True
        await _reply_text(update,
            "✅ *Scanner automático LIGADO*\n"
            "Vou varrer todos os ativos a cada 5 minutos e avisar quando encontrar um sinal FORTE.\n"
            "Para desligar: /scan\\_auto off"
        )
    elif arg in ('off', 'desativar', 'desligar', '0'):
        _auto_scan_active = False
        await _reply_text(update, "⏹ *Scanner automático DESLIGADO.*")
    else:
        status = "LIGADO ✅" if _auto_scan_active else "DESLIGADO ⏹"
        await _reply_text(update,
            f"📡 Scanner automático: *{status}*\n"
            "Uso: `/scan_auto on` ou `/scan_auto off`"
        )


async def eco_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra calendário econômico do dia. Uso: /eco"""
    try:
        summary = economic_calendar.get_calendar_summary()
        await _reply_text(update, summary)
    except Exception as e:
        await _reply_text(update, f"❌ Erro ao buscar calendário: {str(e)}")


async def alert_upcoming_events(context: ContextTypes.DEFAULT_TYPE):
    """Job que alerta sobre eventos econômicos próximos (1h antes)."""
    try:
        upcoming = economic_calendar.get_upcoming_high_impact(minutes_ahead=60)
        if not upcoming:
            return
        
        chat_id = TELEGRAM_CHAT_ID
        for evt in upcoming:
            msg = (
                f"🚨 *EVENTO ECONÔMICO PROXIMO*\n\n"
                f"{economic_calendar.format_event(evt)}\n\n"
                f"_Cuidado: possível volatilidade extrema._"
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
            except Exception:
                pass
    except Exception:
        pass


async def monitor_market(context: ContextTypes.DEFAULT_TYPE):
    """Monitora multiplos ativos do mercado e envia alertas"""
    global last_signal, monitoring_active, monitor_end_time, pending_signal_evaluations, pending_martingale_decisions, monitored_symbols
    global current_rotation_index, monitor_signals_sent, last_pre_alert_key, last_direction_alert_at
    global monitor_target_chat_id, monitor_started_at, monitor_last_alert_at, monitor_last_heartbeat_at
    global monitor_session_results
    
    if not monitoring_active or not monitored_symbols:
        return
    
    chat_id = monitor_target_chat_id or get_telegram_chat_id()
    now = datetime.now()

    # Desativa monitoramento automaticamente ao fim da janela configurada.
    if monitor_end_time and now >= monitor_end_time:
        session_summary = build_monitor_session_summary('tempo máximo atingido')
        monitoring_active = False
        monitor_end_time = None
        monitor_target_chat_id = None
        monitor_started_at = None
        monitor_last_alert_at = None
        monitor_last_heartbeat_at = None
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=session_summary,
                parse_mode='Markdown'
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⏹ **Monitoramento finalizado automaticamente**\n\n"
                    f"Duração máxima de {monitor_duration_minutes} minutos atingida.\n"
                    "Use /monitor on para iniciar um novo ciclo."
                ),
                parse_mode='Markdown'
            )
        return

    # Encerra sessão ao atingir limite e sem avaliações pendentes.
    if monitor_signals_sent >= MONITOR_MAX_SIGNALS and not pending_signal_evaluations:
        session_summary = build_monitor_session_summary('limite de sinais atingido')
        monitoring_active = False
        monitor_end_time = None
        monitor_target_chat_id = None
        monitor_started_at = None
        monitor_last_alert_at = None
        monitor_last_heartbeat_at = None
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=session_summary,
                parse_mode='Markdown'
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⏹ **Monitoramento finalizado automaticamente**\n\n"
                    f"Limite de {MONITOR_MAX_SIGNALS} sinais atingido.\n"
                    "Use /monitor on para iniciar um novo ciclo."
                ),
                parse_mode='Markdown'
            )
        return
    
    # Avalia sinais pendentes primeiro
    remaining_evaluations = []
    new_evaluations = []
    
    for pending in pending_signal_evaluations:
        tf_minutes = timeframe_to_minutes(pending.get('timeframe', config.TIMEFRAME))
        max_wait = timedelta(minutes=max(2, tf_minutes * 2))
        expired = now - pending['evaluate_at'] > max_wait

        decision_seconds = (pending['evaluate_at'] - now).total_seconds()
        if (
            is_weekend_binary_mode(now)
            and tf_minutes <= 1
            and not pending.get('martingale_decision_sent')
            and MARTINGALE_REENTRY_MIN_SECONDS <= decision_seconds <= MARTINGALE_REENTRY_MAX_SECONDS
        ):
            try:
                exchange = ExchangeConnector(testnet=config.TESTNET)
                eval_symbol = pending.get('market_symbol', pending['symbol'])
                tf = pending.get('timeframe', config.TIMEFRAME)
                df_live = exchange.fetch_ohlcv(eval_symbol, tf, limit=200)
                if df_live is not None and len(df_live) >= 40:
                    tech_live = TechnicalIndicators(df_live.iloc[:-1].copy())
                    closed_live = tech_live.calculate_all_indicators(MONITOR_INDICATORS_CONFIG)
                    signal_data = TradingAnalyzer(closed_live).get_current_signal()
                    weekend_setup = evaluate_weekend_binary_setup(closed_live, tf, signal_data)
                    current_price = None
                    ticker = exchange.get_ticker(eval_symbol)
                    if ticker and ticker.get('last') is not None:
                        current_price = float(ticker['last'])
                    else:
                        current_price = float(df_live.iloc[-1]['close'])

                    entry_price = float(pending.get('entry_price') or current_price)
                    pending_signal = int(pending['signal'])
                    is_losing_now = (
                        current_price < entry_price if pending_signal == 1 else current_price > entry_price
                    )

                    if is_losing_now:
                        signal = int(weekend_setup['signal'])
                        setup_score = int(weekend_setup['score'])
                        probability = float(weekend_setup['probability'])
                        score = max(float(signal_data.get('score', 0.5)), float(setup_score) / 10.0)
                        symbol_key = pending.get('symbol_key') or get_monitor_signal_scope_key(pending['symbol'], tf)
                        state_key = f"{symbol_key}:{pending_signal}"
                        tracked_attempts = int(weekend_reentry_tracker.get(state_key, {}).get('alerts_sent', 1))
                        min_probability, min_edge, min_consensus = get_quality_gates(tf)
                        min_setup_score = get_setup_min_score(tf)
                        edge = abs(score - 0.5)
                        consensus = _signal_quality_consensus(signal_data, signal) if signal != 0 else 0
                        if signal != 0:
                            consensus = max(consensus, 3)

                        allow_reentry = (
                            signal == pending_signal
                            and probability >= min_probability
                            and edge >= min_edge
                            and consensus >= min_consensus
                            and setup_score >= min_setup_score
                        )

                        if chat_id:
                            if allow_reentry:
                                action = 'COMPRA' if signal == 1 else 'VENDA'
                                emoji = '🟢' if signal == 1 else '🔴'
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=(
                                        "✅ **REENTRAR**\n\n"
                                        f"{emoji} {action} - {pending['symbol']}\n"
                                        f"⏰ Entrar até {int(decision_seconds)}s antes do fim da operação e executar no próximo candle ({pending['evaluate_at'].strftime('%H:%M')})\n"
                                        f"🔁 Martingale: {tracked_attempts} de {WEEKEND_MAX_REENTRIES}\n"
                                        f"🧠 Setup: {weekend_setup['setup_type']}\n"
                                        f"🏗 Score: {setup_score}\n"
                                        f"📈 Probabilidade: {probability:.1f}%"
                                    ),
                                    parse_mode='Markdown'
                                )

                                new_evaluations.append({
                                    'symbol': pending['symbol'],
                                    'market_symbol': eval_symbol,
                                    'timeframe': tf,
                                    'signal': signal,
                                    'entry_price': current_price,
                                    'evaluate_at': pending['evaluate_at'] + timedelta(minutes=tf_minutes),
                                    'candle_open_time': pending['evaluate_at'],
                                    'martingale_alert_sent': True,
                                    'symbol_key': symbol_key,
                                    'martingale_decision_sent': False,
                                })
                                last_signal[symbol_key] = signal
                                last_pre_alert_key[symbol_key] = f"{symbol_key}:{signal}:{pending['evaluate_at'].strftime('%Y%m%d%H%M')}"
                                last_direction_alert_at[f"{symbol_key}:{signal}"] = now
                                reentry_state_key = f"{symbol_key}:{signal}"
                                prior_state = weekend_reentry_tracker.get(reentry_state_key, {})
                                weekend_reentry_tracker[reentry_state_key] = {
                                    'alerts_sent': int(prior_state.get('alerts_sent', 0)) + 1,
                                    'last_at': now,
                                }
                                monitor_signals_sent += 1
                            else:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=(
                                        "⛔ **NÃO REENTRAR**\n\n"
                                        f"Ativo: {pending['symbol']}\n"
                                        f"⏰ Faltam ~{int(decision_seconds)}s para o fim da operação\n"
                                        "Motivo: o contexto atual não sustenta martingale na mesma direção.\n"
                                        f"🧠 Leitura: {weekend_setup['setup_type']}\n"
                                        f"📈 Probabilidade: {probability:.1f}% | Score: {setup_score}"
                                    ),
                                    parse_mode='Markdown'
                                )
                                reset_weekend_reentry_state(
                                    pending.get('symbol_key') or get_monitor_signal_scope_key(pending['symbol'], tf)
                                )

                        pending['martingale_decision_sent'] = True
            except Exception as exc:
                logger.error('Erro ao antecipar decisao de martingale | symbol=%s timeframe=%s err=%s', pending.get('symbol'), pending.get('timeframe'), exc)

        if now >= pending['evaluate_at']:
            try:
                exchange = ExchangeConnector(testnet=config.TESTNET)
                eval_symbol = pending.get('market_symbol', pending['symbol'])
                tf = pending.get('timeframe', config.TIMEFRAME)

                # Busca OHLCV para avaliar pelo candle real (abertura vs fechamento).
                try:
                    ohlcv_df = exchange.fetch_ohlcv(eval_symbol, tf, limit=5)
                except Exception as _fetch_err:
                    ohlcv_df = None
                    logger.warning("OHLCV falhou na avaliacao | %s: %s", eval_symbol, _fetch_err)

                if ohlcv_df is None or len(ohlcv_df) < 2:
                    if not expired:
                        remaining_evaluations.append(pending)
                    else:
                        logger.warning(
                            "Descartando avaliacao pendente expirada | symbol=%s timeframe=%s evaluate_at=%s",
                            pending.get('symbol'),
                            pending.get('timeframe'),
                            pending.get('evaluate_at')
                        )
                    continue

                # Candle do sinal = penúltimo (último completamente fechado ao avaliar).
                # iloc[-1] é o candle ainda em formação no momento da avaliação.
                signal_candle = ohlcv_df.iloc[-2]
                candle_open = float(signal_candle['open'])
                candle_close = float(signal_candle['close'])

                pending_signal = pending['signal']

                # Resultado binário real: COMPRA ganha se fechou acima da abertura.
                if pending_signal == 1:
                    result_pct = ((candle_close - candle_open) / candle_open) * 100
                else:
                    result_pct = ((candle_open - candle_close) / candle_open) * 100

                is_good = result_pct > 0
                signal_stats['total'] += 1
                if is_good:
                    signal_stats['good'] += 1
                    quality_emoji = "✅"
                    quality_text = "BOM"
                else:
                    signal_stats['bad'] += 1
                    quality_emoji = "❌"
                    quality_text = "RUIM"

                monitor_session_results.append({
                    'symbol': pending['symbol'],
                    'timeframe': pending['timeframe'],
                    'signal': pending_signal,
                    'result_pct': result_pct,
                    'is_good': is_good,
                    'martingale_alert': bool(pending.get('martingale_alert_sent')),
                })

                symbol_key = pending.get('symbol_key') or get_monitor_signal_scope_key(
                    pending['symbol'],
                    pending['timeframe'],
                )
                if is_good:
                    reset_weekend_reentry_state(symbol_key)
                elif timeframe_to_minutes(pending.get('timeframe', config.TIMEFRAME)) <= 1:
                    state_key = f"{symbol_key}:{pending_signal}"
                    current_state = weekend_reentry_tracker.get(state_key, {})
                    alerts_sent = int(current_state.get('alerts_sent', 1))
                    if alerts_sent >= (WEEKEND_MAX_REENTRIES + 1):
                        reset_weekend_reentry_state(symbol_key)

                logger.info(
                    "Sinal avaliado | symbol=%s timeframe=%s direction=%s candle_open=%.4f candle_close=%.4f result_pct=%.4f quality=%s",
                    pending['symbol'],
                    pending['timeframe'],
                    'BUY' if pending_signal == 1 else 'SELL',
                    candle_open,
                    candle_close,
                    result_pct,
                    quality_text
                )
            except Exception as e:
                logger.error(f"Erro ao avaliar sinal de {pending['symbol']}: {e}")
                # Evita loop infinito de pendencia em caso de erro recorrente.
                if not expired:
                    remaining_evaluations.append(pending)
                else:
                    logger.warning(
                        "Descartando avaliacao pendente apos erros recorrentes | symbol=%s timeframe=%s evaluate_at=%s",
                        pending.get('symbol'),
                        pending.get('timeframe'),
                        pending.get('evaluate_at')
                    )
        else:
            remaining_evaluations.append(pending)

    pending_signal_evaluations = remaining_evaluations + new_evaluations

    pending_martingale_decisions = []

    # Evita fila longa de sinais sem bloquear totalmente novos alertas.
    if len(pending_signal_evaluations) >= MAX_PENDING_EVALUATIONS:
        logger.info(
            "Aguardando avaliacao de sinais pendentes (%s/%s) antes de emitir novo alerta.",
            len(pending_signal_evaluations),
            MAX_PENDING_EVALUATIONS,
        )
        return
    
    # Rotacao adaptativa: com listas maiores, verifica mais de 1 ativo por ciclo
    # para não perder a janela operacional de pre-alerta.
    total_symbols = len(monitored_symbols)
    actionable_timeframes = get_actionable_monitor_timeframes(now)
    symbols_per_cycle = get_symbols_per_cycle(total_symbols, actionable_timeframes)

    symbols_to_check = []
    for i in range(symbols_per_cycle):
        idx = (current_rotation_index + i) % total_symbols
        symbols_to_check.append(monitored_symbols[idx])
    current_rotation_index = (current_rotation_index + symbols_per_cycle) % total_symbols
    
    logger.info(
        "Ciclo de monitoramento: verificando %s | timeframes=%s",
        symbols_to_check,
        actionable_timeframes if actionable_timeframes else [config.TIMEFRAME],
    )
    log_market_diagnostic(
        'monitor_cycle',
        profile=BOT_PROFILE,
        market_type=CURRENT_MARKET_TYPE,
        symbols=symbols_to_check,
        timeframes=actionable_timeframes if actionable_timeframes else [config.TIMEFRAME],
    )
    
    # Apenas 1 alerta por ciclo para evitar sinais muito proximos.
    alert_to_send = None
    
    # Reutiliza a mesma conexão por ciclo para reduzir latência e evitar ciclos perdidos.
    exchange = ExchangeConnector(testnet=config.TESTNET)

    # Monitora ativos selecionados do ciclo
    for symbol in symbols_to_check:
        try:
            market_symbol, market_note = resolve_market_symbol(symbol)
            if not market_symbol:
                logger.info("Símbolo sem feed disponível: %s (%s)", symbol, market_note)
                log_market_diagnostic(
                    'monitor_symbol_no_feed',
                    profile=BOT_PROFILE,
                    market_type=CURRENT_MARKET_TYPE,
                    requested_symbol=symbol,
                    reason=market_note,
                )
                continue

            # ══════════════════════════════════════════════════════════════════════════════
            # FILTRO DE LIQUIDEZ CRIPTO - ATLAS v1.1 (Jun 2026)
            # ══════════════════════════════════════════════════════════════════════════════
            # Bloqueia análise de ativos Alt (TIER 2/3) em horários de baixa liquidez.
            # Evita sinais falsos causados por dojis em madrugada asiática e finais de semana.
            # ══════════════════════════════════════════════════════════════════════════════
            symbol_base = symbol.split('/')[0] if '/' in symbol else symbol
            is_crypto = CURRENT_MARKET_TYPE in ('crypto_binary', 'crypto') or symbol_base.upper() in (CRYPTO_TIER1_SYMBOLS | CRYPTO_TIER2_SYMBOLS | CRYPTO_TIER3_SYMBOLS)
            
            if is_crypto:
                can_trade, liquidity_msg = _check_crypto_liquidity_session(symbol_base)
                if not can_trade:
                    profile = _get_crypto_signal_profile(symbol_base)
                    logger.info(
                        "[LIQUIDEZ] ⏸ %s bloqueado - Tier %d (%s) | %s",
                        symbol, profile['tier'], profile['tier_name'], liquidity_msg.replace('❌ ', '')
                    )
                    log_market_diagnostic(
                        'monitor_liquidity_block',
                        profile=BOT_PROFILE,
                        market_type=CURRENT_MARKET_TYPE,
                        requested_symbol=symbol,
                        tier=profile['tier'],
                        tier_name=profile['tier_name'],
                        reason=liquidity_msg,
                    )
                    # Pula este ativo (não analisa, não gasta processamento)
                    continue
            # ══════════════════════════════════════════════════════════════════════════════

            timeframes_to_check = list(actionable_timeframes)
            if not timeframes_to_check:
                continue

            ticker = None
            m5_confirmation_context = None

            for timeframe in timeframes_to_check:
                pre_alert_max_seconds, pre_alert_min_seconds = get_pre_alert_window_seconds(timeframe)
                min_probability, min_edge, min_consensus = get_quality_gates(timeframe)
                min_setup_score = get_setup_min_score(timeframe)

                df = exchange.fetch_ohlcv(market_symbol, timeframe, limit=500)
                if df is None or len(df) < 30:
                    continue

                closed_df = df.iloc[:-1].copy()
                if len(closed_df) < 30:
                    continue

                tech_indicators = TechnicalIndicators(closed_df)
                closed_df = tech_indicators.calculate_all_indicators(MONITOR_INDICATORS_CONFIG)

                analyzer = TradingAnalyzer(closed_df)
                signal_data = analyzer.get_current_signal()
                weekend_mode = is_weekend_binary_mode(now)
                weekend_setup = evaluate_weekend_binary_setup(closed_df, timeframe, signal_data) if weekend_mode else None

                if ticker is None:
                    ticker = exchange.get_ticker(market_symbol)
                current_price = ticker['last'] if ticker else closed_df.iloc[-1]['close']

                if weekend_setup is not None:
                    signal = int(weekend_setup['signal'])
                    score = max(
                        float(signal_data.get('score', 0.5)),
                        float(weekend_setup['score']) / 10.0,
                    )
                    signal_data['probability'] = float(weekend_setup['probability'])
                else:
                    signal = signal_data['signal']
                    score = signal_data['score']
                symbol_key = get_monitor_signal_scope_key(symbol, timeframe)
                
                # ══════════════════════════════════════════════════════════════
                # SISTEMA ATLAS - Confluence Score (SMC + Wyckoff + PA + Elliott + Tradicional)
                # ══════════════════════════════════════════════════════════════
                try:
                    direction_str = 'BUY' if signal == 1 else 'SELL' if signal == -1 else 'NEUTRAL'
                    
                    # Aplica thresholds baseados no tier de liquidez do ativo
                    crypto_profile = _get_crypto_signal_profile(symbol_base) if is_crypto else None
                    min_score_threshold = crypto_profile['min_score'] if crypto_profile else 0.55
                    min_confluence_threshold = 3  # 3 técnicas concordando (padrão para todos)
                    
                    # Análise de confluência completa
                    should_enter, confluence_analysis = confluence_system.should_enter_trade(
                        df=closed_df,
                        direction=direction_str,
                        signal_data=signal_data,
                        min_score=min_score_threshold,      # Score variável por tier (55% Tier1/2, 60% Tier3)
                        min_confluence=min_confluence_threshold
                    )
                    
                    final_score = confluence_analysis['final_score']
                    final_score_pct = confluence_analysis['final_score_pct']
                    confluence_count = confluence_analysis['confluence_count']
                    factors_agree = confluence_analysis['factors_agree']
                    factors_disagree = confluence_analysis['factors_disagree']
                    recommendation = confluence_analysis['recommendation']
                    individual_scores = confluence_analysis['scores']
                    
                    # Logs completos com tier info
                    tier_label = f"Tier{crypto_profile['tier']}" if crypto_profile else "N/A"
                    if should_enter:
                        logger.info(
                            '[ATLAS] ✅ %s (%s) | %s | %s | APROVADO | score=%d%% (min=%d%%) | confluência=%d/5 | fatores=%s',
                            symbol, tier_label, timeframe, direction_str, final_score_pct, 
                            int(min_score_threshold * 100), confluence_count, ','.join(factors_agree)
                        )
                        log_market_diagnostic(
                            event='atlas_filter_pass',
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=direction_str,
                            final_score=final_score,
                            final_score_pct=final_score_pct,
                            confluence_count=confluence_count,
                            recommendation=recommendation,
                            factors_agree=factors_agree,
                            traditional_score=individual_scores['traditional'],
                            smc_score=individual_scores['smc'],
                            wyckoff_score=individual_scores['wyckoff'],
                            price_action_score=individual_scores['price_action'],
                            elliott_score=individual_scores['elliott']
                        )
                    else:
                        block_reason = confluence_analysis.get('block_reason', 'critérios não atingidos')
                        logger.info(
                            '[ATLAS] ❌ %s (%s) | %s | %s | BLOQUEADO: %s | score=%d%% (min=%d%%) | confluência=%d/5',
                            symbol, tier_label, timeframe, direction_str, block_reason, 
                            final_score_pct, int(min_score_threshold * 100), confluence_count
                        )
                        log_market_diagnostic(
                            event='atlas_filter_block',
                            symbol=symbol,
                            timeframe=timeframe,
                            direction=direction_str,
                            final_score=final_score,
                            final_score_pct=final_score_pct,
                            confluence_count=confluence_count,
                            block_reason=block_reason,
                            factors_agree=factors_agree,
                            factors_disagree=factors_disagree,
                            traditional_score=individual_scores['traditional'],
                            smc_score=individual_scores['smc'],
                            wyckoff_score=individual_scores['wyckoff'],
                            price_action_score=individual_scores['price_action'],
                            elliott_score=individual_scores['elliott']
                        )
                        continue  # pular este sinal
                    
                    # Sinal aprovado - adicionar info de confluência ao signal_data
                    signal_data['atlas_score'] = final_score
                    signal_data['atlas_score_pct'] = final_score_pct
                    signal_data['confluence_count'] = confluence_count
                    signal_data['confluence_factors'] = factors_agree
                    signal_data['recommendation'] = recommendation
                    signal_data['individual_scores'] = individual_scores
                    
                except Exception as atlas_err:
                    logger.warning(
                        '[ATLAS] Erro ao analisar %s %s: %s',
                        symbol, timeframe, atlas_err
                    )
                    # Se ATLAS falhar, deixar passar (degradação graceful)
                # ══════════════════════════════════════════════════════════════

                if weekend_mode and timeframe_to_minutes(timeframe) <= 1 and signal == 0:
                    last_signal.pop(symbol_key, None)
                    reset_weekend_reentry_state(symbol_key)

                should_alert_direction = (
                    signal != 0 and (
                        symbol_key not in last_signal
                        or last_signal[symbol_key] != signal
                        or direction_cooldown_elapsed(symbol_key, signal, now, timeframe)
                        or (
                            weekend_mode
                            and not has_pending_martingale_decision(symbol_key, signal)
                            and allow_weekend_reentry(symbol_key, signal, now, timeframe)
                        )
                    )
                )

                reentry_state = weekend_reentry_tracker.get(f"{symbol_key}:{signal}", {}) if signal != 0 else {}
                is_martingale_alert = (
                    weekend_mode
                    and timeframe_to_minutes(timeframe) <= 1
                    and int(reentry_state.get('alerts_sent', 0)) >= 1
                )
                martingale_step = int(reentry_state.get('alerts_sent', 0)) if is_martingale_alert else 0

                if not should_alert_direction or signal == 0:
                    continue

                probability = float(signal_data.get('probability', 0.0))
                edge = abs(float(score) - 0.5)
                consensus = _signal_quality_consensus(signal_data, signal)

                if weekend_mode:
                    consensus = max(consensus, 3 if signal != 0 else 0)
                    if signal == 0:
                        continue
                elif is_false_breakout_risk(closed_df, signal, timeframe):
                    logger.info(
                        "Sinal bloqueado por risco de falso rompimento | symbol=%s timeframe=%s direction=%s",
                        symbol, timeframe, 'BUY' if signal == 1 else 'SELL',
                    )
                    continue

                if probability < min_probability or edge < min_edge or consensus < min_consensus:
                    continue

                if weekend_mode:
                    setup = {
                        'score': int(weekend_setup['score']),
                        'setup_type': weekend_setup['setup_type'],
                        'confirmations': list(weekend_setup['confirmations']),
                        'warnings': list(weekend_setup['warnings']),
                        'volume_ratio': 1.0,
                        'adx': float(weekend_setup['adx']),
                        'rsi': float(closed_df.iloc[-1].get('rsi', 50.0)),
                        'body_ratio': 0.0,
                        'signal_probability': probability,
                        'expiry_candles': int(weekend_setup['expiry_candles']),
                    }
                    if setup['score'] < min_setup_score:
                        logger.info(
                            "Weekend setup descartado por score fraco | symbol=%s timeframe=%s weekend_score=%s warnings=%s",
                            symbol,
                            timeframe,
                            setup['score'],
                            ', '.join(setup['warnings'])
                        )
                        continue
                    if setup['adx'] > WEEKEND_MAX_ADX:
                        logger.info(
                            "Weekend setup descartado por ADX alto | symbol=%s timeframe=%s adx=%.1f",
                            symbol,
                            timeframe,
                            setup['adx'],
                        )
                        continue
                else:
                    setup = evaluate_signal_setup(closed_df, signal, signal_data, timeframe)
                    if setup['score'] < min_setup_score:
                        logger.info(
                            "Sinal descartado por setup fraco | symbol=%s timeframe=%s score=%s setup_score=%s warnings=%s",
                            symbol,
                            timeframe,
                            f"{score:.3f}",
                            setup['score'],
                            ', '.join(setup['warnings'])
                        )
                        continue

                adx_val = setup.get('adx', 0.0)
                if not weekend_mode and adx_val < 15:
                    logger.info(
                        "Sinal bloqueado por ADX muito fraco | symbol=%s adx=%.1f timeframe=%s",
                        symbol, adx_val, timeframe,
                    )
                    continue

                if not weekend_mode and adx_val < 18 and 'MACD acelerando' not in ' '.join(setup['confirmations']):
                    logger.info(
                        "Sinal bloqueado | ADX moderado sem MACD | symbol=%s adx=%.1f timeframe=%s",
                        symbol, adx_val, timeframe,
                    )
                    continue

                primary_trend = 0 if weekend_mode else get_primary_trend(exchange, market_symbol, timeframe)
                primary_tf = get_higher_timeframe(timeframe)
                if primary_trend == signal:
                    setup['confirmations'].append(
                        f"tendencia primaria alinhada no {primary_tf}"
                    )

                confirm_signal = 0
                confirm_primary_trend = 0
                if timeframe == '1m' and not weekend_mode:
                    if m5_confirmation_context is None:
                        df_confirm = exchange.fetch_ohlcv(market_symbol, '5m', limit=200)
                        if df_confirm is not None and len(df_confirm) >= 30:
                            closed_confirm = df_confirm.iloc[:-1].copy()
                            if len(closed_confirm) >= 30:
                                tech_confirm = TechnicalIndicators(closed_confirm)
                                closed_confirm = tech_confirm.calculate_all_indicators(MONITOR_INDICATORS_CONFIG)
                                analyzer_confirm = TradingAnalyzer(closed_confirm)
                                confirm_signal = int(analyzer_confirm.get_current_signal()['signal'])
                                confirm_primary_trend = get_primary_trend(exchange, market_symbol, '5m')
                                m5_confirmation_context = (confirm_signal, confirm_primary_trend)
                            else:
                                m5_confirmation_context = (0, 0)
                        else:
                            m5_confirmation_context = (0, 0)

                    confirm_signal, confirm_primary_trend = m5_confirmation_context

                if weekend_mode:
                    entry_decision = {
                        'allowed': True,
                        'profile': (
                            'scalp reentrada 2x'
                            if timeframe_to_minutes(timeframe) <= 1
                            else 'rejeicao sniper' if 'falsa quebra' in setup['setup_type'] else 'range seletivo'
                        ),
                        'reason': 'setup de fim de semana validado',
                    }
                else:
                    entry_decision = classify_binary_entry(
                        timeframe,
                        signal,
                        probability,
                        setup,
                        consensus,
                        primary_trend,
                        confirm_signal=confirm_signal,
                        confirm_primary_trend=confirm_primary_trend,
                    )
                if not entry_decision['allowed']:
                    logger.info(
                        "Sinal descartado por filtro profissional | symbol=%s timeframe=%s direction=%s motivo=%s",
                        symbol,
                        timeframe,
                        'BUY' if signal == 1 else 'SELL',
                        entry_decision['reason'],
                    )
                    continue

                next_candle = get_next_candle_start(now, timeframe)
                seconds_to_next = (next_candle - now).total_seconds()
                effective_pre_alert_max = pre_alert_max_seconds
                effective_pre_alert_min = pre_alert_min_seconds
                if is_martingale_alert:
                    effective_pre_alert_max = min(pre_alert_max_seconds, MARTINGALE_REENTRY_MAX_SECONDS)
                    effective_pre_alert_min = max(0, min(pre_alert_min_seconds, MARTINGALE_REENTRY_MIN_SECONDS))

                if seconds_to_next > effective_pre_alert_max or seconds_to_next < effective_pre_alert_min:
                    continue

                pre_alert_key = f"{symbol_key}:{signal}:{next_candle.strftime('%Y%m%d%H%M')}"
                if last_pre_alert_key.get(symbol_key) == pre_alert_key:
                    continue

                evaluate_at = next_candle + timedelta(minutes=timeframe_to_minutes(timeframe))
                primary_trend_line = ""
                if primary_trend == signal:
                    primary_trend_line = f"\n📡 Tendência {primary_tf}: {'📈 ALTA' if signal == 1 else '📉 BAIXA'} ✅"
                elif primary_trend != 0:
                    primary_trend_line = f"\n📡 Tendência {primary_tf}: {'📈 ALTA' if primary_trend == 1 else '📉 BAIXA'} ⚠️ contra"

                emoji = "🟢" if signal == 1 else "🔴"
                action = "COMPRA" if signal == 1 else "VENDA"
                candidate_rank = score_monitor_candidate(
                    timeframe,
                    probability,
                    setup['score'],
                    consensus,
                    adx_val,
                    primary_trend,
                    signal,
                )
                if weekend_mode:
                    candidate_rank += 8.0
                elif entry_decision['profile'] == 'entrada direta':
                    candidate_rank += 12.0
                elif entry_decision['profile'] == 'aceita 1 protecao':
                    candidate_rank += 4.0

                entry_profile_label = entry_decision['profile'].upper()
                entry_profile_line = f"🛡 Perfil operacional: {entry_profile_label}"
                if timeframe == '1m' and confirm_signal == signal:
                    entry_profile_line += " | confirmação M5 ✅"

                protection_line = ""
                if entry_decision['profile'] == 'aceita 1 protecao':
                    first_protection = next_candle + timedelta(minutes=timeframe_to_minutes(timeframe))
                    protection_line = (
                        f"\n🚦 Gestão: se o primeiro candle falhar, no máximo 1 proteção em {first_protection.strftime('%H:%M')}"
                    )
                elif weekend_mode:
                    if timeframe_to_minutes(timeframe) <= 1:
                        first_protection = next_candle + timedelta(minutes=1)
                        second_protection = next_candle + timedelta(minutes=2)
                        protection_line = (
                            f"\n🚦 Gestão scalp weekend: se o contexto seguir valido, reemitir no maximo 2 martingales"
                            f"\n1ª proteção: {first_protection.strftime('%H:%M')}"
                            f"\n2ª proteção: {second_protection.strftime('%H:%M')}"
                        )
                    else:
                        protection_line = "\n🚦 Gestão fim de semana: operar só no extremo; se o preço correr, abortar a entrada"

                expiry_candles = int(setup.get('expiry_candles', 1)) if weekend_mode else 1
                expiry_minutes = expiry_candles * timeframe_to_minutes(timeframe)

                if is_martingale_alert:
                    message = f"""
⚠️ **ALERTA SIMPLES DE MARTINGALE**

{emoji} **{action} - {symbol}**

⏰ **Entrar até 10s da abertura do próximo candle ({next_candle.strftime('%H:%M')})**
💸 Sugestão: avaliar dobrar valor somente se o contexto ainda estiver limpo
🔁 Tentativa: {martingale_step} de {WEEKEND_MAX_REENTRIES}
🧠 Setup: {setup['setup_type']}
🏗 Score estrutural: {setup['score']}
📈 Probabilidade: {probability:.1f}%

🔎 Confirmações:
• """ + "\n• ".join(setup['confirmations']) + f"""

⏱ Timeframe: {timeframe}
🕐 {datetime.now().strftime('%H:%M:%S')}
                    """
                else:
                    message = f"""
🚨 **ALERTA DE SINAL!**

{emoji} **{action} - {symbol}**

⏰ **PRE-ALERTA (janela {int(effective_pre_alert_max)}s-{int(effective_pre_alert_min)}s): ENTRAR NA ABERTURA DO PRÓXIMO CANDLE ({next_candle.strftime('%H:%M')})**
💵 Preço Referência: ${current_price:,.2f}{primary_trend_line}
{entry_profile_line}
🧠 Setup: {setup['setup_type']}
🏗 Score estrutural: {setup['score']}/{max(8, min_setup_score + 1)}
📊 Score: {score:.3f}
📈 Probabilidade: {probability:.1f}%
✅ Consenso de indicadores: {consensus}/4

🔎 Confirmações:
• """ + "\n• ".join(setup['confirmations']) + f"""

⏱ Timeframe: {timeframe}
⏳ Expiração binária: {expiry_candles} candle{'s' if expiry_candles > 1 else ''} (~{expiry_minutes} min)
🕐 {datetime.now().strftime('%H:%M:%S')}
                    """

                if setup['warnings']:
                    message += "\n⚠️ Pontos de atenção:\n• " + "\n• ".join(setup['warnings'])
                message += protection_line

                candidate_alert = {
                    'message': message,
                    'symbol': symbol,
                    'market_symbol': market_symbol,
                    'signal': signal,
                    'entry_price': current_price,
                    'evaluate_at': next_candle + timedelta(minutes=expiry_minutes),
                    'candle_open_time': next_candle,
                    'pre_alert_key': pre_alert_key,
                    'symbol_key': symbol_key,
                    'timeframe': timeframe,
                    'rank': candidate_rank,
                    'entry_profile': entry_decision['profile'],
                    'martingale_alert': is_martingale_alert,
                    'martingale_step': martingale_step,
                }

                if alert_to_send is None or candidate_rank > alert_to_send.get('rank', float('-inf')):
                    alert_to_send = candidate_alert

        except Exception as e:
            logger.error(f"Erro ao monitorar {symbol}: {e}")
    
    if alert_to_send:
        if chat_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=alert_to_send['message'],
                parse_mode='Markdown'
            )
            monitor_last_alert_at = now
            monitor_last_heartbeat_at = now

        monitor_signals_sent += 1

        # Registra o sinal para avaliar no fechamento do candle seguinte
        pending_signal_evaluations.append({
            'symbol': alert_to_send['symbol'],
            'market_symbol': alert_to_send['market_symbol'],
            'timeframe': alert_to_send['timeframe'],
            'signal': alert_to_send['signal'],
            'entry_price': alert_to_send['entry_price'],
            'evaluate_at': alert_to_send['evaluate_at'],
            'candle_open_time': alert_to_send.get('candle_open_time'),
            'martingale_alert_sent': alert_to_send.get('martingale_alert', False),
            'symbol_key': alert_to_send['symbol_key'],
        })
        if not alert_to_send.get('evaluate_enabled', True):
            pending_signal_evaluations.pop()
        # Marca último sinal apenas após envio efetivo de alerta.
        last_signal[alert_to_send['symbol_key']] = alert_to_send['signal']
        last_pre_alert_key[alert_to_send['symbol_key']] = alert_to_send['pre_alert_key']
        last_direction_alert_at[f"{alert_to_send['symbol_key']}:{alert_to_send['signal']}"] = now
        if alert_to_send['entry_profile'] == 'scalp reentrada 2x':
            state_key = f"{alert_to_send['symbol_key']}:{alert_to_send['signal']}"
            prior_state = weekend_reentry_tracker.get(state_key, {})
            weekend_reentry_tracker[state_key] = {
                'alerts_sent': int(prior_state.get('alerts_sent', 0)) + 1,
                'last_at': now,
            }
            weekend_reentry_tracker.pop(
                f"{alert_to_send['symbol_key']}:{-alert_to_send['signal']}",
                None,
            )
        else:
            reset_weekend_reentry_state(alert_to_send['symbol_key'])

        entry_log = "n/a" if alert_to_send['entry_price'] is None else f"{alert_to_send['entry_price']:.4f}"
        logger.info(
            "Sinal registrado | symbol=%s timeframe=%s direction=%s entry=%s eval=%s sent=%s/%s",
            alert_to_send['symbol'],
            alert_to_send['timeframe'],
            'BUY' if alert_to_send['signal'] == 1 else 'SELL',
            entry_log,
            'on' if alert_to_send.get('evaluate_enabled', True) else 'off',
            monitor_signals_sent,
            MONITOR_MAX_SIGNALS
        )

        if monitor_signals_sent >= MONITOR_MAX_SIGNALS and not pending_signal_evaluations:
            monitoring_active = False
            monitor_end_time = None
            monitor_target_chat_id = None
            monitor_started_at = None
            monitor_last_alert_at = None
            monitor_last_heartbeat_at = None
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "⏹ **Monitoramento finalizado automaticamente**\n\n"
                        f"Limite de {MONITOR_MAX_SIGNALS} sinais atingido.\n"
                        "Use /monitor on para iniciar um novo ciclo."
                    ),
                    parse_mode='Markdown'
                )
    elif chat_id and MONITOR_HEARTBEAT_SECONDS > 0:
        should_send_heartbeat = False
        if monitor_last_heartbeat_at is None:
            should_send_heartbeat = True
        else:
            should_send_heartbeat = (now - monitor_last_heartbeat_at).total_seconds() >= MONITOR_HEARTBEAT_SECONDS

        if should_send_heartbeat:
            if monitor_last_alert_at is None and monitor_started_at is not None:
                idle_seconds = int((now - monitor_started_at).total_seconds())
            elif monitor_last_alert_at is not None:
                idle_seconds = int((now - monitor_last_alert_at).total_seconds())
            else:
                idle_seconds = 0

            idle_min = idle_seconds // 60
            idle_sec = idle_seconds % 60
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "📡 Monitor ativo (sem novo sinal ainda)\n"
                    f"⏱ Timeframe: {get_monitor_timeframe_label()}\n"
                    f"📊 Ativos monitorados: {len(monitored_symbols)}\n"
                    f"🕒 Último sinal há: {idle_min}m {idle_sec}s\n"
                    f"📌 Sinais enviados: {monitor_signals_sent}/{MONITOR_MAX_SIGNALS}"
                )
            )
            monitor_last_heartbeat_at = now


def main():
    """Inicia o bot do Telegram"""
    if not acquire_instance_lock():
        print("❌ Já existe outra instância do bot rodando.")
        print("Finalize a instância anterior antes de iniciar uma nova.")
        return

    # Carrega token por perfil (ex.: TELEGRAM_BOT_TOKEN_OTC)
    token = get_telegram_bot_token()
    
    if not token:
        print(f"❌ TELEGRAM_BOT_TOKEN não encontrado para perfil '{BOT_PROFILE}'!")
        print("Configure o token no arquivo .env ou config/config.py")
        print("\nPara criar um bot:")
        print("1. Abra o Telegram e procure por @BotFather")
        print("2. Digite /newbot e siga as instruções")
        print("3. Copie o token e adicione no .env:")
        print("   TELEGRAM_BOT_TOKEN_MAIN=seu_token_main")
        print("   TELEGRAM_BOT_TOKEN_OTC=seu_token_otc")
        return
    
    print(f"🤖 Iniciando Bot do Telegram (perfil: {BOT_PROFILE})...")
    print(f"📊 Mercado: {CURRENT_MARKET_TYPE} | Timeframe inicial: {config.TIMEFRAME}")
    
    # Cria aplicação
    application = Application.builder().token(token).build()
    
    # Adiciona handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("ativos", ativos_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("modo", modo_command))
    application.add_handler(CommandHandler("timeframe", timeframe_command))
    application.add_handler(CommandHandler("tf", timeframe_command))
    application.add_handler(CommandHandler("timefrafe", timeframe_command))
    application.add_handler(CommandHandler("ativo", ativo_command))
    application.add_handler(CommandHandler("monitor", monitor_command))
    application.add_handler(CommandHandler("monito", monitor_command))
    application.add_handler(CommandHandler("analise", analise_command))
    application.add_handler(CommandHandler("btc", btc_command))
    application.add_handler(CommandHandler("bitcoin", btc_command))
    application.add_handler(CommandHandler("btcusdt", btc_command))
    application.add_handler(CommandHandler("eth", eth_command))
    application.add_handler(CommandHandler("ethereum", eth_command))
    application.add_handler(CommandHandler("ethusdt", eth_command))
    application.add_handler(CommandHandler("sol", sol_command))
    application.add_handler(CommandHandler("bnb", bnb_command))
    application.add_handler(CommandHandler("ada", ada_command))
    application.add_handler(CommandHandler("xrp", xrp_command))
    application.add_handler(CommandHandler("ltc", ltc_command))
    application.add_handler(CommandHandler("ouro", ouro_command))
    application.add_handler(CommandHandler("xau", xau_command))
    application.add_handler(CommandHandler("sp500", sp500_command))
    application.add_handler(CommandHandler("externo", externo_command))
    application.add_handler(CommandHandler("sinal_externo", externo_command))
    application.add_handler(CommandHandler("listar_externos", listar_externos_command))
    application.add_handler(CommandHandler("scan_auto", scan_auto_command))
    application.add_handler(CommandHandler("bitget_status", bitget_status_command))
    application.add_handler(CommandHandler("bitget_toggle", bitget_toggle_command))
    application.add_handler(CommandHandler("bitget_config", bitget_config_command))
    application.add_handler(CommandHandler("bitget_limits", bitget_limits_command))
    application.add_handler(CommandHandler("eco", eco_command))
    # Handlers para sinais externos (PocketOption, outros bots, canais)
    application.add_handler(CommandHandler("pocket_add", pocket_add_command))
    application.add_handler(CommandHandler("pocket_recent", pocket_recent_command))
    application.add_handler(CommandHandler("pocket_compare", pocket_compare_command))
    application.add_handler(CommandHandler("pocket_help", pocket_help_command))
    
    # Job queue para monitoramento e avaliação de sinais pendentes
    job_queue = application.job_queue
    job_queue.run_repeating(
        monitor_market,
        interval=MONITOR_INTERVAL_SECONDS,
        first=MONITOR_INTERVAL_SECONDS
    )
    job_queue.run_repeating(
        check_paper_trades,
        interval=120,   # a cada 2 minutos
        first=30        # primeira verificação 30s após o boot
    )
    job_queue.run_repeating(
        auto_scan_externos,
        interval=SCAN_POLL_SECONDS,
        first=min(60, SCAN_POLL_SECONDS)
    )
    job_queue.run_repeating(
        alert_upcoming_events,
        interval=600,   # a cada 10 minutos
        first=120       # primeira verificação 2 min após o boot
    )

    auto_started, auto_reason = bootstrap_auto_monitoring()
    if auto_started:
        job_queue.run_once(notify_auto_monitor_started, when=1)
        print(f"▶️ Monitoramento autoativado: {', '.join(monitored_symbols)}")

    if SCAN_AUTO_START:
        global _auto_scan_active
        _auto_scan_active = True
        print("▶️ Scan automático Bitget autoativado (SCAN_AUTO_START=true)")
    elif MONITOR_AUTO_START and auto_reason:
        print(f"⚠️ Auto-monitoramento não iniciado: {auto_reason}")
    
    print(f"✅ Bot iniciado com sucesso! (perfil: {BOT_PROFILE})")
    print("📱 Procure seu bot no Telegram e envie /start")
    print("⏸  Pressione Ctrl+C para parar\n")
    
    # Inicia o bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
