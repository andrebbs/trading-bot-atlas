"""
BitGet Futures Executor
-----------------------
Paper mode (padrão): simula ordens localmente, registra em logs/paper_trades.json
Live mode: executa ordens reais via ccxt na BitGet Futures (linear USDT)

Ativação:
  BITGET_PAPER_TRADING=true   → paper (padrão, seguro)
  BITGET_PAPER_TRADING=false  → live (real money!)

Variáveis de ambiente:
  API_KEY, API_SECRET, BITGET_PASSPHRASE
  BITGET_RISK_PCT   (padrão 1.0 — 1% do saldo por trade)
  BITGET_LEVERAGE   (padrão 5)
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from . import trade_config
except ImportError:
    trade_config = None

logger = logging.getLogger(__name__)

PAPER_TRADING   = os.getenv('BITGET_PAPER_TRADING', 'true').lower() != 'false'
RISK_PCT        = float(os.getenv('BITGET_RISK_PCT', '1.0'))
LEVERAGE        = int(os.getenv('BITGET_LEVERAGE', '5'))
API_KEY         = os.getenv('API_KEY', '')
API_SECRET      = os.getenv('API_SECRET', '')
PASSPHRASE      = os.getenv('BITGET_PASSPHRASE', '')
# SUSDT-FUTURES = simulator Bitget | USDT-FUTURES = live real
PRODUCT_TYPE    = os.getenv('BITGET_PRODUCT_TYPE', 'USDT-FUTURES')
# Moeda para leitura de saldo: SUSDT no simulator, USDT no live
BALANCE_COIN    = 'SUSDT' if PRODUCT_TYPE == 'SUSDT-FUTURES' else 'USDT'
# marginCoin: SUSDT no simulator, USDT no live
MARGIN_COIN     = 'SUSDT' if PRODUCT_TYPE == 'SUSDT-FUTURES' else 'USDT'

PAPER_LOG_PATH  = Path(__file__).parent.parent.parent / 'logs' / 'paper_trades.json'
PAPER_LOG_PATH.parent.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Paper trade store (em memória + persist em JSON)
# ─────────────────────────────────────────────────────────────────────────────

def _load_paper_trades() -> list:
    if PAPER_LOG_PATH.exists():
        try:
            return json.loads(PAPER_LOG_PATH.read_text())
        except Exception:
            return []
    return []


def _save_paper_trades(trades: list):
    try:
        PAPER_LOG_PATH.write_text(json.dumps(trades, indent=2, default=str))
    except Exception as e:
        logger.warning('Erro ao salvar paper trades: %s', e)


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _get_exchange():
    """Retorna instância ccxt BitGet configurada para futures."""
    try:
        import ccxt
    except ImportError:
        raise RuntimeError('ccxt não instalado. Execute: pip install ccxt')

    exchange = ccxt.bitget({
        'apiKey':     API_KEY,
        'secret':     API_SECRET,
        'password':   PASSPHRASE,
        'options':    {'defaultType': 'swap'},  # linear perpetual
        'enableRateLimit': True,
    })
    return exchange


def _fetch_live_price(symbol_usdt: str) -> float:
    """Busca preço atual via ccxt (sem autenticação)."""
    try:
        import ccxt
        ex = ccxt.bitget({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        ticker = ex.fetch_ticker(symbol_usdt + '/USDT:USDT')
        return float(ticker['last'])
    except Exception as e:
        logger.warning('Erro ao buscar preço %s: %s', symbol_usdt, e)
        return 0.0


def _calc_position_size(balance_usdt: float, price: float, risk_pct: float, leverage: int) -> float:
    """
    Calcula quantidade de contratos para arriscar risk_pct% do saldo.
    Com alavancagem: qty = (saldo * risk_pct/100 * leverage) / price
    """
    if price <= 0:
        return 0.0
    notional = balance_usdt * (risk_pct / 100) * leverage
    return notional / price


def _get_minimum_order_amount(exchange, symbol_ccxt: str) -> float:
    try:
        exchange.load_markets()
        market = exchange.markets.get(symbol_ccxt)
        if not market:
            return 0.0
        amount_limits = market.get('limits', {}).get('amount', {})
        min_amount = amount_limits.get('min')
        if min_amount is not None:
            return float(min_amount)
    except Exception:
        pass
    return 0.0


def _round_order_qty(exchange, symbol_ccxt: str, qty: float) -> float:
    try:
        return float(exchange.amount_to_precision(symbol_ccxt, qty))
    except Exception:
        return float(round(qty, 6))


def _create_market_order_with_fallback(exchange, symbol_ccxt: str, side: str, qty: float, params: dict):
    min_qty = _get_minimum_order_amount(exchange, symbol_ccxt)
    if qty <= 0:
        raise ValueError('Quantidade inválida para ordem')

    qty = _round_order_qty(exchange, symbol_ccxt, qty)
    if min_qty and qty < min_qty:
        qty = min_qty

    last_error = None
    while qty >= (min_qty or 0.0):
        try:
            order = exchange.create_market_order(symbol_ccxt, side, qty, params=params)
            return order, qty
        except Exception as e:
            last_error = e
            msg = str(e).lower()
            if 'order amount exceeds the balance' in msg or 'insufficientfunds' in msg:
                qty = max(_round_order_qty(exchange, symbol_ccxt, qty * 0.5), min_qty or 0.0)
                if min_qty and qty < min_qty:
                    break
                continue
            if 'less than the minimum amount' in msg or 'must be greater than minimum amount' in msg:
                break
            raise
    raise last_error


# ─────────────────────────────────────────────────────────────────────────────
# Interface principal
# ─────────────────────────────────────────────────────────────────────────────

def get_market_quality(rsi: float, close_price: float, ema9: float) -> str:
    """
    Qualifica a qualidade do mercado para trading.
    
    Retorna: 'good', 'neutral', ou 'risky'
    
    Critérios:
    - good: RSI entre 35-65 (neutro) + EMA9 alinhada com preço
    - neutral: RSI fora dos extremos mas sem confirmação EMA9
    - risky: RSI extremo (< 20 ou > 80) ou preço desalinhado
    """
    if ema9 <= 0:
        ema_aligned = False
    else:
        ema_diff_pct = abs(close_price - ema9) / ema9 * 100
        ema_aligned = ema_diff_pct <= 1.0  # Menos de 1% de distância
    
    if 35 <= rsi <= 65 and ema_aligned:
        return 'good'
    elif rsi < 15 or rsi > 85:
        return 'risky'
    else:
        return 'neutral'


def execute_trade(asset: str, bitget_symbol: str, direction: str,
                  price: float, rsi: float, quality: str,
                  ema9: Optional[float] = None,
                  market_quality: Optional[str] = None,
                  force_override: bool = False) -> dict:
    """
    Executa ou simula um trade, respeitando limites diários.

    Parâmetros:
      asset            : ex. 'BTC'
      bitget_symbol    : ex. 'BTCUSDT'
      direction        : 'BUY' ou 'SELL'
      price            : preço atual (float)
      rsi              : RSI atual
      quality          : string de qualidade (ex. 'FORTE 🎯')
      ema9             : EMA9 para qualificação de mercado
      market_quality   : override da qualidade (None = calcular)
      force_override   : True = ignora limites diários (admin)

    Retorna dict com resultado do trade.
    """
    side = 'buy' if direction == 'BUY' else 'sell'
    mode = 'PAPER' if PAPER_TRADING else 'LIVE'
    ts   = datetime.now().isoformat()
    
    # Verifica limites diários
    if trade_config and not force_override:
        if market_quality is None and ema9:
            market_quality = get_market_quality(rsi, price, ema9)
        
        can_trade, reason = trade_config.can_trade(market_quality)
        if not can_trade:
            return {'ok': False, 'error': reason, 'mode': mode, 'reason': 'limit_exceeded'}

    if PAPER_TRADING:
        # ── Simulação ─────────────────────────────────────────────────────────
        paper_balance = _get_paper_balance()
        qty = _calc_position_size(paper_balance, price, RISK_PCT, LEVERAGE)
        if qty <= 0:
            return {'ok': False, 'error': 'Saldo paper insuficiente', 'mode': mode}

        trade = {
            'id':       int(time.time() * 1000),
            'mode':     'PAPER',
            'ts':       ts,
            'asset':    asset,
            'symbol':   bitget_symbol,
            'side':     side.upper(),
            'price':    price,
            'qty':      round(qty, 6),
            'notional': round(qty * price, 2),
            'leverage': LEVERAGE,
            'risk_pct': RISK_PCT,
            'rsi':      rsi,
            'quality':  quality,
            'market_quality': market_quality or 'unknown',
            'status':   'OPEN',
            'pnl':      None,
        }
        trades = _load_paper_trades()
        trades.append(trade)
        _save_paper_trades(trades)
        
        # Incrementa contador diário
        if trade_config:
            trade_config.increment_trade_count()
        
        logger.info('[PAPER] %s %s @ %.4f  qty=%.6f  notional=$%.2f  market=%s',
                    side.upper(), asset, price, qty, qty * price, market_quality or 'unknown')
        return {'ok': True, 'trade': trade, 'mode': mode}

    else:
        # ── Live / Simulator Bitget ───────────────────────────────────────────
        if not API_KEY or not API_SECRET or not PASSPHRASE:
            return {'ok': False, 'error': 'Credenciais BitGet não configuradas', 'mode': mode}
        env_label = 'SIMULATOR' if PRODUCT_TYPE == 'SUSDT-FUTURES' else 'LIVE'
        try:
            exchange = _get_exchange()
            balance_info = exchange.fetch_balance({'productType': PRODUCT_TYPE})
            free_bal = float(balance_info.get(BALANCE_COIN, {}).get('free', 0))
            qty = _calc_position_size(free_bal, price, RISK_PCT, LEVERAGE)
            if qty <= 0:
                return {'ok': False, 'error': f'Saldo {BALANCE_COIN} insuficiente ({free_bal:.2f})', 'mode': mode}

            base = bitget_symbol.replace('USDT', '').replace('_UMCBL', '')
            symbol_ccxt = base + '/USDT:USDT'
            # Define alavancagem
            try:
                exchange.set_leverage(LEVERAGE, symbol_ccxt, {'productType': PRODUCT_TYPE})
            except Exception:
                pass

            qty = _round_order_qty(exchange, symbol_ccxt, qty)
            min_qty = _get_minimum_order_amount(exchange, symbol_ccxt)
            if min_qty and qty < min_qty:
                qty = min_qty

            try:
                order, executed_qty = _create_market_order_with_fallback(
                    exchange,
                    symbol_ccxt,
                    side,
                    qty,
                    {
                        'productType': PRODUCT_TYPE,
                        'tradeSide': 'open',   # one-way mode: open position
                    }
                )
                logger.info('[%s] Ordem executada: %s', env_label, order)
                return {'ok': True, 'order': order, 'qty': executed_qty, 'price': price, 'mode': env_label}
            except Exception as e:
                logger.error('[%s] Erro ao executar ordem %s %s: %s', env_label, side, asset, e)
                return {'ok': False, 'error': str(e), 'mode': mode}
        except Exception as e:
            logger.error('[%s] Erro ao executar ordem %s %s: %s', env_label, side, asset, e)
            return {'ok': False, 'error': str(e), 'mode': mode}


# ─────────────────────────────────────────────────────────────────────────────
# Paper balance simulado
# ─────────────────────────────────────────────────────────────────────────────

_PAPER_INITIAL_BALANCE = 1000.0  # $1000 simulados para começar

def _get_paper_balance() -> float:
    """Saldo paper = inicial - notional das posições abertas."""
    trades = _load_paper_trades()
    open_notional = sum(t['notional'] for t in trades if t.get('status') == 'OPEN')
    return max(0.0, _PAPER_INITIAL_BALANCE - open_notional / LEVERAGE)


def get_paper_summary() -> dict:
    """Retorna resumo das operações paper."""
    trades = _load_paper_trades()
    open_trades   = [t for t in trades if t.get('status') == 'OPEN']
    closed_trades = [t for t in trades if t.get('status') == 'CLOSED']
    total_pnl     = sum(t.get('pnl') or 0.0 for t in closed_trades)
    return {
        'mode':          'PAPER' if PAPER_TRADING else 'LIVE',
        'balance':       _get_paper_balance(),
        'initial':       _PAPER_INITIAL_BALANCE,
        'open':          len(open_trades),
        'closed':        len(closed_trades),
        'total_pnl':     total_pnl,
        'open_trades':   open_trades,
        'closed_trades': closed_trades[-5:],  # últimas 5
    }


def is_paper_mode() -> bool:
    return PAPER_TRADING


def is_configured() -> bool:
    """Verifica se credenciais estão preenchidas."""
    return bool(API_KEY and API_SECRET and PASSPHRASE)


# ─────────────────────────────────────────────────────────────────────────────
# Configuração TP / SL / Timeout (paper trading)
# ─────────────────────────────────────────────────────────────────────────────

TP_PCT          = float(os.getenv('BITGET_TP_PCT',          '1.5'))   # % no ativo → TP
SL_PCT          = float(os.getenv('BITGET_SL_PCT',          '1.0'))   # % no ativo → SL
MAX_TRADE_HOURS = float(os.getenv('BITGET_MAX_TRADE_HOURS', '4.0'))   # timeout (horas)


def close_paper_trade(trade_id: int, exit_price: float, reason: str) -> dict:
    """
    Fecha manualmente um paper trade pelo ID.
    Retorna o trade atualizado, ou dict vazio se não encontrado.
    """
    trades = _load_paper_trades()
    updated = {}
    for t in trades:
        if t.get('id') == trade_id and t.get('status') == 'OPEN':
            entry = t['price']
            qty   = t['qty']
            side  = t['side'].upper()
            pnl   = qty * (exit_price - entry) if side == 'BUY' else qty * (entry - exit_price)
            t['status']       = 'CLOSED'
            t['exit_price']   = round(exit_price, 8)
            t['exit_ts']      = datetime.now().isoformat()
            t['close_reason'] = reason
            t['pnl']          = round(pnl, 4)
            t['result']       = 'WIN' if pnl > 0 else 'LOSS'
            updated = t
            break
    if updated:
        _save_paper_trades(trades)
        logger.info('[PAPER] FECHADO %s %s entry=%.4f exit=%.4f pnl=%.4f reason=%s',
                    updated['side'], updated['asset'], updated['price'],
                    exit_price, updated['pnl'], reason)
    return updated


def update_open_paper_trades() -> list:
    """
    Verifica preços atuais de todos os paper trades OPEN.
    Fecha os que atingiram TP, SL ou timeout, em lote (uma só escrita).

    Retorna lista dos trades fechados nesta chamada (cada item é o dict atualizado).
    """
    from datetime import timezone

    trades      = _load_paper_trades()
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    if not open_trades:
        return []

    closed_now      = []
    trades_modified = False
    now_utc         = datetime.now(timezone.utc)

    for t in open_trades:
        asset       = t.get('asset', '')
        entry_price = t['price']
        side        = t['side'].upper()

        # ── Tempo aberto ──────────────────────────────────────────────────
        try:
            open_dt = datetime.fromisoformat(t.get('ts', ''))
            if open_dt.tzinfo is None:
                open_dt = open_dt.replace(tzinfo=timezone.utc)
            elapsed_h = (now_utc - open_dt).total_seconds() / 3600
        except Exception:
            elapsed_h = 0.0

        # ── Preço atual ───────────────────────────────────────────────────
        current_price = _fetch_live_price(asset)
        if current_price <= 0:
            continue   # falha de API — tenta na próxima rodada

        # ── Checar TP / SL / Timeout ──────────────────────────────────────
        if side == 'BUY':
            tp_hit = current_price >= entry_price * (1 + TP_PCT / 100)
            sl_hit = current_price <= entry_price * (1 - SL_PCT / 100)
        else:
            tp_hit = current_price <= entry_price * (1 - TP_PCT / 100)
            sl_hit = current_price >= entry_price * (1 + SL_PCT / 100)
        timeout_hit = elapsed_h >= MAX_TRADE_HOURS

        if tp_hit:
            reason = f'TP+{TP_PCT}%'
        elif sl_hit:
            reason = f'SL-{SL_PCT}%'
        elif timeout_hit:
            reason = f'TIMEOUT_{elapsed_h:.1f}h'
        else:
            continue

        # ── Fechar o trade ────────────────────────────────────────────────
        qty = t['qty']
        pnl = qty * (current_price - entry_price) if side == 'BUY' \
              else qty * (entry_price - current_price)

        t['status']       = 'CLOSED'
        t['exit_price']   = round(current_price, 8)
        t['exit_ts']      = now_utc.isoformat()
        t['close_reason'] = reason
        t['pnl']          = round(pnl, 4)
        t['result']       = 'WIN' if pnl > 0 else 'LOSS'
        closed_now.append(t)
        trades_modified = True

        logger.info('[PAPER] FECHADO %s %s entry=%.4f exit=%.4f pnl=%.4f reason=%s',
                    side, asset, entry_price, current_price, pnl, reason)

    if trades_modified:
        _save_paper_trades(trades)

    return closed_now
