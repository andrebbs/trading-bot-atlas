#!/bin/bash
# Script de Ativação do Sistema ATLAS Completo
# Autor: Sistema ATLAS - Janeiro 2026

echo "════════════════════════════════════════════════════════════"
echo " SISTEMA ATLAS - ATIVAÇÃO COMPLETA"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "📋 Componentes:"
echo "  ✅ Smart Money Concepts (SMC) - Estrutura de mercado"
echo "  ✅ Wyckoff - Análise de volume e fases"
echo "  ✅ Price Action - Padrões de candlestick"
echo "  ✅ Elliott Wave - Ondas de impulso/correção"
echo "  ✅ Confluence Score - Sistema master combinado"
echo ""
echo "⚙️  Configuração:"
echo "  • Score mínimo: 55%"
echo "  • Confluência mínima: 3/5 técnicas"
echo "  • Risco por trade: 0.5%"
echo "  • Leverage: 3x"
echo "  • Max sinais: 6 por sessão"
echo ""
echo "════════════════════════════════════════════════════════════"
echo ""

# Parar bot atual se estiver rodando
echo "🛑 Parando bot atual..."
pkill -f telegram_bot.py 2>/dev/null || true
sleep 2

# Verificar se realmente parou
if pgrep -f telegram_bot.py > /dev/null; then
    echo "⚠️  Bot ainda rodando. Forçando encerramento..."
    killall python3 2>/dev/null || true
    sleep 2
fi

# Limpar processos órfãos
echo "🧹 Limpando processos órfãos..."
pkill -f "telegram_bot.py" 2>/dev/null || true
sleep 1

echo "✅ Bot anterior encerrado."
echo ""

# Verificar dependências
echo "🔍 Verificando módulos..."
if ! python3 -c "import src.core.confluence_score" 2>/dev/null; then
    echo "❌ Erro: módulo confluence_score não encontrado!"
    echo "   Execute: python3 -m pip install -r requirements.txt"
    exit 1
fi

if ! python3 -c "import src.core.wyckoff_detector" 2>/dev/null; then
    echo "❌ Erro: módulo wyckoff_detector não encontrado!"
    exit 1
fi

if ! python3 -c "import src.core.price_action_detector" 2>/dev/null; then
    echo "❌ Erro: módulo price_action_detector não encontrado!"
    exit 1
fi

if ! python3 -c "import src.core.elliott_wave_detector" 2>/dev/null; then
    echo "❌ Erro: módulo elliott_wave_detector não encontrado!"
    exit 1
fi

echo "✅ Todos os módulos encontrados."
echo ""

# Iniciar bot com Sistema ATLAS
echo "🚀 Iniciando bot com Sistema ATLAS Completo..."
bash run_bot_main.sh &

# Aguardar inicialização
sleep 3

# Verificar se iniciou
if pgrep -f telegram_bot.py > /dev/null; then
    PID=$(pgrep -f telegram_bot.py)
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo " ✅ BOT INICIADO COM SUCESSO!"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "📊 Status:"
    echo "  • PID: $PID"
    echo "  • Profile: main"
    echo "  • Market: SUSDT-FUTURES (simulador Bitget)"
    echo ""
    echo "📝 Logs:"
    echo "  • Bot: logs/telegram_bot_main.log"
    echo "  • Diagnóstico: logs/market_diagnostics_main.log"
    echo ""
    echo "🔎 Monitorar logs ATLAS:"
    echo "  tail -f logs/telegram_bot_main.log | grep ATLAS"
    echo ""
    echo "📱 Telegram:"
    echo "  /monitor on   - Iniciar monitoramento"
    echo "  /monitor off  - Parar monitoramento"
    echo "  /stats        - Ver estatísticas"
    echo ""
    echo "════════════════════════════════════════════════════════════"
else
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo " ❌ ERRO AO INICIAR BOT"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Verifique os logs:"
    echo "  cat logs/telegram_bot_main.log | tail -50"
    echo ""
    exit 1
fi
