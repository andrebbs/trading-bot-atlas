#!/usr/bin/env bash
# Script de execução principal do Bot Lógica do Preço M1 / OTC
set -e

echo "=================================================="
echo "  ATLAS — Motor da Lógica do Preço (M1 / OTC)"
echo "Ouve o feed M1, avalia os 4 quadrantes da Lógica do Preço e executa Paper Trading."
echo "=================================================="

export PYTHONPATH="$(pwd):$(pwd)/src"

# Executa o orquestrador principal em modo demo / paper trading
python3 src/main.py --symbols EURUSD GBPUSD USDJPY --min-defenses 3 --demo
