"""Our improvement: P-eFlx, provisioning for a *probabilistic* DR start time.

eFlx (tau = 1) always prepares for a DR request in the very next slot; the Oracle
knows the exact start. P-eFlx uses a prior over start times (e.g. "DR events
cluster around the evening peak") and minimises expected DR-window charging,
conditioned on DR not having started yet.

We vary the TRUE start time to test the prior when it is right, early and late:
    toy:        provision starts slot 0, true starts at slots 2, 4, 6, 8
    manhattan:  provision starts 15:20, true starts 16:00, 16:40, 17:20, 18:00
Run:  .venv/bin/python improvement.py --city toy
      .venv/bin/python improvement.py --city manhattan --days 0 8 --workers 4 >> results/improvement_manhattan_log.txt

Resumable: results are saved after every task (results/improvement_<city>_partial.json),
and finished tasks are skipped on restart -- including ones only recorded in the log.
Append to the log with >> when restarting, so those lines are not wiped.
"""
import re
import argparse
import json
import multiprocessing as mp
import pathlib
import time

import numpy as np

from eflx import policies as P
from eflx.model import step
from eflx.sim import flexibility

TB, N_REC, H = 6, 3, 10
# Manhattan fleet size for this experiment, chosen so DR charging cannot simply drop to zero
# (with 13,000 taxis every policy reaches 0 MWh and nothing can be compared)
REGIME_FILE = pathlib.Path("results/regime.json")
REGIME = json.loads(REGIME_FILE.read_text()) if REGIME_FILE.exists() else None


def normal_prior(T, center, sd):
    s = np.arange(T)
    p = np.exp(-0.5 * ((s - center) / sd) ** 2)
    return p / p.sum()


def setup(city_name, day=0):
    if city_name == "toy":
        import toy_demo as T
        T.T_TOTAL = 30
        city = T.toy_city()
        return city, T.toy_init(city), 0, [2, 4, 6, 8], 6
    from eflx import manhattan as M
    fleet = REGIME["fleet"]
    city = M.make_city(day, fleet=fleet, ports_total=0.3 * fleet)
    state = M.warm_state(day, fleet)
    return city, state, M.PROVISION_START, MANHATTAN_STARTS, M.SLOT(17, 20)


MANHATTAN_STARTS = [50, 52, 54]          # 16:40, 17:20, 18:00
MANHATTAN_POLICIES = ["TRC", "eFlx", "P-eFlx (normal prior)", "P-eFlx (uniform prior)", "Oracle"]
# results identical to the 3,200-taxi reproduction (same day, start 17:20, charging limit)
REUSE = {"TRC": "trc", "eFlx": "eflx", "Oracle": "oracle"}


def policies(T_len, t0, center):
    normal = normal_prior(T_len, center, 2.0)          # "DR usually starts around 17:20 +- 40 min"
    uniform = np.zeros(T_len); uniform[t0 + 1:center + 5] = 1; uniform /= uniform.sum()
    return {"TRC": ("trc", {}), "eFlx": ("eflx", {}),
            "P-eFlx (normal prior)": ("p_eflx", dict(prior=normal)),
            "P-eFlx (normal, hedged rho=0.1)": ("p_eflx", dict(prior=normal, rho=0.1)),
            "P-eFlx (uniform prior)": ("p_eflx", dict(prior=uniform)),
            "Oracle": ("oracle", {})}


def reused(day, start, name):
    f = pathlib.Path(f"results/manhattan_{REGIME['fleet']}.json")
    if start != 52 or name not in REUSE or not f.exists():
        return None
    for r in json.loads(f.read_text()):
        if r["day"] == day and r["limit"] and r["policy"] == REUSE[name]:
            return dict(day=day, start=start, policy=name, flex_kwh=r["flex_kwh"],
                        dr_charge_kwh=r["service_charge_kwh"], served=r["served"] / r["demand"],
                        wall_s=0.0, reused=True)
    return None


