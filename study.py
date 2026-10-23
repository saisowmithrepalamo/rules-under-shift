"""When do expert screening rules pay off?

Simulation study of knowledge-based screening of digital transformation
initiatives (launch / harden / defer) under label scarcity, deployment shift
and rule error. Every number in the paper is produced by this script.

Usage:
    python study.py check     # design check: prevalence and rule firing only
    python study.py run       # full factorial experiment -> results/
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

OUT = Path(__file__).resolve().parent / "results"

OPP = ["innovation", "entrepreneurship", "data_volume", "data_sensitivity", "dt_breadth"]
CTRL = ["access", "encryption", "monitoring", "incident_response", "skills", "vendor"]
FEATURES = OPP + CTRL

TRAIN_SIZES = [150, 300, 600, 1200, 2400]
N_DEPLOY = 5000
N_REPS = 100
TARGET_PREVALENCE = 0.30
BASE_SEED = 2026

# Deployment scenarios. Training data always come from the baseline world.
SCENARIOS = {
    "baseline": dict(control_shift=0.0, vendor_coef=0.0, logit_shift=0.0),
    "control_erosion": dict(control_shift=-0.8, vendor_coef=0.0, logit_shift=0.0),
    "vendor_threat": dict(control_shift=0.0, vendor_coef=4.0, logit_shift=0.0),
    "threat_surge": dict(control_shift=0.0, vendor_coef=0.0, logit_shift=0.7),
}

# Expert rule base: (name, kind, [(feature, op, threshold), ...]).
# Hard rules force deferral; soft rules forbid launch.
RULES = [
    ("H1", "hard", [("data_sensitivity", ">", 0.70), ("access", "<", 0.40)]),
    ("H2", "hard", [("data_sensitivity", ">", 0.75), ("encryption", "<", 0.40)]),
    ("S1", "soft", [("data_volume", ">", 0.65), ("monitoring", "<", 0.40)]),
    ("S2", "soft", [("data_sensitivity", ">", 0.60), ("vendor", "<", 0.40)]),
    ("S3", "soft", [("dt_breadth", ">", 0.60), ("incident_response", "<", 0.35)]),
]
RULE_NOISE = 0.15

DEFER, HARDEN, LAUNCH = 0, 1, 2


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def generate(n, rng, control_shift=0.0):
    """Indicators on (0, 1) from four latent factors plus noise."""
    z_inn, z_ent, z_data, z_ctrl = rng.standard_normal((4, n))
    noise = lambda: rng.standard_normal(n)
    X = {
        "innovation": sigmoid(0.9 * z_inn + 0.5 * noise()),
        "entrepreneurship": sigmoid(0.9 * z_ent + 0.5 * noise()),
        "data_volume": sigmoid(0.9 * z_data + 0.5 * noise()),
        "data_sensitivity": sigmoid(0.7 * z_data + 0.7 * noise()),
        "dt_breadth": sigmoid(0.5 * z_inn + 0.5 * z_data + 0.6 * noise()),
    }
    for c in CTRL:
        X[c] = sigmoid(0.8 * (z_ctrl + control_shift) + 0.7 * noise())
    return pd.DataFrame(X)[FEATURES]


def breach_logit(X, beta0, vendor_coef=0.0):
    """True breach log-odds: main effects plus hinge-shaped control gaps."""
    gap_access = np.maximum(0.0, X.data_sensitivity - X.access)
    gap_monitor = np.maximum(0.0, X.data_volume - X.monitoring)
    gap_encrypt = ((X.data_sensitivity > 0.75) & (X.encryption < 0.40)).astype(float)
    gap_vendor = np.maximum(0.0, X.data_sensitivity - X.vendor)
    return (beta0 + 1.0 * X.data_sensitivity + 0.8 * X.data_volume + 0.4 * X.dt_breadth
            + 0.3 * X.entrepreneurship - 0.5 * X[CTRL].mean(axis=1)
            + 4.0 * gap_access + 3.5 * gap_monitor + 1.8 * gap_encrypt
            + vendor_coef * gap_vendor).to_numpy()


def calibrate_intercept():
    """Intercept giving TARGET_PREVALENCE in a large baseline population."""
    X = generate(200_000, np.random.default_rng([BASE_SEED, 0]))
    lo, hi = -10.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if sigmoid(breach_logit(X, mid)).mean() > TARGET_PREVALENCE:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def value_and_impact(X):
    V = (18 + 35 * X.innovation + 22 * X.entrepreneurship + 12 * X.dt_breadth).to_numpy()
    I = (25 + 90 * X.data_sensitivity + 40 * X.data_volume + 20 * X.dt_breadth).to_numpy()
    return V, I


def payoffs(V, I, q):
    """Expected payoff of defer, harden, launch given breach probability q."""
    return np.column_stack([np.zeros_like(V), 0.55 * V - 5 - 0.35 * q * I, V - q * I])


def perturb_rules(rng):
    return [(name, kind, [(f, op, t + rng.uniform(-RULE_NOISE, RULE_NOISE)) for f, op, t in conds])
            for name, kind, conds in RULES]


def fire(X, rules, drop=()):
    """Boolean masks for hard and soft rules that fire on each initiative."""
    hard = np.zeros(len(X), bool)
    soft = np.zeros(len(X), bool)
    for name, kind, conds in rules:
        if name in drop:
            continue
        m = np.ones(len(X), bool)
        for f, op, t in conds:
            m &= (X[f].to_numpy() > t) if op == ">" else (X[f].to_numpy() < t)
        if kind == "hard":
            hard |= m
        else:
            soft |= m
    return hard, soft


def eu_actions(V, I, q, hard=None, soft=None):
    P = payoffs(V, I, q)
    a = P.argmax(axis=1)
    if soft is not None:
        a = np.where(soft, P[:, :2].argmax(axis=1), a)
    if hard is not None:
        a = np.where(hard, DEFER, a)
    return a


def matched_caution(V, I, q, target_launches):
    """EU actions with risk inflated by a uniform log-odds margin, the smallest
    margin at which launches do not exceed target_launches. Uses predictions only."""
    if (eu_actions(V, I, q) == LAUNCH).sum() <= target_launches:
        return eu_actions(V, I, q), 0.0
    lo, hi = 0.0, 10.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if (eu_actions(V, I, sigmoid(logit(q) + mid)) == LAUNCH).sum() > target_launches:
            lo = mid
        else:
            hi = mid
    return eu_actions(V, I, sigmoid(logit(q) + hi)), hi


def evaluate(a, V, I, p_true):
    P = payoffs(V, I, p_true)
    launched = a == LAUNCH
    return {
        "utility": P[np.arange(len(a)), a].mean(),
        "launched_breach_share": (p_true * launched).sum() / p_true.sum(),
        "launch_share": launched.mean(),
    }


def fit_models(Xtr, ytr, seed):
    lr = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)).fit(Xtr, ytr)
    gb = GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3,
                                    subsample=0.8, random_state=seed).fit(Xtr, ytr)
    return lr, gb


def design_check(beta0):
    rng = np.random.default_rng([BASE_SEED, 1])
    rows = []
    for name, s in SCENARIOS.items():
        X = generate(50_000, rng, s["control_shift"])
        p = sigmoid(breach_logit(X, beta0 + s["logit_shift"], s["vendor_coef"]))
        V, I = value_and_impact(X)
        hard, soft = fire(X, RULES)
        a = eu_actions(V, I, p)
        rows.append({"scenario": name, "prevalence": p.mean(), "hard_fires": hard.mean(),
                     "soft_fires": (soft & ~hard).mean(), "oracle_launch": (a == LAUNCH).mean(),
                     "oracle_harden": (a == HARDEN).mean(), "oracle_defer": (a == DEFER).mean()})
    print(f"intercept {beta0:.4f}")
    print(pd.DataFrame(rows).round(3).to_string(index=False))


def run(beta0):
    records, models = [], []
    for r in range(1, N_REPS + 1):
        rng_tr = np.random.default_rng([BASE_SEED, 10, r])
        Xpool = generate(max(TRAIN_SIZES), rng_tr)
        ypool = rng_tr.binomial(1, sigmoid(breach_logit(Xpool, beta0)))
        noisy_rules = perturb_rules(np.random.default_rng([BASE_SEED, 20, r]))
        deploy = {}
        for name, s in SCENARIOS.items():
            rng_dep = np.random.default_rng([BASE_SEED, 30, r])  # same draws in every scenario
            X = generate(N_DEPLOY, rng_dep, s["control_shift"])
            p = sigmoid(breach_logit(X, beta0 + s["logit_shift"], s["vendor_coef"]))
            y = rng_dep.binomial(1, p)
            V, I = value_and_impact(X)
            deploy[name] = (X, p, y, V, I, fire(X, RULES), fire(X, RULES, drop=("S2",)),
                            fire(X, noisy_rules))
        for n in TRAIN_SIZES:
            lr, gb = fit_models(Xpool.iloc[:n], ypool[:n], r)
            for name, (X, p, y, V, I, rules, rules_nov, rules_noisy) in deploy.items():
                q_lr = lr.predict_proba(X)[:, 1]
                q_gb = gb.predict_proba(X)[:, 1]
                acts = {
                    "oracle_eu": eu_actions(V, I, p),
                    "lr_eu": eu_actions(V, I, q_lr),
                    "lr_eu_rules": eu_actions(V, I, q_lr, *rules),
                    "lr_eu_rules_no_S2": eu_actions(V, I, q_lr, *rules_nov),
                    "lr_eu_noisy_rules": eu_actions(V, I, q_lr, *rules_noisy),
                    "gb_eu": eu_actions(V, I, q_gb),
                    "gb_eu_rules": eu_actions(V, I, q_gb, *rules),
                    "rules_only": np.where(rules[0], DEFER, np.where(rules[1], HARDEN, LAUNCH)),
                }
                target = (acts["lr_eu_rules"] == LAUNCH).sum()
                acts["lr_eu_caution"], margin = matched_caution(V, I, q_lr, target)
                for policy, a in acts.items():
                    records.append({"rep": r, "n_train": n, "scenario": name, "policy": policy,
                                    **evaluate(a, V, I, p)})
                for model, q in (("lr", q_lr), ("gb", q_gb)):
                    models.append({"rep": r, "n_train": n, "scenario": name, "model": model,
                                   "auroc": roc_auc_score(y, q), "brier": np.mean((q - y) ** 2),
                                   "calibration_in_large": q.mean() - p.mean(),
                                   "caution_margin": margin if model == "lr" else np.nan})
        print(f"replication {r}/{N_REPS}", flush=True)
    return pd.DataFrame(records), pd.DataFrame(models)


def contrast(df, a, b, metric):
    """Paired difference a - b per replication, summarised by cell."""
    w = df.pivot_table(index=["scenario", "n_train", "rep"], columns="policy", values=metric)
    d = (w[a] - w[b]).rename("diff").reset_index()
    g = d.groupby(["scenario", "n_train"])["diff"]
    return pd.DataFrame({
        "mean": g.mean(), "p025": g.quantile(0.025), "p975": g.quantile(0.975),
        "positive_reps": g.apply(lambda s: int((s > 0).sum())), "reps": g.size(),
    }).reset_index()


def summarise(rec, mod):
    OUT.mkdir(exist_ok=True)
    rec.to_csv(OUT / "runs_policies.csv", index=False)
    mod.to_csv(OUT / "runs_models.csv", index=False)
    cells = rec.groupby(["scenario", "n_train", "policy"])[
        ["utility", "launched_breach_share", "launch_share"]].mean().reset_index()
    cells.to_csv(OUT / "cell_means.csv", index=False)
    mod.groupby(["scenario", "n_train", "model"])[
        ["auroc", "brier", "calibration_in_large", "caution_margin"]].mean().reset_index().to_csv(
        OUT / "model_means.csv", index=False)
    contrasts = {
        "rule_gain_lr": ("lr_eu_rules", "lr_eu"),
        "knowledge_vs_caution": ("lr_eu_rules", "lr_eu_caution"),
        "vendor_rule_ablation": ("lr_eu_rules", "lr_eu_rules_no_S2"),
        "noisy_rule_gain_lr": ("lr_eu_noisy_rules", "lr_eu"),
        "rule_gain_gb": ("gb_eu_rules", "gb_eu"),
        "lr_vs_gb": ("lr_eu", "gb_eu"),
        "rules_vs_rules_only": ("lr_eu_rules", "rules_only"),
        "oracle_vs_lr": ("oracle_eu", "lr_eu"),
    }
    out = []
    for label, (a, b) in contrasts.items():
        for metric in ("utility", "launched_breach_share"):
            c = contrast(rec, a, b, metric)
            c.insert(0, "metric", metric)
            c.insert(0, "contrast", label)
            out.append(c)
    allc = pd.concat(out)
    allc.to_csv(OUT / "contrasts.csv", index=False)
    meta = {"intercept": BETA0, "n_reps": N_REPS, "n_deploy": N_DEPLOY, "train_sizes": TRAIN_SIZES,
            "scenarios": SCENARIOS, "rules": RULES, "rule_noise": RULE_NOISE,
            "target_prevalence": TARGET_PREVALENCE, "base_seed": BASE_SEED}
    (OUT / "settings.json").write_text(json.dumps(meta, indent=2))
    print(allc[allc.metric == "utility"].round(3).to_string(index=False))


if __name__ == "__main__":
    BETA0 = calibrate_intercept()
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    if mode == "check":
        design_check(BETA0)
    else:
        summarise(*run(BETA0))
