"""The two paper experiments not covered by run_manhattan.py.

fig11   Fig. 11 (Sec. 7.2.3): flexibility and DR-window charging vs the length of the
        provision stage. The DR window stays fixed; provisioning starts tau slots before it
        (the fleet runs TRC until then).
table1  Table 1 (Sec. 7.2.4): eFlx under passenger-demand prediction error. The planner sees
        a noisy forecast, the fleet meets the true demand. The paper only says "random noise"
        equivalent to a 10% error; ASSUMPTION: forecast = demand * (1 + e), e ~ N(0, s) with
        s = 0.125, i.e. a mean absolute error of 10%, drawn independently per slot and region.

Run:  .venv/bin/python paper_extras.py --city toy
      .venv/bin/python paper_extras.py --city manhattan --day 0 --workers 8 >> results/extras_manhattan_log.txt
Output: results/extras_<city>.json, results/fig11_<city>.png, results/table1_<city>.md
Resumable: finished tasks in results/extras_<city>.json are skipped on restart.
"""
import argparse
import dataclasses
import json
import multiprocessing as mp
import pathlib
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from eflx import policies as P
from eflx.model import step
from eflx.sim import flexibility

NOISE_SD = 0.125            # mean |e| = 0.125 * sqrt(2/pi) = 10%
SEEDS = {"toy": list(range(10)), "manhattan": [0, 1]}
R = pathlib.Path("results")


def setup(city_name, day):
    """-> city, fleet state at the earliest provision start, that start, TAU, TB, N_REC, H"""
    if city_name == "toy":
        import toy_demo as T
        city = T.toy_city()
        return city, T.toy_init(city), 0, T.TAU, T.TB, T.N_REC, T.H
    from eflx import manhattan as M
    fleet = json.loads((R / "regime.json").read_text())["fleet"]
    city = M.make_city(day, fleet=fleet, ports_total=0.3 * fleet)
    return city, M.warm_state(day, fleet), M.PROVISION_START, M.TAU, M.TB, M.N_REC, M.H


def noisy_forecast(demand, seed):
    e = np.random.default_rng(seed).normal(0, NOISE_SD, demand.shape)
    return np.clip(demand * (1 + e), 0, None)


def run_task(args):
    city_name, day, exp, pol, x = args          # x = tau (fig11) or seed / None (table1)
    city, state, t0, TAU, TB, N_REC, H = setup(city_name, day)
    t1 = time.time()
    if exp == "fig11":
        start = t0 + TAU - x                     # same DR window, shorter provisioning
        for t in range(t0, start):               # fleet runs TRC until provisioning starts
            state, _ = step(city, state, P.reference(city, state, t, H).decisions(0), t)
        r = flexibility(city, state, pol, start, x, TB, N_REC, H)
    else:
        plan_city = city if x is None else dataclasses.replace(city, demand=noisy_forecast(city.demand, x))
        r = flexibility(plan_city, state, pol, t0, TAU, TB, N_REC, H, true_demand=city.demand)
    out = dict(exp=exp, policy=pol, x=x, day=day, flex_kwh=r["flex_kwh"],
               dr_charge_kwh=r["service_charge_kwh"], served=r["served"] / r["demand"],
               wall_s=time.time() - t1)
    print(f"{exp} {pol:5s} x={x}  flex {out['flex_kwh']:9.1f} kWh  DR charge {out['dr_charge_kwh']:9.1f} kWh  "
          f"served {100 * out['served']:.2f}%  {out['wall_s']:.0f}s", flush=True)
    return out


def report(city_name, results):
    tag = city_name
    TAU = setup(city_name, 0)[3]
    f11 = [r for r in results if r["exp"] == "fig11"]
    if f11:
        fig, axs = plt.subplots(1, 2, figsize=(9, 3.4))
        for pol, style in (("trc", "o--"), ("eflx", "s-")):
            pts = sorted((r["x"] * 20, r) for r in f11 if r["policy"] == pol)
            for ax, key in zip(axs, ("flex_kwh", "dr_charge_kwh")):
                scale = 1e3 if city_name == "manhattan" else 1
                ax.plot([m for m, _ in pts], [r[key] / scale for _, r in pts], style, label=pol.upper().replace("EFLX", "eFlx"))
        unit = "MWh" if city_name == "manhattan" else "kWh"
        axs[0].set_title("(a) Flexibility"); axs[0].set_ylabel(f"flexibility ({unit})")
        axs[1].set_title("(b) Charging during DR"); axs[1].set_ylabel(f"charging energy ({unit})")
        for ax in axs:
            ax.set_xlabel("duration of provision stage (min)"); ax.set_xticks([20 * k for k in range(1, TAU + 1)])
            ax.legend(fontsize=8); ax.grid(alpha=0.3)
        fig.suptitle(f"Fig. 11 (ours, {tag}): performance vs duration of provision stage", fontsize=10)
        fig.tight_layout(); fig.savefig(R / f"fig11_{tag}.png", dpi=150); plt.close(fig)
    t1 = [r for r in results if r["exp"] == "table1"]
    if t1:
        unit, scale = ("MWh", 1e3) if city_name == "manhattan" else ("kWh", 1)
        rows = [f"| Policy | Flexibility w/o error ({unit}) | w/ error | change | DR charging w/o error ({unit}) "
                f"| w/ error | change | Served w/ error |", "|---|---|---|---|---|---|---|---|"]
        for pol in ("eflx", "trc"):
            base = [r for r in t1 if r["policy"] == pol and r["x"] is None]
            noisy = [r for r in t1 if r["policy"] == pol and r["x"] is not None]
            if not base or not noisy:
                continue
            b, mean = base[0], lambda k: np.mean([r[k] for r in noisy])
            ch = lambda k: 100 * (mean(k) - b[k]) / b[k] if b[k] else float("nan")
            rows.append(f"| {'eFlx' if pol == 'eflx' else 'TRC'} | {b['flex_kwh'] / scale:.2f} | {mean('flex_kwh') / scale:.2f} "
                        f"| {ch('flex_kwh'):+.2f}% | {b['dr_charge_kwh'] / scale:.2f} | {mean('dr_charge_kwh') / scale:.2f} "
                        f"| {ch('dr_charge_kwh'):+.2f}% | {100 * mean('served'):.2f}% |")
        n = len({r["x"] for r in t1 if r["x"] is not None})
        rows.append(f"\nMean over {n} noise seeds; forecast error: mean absolute error 10% (paper Table 1: "
                    "eFlx flexibility -1.33%, DR charging +7.69%).")
        (R / f"table1_{tag}.md").write_text("\n".join(rows) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=["toy", "manhattan"], default="toy")
    ap.add_argument("--day", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    TAU = setup(args.city, args.day)[3]
    tasks = [(args.city, args.day, "fig11", pol, tau) for tau in range(TAU, 0, -1) for pol in ("eflx", "trc")]
    tasks += [(args.city, args.day, "table1", pol, s) for pol in ("eflx", "trc") for s in [None] + SEEDS[args.city]]
    out = R / f"extras_{args.city}.json"
    results = json.loads(out.read_text()) if out.exists() else []
    done = {(r["exp"], r["policy"], r["x"]) for r in results}
    todo = [t for t in tasks if (t[2], t[3], t[4]) not in done]
    print(f"{len(todo)} of {len(tasks)} tasks to run", flush=True)
    with mp.Pool(args.workers) as pool:
        for r in pool.imap_unordered(run_task, todo):
            results.append(r)
            out.write_text(json.dumps(results, indent=1))
    report(args.city, results)
    print("saved", out, flush=True)


if __name__ == "__main__":
    main()
