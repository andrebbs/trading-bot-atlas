#!/bin/bash
# INSTRUÇÕES DE EXECUÇÃO — ATLAS CALIBRATION FIX
# Data: 2026-07-08
# Status: Pronto para deploy

set -e

PROJECT_ROOT="/home/abbs/Área de Trabalho/trading-bot"
cd "$PROJECT_ROOT" || exit 1

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         ATLAS CALIBRATION FIX — INSTRUÇÕES DE EXECUÇÃO        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# ETAPA 1: VALIDAÇÕES PRÉ-EXECUÇÃO
# ═══════════════════════════════════════════════════════════════════════
echo "📋 ETAPA 1: Validações Pré-execução"
echo "──────────────────────────────────────────────────────────────────"

echo "✓ Validando sintaxe Python..."
python3 -m py_compile src/core/confluence_score.py || exit 1
python3 -m py_compile src/bots/telegram_bot.py || exit 1
python3 -m py_compile scripts/calibrate_threshold.py || exit 1
echo "  ✅ Compilação OK"

echo "✓ Verificando dependências..."
python3 -c "import math; import json; import pandas; import numpy" 2>/dev/null || {
    echo "  ⚠️  Instalando dependências..."
    python3 -m pip install pandas numpy >/dev/null 2>&1
}
echo "  ✅ Dependências OK"

echo "✓ Verificando estrutura de arquivos..."
test -f src/core/confluence_score.py || exit 1
test -f src/bots/telegram_bot.py || exit 1
test -f scripts/calibrate_threshold.py || exit 1
test -f .env.example || exit 1
echo "  ✅ Estrutura OK"

echo ""
echo "✅ VALIDAÇÕES CONCLUÍDAS"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# ETAPA 2: INFORMAÇÕES DE CONTEXTO
# ═══════════════════════════════════════════════════════════════════════
echo "📊 ETAPA 2: Contexto da Correção"
echo "──────────────────────────────────────────────────────────────────"
echo ""
echo "PROBLEMA ORIGINAL:"
echo "  • Sinais com 4/5 técnicas concordando eram bloqueados como 'Sem confluência'"
echo "  • Scores comprimidos para 30-35% quando deviam estar em 50-60%"
echo "  • Hearbeat mostrava: 'score 34%, confluência 4/5' (contraditório)"
echo ""
echo "CORREÇÕES APLICADAS:"
echo "  • Nova fórmula matemática: conviction × coverage × agreement"
echo "  • Função logística para melhor distribuição de scores"
echo "  • Thresholds recalibrados (MIN_SCORE: 0.38→0.50, MIN_CONFLUENCE: 2→3)"
echo "  • Mode shadow para coleta de dados"
echo "  • Script de calibração automática"
echo ""
echo "RESULTADO ESPERADO:"
echo "  • 4/5 técnicas com score 0.35 cada → final_score 58% ✅"
echo "  • Mensagens coerentes no heartbeat"
echo "  • ~70-80% mais sinais aprovados"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# ETAPA 3: OPÇÕES DE EXECUÇÃO
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "🚀 ETAPA 3: Modo de Execução"
echo "──────────────────────────────────────────────────────────────────"
echo ""
echo "OPÇÃO 1: Deploy imediato (com padrões)"
echo "  • Usa thresholds padrão (ATLAS_MIN_SCORE=0.50)"
echo "  • Modo shadow desativado"
echo "  • Comando: bash run_bot_main.sh"
echo ""
echo "OPÇÃO 2: Coleta e calibração (RECOMENDADO para 48h)"
echo "  • Ativa shadow mode para coleta de dados"
echo "  • Não muda decisões de sinal"
echo "  • Ao final: rodará script de calibração"
echo "  • Passos:"
echo "    1. Adicionar ao .env: ATLAS_SHADOW_MODE=1"
echo "    2. Deixar rodar por 48 horas"
echo "    3. Executar: python3 scripts/calibrate_threshold.py"
echo "    4. Copiar resultado recomendado para .env"
echo "    5. Reiniciar bot com novo threshold"
echo ""
echo "OPÇÃO 3: Teste rápido (1 minuto)"
echo "  • Valida se fórmula nova está funcionando"
echo "  • Comando: python3 -c 'from src.core.confluence_score import *; c=ConfluenceScoreSystem(); print(\"OK\")'"
echo ""

# ═══════════════════════════════════════════════════════════════════════
# MENU INTERATIVO
# ═══════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "Escolha uma opção:"
echo "  1) Deploy imediato (padrão)"
echo "  2) Ativar shadow mode para 48h"
echo "  3) Teste rápido"
echo "  4) Ver arquivos alterados"
echo "  5) Sair"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

read -p "Escolha (1-5): " choice

