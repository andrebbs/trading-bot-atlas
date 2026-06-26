"""
Parser de sinais do bot/canal Telegram da PocketOption.

Este módulo extrai informações estruturadas de mensagens de sinais
recebidas de canais de trading.
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Representa um sinal de trading extraído de mensagem."""
    source: str  # 'pocketoption', 'manual', etc
    timestamp: datetime
    asset: str  # 'EUR/USD', 'BTCUSD', etc
    signal: str  # 'CALL', 'PUT'
    timeframe: str  # '1m', '5m', '15m'
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    confidence: Optional[str] = None  # 'high', 'medium', 'low'
    expiry_time: Optional[str] = None
    strategy_name: Optional[str] = None
    raw_message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'asset': self.asset,
            'signal': self.signal,
            'timeframe': self.timeframe,
            'entry_price': self.entry_price,
            'target_price': self.target_price,
            'stop_loss': self.stop_loss,
            'confidence': self.confidence,
            'expiry_time': self.expiry_time,
            'strategy_name': self.strategy_name,
        }


class PocketSignalParser:
    """Parser inteligente de mensagens de sinais de trading."""

    LABELED_ASSET_PATTERNS = [
        r'(?:ATIVO|ASSET)\s*[:\-]\s*([^\n\r]+)',
    ]

    ASSET_ALIASES = {
        'BITCOIN': 'BTC/USDT',
        'BTC': 'BTC/USDT',
        'ETHEREUM': 'ETH/USDT',
        'ETHER': 'ETH/USDT',
        'ETH': 'ETH/USDT',
        'SOLANA': 'SOL/USDT',
        'SOL': 'SOL/USDT',
        'BINANCE COIN': 'BNB/USDT',
        'BNB': 'BNB/USDT',
        'RIPPLE': 'XRP/USDT',
        'XRP': 'XRP/USDT',
        'CARDANO': 'ADA/USDT',
        'ADA': 'ADA/USDT',
        'LITECOIN': 'LTC/USDT',
        'LTC': 'LTC/USDT',
        'GOLD': 'XAU/USD',
        'OURO': 'XAU/USD',
        'XAU': 'XAU/USD',
        'PAXG': 'PAXG/USDT',
        'OIL': 'OIL',
    }

    KNOWN_ASSET_CODES = {
        'ADA', 'AUD', 'BNB', 'BTC', 'CAD', 'CHF', 'DOGE', 'ETH', 'EUR',
        'GBP', 'JPY', 'LTC', 'NZD', 'PAXG', 'SOL', 'USD', 'USDC', 'USDT',
        'XAG', 'XAU', 'XRP',
    }
    
    SIGNAL_PATTERNS = [
        r'\b(CALL|BUY|COMPRA|UP|⬆️|🟢)\b',
        r'\b(PUT|SELL|VENDA|DOWN|⬇️|🔴)\b',
    ]
    
    TIMEFRAME_PATTERNS = [
        r'(\d+)\s*(?:min|m|minutos?)',  # 5m, 5 min, 5 minutos
        r'M(\d+)',  # M5, M15
        r'(\d+)M\b',  # 5M, 15M
    ]
    
    def __init__(self):
        self.signal_history: List[TradingSignal] = []
    
    def parse(self, message: str, source: str = 'unknown') -> Optional[TradingSignal]:
        """
        Analisa mensagem e extrai sinal de trading.
        
        Args:
            message: Texto da mensagem
            source: Origem (nome do canal/bot)
            
        Returns:
            TradingSignal se encontrado, None caso contrário
        """
        message = message.strip()
        
        # Extrair ativo
        asset = self._extract_asset(message)
        if not asset:
            logger.debug(f"Nenhum ativo encontrado em: {message[:50]}...")
            return None
        
        # Extrair sinal CALL/PUT
        signal = self._extract_signal(message)
        if not signal:
            logger.debug(f"Nenhum sinal CALL/PUT em: {message[:50]}...")
            return None
        
        # Extrair timeframe
        timeframe = self._extract_timeframe(message) or '5m'
        
        # Extrair preços (se houver)
        entry_price = self._extract_price(message, 'entry')
        target_price = self._extract_price(message, 'target')
        stop_loss = self._extract_price(message, 'stop')
        
        # Extrair confiança
        confidence = self._extract_confidence(message)
        
        # Criar objeto de sinal
        trading_signal = TradingSignal(
            source=source,
            timestamp=datetime.now(),
            asset=asset,
            signal=signal,
            timeframe=timeframe,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            confidence=confidence,
            raw_message=message,
        )
        
        # Armazenar em histórico
        self.signal_history.append(trading_signal)
        
        # Manter apenas últimos 100 sinais
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]
        
        logger.info(f"✅ Sinal detectado: {asset} {signal} {timeframe} de {source}")
        return trading_signal
    
    def _extract_asset(self, text: str) -> Optional[str]:
        """Extrai nome do ativo da mensagem."""
        text_upper = text.upper()

        for pattern in self.LABELED_ASSET_PATTERNS:
            match = re.search(pattern, text_upper)
            if match:
                asset = self._normalize_asset(match.group(1))
                if asset:
                    return asset

        otc_match = re.search(r'\b([A-Z]{3,5})[/-]?([A-Z]{3,5})\s*OTC\b', text_upper)
        if otc_match:
            asset = self._normalize_asset(f"{otc_match.group(1)}/{otc_match.group(2)}")
            if asset:
                return f"{asset} OTC"

        for match in re.finditer(r'\b([A-Z]{3,5})[/-]?([A-Z]{3,5})\b', text_upper):
            asset = self._normalize_asset(f"{match.group(1)}/{match.group(2)}")
            if asset:
                return asset

        for alias in sorted(self.ASSET_ALIASES, key=len, reverse=True):
            if re.search(rf'\b{re.escape(alias)}\b', text_upper):
                return self.ASSET_ALIASES[alias]

        return None

    def _normalize_asset(self, raw_asset: str) -> Optional[str]:
        """Normaliza ativo bruto para um símbolo conhecido."""
        asset = re.sub(r'[^A-Z0-9/\- ]+', ' ', (raw_asset or '').upper())
        asset = re.sub(r'\s+', ' ', asset).strip()

        if not asset:
            return None

        if asset.endswith(' OTC'):
            normalized = self._normalize_asset(asset[:-4])
            return f"{normalized} OTC" if normalized else None

        alias = self.ASSET_ALIASES.get(asset)
        if alias:
            return alias

        compact = asset.replace(' ', '')
        alias = self.ASSET_ALIASES.get(compact)
        if alias:
            return alias

        candidate = compact.replace('-', '/').replace('//', '/')
        if '/' in candidate:
            base, quote = candidate.split('/', 1)
            if base in self.KNOWN_ASSET_CODES and quote in self.KNOWN_ASSET_CODES:
                return f"{base}/{quote}"
            return None

        for split_idx in (3, 4, 5):
            if split_idx >= len(candidate):
                continue
            base = candidate[:split_idx]
            quote = candidate[split_idx:]
            if base in self.KNOWN_ASSET_CODES and quote in self.KNOWN_ASSET_CODES:
                return f"{base}/{quote}"

        return None
    
    def _extract_signal(self, text: str) -> Optional[str]:
        """Extrai direção do sinal (CALL ou PUT)."""
        text_upper = text.upper()
        
        # Procurar CALL/BUY
        if re.search(self.SIGNAL_PATTERNS[0], text_upper):
            return 'CALL'
        
        # Procurar PUT/SELL
        if re.search(self.SIGNAL_PATTERNS[1], text_upper):
            return 'PUT'
        
        # Detectar por emojis
        if '🟢' in text or '⬆️' in text or '📈' in text:
            return 'CALL'
        if '🔴' in text or '⬇️' in text or '📉' in text:
            return 'PUT'
        
        return None
    
    def _extract_timeframe(self, text: str) -> Optional[str]:
        """Extrai timeframe da mensagem."""
        for pattern in self.TIMEFRAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                minutes = match.group(1)
                return f"{minutes}m"
        
        # Timeframes comuns por extenso
        if 'cinco minutos' in text.lower() or '5 minutos' in text.lower():
            return '5m'
        if 'um minuto' in text.lower() or '1 minuto' in text.lower():
            return '1m'
        if 'quinze minutos' in text.lower() or '15 minutos' in text.lower():
            return '15m'
        
        return None
    
    def _extract_price(self, text: str, price_type: str) -> Optional[float]:
        """Extrai preço da mensagem (entry, target, stop)."""
        patterns = {
            'entry': r'(?:entry|entrada|preço)[:\s]+([0-9]+\.?[0-9]*)',
            'target': r'(?:target|alvo|tp|take profit)[:\s]+([0-9]+\.?[0-9]*)',
            'stop': r'(?:stop|sl|stop loss)[:\s]+([0-9]+\.?[0-9]*)',
        }
        
        pattern = patterns.get(price_type)
        if not pattern:
            return None
        
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        
        return None
    
    def _extract_confidence(self, text: str) -> Optional[str]:
        """Extrai nível de confiança do sinal."""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['alta confiança', 'high confidence', 'forte', 'strong']):
            return 'high'
        if any(word in text_lower for word in ['média', 'medium', 'moderado']):
            return 'medium'
        if any(word in text_lower for word in ['baixa', 'low', 'fraco', 'weak']):
            return 'low'
        
        # Detectar por emojis
        if '🔥' in text or '⭐' in text:
            return 'high'
        if '⚠️' in text:
            return 'medium'
        
        return None
    
    def get_recent_signals(self, minutes: int = 60) -> List[TradingSignal]:
        """Retorna sinais recentes dentro de X minutos."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [
            signal for signal in self.signal_history
            if signal.timestamp >= cutoff
        ]
    
    def get_signals_by_asset(self, asset: str, minutes: int = 1440) -> List[TradingSignal]:
        """Retorna sinais de um ativo específico."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        asset_normalized = asset.upper().replace('-', '/')
        
        return [
            signal for signal in self.signal_history
            if signal.timestamp >= cutoff and signal.asset.upper().replace('-', '/') == asset_normalized
        ]


def test_parser():
    """Testa parser com mensagens exemplo."""
    parser = PocketSignalParser()
    
    test_messages = [
        "🟢 EUR/USD CALL - M5 - Alta confiança",
        "🔴 GBPUSD PUT 15m",
        "Sinal: AUD/CAD OTC - COMPRA - 1 minuto",
        "📈 BTCUSD BUY Entry: 45000 Target: 46000 Stop: 44500",
        "⬇️ GOLD SELL - 5min - Confiança média",
        "EUR/USD OTC CALL M1",
    ]
    
    print("🧪 Testando parser de sinais...\n")
    
    for msg in test_messages:
        signal = parser.parse(msg, source='test')
        if signal:
            print(f"✅ '{msg[:40]}...'")
            print(f"   → {signal.asset} {signal.signal} {signal.timeframe}")
            if signal.confidence:
                print(f"   → Confiança: {signal.confidence}")
        else:
            print(f"❌ '{msg[:40]}...' - Não detectado")
        print()
    
    print(f"📊 Total de sinais no histórico: {len(parser.signal_history)}")


if __name__ == '__main__':
    test_parser()
