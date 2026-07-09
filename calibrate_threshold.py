#!/usr/bin/env python3
"""
ATLAS - Calibrador de threshold (modo shadow).
Uso:
  1) Rode o bot 48h com:  export ATLAS_SHADOW_MODE=1
                          export ATLAS_SHADOW_LOG=/tmp/atlas_shadow.jsonl
  2) Depois:              python calibrate_threshold.py /tmp/atlas_shadow.jsonl
Ele mede a distribuição REAL de 'final_score' e sugere min_score no percentil-alvo.
"""
import sys, json, statistics as st

def main(path, target_pctl=80):
    finals, byconf = [], {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            finals.append(r['final'])
            byconf.setdefault(r.get('conf', 0), []).append(r['final'])

    if not finals:
        print("Sem dados no log. O bot rodou com ATLAS_SHADOW_MODE=1?")
        return

    finals.sort()
    n = len(finals)
    def pctl(p):
        k = min(n-1, int(round((p/100.0)*(n-1))))
        return finals[k]

    print(f"Amostras: {n}")
    print(f"min={finals[0]:.3f}  mediana={st.median(finals):.3f}  max={finals[-1]:.3f}")
    for p in (50, 60, 70, 80, 85, 90, 95):
        print(f"  P{p}: {pctl(p):.3f}")

    rec = pctl(target_pctl)
    print(f"\n>>> RECOMENDADO min_score (P{target_pctl}) = {rec:.2f}")
    n_pass = sum(1 for x in finals if x >= rec)
    print(f"    -> deixaria passar ~{n_pass}/{n} candidatos ({100*n_pass/n:.1f}%)")

    print("\nDistribuição por confluência (média do final_score):")
    for c in sorted(byconf):
        vals = byconf[c]
        print(f"  conf {c}/5: n={len(vals):<4} media={st.mean(vals):.3f}")

    print("\nAplique em produção (exemplo):")
    print(f"  export ATLAS_MIN_SCORE={rec:.2f}")
    print(f"  # e no telegram_bot: min_score={rec:.2f}, min_confluence=3")

if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else '/tmp/atlas_shadow.jsonl'
    tgt = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    main(p, tgt)
