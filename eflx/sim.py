"""Algorithm 2: MPC loop over the provision / service / recovery stages."""
import numpy as np

from . import policies as P
from .model import step


def _service_decision(city, state, t, H, window, service_eps=0.0, upward=False):
    ref = P.reference(city, state, t, H)
    served, idle = P._ref_metrics(ref)
    return P.response(city, state, t, H, window, served, idle,
                      service_eps=service_eps, upward=upward).decisions(0)


def run(city, init, policy, t_start, tau, Tb, n_recovery, H, charge_limit=True, respond=True,
        true_demand=None, service_eps=0.0, upward=False, **kw):
    """Simulate one DR program.

    policy   : 'trc' | 'eflx' | 'oracle' | 'r2i' | 'tes'  (used in the provision stage)
    respond  : if False the fleet keeps running the reference policy through the
               service stage (the non-responding baseline used to measure flexibility)
    true_demand : (T, n) demand the fleet actually meets; if given, `city.demand` is only
               the planner's forecast (robustness test, paper Sec. 7.2.4)
    service_eps, upward : service-stage variants (see policies.response)
    Returns (per-slot log, state at the start of the service stage).
    """
    window = (t_start + tau, t_start + tau + Tb)
    state, log, state_ws = init, [], None
    for t in range(t_start, window[1] + n_recovery):
        if t < window[0]:
            stage = "provision"
            if policy == "trc":
                dec = P.reference(city, state, t, H).decisions(0)
            elif policy == "eflx":
                dec = P.eflx(city, state, t, H, Tb, charge_limit)
            elif policy == "oracle":
                dec = P.oracle(city, state, t, H, window, charge_limit)
            elif policy == "r2i":
                dec = P.r2i(city, state, t, H, charge_limit)
            elif policy == "tes":
                dec = P.tes(city, state, t, H)
            elif policy == "p_eflx":
                dec = P.p_eflx(city, state, t, H, Tb, kw["prior"], charge_limit, kw.get("rho"))
            else:
                raise ValueError(policy)
        elif t < window[1]:
            stage = "service"
            if state_ws is None:
                state_ws = state
            dec = (_service_decision(city, state, t, H, window, service_eps, upward) if respond
                   else P.reference(city, state, t, H).decisions(0))
        else:
            stage = "recovery"
            dec = P.reference(city, state, t, H).decisions(0)
        n_before = state.total()
        state, m = step(city, state, dec, t, None if true_demand is None else true_demand[t])
        assert abs(state.total() - n_before) < 1e-4, "taxis were created or lost"
        log.append(dict(t=t, stage=stage, **m, energy=state.energy_levels()))
    return log, state_ws


def stage_sum(log, stage, key):
    return sum(r[key] for r in log if r["stage"] == stage)


def flexibility(city, init, policy, t_start, tau, Tb, n_recovery, H, charge_limit=True,
                true_demand=None, **kw):
    """Eq. (6): charging gap between the non-responding baseline and the response,
    both started from the fleet state the policy reached at the DR start.
    For the Oracle the baseline is TRC from the same initial state (Sec. 7.1)."""
    log, s_ws = run(city, init, policy, t_start, tau, Tb, n_recovery, H, charge_limit,
                    true_demand=true_demand, **kw)
    ws = t_start + tau
    if policy == "oracle":
        base_log, _ = run(city, init, "trc", t_start, tau, Tb, 0, H, respond=False, true_demand=true_demand)
        base = stage_sum(base_log, "service", "charging")
    else:
        base_log, _ = run(city, s_ws, "trc", ws, 0, Tb, 0, H, respond=False, true_demand=true_demand)
        base = stage_sum(base_log, "service", "charging")
    resp = stage_sum(log, "service", "charging")
    return dict(policy=policy, log=log,
                flex_kwh=city.kwh(base - resp),
                service_charge_kwh=city.kwh(resp),
                provision_charge_kwh=city.kwh(stage_sum(log, "provision", "charging")),
                provision_idle=stage_sum(log, "provision", "idle"),
                provision_wait=stage_sum(log, "provision", "waiting"),
                served=sum(r["served"] for r in log), demand=sum(r["demand"] for r in log))
