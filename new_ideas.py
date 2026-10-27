"""Two extensions suggested by gaps in the paper. Both change only the DR service stage,
so each policy provisions once and every variant starts from the same fleet state.

tradeoff  Service vs flexibility: inside the DR window the fleet may serve only (1 - eps) of
          the reference policy's passengers, eps = 0..10%. The paper mentions a "controlled
          service compromise" (Sec. 2.4) but never measures it.
upward    Absorbing surplus power: the grid asks the fleet to charge MORE during the window
          (e.g. surplus solar or wind). The response maximises charging instead of minimising
          it, with the same service and idle-distance rules. The paper only studies cuts.

Run:  .venv/bin/python new_ideas.py --city toy
      .venv/bin/python new_ideas.py --city manhattan --day 0 --workers 8 >> results/new_ideas_manhattan_log.txt
Output: results/new_ideas_<city>.json, results/tradeoff_<city>.png, results/upward_<city>.png
"""
import argparse
import json
import multiprocessing as mp
import pathlib
import pickle
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eflx.sim import run, stage_sum
from paper_extras import setup

POLICIES = ["trc", "r2i", "eflx"]
EPS = [0.0, 0.025, 0.05, 0.075, 0.10]
LABEL = {"trc": "TRC", "r2i": "R2I", "eflx": "eFlx"}
R = pathlib.Path("results")


def provision(args):
    """Fleet state at the DR start after this policy's provision stage (with charging limit)."""
    city_name, day, pol = args
    cache = R / f"ws_{city_name}_{day}_{pol}.pkl"
    if not cache.exists():
        city, state, t0, TAU, TB, N_REC, H = setup(city_name, day)
        _, s_ws = run(city, state, pol, t0, TAU, TB, 0, H, respond=False)   # Tb sets the window eFlx prepares for
        cache.write_bytes(pickle.dumps(s_ws))
    return pol


def service(args):
    city_name, day, pol, variant, eps = args
    city, _, t0, TAU, TB, N_REC, H = setup(city_name, day)
    s_ws = pickle.loads((R / f"ws_{city_name}_{day}_{pol}.pkl").read_bytes())
    t1 = time.time()
    log, _ = run(city, s_ws, "trc", t0 + TAU, 0, TB, 0, H, respond=(variant != "base"),
                 service_eps=eps, upward=(variant == "up"))
    out = dict(policy=pol, variant=variant, eps=eps, day=day,
               charge_kwh=city.kwh(stage_sum(log, "service", "charging")),
               served=stage_sum(log, "service", "served"), wall_s=time.time() - t1)
    print(f"{pol:5s} {variant:4s} eps={eps:.3f}  DR charge {out['charge_kwh']:9.1f} kWh  "
          f"served {out['served']:9.1f}  {out['wall_s']:.0f}s", flush=True)
    return out


def summarise(results):
    """Per policy: baseline, flexibility at each eps, upward flexibility."""
    rows = {}
    for pol in POLICIES:
        base = [r for r in results if r["policy"] == pol and r["variant"] == "base"]
        if not base:
            continue
        b = base[0]
        cut = {r["eps"]: (b["charge_kwh"] - r["charge_kwh"], r["served"] / b["served"])
               for r in results if r["policy"] == pol and r["variant"] == "down"}
        up = [r["charge_kwh"] - b["charge_kwh"] for r in results if r["policy"] == pol and r["variant"] == "up"]
        rows[pol] = dict(base_kwh=b["charge_kwh"], flex=cut, up_kwh=up[0] if up else None)
    return rows


def report(city_name, results):
    rows = summarise(results)
    scale, unit = (1e3, "MWh") if city_name == "manhattan" else (1, "kWh")
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for pol, style in zip(POLICIES, ("o--", "^:", "s-")):
        if pol in rows and rows[pol]["flex"]:
            e = sorted(rows[pol]["flex"])
            ax.plot([100 * x for x in e], [rows[pol]["flex"][x][0] / scale for x in e], style, label=LABEL[pol])
    ax.set_xlabel("service given up during DR, ε (%)"); ax.set_ylabel(f"flexibility ({unit})")
    ax.set_title(f"Service vs flexibility ({city_name}): serve ≥ (1 − ε) of normal passengers", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(R / f"tradeoff_{city_name}.png", dpi=150); plt.close(fig)

    pols = [p for p in POLICIES if p in rows and rows[p]["up_kwh"] is not None and 0.0 in rows[p]["flex"]]
    if pols:
        fig, ax = plt.subplots(figsize=(6.5, 3.6))
        x = range(len(pols))
        ax.bar([i - 0.2 for i in x], [rows[p]["flex"][0.0][0] / scale for p in pols], 0.4, label="cut charging (paper's DR)")
        ax.bar([i + 0.2 for i in x], [rows[p]["up_kwh"] / scale for p in pols], 0.4, label="extra charging (absorb surplus)")
        ax.set_xticks(list(x)); ax.set_xticklabels([LABEL[p] for p in pols])
        ax.set_ylabel(f"flexibility in the 2-h window ({unit})")
        ax.set_title(f"Downward vs upward flexibility ({city_name}), same provisioning", fontsize=10)
        ax.grid(alpha=0.3, axis="y"); ax.legend(fontsize=8); fig.tight_layout()
        fig.savefig(R / f"upward_{city_name}.png", dpi=150); plt.close(fig)

    for pol, r in rows.items():
        flex = ", ".join(f"ε={100 * e:g}%: {v[0] / scale:.2f} {unit} (served {100 * v[1]:.1f}%)"
                         for e, v in sorted(r["flex"].items()))
        up = f"{r['up_kwh'] / scale:.2f} {unit}" if r["up_kwh"] is not None else "-"
        print(f"{LABEL[pol]:5s} baseline {r['base_kwh'] / scale:.2f} {unit} | {flex} | upward {up}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=["toy", "manhattan"], default="toy")
    ap.add_argument("--day", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    out = R / f"new_ideas_{args.city}.json"
    results = json.loads(out.read_text()) if out.exists() else []
    done = {(r["policy"], r["variant"], r["eps"]) for r in results}
    tasks = [(args.city, args.day, p, "base", 0.0) for p in POLICIES]
    tasks += [(args.city, args.day, p, "down", e) for p in POLICIES for e in EPS]
    tasks += [(args.city, args.day, p, "up", 0.0) for p in POLICIES]
    todo = [t for t in tasks if (t[2], t[3], t[4]) not in done]
    print(f"{len(todo)} of {len(tasks)} tasks to run", flush=True)
    with mp.Pool(args.workers) as pool:
        pool.map(provision, [(args.city, args.day, p) for p in POLICIES])
        print("provisioning done", flush=True)
        for r in pool.imap_unordered(service, todo):
            results.append(r)
            out.write_text(json.dumps(results, indent=1))
    report(args.city, results)


if __name__ == "__main__":
    main()
