# When do expert screening rules pay off?

Code and outputs for a simulation study that follows up the KCID-AI paper
([kb-ai-dt-readiness](https://github.com/saisowmithrepalamo/kb-ai-dt-readiness)).
KCID-AI found that cybersecurity screening rules cut launched breaches but did not
raise decision utility when training and deployment data came from the same world.
This study asks when rules do earn their cost: with few labelled initiatives, under
three kinds of deployment shift, and when the rules themselves are imprecise.

All data are synthetic. No real enterprise or breach records are used.

## Read the paper

| File | What it is |
|---|---|
| [`paper.md`](paper.md) | The full manuscript: methods, pre-stated hypotheses, results, discussion and references |
| [`figures/`](figures/) | Fig. 1 (policy paths) and Fig. 2 (rule gain) as they appear in the paper |

Author name, affiliation and email are left blank in the manuscript.

## Design

- Five training-sample sizes (150 to 2,400 initiatives) crossed with four deployment
  scenarios: baseline, control erosion, an emerging vendor threat and a uniform
  threat surge. 100 replications per cell, 5,000 deployment initiatives each.
- Nine screening policies, including an oracle, logistic regression and gradient
  boosting with and without the rule base, noisy rules, a rule ablation, rule-only
  screening, and a matched-caution control that launches as many initiatives as the
  rule policy using one uniform risk margin.
- Seven hypotheses fixed before the full run; `verdicts.py` scores them against
  their stated refutation criteria.

## Main findings

- Rules lowered the launched-breach share in all 20 cells, by 4.7 to 8.5 points.
- They raised mean utility appreciably only with 150 or 300 training initiatives,
  under the threat surge and the vendor threat (by 0.06 to 0.44 per initiative).
- The matched-caution policy had higher mean utility than the rules in 19 of 20 cells.
- The vendor-gap rule raised utility in all 100 replications at every training size
  when the vendor threat arrived, and lowered it in all 100 when it did not.

Two of the seven hypotheses were supported.

## Reproduce

Tested with Python 3.12.4 and the versions pinned in `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MPLCONFIGDIR="$(pwd)/.mplconfig"
python study.py check   # design check: prevalence and rule firing rates only
python study.py run     # full experiment, about 10 minutes on 8 cores
python verdicts.py      # scores hypotheses H1-H7
python figures.py       # results/Figure_2.png and .pdf
```

Base seed 2026; every replication, training pool and deployment set is seeded from it.

## Outputs (`results/`)

| File | Contents |
|---|---|
| `runs_policies.csv` | One row per replication, training size, scenario and policy |
| `runs_models.csv` | AUROC, Brier score and calibration of each fitted model |
| `cell_means.csv` | Mean utility, launched-breach share and launch share per cell |
| `contrasts.csv` | Paired contrasts: mean, 2.5th and 97.5th percentiles, positive replications |
| `settings.json` | Intercept, seeds, rules and scenario settings used |
| `Figure_2.png` / `.pdf` | Print version from `figures.py`: rule gain and rules versus matched caution, by training size |
