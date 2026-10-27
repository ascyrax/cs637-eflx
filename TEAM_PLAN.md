# CS637 project: eFlx evaluation, team plan (3 members)

## Who owns what
| | Member A: the paper & its formulation | Member B: implementation & validation | Member C: data, reproduction & improvement |
|---|---|---|---|
| Work | Explain Sec. 2–6; critique of the *formulation* | `eflx/model.py`, `fastplan.py`, `tests/`, `toy_demo.py` | `scripts/get_nyc_data.py`, `run_manhattan.py`, `make_figures.py`, improvement experiment |
| Critique points | Flexibility metric is relative to each policy's own baseline; no reward for storing energy (Problem 5); missing parameters (β, η, battery, ports); unrealistic energy use (L1 = 1 per slot); P/Q don't depend on served demand | LP degeneracy (same optimum, different solutions → different results); fractional taxis; the same model is used as both optimiser and simulator; Oracle horizon pitfall | Only one DR window (17:20); no error bars / number of days; rebound after DR; sensitivity to fleet size / ports; eFlx vs Oracle gap |
| Slides | 1–7 | 8–13 (incl. demo) | 14–19 |

## Slide outline (~21 slides, ~14 min video, ~4.5 min per person; full detail in SLIDES_OUTLINE.md)
**Member A**
1. Title, team, paper citation
2. Motivation: e-taxi fleets as demand-response (DR) providers; the 3 DR stages (paper Fig. 1)
3. Where flexibility comes from: taxi redundancy × energy reserve (Fig. 3)
4. The model: regions, battery levels, vacant/occupied/charging states (Eq. 1–4)
5. Reference / response / provisioning problems; why it is bi-level; Algorithm 1 and MPC (Alg. 2)
6. The paper's claims (+5.52% flexibility, −19.98% DR charging, within 0.52% of Oracle) + formulation critique

**Member B**
7. "No code released": how we rebuilt it from the equations (code map)
8. Validation: cvxpy spec vs fast sparse LP give identical optima; taxi conservation checks
9. Toy model results (2 regions, 100 taxis) + recreated Fig. 8
10. Finding: regime dependence (a supply-starved fleet has ~0 flexibility)
11. Finding: LP degeneracy changes results by up to ~15%; assumptions we had to make

**Member C**
12. NYC TLC data pipeline: 2M trips → 12 regions, demand per slot
13. Manhattan reproduction: Figs 6 and 7 (ours vs paper)
14. Claims table: paper vs ours
15. Overhead (Figs 9, 10) + experimental-design critique
16. Our improvement + results
17. Conclusion: what holds, what doesn't, what we'd change
18. **Contribution: A 33.3% · B 33.3% · C 33.3%** (list each person's tasks)

## Schedule (deadline Oct 30)
| Dates | A | B | C |
|---|---|---|---|
| Oct 21–23 | Read paper deeply, draft slides 1–6 | Run toy + tests, understand code | Run Manhattan experiment, check results |
| Oct 24–26 | Formulation critique; help B/C check | Degeneracy / sensitivity experiments | Improvement experiment |
| Oct 27–28 | Script + final slides | Script + final slides | Script + final slides |
| Oct 29 | Record together (real voices), merge video, export PDF | | |
| Oct 30 | Zip .mp4 + slides, submit on HelloIITK | | |
