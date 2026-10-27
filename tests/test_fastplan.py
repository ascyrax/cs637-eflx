"""The fast sparse LP must give the same optimum as the readable cvxpy spec (model.Plan).

Run:  .venv/bin/python tests/test_fastplan.py
"""
import pathlib
import sys

import cvxpy as cp
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import toy_demo as T  # noqa: E402
from eflx.fastplan import FastPlan  # noqa: E402
from eflx.model import Plan, State  # noqa: E402

BETA, EPS = 0.01, 1e-3


def random_state(city, rng):
    V = rng.uniform(0, 4, (city.L, city.n)); O = rng.uniform(0, 2, (city.L, city.n))
    D = rng.uniform(0, 2, (city.L, city.m))
    return State(V, O, D)


def check(city, state, t, H):
    # reference objective
    a = Plan(city, state, t, H)
    va = a.solve(cp.Maximize(sum(a.served) - BETA * sum(a.idle) + EPS * sum(a.charge)))
    b = FastPlan(city, state, t, H)
    vb = b.solve(sum(b.served) - BETA * sum(b.idle) + EPS * sum(b.charge), maximize=True)
    assert np.isclose(va, vb, rtol=1e-6, atol=1e-6), (va, vb)
    # response-style objective with service constraints taken from the reference
    served = b.values(b.served)
    a2 = Plan(city, state, t, H)
    a2.cons += [a2.served[k] >= served[k] - 1e-6 for k in range(H)]
    wa = a2.solve(cp.Minimize(sum(a2.charge[2:6])))
    b2 = FastPlan(city, state, t, H)
    for k in range(H):
        b2.add(b2.served[k], lo=served[k] - 1e-6)
    wb = b2.solve(sum(b2.charge[2:6]))
    assert np.isclose(wa, wb, rtol=1e-5, atol=1e-5), (wa, wb)
    return va, wa


if __name__ == "__main__":
    city = T.toy_city()
    rng = np.random.default_rng(0)
    states = [T.toy_init(city)] + [random_state(city, rng) for _ in range(3)]
    for k, s in enumerate(states):
        va, wa = check(city, s, t=2 * k, H=T.H)
        print(f"case {k}: reference obj {va:9.4f}, response obj {wa:8.4f}  -> identical")
    print("FastPlan matches the cvxpy spec")
