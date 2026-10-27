"""E-taxi fleet model from eFlx (Zhou et al., ICCPS'25), Sections 3 and 4.

Everything here is the aggregated ("fluid") model: taxis are counted per
(battery level, region / station) and the counts are relaxed to real numbers,
exactly as the paper does at the end of Sec. 3.1.2.

Index conventions (0-based, unlike the paper):
    l  battery level, 0 .. L-1   (0 = empty)
    i  region,        0 .. n-1
    j  charging station, 0 .. m-1
    k  slot offset inside an optimisation horizon (absolute slot t = t0 + k)

Assumptions we had to make because the paper does not specify them are
marked with "ASSUMPTION" and collected in NOTES.md.
"""
from dataclasses import dataclass

import cvxpy as cp
import numpy as np


@dataclass
class City:
    n: int                    # regions
    m: int                    # charging stations
    L: int                    # number of battery levels (paper: L-hat = 15)
    L1: int                   # levels used per working slot (paper: 1)
    L2: int                   # levels gained per charging slot (paper: 3)
    ports: np.ndarray         # (m,) charging ports e_j
    demand: np.ndarray        # (T, n) passenger requests r_i^t
    Pv: np.ndarray            # (T, n, n) unoccupied -> vacant in dest region
    Po: np.ndarray            # (T, n, n) unoccupied -> occupied in dest region
    Qv: np.ndarray            # (T, n, n) occupied   -> vacant (trip completed)
    Qo: np.ndarray            # (T, n, n) occupied   -> still occupied
    mu: np.ndarray            # (n, n) region-region distance (miles)
    phi: np.ndarray           # (n, m) region-station distance
    vss: np.ndarray           # (m, m) station-station distance
    reach_rr: np.ndarray      # (n, n) bool, reachable within one slot (Eq. 5f)
    reach_rs: np.ndarray      # (n, m) bool (Eq. 5e)
    reach_ss: np.ndarray      # (m, m) bool
    kwh_per_level: float      # ASSUMPTION: energy of one battery level

    @property
    def max_charge_level(self):
        # ASSUMPTION: a taxi only charges if a full slot of charge fits
        # (the paper does not say what happens at the top level).
        return self.L - 1 - self.L2

    def kwh(self, taxi_slots_charging):
        """Convert 'number of taxis charging for one slot' to kWh."""
        return taxi_slots_charging * self.L2 * self.kwh_per_level


@dataclass
class State:
    V: np.ndarray  # (L, n) vacant
    O: np.ndarray  # (L, n) occupied
    D: np.ndarray  # (L, m) at charging stations (charging or waiting)

    def total(self):
        return self.V.sum() + self.O.sum() + self.D.sum()

    def energy_levels(self):
        lv = np.arange(self.V.shape[0])
        return float((lv[:, None] * (self.V + self.O)).sum() + (lv[:, None] * self.D).sum())


def _drop(l, L1):
    """Battery level after one working slot (clamped at empty)."""
    return max(l - L1, 0)


