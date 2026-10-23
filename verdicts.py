"""Score hypotheses H1-H7 against the criteria frozen in the manuscript (Section 3.6)."""
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
c = pd.read_csv(OUT / "contrasts.csv")
SIZES = [150, 300, 600, 1200, 2400]


def get(contrast, scenario, n, metric="utility"):
    return c[(c.contrast == contrast) & (c.scenario == scenario) & (c.n_train == n)
             & (c.metric == metric)].iloc[0]


def consistent(row):
    return row.positive_reps >= 95


lines = []
g = get("rule_gain_lr", "baseline", 2400)
b = get("rule_gain_lr", "baseline", 2400, "launched_breach_share")
lines.append(("H1", not consistent(g) and (b.reps - b.positive_reps) >= 95,
              f"gain {g['mean']:.3f} ({g.positive_reps}/100 positive); breach share falls in "
              f"{b.reps - b.positive_reps}/100"))
g150, g2400 = get("rule_gain_lr", "baseline", 150), get("rule_gain_lr", "baseline", 2400)
lines.append(("H2", g150["mean"] > g2400["mean"] and g150.positive_reps >= 75,
              f"gain at 150 {g150['mean']:.3f} ({g150.positive_reps}/100) vs 2400 {g2400['mean']:.3f}"))
r = [get("rule_gain_lr", "control_erosion", n) for n in SIZES]
lines.append(("H3", all(consistent(x) for x in r),
              "; ".join(f"n={n}: {x['mean']:.3f} ({x.positive_reps})" for n, x in zip(SIZES, r))))
r = [get("rule_gain_lr", "vendor_threat", n) for n in SIZES]
a = [get("vendor_rule_ablation", "vendor_threat", n) for n in SIZES]
share = sum(x["mean"] for x in a) / sum(x["mean"] for x in r)
lines.append(("H4", all(consistent(x) for x in r) and share > 0.5,
              "; ".join(f"n={n}: {x['mean']:.3f} ({x.positive_reps})" for n, x in zip(SIZES, r))
              + f"; S2 share of gain {share:.2f}"))
r = [get("knowledge_vs_caution", "threat_surge", n) for n in SIZES]
lines.append(("H5", not any(consistent(x) for x in r),
              "; ".join(f"n={n}: {x['mean']:.3f} ({x.positive_reps})" for n, x in zip(SIZES, r))))
ok = True
txt = []
for s in ("control_erosion", "vendor_threat"):
    r = [get("knowledge_vs_caution", s, n) for n in SIZES]
    ok &= all(consistent(x) for x in r)
    txt.append(s + ": " + ", ".join(f"{x['mean']:.3f} ({x.positive_reps})" for x in r))
lines.append(("H6", ok, "; ".join(txt)))
kept = {}
for s in ("control_erosion", "vendor_threat"):
    noisy = sum(get("noisy_rule_gain_lr", s, n)["mean"] for n in SIZES)
    correct = sum(get("rule_gain_lr", s, n)["mean"] for n in SIZES)
    kept[s] = noisy / correct
lines.append(("H7", all(v < 0.5 for v in kept.values()),
              ", ".join(f"{k} keeps {v:.2f}" for k, v in kept.items())))

for h, supported, detail in lines:
    print(f"{h}: {'SUPPORTED' if supported else 'NOT SUPPORTED'} | {detail}")
