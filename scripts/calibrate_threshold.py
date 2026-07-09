#!/usr/bin/env python3
"""
Script de calibração de thresholds ATLAS
Analisa logs shadow em JSONL e recomenda scores mínimos baseados em percentis
"""
import sys
import json
import statistics as st
from collections import defaultdict


def percentile(values, p):
    """Calcula percentil de uma lista de valores"""
    values = sorted(values)
    if not values:
        return None
    k = round((p / 100) * (len(values) - 1))
    return values[int(k)]


def main(path="/tmp/atlas_shadow.jsonl", target=80):
    """
    Lê arquivo JSONL com registros de scores ATLAS e recomenda thresholds
    
    Args:
        path: Caminho ao arquivo de log shadow
        target: Percentil alvo para recomendação (padrão 80)
    """
    finals = []
    by_conf = defaultdict(list)
    by_direction = {'BUY': [], 'SELL': []}
    
    print(f"\n📊 Calibração ATLAS — Analisando {path}")
    print("=" * 70)

    try:
        with open(path, "r", encoding="utf-8") as f:
            count = 0
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    count += 1
                except Exception:
                    continue

                final = float(r.get("final", 0))
                conf = int(r.get("conf", 0))
                direction = r.get("direction", "UNKNOWN")

                finals.append(final)
                by_conf[conf].append(final)
                if direction in by_direction:
                    by_direction[direction].append(final)
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {path}")
        print("\n💡 Para gerar dados shadow:")
        print("   1. Configure: ATLAS_SHADOW_MODE=1 no .env")
        print("   2. Rode o bot por 24-48h para coletar dados")
        print("   3. Execute este script novamente")
        return

    if not finals:
        print("❌ Nenhum dado encontrado no arquivo")
        print("\n💡 Para gerar dados shadow:")
        print("   1. Configure: ATLAS_SHADOW_MODE=1 no .env")
        print("   2. Rode o bot por 24-48h para coletar dados")
        print("   3. Execute este script novamente")
        return

    finals = sorted(finals)

    print(f"\n📈 ESTATÍSTICAS GLOBAIS")
    print("-" * 70)
    print(f"Amostras analisadas: {len(finals)}")
    print(f"Mínimo: {finals[0]:.4f} (0%)")
    print(f"Q1 (25%): {percentile(finals, 25):.4f}")
    print(f"Mediana (50%): {st.median(finals):.4f}")
    print(f"Q3 (75%): {percentile(finals, 75):.4f}")
    print(f"Máximo: {finals[-1]:.4f} (100%)")
    print(f"Média: {st.mean(finals):.4f}")
    print(f"Desvio padrão: {st.stdev(finals) if len(finals) > 1 else 0:.4f}")

    print(f"\n📊 PERCENTIS")
    print("-" * 70)
    for p in [40, 50, 60, 70, 75, 80, 85, 90, 95]:
        val = percentile(finals, p)
        count_passed = sum(1 for x in finals if x >= val)
        pct_passed = (count_passed / len(finals) * 100)
        print(f"P{p:2d}: {val:.4f} ({count_passed:4d} amostras, {pct_passed:5.1f}% passariam)")

    rec = percentile(finals, target)
    passed = sum(1 for x in finals if x >= rec)
    pct_passed = (passed / len(finals) * 100) if finals else 0

    print(f"\n✅ RECOMENDAÇÃO")
    print("-" * 70)
    print(f"Percentil alvo: P{target}")
    print(f"ATLAS_MIN_SCORE = {rec:.2f} (ou {int(rec*100)}%)")
    print(f"→ {passed}/{len(finals)} sinais passariam ({pct_passed:.1f}%)")

    print(f"\n📉 POR CONFLUÊNCIA (# técnicas concordando)")
    print("-" * 70)
    for conf in sorted(by_conf.keys()):
        vals = by_conf[conf]
        if not vals:
            continue
        mean_val = st.mean(vals)
        median_val = st.median(vals)
        p80_val = percentile(vals, 80)
        print(
            f"{conf}/5: n={len(vals):4d} | "
            f"média={mean_val:.3f} | "
            f"mediana={median_val:.3f} | "
            f"P80={p80_val:.3f}"
        )

    print(f"\n🔄 POR DIREÇÃO")
    print("-" * 70)
    for direction, vals in by_direction.items():
        if not vals:
            continue
        mean_val = st.mean(vals)
        median_val = st.median(vals)
        p80_val = percentile(vals, 80)
        print(
            f"{direction:4s}: n={len(vals):4d} | "
            f"média={mean_val:.3f} | "
            f"mediana={median_val:.3f} | "
            f"P80={p80_val:.3f}"
        )

    print(f"\n💡 PRÓXIMOS PASSOS")
    print("-" * 70)
    print(f"1. Copie o valor recomendado para seu .env:")
    print(f"   ATLAS_MIN_SCORE={rec:.2f}")
    print(f"\n2. Ou use variável de ambiente na execução:")
    print(f"   ATLAS_MIN_SCORE={rec:.2f} bash run_bot_main.sh")
    print(f"\n3. Continue rodando com ATLAS_SHADOW_MODE=1 para refinar")
    print()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/atlas_shadow.jsonl"
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    main(path, target)