class Plan:
    """Decision variables + fleet dynamics (Eq. 1-4, 5e-5g) over H slots.

    Policies (reference / response / eFlx) add an objective and a few extra
    constraints on top of the expressions exposed here.
    """

    def __init__(self, city: City, state: State, t0: int, H: int):
        c = city
        self.city, self.t0, self.H = c, t0, H
        L, n, m = c.L, c.n, c.m
        self.cons = []

        # --- decision variables, Sec. 3.1.2 ---
        self.x = [[cp.Variable((n, m), nonneg=True) for _ in range(L)] for _ in range(H)]   # region  -> station
        self.y = [[cp.Variable((n, n), nonneg=True) for _ in range(L)] for _ in range(H)]   # region  -> region
        self.xd = [[cp.Variable((m, m), nonneg=True) for _ in range(L)] for _ in range(H)]  # station -> station
        self.yd = [[cp.Variable((m, n), nonneg=True) for _ in range(L)] for _ in range(H)]  # station -> region
        self.u = [[cp.Variable(m, nonneg=True) for _ in range(L)] for _ in range(H)]        # charging (Sec. 3.3)

        # --- state variables; slot 0 is the measured state ---
        self.V = [state.V] + [cp.Variable((L, n), nonneg=True) for _ in range(H)]
        self.O = [state.O] + [cp.Variable((L, n), nonneg=True) for _ in range(H)]
        self.D = [state.D] + [cp.Variable((L, m), nonneg=True) for _ in range(H)]

        self.S, self.served, self.charge, self.idle, self.at_station = [], [], [], [], []
        for k in range(H):
            t = t0 + k
            x, y, xd, yd, u = self.x[k], self.y[k], self.xd[k], self.yd[k], self.u[k]
            S_k, arrivals = [], []
            for l in range(L):
                # Eq. (1): every available taxi gets exactly one dispatch decision
                self.cons += [cp.sum(x[l], axis=1) + cp.sum(y[l], axis=1) == self.V[k][l],
                              cp.sum(xd[l], axis=1) + cp.sum(yd[l], axis=1) == self.D[k][l]]
                # Eq. (5e), (5f): destination must be reachable within one slot
                for var, mask in ((x[l], c.reach_rs), (y[l], c.reach_rr),
                                  (xd[l], c.reach_ss), (yd[l], c.reach_rs.T)):
                    if not mask.all():
                        self.cons.append(cp.multiply(~mask, var) == 0)
                # Eq. (2a): taxis available to serve passengers in each region
                S_l = cp.sum(y[l], axis=0) + cp.sum(yd[l], axis=0)
                S_k.append(S_l)
                # Eq. (3): only taxis at the station can charge
                A_l = cp.sum(x[l], axis=0) + cp.sum(xd[l], axis=0)
                arrivals.append(A_l)
                self.cons.append(u[l] <= A_l)
                if l > c.max_charge_level:
                    self.cons.append(u[l] == 0)
                # Eq. (5g): low-battery taxis must not serve passengers
                if l <= c.L1:
                    self.cons.append(S_l == 0)
            # Eq. (3): charging-port capacity
            self.cons.append(sum(u) <= c.ports)

            # Eq. (2b), (2c): mobility transitions (energy drops by L1)
            Vn = [0] * L
            On = [0] * L
            for l in range(L):
                d = _drop(l, c.L1)
                Vn[d] = Vn[d] + c.Pv[t].T @ S_k[l] + c.Qv[t].T @ self.O[k][l]
                On[d] = On[d] + c.Po[t].T @ S_k[l] + c.Qo[t].T @ self.O[k][l]
            # Eq. (4): station dynamics (charged taxis gain L2 levels; others wait)
            Dn = []
            for l in range(L):
                gained = u[l - c.L2] if l - c.L2 >= 0 else 0
                Dn.append(gained + arrivals[l] - u[l])
            for l in range(L):
                self.cons += [self.V[k + 1][l] == Vn[l],
                              self.O[k + 1][l] == On[l],
                              self.D[k + 1][l] == Dn[l]]

            # J_trans = sum_i min(r_i, sum_l S_i^l), linearised with an auxiliary variable
            J = cp.Variable(n, nonneg=True)
            self.cons += [J <= c.demand[t], J <= sum(S_k)]
            self.served.append(cp.sum(J))
            # J_idle: idle driving caused by dispatch decisions
            self.idle.append(sum(cp.sum(cp.multiply(c.phi, x[l])) + cp.sum(cp.multiply(c.phi.T, yd[l]))
                                 + cp.sum(cp.multiply(c.mu, y[l])) + cp.sum(cp.multiply(c.vss, xd[l]))
                                 for l in range(L)))
            self.charge.append(sum(cp.sum(u[l]) for l in range(L)))
            self.at_station.append(sum(cp.sum(a) for a in arrivals))
            self.S.append(S_k)
        # total battery energy (in levels) of the fleet at each future slot
        lv = np.arange(L)
        self.energy = [lv @ (self.V[k + 1] + self.O[k + 1]) @ np.ones(n) + lv @ self.D[k + 1] @ np.ones(m)
                       for k in range(H)]

    def fix_first_slots(self, decisions_list):
        """Pin the first len(decisions_list) slots to given decisions (Alg. 1, line 4)."""
        for k, dec in enumerate(decisions_list):
            for l in range(self.city.L):
                self.cons += [self.x[k][l] == dec["x"][l], self.y[k][l] == dec["y"][l],
                              self.xd[k][l] == dec["xd"][l], self.yd[k][l] == dec["yd"][l],
                              self.u[k][l] == dec["u"][l]]

    def solve(self, objective):
        prob = cp.Problem(objective, self.cons)
        prob.solve(solver=cp.HIGHS, threads=1)   # same as fastplan: HiGHS refuses a thread count that differs from its first solve
        if prob.status not in ("optimal", "optimal_inaccurate"):
            raise RuntimeError(f"LP status {prob.status} at t0={self.t0}")
        return prob.value

    def decisions(self, k=0):
        g = lambda v: np.clip(v.value, 0, None)
        L = self.city.L
        return {name: [g(getattr(self, name)[k][l]) for l in range(L)]
                for name in ("x", "y", "xd", "yd", "u")}

    def values(self, exprs):
        return np.array([float(e.value) for e in exprs])


def step(city: City, state: State, dec, t: int, true_demand=None):
    """Apply one slot of decisions to the fleet (numpy version of Eq. 1-4).

    Returns the next state and per-slot metrics. This is our 'simulator'.
    NOTE: it uses the same fluid model as the optimiser, as the paper appears
    to do -- one of the critique points (no model mismatch is tested).
    """
    c = city
    L = c.L
    demand = c.demand[t] if true_demand is None else true_demand
    S = [dec["y"][l].sum(0) + dec["yd"][l].sum(0) for l in range(L)]
    A = [dec["x"][l].sum(0) + dec["xd"][l].sum(0) for l in range(L)]
    u = [np.minimum(dec["u"][l], A[l]) for l in range(L)]
    V = np.zeros((L, c.n)); O = np.zeros((L, c.n)); D = np.zeros((L, c.m))
    for l in range(L):
        d = _drop(l, c.L1)
        V[d] += c.Pv[t].T @ S[l] + c.Qv[t].T @ state.O[l]
        O[d] += c.Po[t].T @ S[l] + c.Qo[t].T @ state.O[l]
        D[l] += A[l] - u[l]
        D[min(l + c.L2, L - 1)] += u[l]
    served = np.minimum(demand, sum(S)).sum()
    idle = sum((c.phi * dec["x"][l]).sum() + (c.phi.T * dec["yd"][l]).sum()
               + (c.mu * dec["y"][l]).sum() + (c.vss * dec["xd"][l]).sum() for l in range(L))
    charging = sum(x.sum() for x in u)
    waiting = sum((A[l] - u[l]).sum() for l in range(L))
    return State(V, O, D), dict(served=served, demand=demand.sum(), idle=idle,
                                charging=charging, waiting=waiting)
