# eFlx re-implementation: notes

## Code map
| File | Paper section |
|---|---|
| `eflx/model.py` `Plan` | Sec. 3: state, decisions, Eq. (1)–(4), (5e)–(5g), J_trans, J_idle |
| `eflx/model.py` `step` | our fluid "simulator" (same equations, applied with numbers) |
| `eflx/policies.py` `reference` | Problem 3 (TRC) |
| `eflx/policies.py` `response` | Problem 1 / Problem 5 |
| `eflx/policies.py` `eflx` | Algorithm 1 (τ = 1) |
| `eflx/policies.py` `oracle`, `r2i`, `tes` | baselines of Sec. 7.1 |
| `eflx/sim.py` | Algorithm 2 (MPC loop) and flexibility metric Eq. (6) |
| `toy_demo.py` | 2-region toy experiment |
| `scripts/get_nyc_data.py` | NYC TLC data → demand / OD matrices |

## Assumptions (the paper does not specify these)
1. **β** (idle-distance weight in Problem 3) = 0.01; **η** (Eq. 5d) = 0.05.
2. **Energy per level**: the paper reports MWh but never gives battery size or charger power. Toy: 10 kWh/level, so one charging slot = 20 kWh (60 kW charger).
3. **TRC charging is undefined**: Problem 3 has no charging term, so how much the reference policy charges is arbitrary (many optimal LP solutions). We add a tiny reward (1e-3) so it charges whenever a port is free.
4. A taxi charges only if a full slot of charge (L2 levels) fits in the battery.
5. Taxis at level ≤ L1 cannot serve (Eq. 5g, translated to 0-based levels).
6. Algorithm 1's initial reference prediction Ĵ⁰ comes from solving Problem 3 on the current state, not from historical data.
7. **R2I** is our LP reading of the paper's one-paragraph description: keep TRC service, park as many idle taxis at stations as possible.
8. **Oracle horizon**: it must cover the whole DR window. With T_c = 10 slots and a 2-hour provision stage, it would otherwise not see part of the window (we hit this bug ourselves).
9. Manhattan is split into TLC-zone groups. The paper's 38 Con Edison grid regions are not available as a zone list.

10. **Manhattan instance** (`eflx/manhattan.py`): 12 regions built by clustering 62 TLC zones on trip distances; one charging hub per region; 4,000 ports total, split by drop-off share; 3 kWh per level (42 kWh battery, 27 kW charging); 13,000 taxis; a dispatch must be under 4 miles. The chance an available taxi gets a trip = demand / (0.7 × fleet), and a trip longer than one slot ends with probability 0.8 per slot. Warm-up runs TRC 12:00–15:20.
11. The paper's own parameters imply a very high energy use: L1 = 1 level per 20 min with 15 levels means a full battery lasts about 4.7 h of cruising. That is roughly 3–4× the ">50 kWh per day" the paper cites ([5]) for a 12 h shift. Higher consumption means more charging, and more charging means more flexibility.

## Validation
- `tests/test_fastplan.py`: the fast sparse builder gives the same optimal objective as the cvxpy spec on 4 toy states (reference and response LPs).
- **LP degeneracy:** both builders reach the same optimum but pick *different optimal solutions*. In the toy this moves the policy outcomes by up to ~15% (e.g. Oracle DR charging 561 vs 650 kWh). The paper's LPs have many equally good solutions, so its reported numbers partly depend on the solver's tie-breaking. This is a reproducibility issue worth a slide.

## Findings so far (toy model, preliminary)
- **Reproduced:** with a moderately loaded fleet, eFlx provisioning increases flexibility and cuts DR-window charging vs TRC, at 100% service.
- **Regime dependence:** with an under-supplied fleet (95% service), *every* policy has ~0 flexibility. The benefit depends heavily on spare capacity, which the paper only discusses qualitatively (Fig. 3).
- **eFlx is not within 0.5% of the Oracle** in our toy (the paper claims 0.52%). DR-window charging: Oracle 561 kWh, eFlx 712 kWh, TRC 1083 kWh. See results/toy_results.txt.
- **R2I beats eFlx on DR-window charging** in the toy (668 vs 712 kWh), although eFlx has higher "flexibility". The paper reports the opposite (eFlx 16% lower than R2I).
- **Rebound effect:** every policy jumps straight back to full charging power at 19:20 (results/toy_fig8.png). The paper doesn't measure this.
- **The flexibility metric (Eq. 6) is relative to each policy's own baseline**, so a policy whose baseline charges more looks "more flexible" even if it charges more during the DR window. Compare the flex and DR-charge columns: their rankings differ.
- **Problem 5 doesn't reward storing energy** during provisioning (it only minimises DR-window charging). Removing the charging limit can therefore lead to *less* provision charging; our eFlx run without the limit charged less than with it.
- **Model consistency:** the mobility probabilities P, Q are fixed and don't depend on how much demand is actually served (Eq. 2b–2c), so supply exceeding demand still turns "occupied" at the same rate.

