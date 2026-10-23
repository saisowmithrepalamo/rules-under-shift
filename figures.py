"""Submission figures from results/contrasts.csv (run study.py first)."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

OUT = Path(__file__).resolve().parent / "results"
SCENARIOS = ["baseline", "control_erosion", "vendor_threat", "threat_surge"]
LABELS = {"baseline": "Baseline", "control_erosion": "Control erosion",
          "vendor_threat": "Vendor threat", "threat_surge": "Threat surge"}


def panel(ax, c, contrast, title):
    d = c[(c.contrast == contrast) & (c.metric == "utility")]
    for i, s in enumerate(SCENARIOS):
        r = d[d.scenario == s].sort_values("n_train")
        x = r.n_train * (1 + 0.04 * (i - 1.5))  # small dodge so whiskers do not overlap
        ax.errorbar(x, r["mean"], yerr=[r["mean"] - r.p025, r.p975 - r["mean"]],
                    marker="o", capsize=3, label=LABELS[s])
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks([150, 300, 600, 1200, 2400], ["150", "300", "600", "1,200", "2,400"])
    ax.set_xlabel("Training initiatives (log scale)")
    ax.set_ylabel("Utility difference per initiative")
    ax.set_title(title)


def main():
    c = pd.read_csv(OUT / "contrasts.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    panel(axes[0], c, "rule_gain_lr", "(a) Rules vs no rules (LR-EU)")
    panel(axes[1], c, "knowledge_vs_caution", "(b) Rules vs matched caution")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"Figure_2.{ext}", dpi=300)


if __name__ == "__main__":
    main()
