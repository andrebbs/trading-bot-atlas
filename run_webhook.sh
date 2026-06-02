#!/usr/bin/env bash
# run_webhook.sh — Inicia o servidor webhook TradingView → Telegram
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Ativa o ambiente virtual se existir
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Carrega variáveis de ambiente do .env
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "🌐 Iniciando Webhook TradingView → Telegram"
echo "   Porta: ${WEBHOOK_PORT:-8080}"
echo "   Perfil: ${BOT_PROFILE:-main}"
echo ""
echo "   Configure o alerta no TradingView com a URL:"
echo "   http://SEU_IP_PUBLICO:${WEBHOOK_PORT:-8080}/webhook"
echo ""
echo "   Para testar localmente:"
echo "   curl -X POST http://localhost:${WEBHOOK_PORT:-8080}/webhook \\"
echo '     -H "Content-Type: application/json" \'
echo '     -d '"'"'{"ticker":"EURUSD","interval":"5m","action":"BUY","close":"1.0850","message":"Setup EMA crossover confirmado"}'"'"
echo ""

python3 -m src.bots.webhook_server