def run_task(args):
    city_name, day, start, name = args
    if city_name == "manhattan" and (out := reused(day, start, name)):
        print(f"day {day} start {start} {name:32s} reused from reproduction", flush=True)
        return out
    city, init, t0, _, center = setup(city_name, day)
    pol, kw = policies(len(city.demand), t0, center)[name]
    t_wall = time.time()
    r = flexibility(city, init, pol, t0, start - t0, TB, N_REC, H, **kw)
    out = dict(day=day, start=start, policy=name, flex_kwh=r["flex_kwh"],
               dr_charge_kwh=r["service_charge_kwh"], served=r["served"] / r["demand"],
               wall_s=time.time() - t_wall)
    print(f"day {day} start {start} {name:32s} flex {out['flex_kwh']:9.1f}  "
          f"DR charge {out['dr_charge_kwh']:9.1f}  served {100 * out['served']:.2f}%", flush=True)
    return out


LOG_LINE = re.compile(r"day (\d+) start (\d+) (.+?)\s+flex\s+([-\d.]+)\s+DR charge\s+([-\d.]+)\s+served ([\d.]+)%")


def finished(city_name):
    """Tasks already done: from the partial results file, then from log lines."""
    done = {}
    part = pathlib.Path(f"results/improvement_{city_name}_partial.json")
    if part.exists():
        for r in json.loads(part.read_text()):
            done[(r["day"], r["start"], r["policy"])] = r
    log = pathlib.Path(f"results/improvement_{city_name}_log.txt")
    if log.exists():
        for m in LOG_LINE.finditer(log.read_text()):
            day, start, name = int(m[1]), int(m[2]), m[3].strip()
            done.setdefault((day, start, name), dict(day=day, start=start, policy=name, flex_kwh=float(m[4]),
                                                     dr_charge_kwh=float(m[5]), served=float(m[6]) / 100,
                                                     wall_s=None, from_log=True))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=["toy", "manhattan"], default="toy")
    ap.add_argument("--days", type=int, nargs="+", default=[0])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    if args.city == "manhattan" and REGIME is None:
        print(f"no {REGIME_FILE} yet: choose the fleet size first (see NOTES.md); not running")
        return
    city, _, t0, starts, center = setup("toy") if args.city == "toy" else (None, None, None,
                                                                            None, None)
    if args.city == "manhattan":
        from eflx import manhattan as M
        starts = MANHATTAN_STARTS
        names = MANHATTAN_POLICIES
    else:
        names = list(policies(len(city.demand), t0, center))
    tasks = [(args.city, d, s, n) for d in args.days for s in starts for n in names]
    done = finished(args.city)
    rows = [done[(d, s, n)] for _, d, s, n in tasks if (d, s, n) in done]
    todo = [t for t in tasks if (t[1], t[2], t[3]) not in done]
    print(f"{len(rows)} tasks already done, {len(todo)} to run", flush=True)
    part = pathlib.Path(f"results/improvement_{args.city}_partial.json")
    if args.workers > 1:
        with mp.Pool(args.workers) as pool:
            for r in pool.imap_unordered(run_task, todo):
                rows.append(r)
                part.write_text(json.dumps(rows, indent=1))
    else:
        for t in todo:
            rows.append(run_task(t))
            part.write_text(json.dumps(rows, indent=1))
    out = pathlib.Path(f"results/improvement_{args.city}.json")
    out.write_text(json.dumps(rows, indent=1))

    # summary: DR-window charging per policy and true start (mean over days)
    print(f"\nDR-window charging (kWh), mean over days {args.days}; lower is better")
    print(f"{'policy':34s}" + "".join(f"{'start ' + str(s):>12s}" for s in starts) + f"{'mean':>10s}")
    for n in names:
        v = [np.mean([r["dr_charge_kwh"] for r in rows if r["policy"] == n and r["start"] == s]) for s in starts]
        print(f"{n:34s}" + "".join(f"{x:12.1f}" for x in v) + f"{np.mean(v):10.1f}")
    print("saved", out)


if __name__ == "__main__":
    main()