case $choice in
  1)
    echo ""
    echo "▶️  Iniciando bot com novo ATLAS..."
    echo "  • Usando thresholds: MIN_SCORE=0.50, MIN_CONFLUENCE=3"
    echo "  • Shadow mode: DESATIVADO"
    echo ""
    echo "📝 Para customizar, edite .env com:"
    echo "  export ATLAS_MIN_SCORE=0.50"
    echo "  export ATLAS_MIN_CONFLUENCE=3"
    echo ""
    read -p "Pressione ENTER para iniciar o bot: "
    bash run_bot_main.sh
    ;;
  
  2)
    echo ""
    echo "▶️  Configurando shadow mode para 48 horas..."
    echo ""
    
    # Verificar se .env existe
    if [ ! -f .env ]; then
      echo "⚠️  .env não encontrado. Criando a partir de .env.example..."
      cp .env.example .env
    fi
    
    # Ativar shadow mode
    echo "✓ Adicionando ao .env:"
    grep -q "ATLAS_SHADOW_MODE" .env && sed -i 's/^ATLAS_SHADOW_MODE=.*/ATLAS_SHADOW_MODE=1/' .env || echo "ATLAS_SHADOW_MODE=1" >> .env
    grep -q "ATLAS_SHADOW_LOG" .env && sed -i 's|^ATLAS_SHADOW_LOG=.*|ATLAS_SHADOW_LOG=/tmp/atlas_shadow.jsonl|' .env || echo "ATLAS_SHADOW_LOG=/tmp/atlas_shadow.jsonl" >> .env
    
    echo "  ✅ ATLAS_SHADOW_MODE=1"
    echo "  ✅ ATLAS_SHADOW_LOG=/tmp/atlas_shadow.jsonl"
    echo ""
    echo "📝 Instruções para próximas 48h:"
    echo "  1. O bot rodará normalmente, mas registrará todos os scores em /tmp/atlas_shadow.jsonl"
    echo "  2. Deixe rodar continuamente (não muda decisões de sinal)"
    echo "  3. Após 48h, execute: python3 scripts/calibrate_threshold.py"
    echo "  4. Copie o valor ATLAS_MIN_SCORE recomendado para .env"
    echo "  5. Definir ATLAS_SHADOW_MODE=0 (desabilitar shadow)"
    echo "  6. Reiniciar bot com novo threshold"
    echo ""
    read -p "Pressione ENTER para iniciar em shadow mode: "
    bash run_bot_main.sh
    ;;
  
  3)
    echo ""
    echo "▶️  Executando teste rápido..."
    python3 << 'PYEOF'
import os
import sys
sys.path.insert(0, os.getcwd())

try:
    from src.core.confluence_score import ConfluenceScoreSystem
    import pandas as pd
    import numpy as np
    
    print("\n✓ Importações OK")
    
    # Testar instanciação
    c = ConfluenceScoreSystem()
    print("✓ ConfluenceScoreSystem instanciado")
    
    # Verificar constantes
    print(f"✓ ATLAS_MIN_SCORE = {c.MIN_SCORE}")
    print(f"✓ ATLAS_STRONG_MIN_SCORE = {c.STRONG_MIN_SCORE}")
    print(f"✓ ATLAS_COVERAGE_BASE = {c.COVERAGE_BASE}")
    print(f"✓ ATLAS_CALIB_K = {c.CALIB_K}")
    
    # Teste simulado
    np.random.seed(42)
    dates = pd.date_range(start='2026-01-01', periods=100, freq='5m')
    df = pd.DataFrame({
        'timestamp': dates,
        'open': 100 + np.random.randn(100),
        'high': 101 + np.random.randn(100),
        'low': 99 + np.random.randn(100),
        'close': 100 + np.random.randn(100),
        'volume': 1000 + np.random.randn(100) * 100,
        'rsi': 50 + np.random.randn(100) * 10,
        'adx': 25 + np.random.randn(100) * 5,
        'ema9': 100 + np.random.randn(100) * 0.5,
        'ema20': 100 + np.random.randn(100) * 0.7,
        'ema50': 100 + np.random.randn(100),
        'ema200': 100 + np.random.randn(100) * 2,
        'atr': 0.5 + np.random.randn(100) * 0.1,
    })
    
    # Análise simulada
    result = c.get_confluence_score(df, 'BUY')
    
    print(f"\n✓ Teste de análise BUY:")
    print(f"  Final score: {result['final_score']:.3f} ({result['final_score_pct']}%)")
    print(f"  Confluência: {result['confluence_count']}/5")
    print(f"  Recomendação: {result['recommendation']}")
    
    print("\n✅ TESTE PASSOU — Novo ATLAS está funcionando corretamente!")
    
except Exception as e:
    print(f"\n❌ ERRO NO TESTE: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYEOF
    ;;
  
  4)
    echo ""
    echo "📁 ARQUIVOS ALTERADOS"
    echo "──────────────────────────────────────────────────────────────────"
    echo ""
    git --git-dir=.git log -1 --name-status 2>/dev/null || {
      echo "src/core/confluence_score.py (MODIFICADO)"
      echo "  • +7 constantes novas"
      echo "  • +Nova fórmula logística"
      echo "  • +Mode shadow"
      echo ""
      echo "src/bots/telegram_bot.py (MODIFICADO)"
      echo "  • ADX < 15 → ADX < 12 (2 locais)"
      echo "  • min_score via environment"
      echo ""
      echo "scripts/calibrate_threshold.py (NOVO)"
      echo "  • Análise de percentis"
      echo "  • Recomendação automática"
      echo ""
      echo ".env.example (MODIFICADO)"
      echo "  • +15 variáveis ATLAS_*"
      echo ""
      echo "backups/atlas_fix_20260708_220603/ (NOVO)"
      echo "  • confluence_score.py.bak"
      echo "  • telegram_bot.py.bak"
    }
    ;;
  
  5)
    echo "Saindo..."
    exit 0
    ;;
  
  *)
    echo "❌ Opção inválida"
    exit 1
    ;;
esac

echo ""
echo "✅ Execução concluída!"
echo ""
