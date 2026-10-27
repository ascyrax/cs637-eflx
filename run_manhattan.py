"""Manhattan experiment (paper Sec. 7): every policy on several real weekdays.

For each day: warm up the fleet with TRC from 12:00 to 15:20, then run the
provision (15:20-17:20) / DR service (17:20-19:20) / recovery stages for each
policy, with and without the provisioning charging limit.

Run:  .venv/bin/python run_manhattan.py --days 0 4 8 12 16 --workers 8
Output: results/manhattan.json (read by make_figures.py)
"""
import argparse
import json
import multiprocessing as mp
import pathlib
import time

from eflx import manhattan as M
from eflx import policies as P
from eflx.model import step
from eflx.sim import flexibility

OUT = pathlib.Path("results")
CONFIGS = [(True, "trc"), (True, "r2i"), (True, "eflx"), (True, "oracle"),
           (False, "r2i"), (False, "tes"), (False, "eflx")]


def make(day, fleet):
    return M.make_city(day, fleet=fleet, ports_total=0.3 * fleet)


def warm_state(args):
    day, fleet = args
    return day, M.warm_state(day, fleet)


def run_one(args):
    day, limit, pol, state, fleet = args
    city = make(day, fleet)
    P.STATS.update(lp_solves=0, alg1_iters=[])
    t0 = time.time()
    r = flexibility(city, state, pol, M.PROVISION_START, M.TAU, M.TB, M.N_REC, M.H, charge_limit=limit)
    log = r.pop("log")
    r.update(day=day, limit=limit, wall_s=time.time() - t0, lp_solves=P.STATS["lp_solves"],
             alg1_iters=P.STATS["alg1_iters"],
             charging_kw=[city.kwh(x["charging"]) * 3 for x in log], slots=[x["t"] for x in log])
    print(f"day {day:2d} {'limit' if limit else 'nolim'} {pol:6s} flex {r['flex_kwh'] / 1e3:7.2f} MWh  "
          f"DR charge {r['service_charge_kwh'] / 1e3:7.2f} MWh  served {100 * r['served'] / r['demand']:.2f}%  "
          f"{r['wall_s']:.0f}s", flush=True)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, nargs="+", default=[0, 4, 8, 12, 16])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="results/manhattan.json")
    ap.add_argument("--fleet", type=int, default=13000)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    with mp.Pool(args.workers) as pool:
        warm = dict(pool.map(warm_state, [(d, args.fleet) for d in args.days]))
        print("warm-up done", flush=True)
        # slowest tasks (eFlx) first so the pool stays busy at the end
        order = {"eflx": 0, "oracle": 1, "r2i": 2, "tes": 2, "trc": 3}
        tasks = sorted([(d, lim, pol, warm[d], args.fleet) for d in args.days for lim, pol in CONFIGS],
                       key=lambda x: order[x[2]])
        results = []
        for r in pool.imap_unordered(run_one, tasks):
            results.append(r)
            pathlib.Path(args.out).write_text(json.dumps(results, indent=1))   # keep partial results
    print("saved", args.out)


if __name__ == "__main__":
    main()