## Improvement: P-eFlx (probabilistic DR arrival)
- **Idea:** eFlx always assumes DR starts next slot (τ = 1); the Oracle knows the exact start. P-eFlx takes a prior over start times and, at each slot (given DR hasn't started yet), minimises *expected* DR-window charging: slot k gets weight w_k = Σ_s P(start = s | start > t) · 1[s ≤ t+k < s+T_b]. Same LP size as eFlx, only the objective weights change (`policies.dr_weights`, `policies.p_eflx`).
- **Optional hedge ρ:** also keep "immediate-DR" readiness within (1+ρ) of eFlx's best value.
- **Sanity check:** with a "next slot" prior, P-eFlx reproduces eFlx exactly (flex 1266.9150 kWh in both).
- **Toy result** (`results/improvement_toy.png`; prior centred on slot 6, true start varied 2/4/6/8). Mean DR-window charging: eFlx 677 kWh, P-eFlx 461 kWh (**−32%**), hedged 512, uniform prior 479, Oracle 656. P-eFlx is better at every true start, including early ones where its prior is wrong.
- **Why it works:** provision charging is about equal for every policy (~1790 kWh at start 6), but P-eFlx enters DR with more stored energy (4342 vs 4083 kWh). eFlx keeps chasing a window that moves forward every slot; P-eFlx parks idle taxis (no energy used) and positions the fleet for the likely window.
- **Caveat:** the "Oracle" is not a true upper bound in closed loop. It is re-planned greedily each slot like the others, and in the toy it does worse than eFlx at early starts. The paper calls it a "performance bound" (Sec. 7.2.1), which is not justified.

## Manhattan regime (fleet size) finding
Open-loop check from the 15:20 fleet state (day 0, ports = 0.3 × fleet): can DR-window charging (17:20–19:20) be cut to zero with 100% service?

| Fleet | TRC DR charging | Best possible DR charging |
|---|---|---|
| 13,000 (paper) | — | 0 MWh (every policy reached 0 in the closed-loop runs) |
| 8,000 | 100.6 MWh | 0 MWh |
| 6,000 | 66.2 MWh | 0 MWh |
| 5,000 | 59.0 MWh | 0 MWh |
| 4,000 | 35.0 MWh | 0 MWh |
| **3,200** | 12.5 MWh | **6.6 MWh** |

- Arithmetic behind it: ~2,400 taxis on the road burn ~14,400 levels in 2 h, while 5,000 taxis hold ~45,000 levels, and parked taxis use no energy. In the paper's model, a Manhattan fleet is almost always in the "high flexibility, no cost" corner of Fig. 3.
- The paper reports nonzero eFlx DR charging (30.7 MWh, Table 1) with 13,000 taxis, so its unpublished parameters must make the fleet much tighter. Its results depend on that choice, and it shows no sensitivity analysis.
- 13,000-taxi results are kept as the "easy regime" (`results/manhattan.json`). In that regime, eFlx and Oracle both reach 0 MWh during DR, yet eFlx's "flexibility" is ~40% higher, purely because of the Eq. 6 baseline. That's direct evidence for the metric critique.
- Main comparisons use **3,200 taxis** (`results/regime.json`, `results/manhattan_3200.json`, `results/improvement_manhattan.json`).

## Manhattan reproduction at 3,200 taxis (3 weekdays; `results/manhattan_3200_claims.md`)
- Claims compared on **totals over days**; a mean of daily ratios blows up on easy days (day 16 has only 0.2–4.6 MWh of DR charging).
- **Direction holds, size doesn't:** with the charging limit, eFlx cuts DR charging by 4.8% vs TRC (paper: 19.98%) and 2.3% vs R2I (paper: 16.36%). Flexibility +4.0% vs TRC (paper +5.52%), the closest match.
- **The gain comes from one day:** day 0: −1.4%, day 8: 0%, day 16: −41% vs TRC. Results vary a lot by day, and the paper reports no per-day variation.
- **Without the charging limit eFlx loses to R2I and TES** (+11% and +10% more DR charging). The paper reports eFlx −25% and −31%.
- **Oracle gap is 4.6%**, not 0.51%.
- **Service:** eFlx matches TRC on every day (98.83 vs 98.85%, 94.91 vs 94.82%, 100 vs 100%), so no gain comes from dropping passengers. But at 3,200 taxis nobody serves 100% on days 0 and 8.
- **Overhead is higher than claimed:** idle driving +9.7% (paper +2.06%), waiting +44% (paper +2.12%).
- Runtime: 236 s per provision slot (paper 254.7 s), Algorithm 1 averages 3.9 iterations (max 5).

## P-eFlx at Manhattan scale (3,200 taxis; days 0 and 8; true DR start 16:40 / 17:20 / 18:00)
Totals of DR-window charging over 6 runs (`results/improvement_manhattan.json`, `results/improvement_manhattan.png`):

| Policy | DR charging | vs eFlx | Mean service |
|---|---|---|---|
| TRC | 130.3 MWh | −1.3% | 96.63% |
| eFlx | 132.0 MWh | — | 96.78% |
| **P-eFlx (normal prior)** | **128.5 MWh** | **−2.6%** | 96.63% |
| P-eFlx (uniform prior) | 129.3 MWh | −2.0% | 96.82% |
| Oracle | 127.5 MWh | −3.4% | 96.77% |

- **Day 0:** everyone within ~1% (no room to shift charging that day). **Day 8:** P-eFlx beats eFlx at all three start times (−9%, −3%, −4%).
- P-eFlx closes ~75% of the gap between eFlx and the Oracle, without knowing the start time.
- **eFlx did worse than plain TRC overall (+1.3%)**: always assuming "DR next slot" can backfire.
- **Service caveat:** on day 8 at 16:40, P-eFlx (normal) served 92.9% vs eFlx 94.0%, so part of that day's gain may come from serving fewer passengers. Overall average service: 96.63% vs 96.78%. The uniform-prior version gets −2.0% *with* higher service than eFlx.
- Much smaller than the toy's −32%: the tight Manhattan fleet has little room to shift charging, the same pattern as the reproduction.
