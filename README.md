# Evaluating eFlx: energy flexibility provisioning for e-taxi fleets

CS637 (IIT Kanpur) research-paper evaluation project. We re-implement, reproduce, critique and extend:

> L. Zhou, Y. Zhao, Y. Yuan, et al. **"eFlx: Energy Flexibility Provisioning for E-taxi Fleets."** ICCPS 2025.

The paper keeps an electric-taxi fleet ready to cut its charging load when the grid issues a demand-response (DR) request, without dropping passengers. No code was released, so everything here is rebuilt from the paper's equations.

**Video presentation:** [VIDEO LINK](https://example.com/replace-me) · **Slides:** [SLIDES LINK](https://example.com/replace-me)

## Team
| Name | Roll no. | Role | Contribution |
|---|---|---|---|
| Ghada Suleiman | 261330004 | Paper study (DR, problem, eFlx, claims), extension ideas | 33.3% |
| Suraj Singh Raman | 261110067 | Critique, implementation, validation, toy experiments, demo, data pipeline | 33.3% |
| Rishikesh Sawant | 261110052 | Manhattan reproduction, new use cases and ideas | 33.3% |

## What's in this repo
| | Where |
|---|---|
| **Implementation** of the model (Eq. 1–4), reference/response/provisioning LPs (Problems 1, 3, 5), Algorithm 1, MPC loop (Algorithm 2), flexibility metric (Eq. 6) and the baselines TRC, R2I, TES, Oracle | `eflx/` |
| **Validation**: the fast sparse LP builder gives the same optima as the readable cvxpy version | `tests/test_fastplan.py` |
| **Toy experiment** (2 regions, 100 taxis) | `toy_demo.py` |
| **Reproduction on real NYC data** (Manhattan, March 2024 TLC trips) | `scripts/get_nyc_data.py`, `run_manhattan.py`, `make_figures.py` |
| **Our improvement, P-eFlx**: plans for a probability distribution over the DR start time instead of assuming "DR starts next slot" | `improvement.py`, `eflx/policies.py` (`p_eflx`) |
| **Paper's Fig. 11 and Table 1** (provision length, demand-forecast noise) | `paper_extras.py` |
| **Second new idea and a new use case**: service vs flexibility trade-off; absorbing surplus power (upward flexibility) | `new_ideas.py` |
| **Results** (figures, JSON, logs, paper-vs-ours claims tables) | `results/` |
| **Project report**: one section per activity in the brief, paper and our figures side by side | `REPORT.md` |
| **Assumptions, findings and critique** | `NOTES.md` |
| **Presentation outline** | `SLIDES_OUTLINE.md` |

### Code map
| Paper | Code |
|---|---|
| Sec. 3: state, decisions, Eq. (1)–(4), (5e)–(5g) | `eflx/model.py` (readable cvxpy version, also the fluid simulator `step`) |
| Same LPs at Manhattan scale | `eflx/fastplan.py` (sparse matrices → HiGHS) |
| Problem 3 (TRC), Problems 1/5, Algorithm 1, baselines of Sec. 7.1 | `eflx/policies.py` |
| Algorithm 2 (MPC) and Eq. (6) | `eflx/sim.py` |
| Manhattan instance (12 regions, ports, fleet, warm-up) | `eflx/manhattan.py` |

## Setup
Developed and tested with Python 3.14 on macOS.
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Quick start
```bash
.venv/bin/python tests/test_fastplan.py   # ~4 s: fast LP builder == cvxpy spec on 4 states
.venv/bin/python toy_demo.py              # ~7 s: toy experiment, prints the results table, writes results/toy_fig8.png
.venv/bin/python improvement.py --city toy  # P-eFlx vs eFlx vs Oracle on the toy, writes results/improvement_toy.*
.venv/bin/python paper_extras.py --city toy  # ~11 s: paper's Fig. 11 and Table 1 on the toy, writes results/fig11_toy.png, table1_toy.md
```

## Full Manhattan reproduction (hours)
```bash
.venv/bin/python scripts/get_nyc_data.py   # downloads ~60 MB of TLC data, writes data/manhattan_od.npz (already included)
.venv/bin/python run_manhattan.py --fleet 3200 --days 0 8 16 --out results/manhattan_3200.json
.venv/bin/python make_figures.py manhattan_3200 3200      # Figs 6-10 + claims table
.venv/bin/python paper_extras.py --city manhattan --day 0 --workers 8   # Fig. 11 + Table 1
.venv/bin/python improvement.py --city manhattan --days 0 8 --workers 4 >> results/improvement_manhattan_log.txt
```
eFlx takes ~4 min per 20-minute provision slot at this scale. `--workers` runs policies/days in parallel; `improvement.py` resumes if interrupted. The 13,000-taxi run (the paper's fleet size) is `run_manhattan.py` with the default `--fleet`, followed by `make_figures.py`.

## Headline results
Manhattan, 3,200 taxis, totals over 3 weekdays (`results/manhattan_3200_claims.md`):

| Claim (with charging limit) | Paper | Ours |
|---|---|---|
| Flexibility, eFlx vs TRC | +5.52% | +3.95% |
| DR-window charging, eFlx vs TRC | −19.98% | −4.81% |
| DR-window charging, eFlx vs R2I | −16.36% | −2.27% |
| DR-window charging, eFlx vs Oracle | +0.51% | +4.61% |

- The direction of the paper's claims holds, but the gains are much smaller. Without the charging limit, eFlx does worse than R2I and TES.
- At the paper's fleet size (13,000 taxis), every policy reaches 0 MWh of DR charging, so the policies can't be told apart. That's why we use 3,200 taxis (`results/regime.json`).
- **P-eFlx** cuts DR-window charging vs eFlx by 32% on the toy model and 2.6% on Manhattan, closing ~75% of the gap to the Oracle without knowing the DR start time.

See `NOTES.md` for every assumption we had to make (the paper omits several parameters) and the full list of findings.

## Data
NYC Taxi & Limousine Commission trip records, March 2024 (<https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>). The processed model input `data/manhattan_od.npz` is included; the raw parquet file is downloaded by `scripts/get_nyc_data.py`.

The paper itself is not included (copyright); see the ICCPS 2025 proceedings.
