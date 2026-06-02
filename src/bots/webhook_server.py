"""
Servidor webhook para receber alertas do TradingView e encaminhar ao Telegram.

Fluxo:
  TradingView Alert → POST /webhook → formata mensagem → envia ao Telegram

Configuração no TradingView (campo "Message" do alerta):
  {
    "ticker": "{{ticker}}",
    "exchange": "{{exchange}}",
    "close": "{{close}}",
    "volume": "{{volume}}",
    "interval": "{{interval}}",
    "time": "{{time}}",
    "action": "BUY",
    "message": "Texto personalizado do alerta"
  }

Ou simplesmente texto livre:
  🟢 CALL — EURUSD — 5m — entrada na abertura do próximo candle
"""

import os
import json
import hmac
import hashlib
import logging
import asyncio
from typing import Optional
from datetime import datetime
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('webhook_server')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

app = Flask(__name__)

# ── Configurações ──────────────────────────────────────────────────────────────

BOT_PROFILE = os.getenv('BOT_PROFILE', 'main').strip().lower() or 'main'

def _get_env(key: str) -> Optional[str]:
    """Tenta ler variável com sufixo de perfil, depois genérica."""
    suffix = BOT_PROFILE.upper().replace('-', '_')
    return (
        os.getenv(f'{key}_{suffix}')
        or os.getenv(key)
    )

TELEGRAM_BOT_TOKEN = _get_env('TELEGRAM_BOT_TOKEN') or ''
TELEGRAM_CHAT_ID   = _get_env('TELEGRAM_CHAT_ID')   or ''

# Segredo opcional para validar que o request vem do TradingView
# Configure em .env: WEBHOOK_SECRET=sua_chave_secreta
# No TradingView, adicione no URL: /webhook?secret=sua_chave_secreta
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '').strip()

WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '8080'))


# ── Utilitários ────────────────────────────────────────────────────────────────

def _verify_secret(req) -> bool:
    """Verifica o secret no query string. Se não configurado, aceita tudo."""
    if not WEBHOOK_SECRET:
        return True
    return req.args.get('secret', '') == WEBHOOK_SECRET


def _send_telegram(message: str) -> bool:
    """Envia mensagem ao Telegram via Bot API (síncrono, simples)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error('TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados')
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error('Telegram API error %s: %s', resp.status_code, resp.text)
        return False
    except Exception as e:
        logger.error('Erro ao enviar para Telegram: %s', e)
        return False


def _format_signal(data: dict) -> str:
    """
    Formata o payload do TradingView em mensagem Telegram.
    Aceita payload JSON estruturado ou campo 'message' livre.
    """
    now = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    # Se veio texto livre no campo 'message', encaminha diretamente
    if 'message' in data and len(data) <= 3:
        return (
            f"📡 *Alerta TradingView*\n"
            f"🕐 {now}\n\n"
            f"{data['message']}"
        )

    # Payload estruturado (variáveis do Pine Script)
    ticker   = data.get('ticker', data.get('symbol', '?'))
    exchange = data.get('exchange', '')
    close    = data.get('close', data.get('price', ''))
    interval = data.get('interval', data.get('timeframe', ''))
    action   = data.get('action', data.get('signal', '')).upper()
    msg_text = data.get('message', '')

    # Emoji por direção
    if action in ('BUY', 'CALL', 'LONG', 'COMPRA', '1'):
        emoji = '🟢'
        direction = 'COMPRA / CALL'
    elif action in ('SELL', 'PUT', 'SHORT', 'VENDA', '-1'):
        emoji = '🔴'
        direction = 'VENDA / PUT'
    else:
        emoji = '🟡'
        direction = action or 'AGUARDAR'

    lines = [
        f"📡 *Alerta TradingView*",
        f"🕐 {now}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} *{direction}*",
    ]

    if ticker:
        exch_label = f" ({exchange})" if exchange else ''
        lines.append(f"📊 Ativo: `{ticker}`{exch_label}")
    if interval:
        lines.append(f"⏱ Timeframe: {interval}")
    if close:
        lines.append(f"💵 Preço: {close}")
    if msg_text:
        lines.append(f"\n📝 {msg_text}")

    lines.append("\n⚠️ Confirme o setup no gráfico antes de operar")
    return '\n'.join(lines)


# ── Rotas ──────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Health check — útil para saber se o servidor está no ar."""
    return jsonify({
        'status': 'ok',
        'profile': BOT_PROFILE,
        'telegram_configured': bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        'secret_enabled': bool(WEBHOOK_SECRET),
        'time': datetime.now().isoformat(),
    })


@app.route('/webhook', methods=['POST'])
def webhook():
    """Recebe alertas do TradingView."""
    # Validação do secret
    if not _verify_secret(request):
        logger.warning('Webhook recebido com secret inválido de %s', request.remote_addr)
        return jsonify({'error': 'unauthorized'}), 401

    # Parse do body — aceita JSON ou texto puro
    try:
        if request.is_json:
            data = request.get_json(force=True)
        else:
            raw = request.data.decode('utf-8').strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Texto puro — trata como mensagem livre
                data = {'message': raw}
    except Exception as e:
        logger.error('Erro ao parsear body: %s', e)
        return jsonify({'error': 'bad_request'}), 400

    if not data:
        return jsonify({'error': 'empty_body'}), 400

    logger.info('Alerta recebido: %s', json.dumps(data, ensure_ascii=False)[:200])

    message = _format_signal(data)
    success = _send_telegram(message)

    if success:
        logger.info('Mensagem enviada ao Telegram com sucesso')
        return jsonify({'status': 'ok'}), 200
    else:
        logger.error('Falha ao enviar ao Telegram')
        return jsonify({'error': 'telegram_failed'}), 500


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'TradingView Webhook → Telegram',
        'endpoints': {
            'GET  /health': 'Status do servidor',
            'POST /webhook': 'Recebe alerta do TradingView',
        },
        'docs': 'Configure o alerta no TradingView apontando para http://SEU_IP:8080/webhook',
    })


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not TELEGRAM_BOT_TOKEN:
        logger.warning('TELEGRAM_BOT_TOKEN não configurado — mensagens não serão enviadas')
    if not TELEGRAM_CHAT_ID:
        logger.warning('TELEGRAM_CHAT_ID não configurado — mensagens não serão enviadas')
    if not WEBHOOK_SECRET:
        logger.warning('WEBHOOK_SECRET não configurado — qualquer request será aceito')

    logger.info('Iniciando webhook server em %s:%s (perfil: %s)', WEBHOOK_HOST, WEBHOOK_PORT, BOT_PROFILE)
    app.run(host=WEBHOOK_HOST, port=WEBHOOK_PORT, debug=False)
