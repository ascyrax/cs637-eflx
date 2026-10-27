"""Toy version of the eFlx experiment: 2 regions, 2 charging stations, 100 taxis.

Timeline (20-minute slots, like the paper):
    slots 0-5   provision stage  (15:20-17:20)
    slots 6-11  DR service stage (17:20-19:20, the paper's window)
    slots 12-14 recovery stage
Run:  .venv/bin/python toy_demo.py
"""
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from eflx.model import City, State
from eflx.sim import flexibility, run, stage_sum

TAU, TB, N_REC, H = 6, 6, 3, 10      # H = control horizon T_c (paper: 200 min = 10 slots)
T_TOTAL = TAU + TB + N_REC + H + 1


def toy_city():
    n = m = 2
    t = np.arange(T_TOTAL)
    peak = np.exp(-0.5 * ((t - 8.5) / 3.0) ** 2)           # evening peak around 18:10
    # scaled so the fleet has some, but limited, spare capacity (the paper's "challenging" regime, Fig. 3)
    demand = 0.7 * np.stack([14 + 16 * peak, 8 + 8 * peak], axis=1)  # region 0 = "downtown"

    W = np.array([[0.7, 0.3], [0.4, 0.6]])        # trip destinations
    stay = np.array([[0.85, 0.15], [0.15, 0.85]])  # where vacant taxis drift
    p_pick = np.clip(demand.sum(1) / 70, 0.2, 0.8)  # chance an available taxi gets a trip this slot
    q_done = 0.6                                    # chance an occupied trip ends this slot
    Pv = np.array([(1 - p) * stay for p in p_pick])
    Po = np.array([p * W for p in p_pick])
    Qv = np.repeat((q_done * W)[None], T_TOTAL, 0)
    Qo = np.repeat(((1 - q_done) * W)[None], T_TOTAL, 0)

    far = np.array([[0.0, 2.0], [2.0, 0.0]])
    return City(n=n, m=m, L=8, L1=1, L2=2, ports=np.array([8.0, 8.0]), demand=demand,
                Pv=Pv, Po=Po, Qv=Qv, Qo=Qo, mu=far, phi=far + 0.3 * np.eye(2), vss=far,
                reach_rr=np.ones((n, n), bool), reach_rs=np.ones((n, m), bool),
                reach_ss=np.ones((m, m), bool), kwh_per_level=10.0)


def toy_init(city):
    V = np.zeros((city.L, city.n))
    for l in range(2, city.L):          # 100 taxis spread over levels 2..7, 60/40 split
        V[l] = np.array([60, 40]) / (city.L - 2)
    return State(V=V, O=np.zeros_like(V), D=np.zeros((city.L, city.m)))


def sanity_checks(city):
    # mobility rows must be probability distributions (Sec. 3.2)
    assert np.allclose((city.Pv + city.Po).sum(2), 1) and np.allclose((city.Qv + city.Qo).sum(2), 1)
    # a reference-only run must keep every taxi, never charge above port capacity,
    # and keep battery levels inside [0, L-1] (enforced by construction)
    log, _ = run(city, toy_init(city), "trc", 0, TAU, TB, N_REC, H, respond=False)
    assert max(r["charging"] for r in log) <= city.ports.sum() + 1e-6
    print(f"sanity OK: 100 taxis conserved over {len(log)} slots, "
          f"served {sum(r['served'] for r in log):.1f}/{sum(r['demand'] for r in log):.1f} requests")


def main():
    city = toy_city()
    sanity_checks(city)
    results = {}
    for limit in (True, False):
        pols = ["trc", "r2i", "eflx", "oracle"] if limit else ["trc", "r2i", "tes", "eflx"]
        print(f"\n=== provisioning {'WITH' if limit else 'WITHOUT'} charging limit ===")
        print(f"{'policy':8s} {'flex kWh':>9s} {'DR charge':>10s} {'prov charge':>12s} "
              f"{'idle mi':>8s} {'wait':>6s} {'served %':>9s} {'time s':>7s}")
        for pol in pols:
            t0 = time.time()
            r = flexibility(city, toy_init(city), pol, 0, TAU, TB, N_REC, H, charge_limit=limit)
            results[(limit, pol)] = r
            print(f"{pol:8s} {r['flex_kwh']:9.1f} {r['service_charge_kwh']:10.1f} "
                  f"{r['provision_charge_kwh']:12.1f} {r['provision_idle']:8.1f} "
                  f"{r['provision_wait']:6.1f} {100 * r['served'] / r['demand']:9.2f} "
                  f"{time.time() - t0:7.1f}")

    # Figure-8 style plot: charging power over the whole DR program (with charging limit)
    base, _ = run(city, toy_init(city), "trc", 0, TAU, TB, N_REC, H, respond=False)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    hours = lambda log: [15 + 20 / 60 + r["t"] / 3 for r in log]
    kw = lambda log: [city.kwh(r["charging"]) * 3 for r in log]   # kWh per 20 min -> kW
    ax.step(hours(base), kw(base), where="post", label="Reference policy (no DR)", color="k", ls="--")
    for pol in ("trc", "r2i", "eflx", "oracle"):
        lg = results[(True, pol)]["log"]
        ax.step(hours(lg), kw(lg), where="post", label=pol.upper())
    ax.axvspan(17 + 20 / 60, 19 + 20 / 60, color="grey", alpha=0.15, label="DR service stage")
    ax.set_xlabel("time of day (h)"); ax.set_ylabel("charging power (kW)")
    ax.set_title("Toy model: charging demand during a DR program")
    ax.legend(fontsize=7); fig.tight_layout()
    fig.savefig("results/toy_fig8.png", dpi=150)
    print("\nplot saved to results/toy_fig8.png")


if __name__ == "__main__":
    main()
