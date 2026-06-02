#!/bin/bash
# Script de Ativação Fase 1 SMC
# Data: 29/05/2026

echo "🚀 ATIVANDO SISTEMA COM SMC - FASE 1"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Verificar se bot já está rodando
if pgrep -f "telegram_bot.py" > /dev/null; then
    echo "⏸  Bot detectado rodando. Parando..."
    pkill -f "telegram_bot.py"
    sleep 3
fi

# Confirmar que parou
if pgrep -f "telegram_bot.py" > /dev/null; then
    echo "❌ Bot ainda rodando. Forçando parada..."
    pkill -9 -f "telegram_bot.py"
    sleep 2
fi

echo "✅ Bot parado"
echo ""

# Mostrar configuração atual
echo "📊 CONFIGURAÇÃO ATIVA:"
echo "  Risk: 0.5% por trade (conservador)"
echo "  Leverage: 3x (reduzido)"
echo "  Produto: SUSDT-FUTURES (simulator)"
echo "  SMC Threshold: 0.35 (mínimo)"
echo ""

# Iniciar bot
echo "🔄 Iniciando bot com SMC ativado..."
cd /home/abbs/trading-bot

# Executar em background
nohup bash run_bot_main.sh > logs/startup_smc_$(date +%Y%m%d_%H%M%S).log 2>&1 &

sleep 3

# Verificar se subiu
if pgrep -f "telegram_bot.py" > /dev/null; then
    PID=$(pgrep -f "telegram_bot.py")
    echo "✅ Bot iniciado com sucesso! PID: $PID"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "🎯 PRÓXIMOS PASSOS:"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "1. Abra o Telegram e digite:"
    echo "   /monitor on"
    echo ""
    echo "2. Acompanhe os logs em tempo real:"
    echo "   tail -f logs/telegram_bot_main.log | grep -E 'SMC|FILTER'"
    echo ""
    echo "3. Ver sinais bloqueados/aprovados:"
    echo "   grep 'SMC FILTER' logs/telegram_bot_main.log"
    echo ""
    echo "4. Diagnóstico detalhado:"
    echo "   tail -f logs/market_diagnostics_main.log | grep smc"
    echo ""
    echo "5. Após 7 dias, gerar relatório:"
    echo "   python3 analyze_performance.py"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "📈 META FASE 1 (7 dias):"
    echo "  • Win Rate: 28% → 45-50%"
    echo "  • Trades mínimos: 20"
    echo "  • Sinais bloqueados: ~50% (ranging markets)"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "🔥 Sistema SMC ativo! Bora dominar o mercado! 🚀"
else
    echo "❌ Erro ao iniciar bot. Verifique os logs:"
    echo "   tail -50 logs/telegram_bot_main.log"
fi
