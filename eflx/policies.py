"""Coordination policies from eFlx Sec. 4-5, plus the baselines of Sec. 7.1."""
import numpy as np

from .fastplan import FastPlan as Plan

BETA = 0.01        # ASSUMPTION: weight of idle distance in the reference objective (not given)
ETA = 0.05         # ASSUMPTION: allowed idle-distance increase in Eq. (5d) (not given)
EPS_CHARGE = 1e-3  # ASSUMPTION: tiny reward so the reference policy charges when it can
                   # (otherwise its charging is arbitrary: the paper's TRC objective has no charging term)
TOL = 1e-6
STATS = {"lp_solves": 0, "alg1_iters": []}


def _solve(p, objective, maximize=False):
    STATS["lp_solves"] += 1
    return p.solve(objective, maximize)


def reference(city, state, t, H, fixed=None):
    """Problem 3: maximise passengers served minus beta * idle distance (TRC)."""
    p = Plan(city, state, t, H)
    if fixed:
        p.fix_first_slots(fixed)
    _solve(p, sum(p.served) - BETA * sum(p.idle) + EPS_CHARGE * sum(p.charge), maximize=True)
    return p


def _ref_metrics(ref):
    return ref.values(ref.served), float(ref.values(ref.idle).sum())


def window_weights(t, H, window):
    return np.array([1.0 if window[0] <= t + k < window[1] else 0.0 for k in range(H)])


def response(city, state, t, H, window, ref_served, ref_idle, cap=None, weights=None, extra=(),
             service_eps=0.0, upward=False):
    """Problem 1 / Problem 5: minimise charging inside the DR `window` (absolute slots).

    Constraints: per-slot service no worse than the reference (5c), idle distance
    within (1+eta) of the reference (5d), and optionally charging no more than
    `cap[k]` in slot k (Eq. 5b / 8d, used during provisioning).
    `weights` (per slot of the horizon) replaces the 0/1 window indicator; used by P-eFlx.
    `extra` is a list of (slot weights, upper bound) constraints on weighted charging.
    Our extensions (new_ideas.py):
    `service_eps` lets service inside the DR window drop to (1 - eps) of the reference
                  (the paper's "controlled service compromise", never measured there);
    `upward`      maximises charging in the window instead (absorbing surplus power).
    """
    p = Plan(city, state, t, H)
    in_dr = window_weights(t, H, window) if window is not None else np.zeros(H)
    for k in range(H):
        p.add(p.served[k], lo=ref_served[k] * (1 - service_eps * in_dr[k]) - TOL)
    p.add(sum(p.idle), hi=(1 + ETA) * ref_idle + TOL)
    for k, c in (cap or {}).items():
        p.add(p.charge[k], hi=c + TOL)
    for w, hi in extra:
        p.add(sum(w[k] * p.charge[k] for k in range(H) if w[k]), hi=hi + TOL)
    w = window_weights(t, H, window) if weights is None else weights
    # small idle term only breaks ties between equally good plans
    sign = -1.0 if upward else 1.0
    _solve(p, sum(sign * w[k] * p.charge[k] for k in range(H) if w[k]) + 1e-4 * sum(p.idle))
    return p


def _weighted_charge(p, w):
    return float(sum(w[k] * p.value(p.charge[k]) for k in range(len(w)) if w[k]))


def dr_weights(t, H, Tb, prior):
    """Our improvement: probability that each horizon slot lies inside the DR window,
    given that DR has not started by slot t.

    prior[s] = probability that the DR service stage starts at absolute slot s.
    w_k = sum_s P(start = s | start > t) * 1[s <= t + k < s + Tb]
    """
    q = np.zeros(len(prior))
    q[t + 1:] = prior[t + 1:]
    if q.sum() <= 0:            # the prior says DR should already have happened: be ready now
        q[t + 1] = 1.0
    q /= q.sum()
    w = np.zeros(H)
    for s in np.nonzero(q)[0]:
        for k in range(max(s - t, 0), min(s + Tb - t, H)):
            w[k] += q[s]
    return w


