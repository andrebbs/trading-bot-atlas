"""
Trade configuration and daily limit tracking.
Manages: max trades per day, risk %, leverage, loss limit.
Persists settings and daily counters to logs/trade_config.json
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional, Tuple


CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'trade_config.json')


# Default configuration
DEFAULT_CONFIG = {
    'max_trades_per_day': 5,
    'risk_pct': 1.0,
    'leverage': 5,
    'daily_loss_limit_pct': 3.0,  # Stop if daily loss > 3% of balance
    'require_market_good': False,  # If true, only trade when market quality is "good"
}


def _ensure_config_file():
    """Create config file if it doesn't exist."""
    if not os.path.exists(CONFIG_FILE):
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            today = datetime.utcnow().strftime('%Y-%m-%d')
            data = {
                'config': DEFAULT_CONFIG,
                'today': today,
                'trades_count': 0,
                'daily_pnl': 0.0,
                'updated': datetime.utcnow().isoformat(),
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def _load_config() -> Dict:
    """Load configuration from file."""
    _ensure_config_file()
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    
    today = datetime.utcnow().strftime('%Y-%m-%d')
    return {
        'config': DEFAULT_CONFIG.copy(),
        'today': today,
        'trades_count': 0,
        'daily_pnl': 0.0,
        'updated': datetime.utcnow().isoformat(),
    }


def _save_config(data: Dict):
    """Save configuration to file."""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        data['updated'] = datetime.utcnow().isoformat()
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _reset_daily_if_needed(data: Dict) -> Dict:
    """Reset daily counters if date changed."""
    today = datetime.utcnow().strftime('%Y-%m-%d')
    if data.get('today') != today:
        data['today'] = today
        data['trades_count'] = 0
        data['daily_pnl'] = 0.0
        _save_config(data)
    return data


def get_config() -> Dict:
    """Get current configuration."""
    data = _load_config()
    data = _reset_daily_if_needed(data)
    return data.get('config', DEFAULT_CONFIG.copy())


def update_config(updates: Dict) -> Dict:
    """Update configuration. Returns new config."""
    data = _load_config()
    data = _reset_daily_if_needed(data)
    cfg = data.get('config', DEFAULT_CONFIG.copy())
    
    # Update only allowed keys
    allowed_keys = set(DEFAULT_CONFIG.keys())
    for k, v in updates.items():
        if k in allowed_keys:
            # Validate values
            if k == 'max_trades_per_day' and isinstance(v, int) and v > 0:
                cfg[k] = v
            elif k == 'risk_pct' and isinstance(v, (int, float)) and 0 < v <= 5:
                cfg[k] = float(v)
            elif k == 'leverage' and isinstance(v, int) and 1 <= v <= 10:
                cfg[k] = v
            elif k == 'daily_loss_limit_pct' and isinstance(v, (int, float)) and v > 0:
                cfg[k] = float(v)
            elif k == 'require_market_good' and isinstance(v, bool):
                cfg[k] = v
    
    data['config'] = cfg
    _save_config(data)
    return cfg


def get_daily_stats() -> Dict:
    """Get today's trade stats: count, P&L, limits."""
    data = _load_config()
    data = _reset_daily_if_needed(data)
    cfg = data.get('config', DEFAULT_CONFIG.copy())
    
    return {
        'trades_today': data.get('trades_count', 0),
        'max_trades': cfg['max_trades_per_day'],
        'daily_pnl': data.get('daily_pnl', 0.0),
        'daily_loss_limit': cfg['daily_loss_limit_pct'],
        'risk_pct': cfg['risk_pct'],
        'leverage': cfg['leverage'],
        'require_market_good': cfg['require_market_good'],
    }


def can_trade(market_quality: Optional[str] = None) -> Tuple[bool, str]:
    """
    Check if trading is allowed.
    
    Args:
        market_quality: "good", "neutral", or "risky" (optional)
    
    Returns:
        (allowed: bool, reason: str)
    """
    data = _load_config()
    data = _reset_daily_if_needed(data)
    cfg = data.get('config', DEFAULT_CONFIG.copy())
    
    # Check trade count
    if data.get('trades_count', 0) >= cfg['max_trades_per_day']:
        return False, 'Limite diario de %d trades atingido' % cfg['max_trades_per_day']
    
    # Check daily P&L limit
    if data.get('daily_pnl', 0.0) < 0 and abs(data['daily_pnl']) / 1000.0 * 100 > cfg['daily_loss_limit_pct']:
        return False, 'Limite de perda diaria (%.1f%%) atingido' % cfg['daily_loss_limit_pct']
    
    # Check market quality requirement
    if cfg['require_market_good'] and market_quality != 'good':
        return False, 'Mercado nao esta bom (qualidade: %s)' % (market_quality or 'unknown')
    
    return True, 'OK'


def increment_trade_count():
    """Increment today's trade count."""
    data = _load_config()
    data = _reset_daily_if_needed(data)
    data['trades_count'] = data.get('trades_count', 0) + 1
    _save_config(data)


def update_daily_pnl(pnl_amount: float):
    """Update today's P&L (called after trade closes)."""
    data = _load_config()
    data = _reset_daily_if_needed(data)
    data['daily_pnl'] = data.get('daily_pnl', 0.0) + pnl_amount
    _save_config(data)


def reset_daily_stats():
    """Manually reset daily stats (admin only)."""
    data = _load_config()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    data['today'] = today
    data['trades_count'] = 0
    data['daily_pnl'] = 0.0
    _save_config(data)
