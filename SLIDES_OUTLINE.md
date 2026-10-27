# eFlx evaluation: slide outline (3 members, ~14 min)

Each slide lists **On slide** (what's written or shown), **Visual**, and **Say** (speaker notes, to put in your own words).
Manhattan numbers come from `results/manhattan_3200_claims.md`, `results/manhattan_claims.md` (13,000 taxis), `results/regime.json` and `results/improvement_manhattan.json`. Figures come from `results/manhattan_3200_fig*.png`, `results/manhattan_fig6.png`, `results/toy_fig8.png` and `results/improvement_*.png`.

## Submission rules (from the course announcement)
- One zip on HelloIITK: video (.mp4) + slides (.ppt or .pdf). Also a link to the GitHub repo with all artefacts.
- All members speak roughly equally; **real voices, not AI-generated**. Faces are not required (a webcam bubble is optional).
- **Last slide must show each member's percentage contribution.**
- After submission: watch ≥1 other group's video and ask ≥1 question; then answer the questions on ours (n questions for n members is enough).

## Structure and timing
The four activities in the project brief map onto sections: *implement* → 3, *reproduce* → 4–5, *new ideas* → 6, *new use cases* → 4 and 6. "Evaluate the paper" → 2 and 5.

| # | Section | Slides | Time | Speaker |
|---|---|---|---|---|
| 1 | Paper summary: problem, model, eFlx algorithm, claims | 1–6 | 2.5 min | A |
| 2 | Critique of the formulation | 7 | 1.5 min | A |
| 3 | Implementation: code map, assumptions, validation | 8–9 | 1.5 min | B |
| 4 | Toy results, regime dependence, LP degeneracy, live demo | 10–13 | 3 min | B |
| 5 | Manhattan reproduction: ours vs paper, claims table, honest analysis, Fig. 11 + Table 1 | 14–18 | 3 min | C |
| 6 | Extensions: new use cases + P-eFlx | 19–20 | 2 min | C |
| 7 | Conclusion + contribution slide | 21–22 | 1 min | all |

Per person: A ≈ 4 min, B ≈ 4.5 min, C ≈ 4.5 min, plus a shared closing. Rough pace: ~40–50 s per slide.

---

## Section 1: Paper summary (Member A, slides 1–6, ~2.5 min)

### Slide 1: Title
- **On slide:** "Evaluating eFlx: Energy Flexibility Provisioning for E-taxi Fleets". Paper: Zhou, Zhao, Yuan, Xu, Lin, ICCPS 2025. CS637 project, team names, roll numbers.
- **Visual:** a taxi + grid icon, or the paper's Fig. 4 framework diagram, small.
- **Say:** Introduce the team and the paper. State the goal: this is a **reproduction study**. We rebuilt the method from the paper alone (no code is public), reproduced the experiments on real NYC data, critiqued the paper, and extended it with new experiments and an improved algorithm.

### Slide 2: Why e-taxi fleets matter for the grid
- **On slide:**
  - An e-taxi uses >50 kWh/day; a 13,000-taxi fleet is a major electricity consumer
  - Demand Response (DR): the grid asks consumers to cut load in emergencies (e.g. NYISO DSASP, respond within 10 min)
  - Unlike buildings or factories, a fleet can shift charging in **time and space** without losing passengers
- **Visual:** paper Fig. 1 (provision → service → recovery stages).
- **Say:** Walk through the three stages. Key idea: the fleet must be *ready* at all times, because the DR request can come without warning.

### Slide 3: Where flexibility comes from
- **On slide:** flexibility = spare taxis (redundancy) × stored energy (energy reserve). The paper targets the hard middle case: some spare taxis, some energy.
- **Visual:** paper Fig. 3 (2×2 quadrant).
- **Say:** If every taxi is needed for passengers, nothing can be cut. If there are many spare, charged taxis, it's easy. The interesting regime is in between. (B and C later show we hit both extremes.)

### Slide 4: The model
- **On slide:**
  - City → regions; battery → 15 levels; time → 20-min slots
  - Taxi states: vacant, occupied, charging, waiting
  - Decisions: send vacant taxis to regions (y) or chargers (x); charge (u)
  - Linear dynamics (Eq. 1–4), fixed probabilities P, Q from historical data
- **Visual:** a simple diagram: region ↔ station arrows, battery bar going down 1 level per slot and up 3 per charging slot.
- **Say:** Everything is counted, not tracked per taxi ("fluid" model), and counts are real numbers, so it's a linear program (LP).

### Slide 5: The method
- **On slide:**
  - Reference policy (Problem 3): maximise passengers served (= TRC)
  - Response policy (Problem 1): minimise charging during DR, same service
  - Provisioning (Problem 4): choose actions *now* that maximise flexibility later → **bi-level** (an optimisation inside an optimisation)
  - Trick: predict the reference → single LP (Problem 5), iterate (Algorithm 1), run as MPC assuming DR starts next slot (τ = 1)
- **Visual:** paper Fig. 5 (bi-level structure) or a flowchart of Algorithm 1.
- **Say:** Explain why it's hard: the policy being optimised is also the baseline flexibility is measured against, which gives an infinite loop. They break it by using the reference policy as the baseline.

### Slide 6: The paper's claims
- **On slide:**
  - Setup: ~13,000 Manhattan e-taxis, real NYC data, DR window 17:20–19:20
  - Baselines: TRC (normal operation), R2I (park idle taxis at stations), TES, Oracle (knows the DR start time)
  - Claims: **+5.52%** flexibility vs TRC; **−19.98%** DR-window charging vs TRC; within **0.52%** of the Oracle; overhead ~2% (idle driving, waiting); passenger service unchanged
- **Visual:** a short claims list, or the paper's Table 1 cropped.
- **Say:** These are the numbers we set out to test. Note that the headline "19.98%" is DR-window charging, while the flexibility gain itself is only 5.52%.

---

## Section 2: Critique of the formulation (Member A, slide 7, ~1.5 min)

### Slide 7: What we question in the paper itself
- **On slide:**
  1. **Metric:** flexibility (Eq. 6) is measured against each policy's *own* baseline, so a policy with a higher baseline looks "more flexible" even if it charges more during DR
  2. **Objective:** Problem 5 never rewards storing energy, so removing the charging limit can make eFlx charge *less* before DR
  3. **Missing parameters:** β, η, battery size, charger power, number of ports, number of days evaluated
  4. **Energy use:** L1 = 1 level per 20 min means a battery lasts ~4.7 h, about 3–4× the paper's own ">50 kWh/day" figure; more consumption → more charging → more flexibility
  5. **Mobility model:** P, Q are fixed, so supply beyond demand still turns "occupied" at the same rate
  6. **"Oracle" is not a real bound:** it is also re-planned greedily each slot, so it can lose to eFlx
  7. Notation slips (Eq. 6 has a free index l; Eq. 5b indexes u by region instead of station)
- **Visual:** numbered list, with icons for the top three.
- **Say:** These matter because they change what the results mean. Hand over to B: "To test the claims, we had to rebuild the system ourselves."

---

## Section 3: Implementation (Member B, slides 8–9, ~1.5 min)

### Slide 8: Rebuilding eFlx with no code
- **On slide:**
  - **Stack:** Python, numpy/scipy, cvxpy, HiGHS LP solver (free), pandas for NYC data, matplotlib; runs on a laptop
  - **Code map** (the paper is the specification; each equation becomes code):
    | Paper | Our code |
    |---|---|
    | Eq. 1–4, 5e–5g | `eflx/model.py` (readable, cvxpy) |
    | Problems 1, 3, 5, Alg. 1, baselines | `eflx/policies.py` |
    | Alg. 2 (MPC), Eq. 6 | `eflx/sim.py` |
    | Manhattan-scale LP | `eflx/fastplan.py` (sparse matrix → HiGHS) |
    | NYC data → demand and trip matrices | `scripts/get_nyc_data.py`, `eflx/manhattan.py` |
  - **Challenges:** missing parameters (we chose β = 0.01, η = 0.05, 3 kWh per battery level, 4,000 ports); TRC's charging is undefined (tiny reward to charge when a port is free); the 38 Con Edison regions aren't public (12 regions clustered from taxi zones). Full list in `NOTES.md`.
- **Visual:** the GitHub folder tree, plus Eq. (1) from the paper next to the 3 lines of Python that implement it.
- **Say:** Every assumption is documented so someone else can change it.

### Slide 9: How we know our code is right
- **On slide:**
  - Taxi count is conserved every slot (assert in the simulator)
  - Toy model small enough to check by hand
  - Readable cvxpy version vs fast sparse version: **identical optimal values** on 4 test states
  - Fast version: **~20× faster** (toy run 4 min → 12 s)
- **Visual:** the test output (case 0–3 "identical"), plus a timing bar.
- **Say:** The readable version is the "spec", the fast version is what we run at scale, and the test proves they agree.

---

## Section 4: Toy results, findings and demo (Member B, slides 10–13, ~3 min)

### Slide 10: Toy model results (new small use case)
- **On slide:** 2 regions, 2 stations, 100 taxis, DR 17:20–19:20.
  | Policy | Flexibility (kWh) | DR charging (kWh) |
  |---|---|---|
  | TRC | 870 | 1050 |
  | R2I | 1256 | 628 |
  | eFlx | 1267 | 653 |
  | Oracle | 1270 | 650 |
- **Visual:** `results/toy_fig8.png`.
- **Say:** The paper's core idea reproduces: provisioning cuts DR charging by ~38% vs TRC at 100% service. Point out the spike back to full charging at 19:20 (rebound; C returns to this).
- **Source:** `results/toy_results.txt` (current code, fast builder; re-run on Oct 22 and matches these numbers). The older run with the cvxpy builder (TRC 1083, R2I 668, eFlx 712, Oracle 561 kWh) is kept in `results/toy_results_cvxpy_builder.txt` for Slide 12.

### Slide 11: Finding 1, flexibility depends on spare capacity
- **On slide:** first toy setup: fleet slightly short (95% served) → **every policy had ~0 flexibility**. At 70% demand, flexibility appears.
- **Visual:** two bars: "under-supplied: ~0 kWh" vs "moderate load: 870–1270 kWh".
- **Say:** This confirms the paper's Fig. 3 with numbers, which the paper only shows qualitatively. The gains depend heavily on how many spare taxis the fleet has, so the paper should report results across fleet sizes (C shows this on Manhattan).

### Slide 12: Finding 2, results depend on which optimum the solver picks
- **On slide:**
  - Both builders reach the same optimal *objective* but choose different optimal *solutions*
  - Downstream outcome changes by up to ~15% (Oracle DR charging 561 vs 650 kWh)
  - Also found: the Oracle must see the whole DR window, otherwise it does worse than eFlx (a bug we hit ourselves)
- **Visual:** the two toy tables side by side, differences highlighted.
- **Say:** The paper's LPs have many tied solutions, so reported small gaps (like "0.52% from Oracle") may be within solver noise. A fix: add explicit tie-breaking objectives and report them.

### Slide 13: Live demo (pre-recorded screen capture, ~45 s)
- **On slide / screen:**
  1. GitHub repo page → `README.md` (setup + how to run)
  2. `.venv/bin/python tests/test_fastplan.py` → cases 0–3 "identical"
  3. `.venv/bin/python toy_demo.py` (~12 s) → results table prints, `results/toy_fig8.png` is generated and opened
- **Visual:** the terminal recording itself.
- **Say:** Anyone can clone the repo and get these numbers. The Manhattan runs use the same code but take ~4 min per 20-min slot, so we show their saved outputs instead of running them live. Hand over to C for the real-data results.
- **Note:** record this clip in advance so nothing can fail on camera. Needs the GitHub repo and README to exist first.

---

## Section 5: Manhattan reproduction (Member C, slides 14–17, ~2.5 min)

### Slide 14: Real NYC data
- **On slide:**
  - NYC TLC yellow-taxi trips, March 2024: **2.01 M** weekday Manhattan trips over 21 days
  - 62 zones clustered into 12 regions using trip distances (the paper's 38 grid regions aren't public)
  - ~2,430 trips per 20-min slot at the 17:20–19:20 peak; 84% of trips finish within one slot
  - L = 15, L1 = 1, L2 = 3 (paper values); 4,000 ports, 3 kWh/level (our choices)
- **Visual:** demand-per-slot curve over a day, DR window shaded (can add to `make_figures.py`).
- **Say:** Mention each assumption and why.

### Slide 15: Reproducing Figs 6 and 7, ours next to the paper's
- **On slide:** flexibility and DR-window charging per policy, with and without the charging limit, **mean ± sd over 3 weekdays** (the paper shows no error bars).
- **Visual:** paper Fig. 6 / Fig. 7 on the left; `results/manhattan_3200_fig6.png`, `results/manhattan_3200_fig7.png` on the right.
- **Say:** At the paper's 13,000 taxis, *every* policy cuts DR charging to 0 MWh, so the claim can't be tested; that's why we use a tight 3,200-taxi fleet (Slide 18 explains how we picked it). There, eFlx < R2I < TRC in DR charging holds in direction, but the error bars are large: day 16 is far easier than days 0 and 8.

### Slide 16: Claim-by-claim comparison
- **On slide:** the table from `results/manhattan_3200_claims.md` (Paper vs Ours for each claim), each row marked ✓ holds / ✗ doesn't / ~ partly.
- **Visual:** the table with coloured ticks.
- **Say:** With the charging limit: DR charging eFlx vs TRC −4.8% (paper −19.98%), vs R2I −2.3% (paper −16.36%), gap to Oracle 4.6% (paper 0.51%); flexibility +4.0% (paper +5.52%), the closest match. Without the limit, eFlx is *worse* than R2I and TES (+11% / +10%; paper −25% / −31%). The gain comes almost entirely from one day (day 0 −1.4%, day 8 0%, day 16 −41%). Service matches TRC, so eFlx isn't dropping passengers. **Why the gap:** unpublished parameters, fleet-size regime, LP degeneracy, day-to-day variation, not hardware or random seeds.

### Slide 17: Overhead + experimental-design critique
- **On slide:**
  - Overhead (Figs 9, 10): idle driving +9.7%, waiting at stations +44% vs paper's +2.06% / +2.12%
  - Runtime: 236 s per 20-min slot vs paper's 254.7 s; Algorithm 1 needs 3.9 iterations on average (not reported in the paper)
  - 13,000-taxi run: eFlx scores ~40% higher "flexibility" while every policy charges 0 MWh during DR (Eq. 6 baseline effect, evidence for Slide 7's metric critique)
  - Experimental design: only one DR window (17:20); unclear number of days; no variance; fluid model used as both optimiser and "simulator"; noise model for the robustness test not given; **rebound after DR not measured**
- **Visual:** `results/manhattan_3200_fig10.png` + `results/manhattan_3200_fig8.png` with the post-19:20 spike circled.
- **Say:** The rebound matters: pushing charging out of the DR window can create a new peak for the grid.

### Slide 17b (deck slide 18): Fig. 11 and Table 1
- **On slide:** paper Fig. 11 above our Fig. 11 (toy; Manhattan when its run finishes); Table 1 comparison: paper flexibility −1.33% / DR charging +7.69% vs ours (toy) +3.6% / −7.0% with service 95.4%.
- **Say:** Fig. 11 holds: more lead time, more flexibility. Table 1 flips sign because the noisy plan misses ~5% of passengers, which the paper never reports; eFlx still beats TRC. Deck slides after this one are numbered one higher than in this outline.

---

## Section 6: Extensions (Member C, slides 18–19, ~2 min)

### Slide 18: New use cases we added
- **On slide:**
  - **Fleet-size sweep** (13,000 → 3,200 taxis): best possible DR charging is 0 MWh down to 4,000 taxis; only at 3,200 does it stay above 0 (6.6 MWh). The paper's fleet sits in the "easy" corner of its own Fig. 3.
  - **DR starting at different times** (16:40 / 17:20 / 18:00) instead of the paper's single 17:20 window
  - **Multiple weekdays** with error bars instead of one scenario
  - **Toy model** (Slides 10–12) and **rebound after DR**
- **Visual:** small table of fleet size vs TRC DR charging vs best possible DR charging (from `NOTES.md`).
- **Say:** These show *when* eFlx helps, which the paper doesn't test.

### Slide 19: Our improvement: P-eFlx (probabilistic DR arrival)
- **On slide:**
  - Problem: eFlx always assumes "DR starts in the next 20 min" (τ = 1), which is too pessimistic; the Oracle knows the exact start, which is unrealistic
  - P-eFlx: use a prior over start times (e.g. DR events cluster around the evening peak); each slot, minimise **expected** DR charging given DR hasn't started yet
  - One-line change: weight w_k = P(slot k is inside the DR window | not started yet); same LP size as eFlx
  - Sanity: with a "next slot" prior, P-eFlx = eFlx exactly
  - Toy result: **−32% DR charging vs eFlx** on average, better at every true start time; hedged version (ρ = 0.1) keeps readiness for an immediate DR
  - Manhattan (3,200 taxis, 2 days × 3 start times): **−2.6% DR charging vs eFlx** (uniform prior −2.0%); closes ~75% of the gap to the Oracle without knowing the start time; eFlx itself was worse than TRC (+1.3%)
  - Honest caveats: day 0 shows no difference; part of day 8's gain at 16:40 coincides with ~1 pp lower service
- **Visual:** `results/improvement_toy.png` and `results/improvement_manhattan.png`.
- **Say:** Same charging before DR, but more energy left at DR start, because idle taxis are parked instead of cruising and the fleet is positioned for the likely window.

---

## Section 7: Conclusion (all, slides 20–21, ~1 min)

### Slide 20: Conclusion
- **On slide:**
  - ✓ Core idea holds: provisioning increases fleet flexibility at full service
  - ~ Size of gains: −4.8% DR charging vs TRC (paper −19.98%), Oracle gap 4.6% (paper 0.51%)
  - ✗ Without the charging limit eFlx loses to R2I/TES; at the paper's fleet size nothing can be compared (all 0 MWh)
  - Limitations of our work: our parameter choices, 12 regions instead of 38, fluid simulator (not per-taxi), 3 weekdays
  - With more time: per-taxi (agent-based) simulator, explicit LP tie-breaking, more DR windows and days, learn the DR-start prior from real grid data
  - Our contribution: open re-implementation, multi-day evaluation with error bars, new use cases, P-eFlx
- **Visual:** three short columns: Holds / Doesn't hold / We improved.
- **Say:** Split it: A reads "holds / doesn't hold", B the limitations, C the future work. One line each on what we learned (reproducing a paper with no code mostly means discovering what it leaves out).

### Slide 21: Contribution (required)
- **On slide:**
  | Member | Contribution | Tasks |
  |---|---|---|
  | A | 33.3% | Paper analysis, formulation critique, slides 1–7 |
  | B | 33.3% | Implementation, validation, toy experiments, demo, slides 8–13 |
  | C | 33.3% | Data pipeline, Manhattan experiments, new use cases, improvement, slides 14–19 |
- **Say:** Thank you; all three speak for this closing line.