def p_eflx(city, state, t, H, Tb, prior, charge_limit=True, rho=None, max_iter=5):
    """P-eFlx: Algorithm 1 with the tau = 1 window replaced by expected DR-window weights.

    rho = None : minimise expected DR charging only.
    rho >= 0   : also keep readiness for an immediate DR within (1 + rho) of what
                 eFlx would achieve (a hedge against the prior being wrong).
    """
    w = dr_weights(t, H, Tb, prior)
    w1 = window_weights(t, H, (t + 1, t + 1 + Tb))
    ref = reference(city, state, t, H)
    cap = {0: ref.value(ref.charge[0])} if charge_limit else None
    dec = None
    for it in range(max_iter + 1):
        if dec is not None:
            ref = reference(city, state, t, H, fixed=[dec])
        served, idle = _ref_metrics(ref)
        extra = ()
        if rho is not None:
            best_now = _weighted_charge(response(city, state, t, H, None, served, idle, cap, weights=w1), w1)
            extra = [(w1, (1 + rho) * best_now + 1e-3)]
        new = response(city, state, t, H, None, served, idle, cap, weights=w, extra=extra).decisions(0)
        if dec is not None and max(np.abs(new[key] - dec[key]).max() for key in dec) < 1e-3:
            dec = new
            break
        dec = new
    STATS["alg1_iters"].append(it)
    return dec


def eflx(city, state, t, H, Tb, charge_limit=True, max_iter=5):
    """Algorithm 1 with tau = 1: provision for a DR window that may start next slot."""
    window = (t + 1, t + 1 + Tb)
    ref = reference(city, state, t, H)
    # ASSUMPTION: the initial reference prediction (J-hat^0) comes from solving Problem 3
    # on the current state instead of from historical data.
    served, idle = _ref_metrics(ref)
    cap = {0: ref.value(ref.charge[0])} if charge_limit else None   # P_TRC in Eq. (8d)
    dec = response(city, state, t, H, window, served, idle, cap).decisions(0)
    it = 0
    for it in range(1, max_iter + 1):
        ref = reference(city, state, t, H, fixed=[dec])     # Alg. 1, line 4
        served, idle = _ref_metrics(ref)
        new = response(city, state, t, H, window, served, idle, cap).decisions(0)   # line 5
        delta = max(np.abs(new[key] - dec[key]).max() for key in dec)
        dec = new
        if delta < 1e-3:
            break
    STATS["alg1_iters"].append(it)
    return dec


def oracle(city, state, t, H, window, charge_limit=True):
    """Knows the real DR window; charging capped at TRC level in every provision slot."""
    # the horizon must cover the whole DR window, otherwise the "oracle" is blind to part of it
    H = max(H, window[1] - t)
    ref = reference(city, state, t, H)
    served, idle = _ref_metrics(ref)
    cap = None
    if charge_limit:
        cap = {k: ref.value(ref.charge[k]) for k in range(min(window[0] - t, H))}
    return response(city, state, t, H, window, served, idle, cap).decisions(0)


def r2i(city, state, t, H, charge_limit=True):
    """Reactive charging to idling time (our LP reading of the paper's description):
    keep service equal to TRC, but park as many idle taxis at stations as possible
    instead of letting them roam; they charge if a port is free, otherwise wait."""
    ref = reference(city, state, t, H)
    served, _ = _ref_metrics(ref)
    p = Plan(city, state, t, H)
    for k in range(H):
        p.add(p.served[k], lo=served[k] - TOL)
    if charge_limit:
        p.add(p.charge[0], hi=ref.value(ref.charge[0]) + TOL)
    _solve(p, p.at_station[0] + EPS_CHARGE * p.charge[0] - 1e-4 * sum(p.idle), maximize=True)
    return p.decisions(0)


def tes(city, state, t, H):
    """Taxi service with energy storage: maximise stored energy next slot, keep service."""
    ref = reference(city, state, t, H)
    served, _ = _ref_metrics(ref)
    p = Plan(city, state, t, H)
    for k in range(H):
        p.add(p.served[k], lo=served[k] - TOL)
    _solve(p, p.energy[0] - 1e-4 * sum(p.idle), maximize=True)
    return p.decisions(0)
