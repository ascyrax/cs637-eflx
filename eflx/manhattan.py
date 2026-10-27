"""Manhattan instance built from NYC TLC data (scripts/get_nyc_data.py).

Paper settings we keep (Sec. 7.1): 20-minute slots, L-hat = 15, L1 = 1, L2 = 3,
~13,000 taxis, DR service stage 17:20-19:20, control horizon T_c = 200 min.
"""
import pathlib

import numpy as np

from .model import City, State

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "manhattan_od.npz"
SLOT = lambda hh, mm: (hh * 60 + mm) // 20

# timeline (absolute slots of the day)
WARMUP_START = SLOT(12, 0)       # fleet runs TRC from here to reach a realistic state
PROVISION_START = SLOT(15, 20)
TAU, TB, N_REC, H = 6, 6, 3, 10  # 2 h provision, 2 h DR service, 1 h recovery, T_c = 10 slots


def load():
    return dict(np.load(DATA))


def make_city(day=None, fleet=13000, ports_total=4000, kwh_per_level=3.0, reach_miles=4.0,
              q_done=0.8, data=None):
    """day: index into the 21 weekdays (None = average weekday).

    ASSUMPTIONS (none of these are given in the paper):
      ports_total    total charging ports, split across regions by drop-off share
      kwh_per_level  3 kWh -> 42 kWh battery, 27 kW charging (keeps fleet charging in the
                     same tens-of-MW range as the paper's Fig. 2)
      reach_miles    a dispatch must be under this distance to finish within one slot
      p_pick         chance an available taxi gets a trip = demand / available taxis
      q_done         chance a trip already longer than one slot ends in the next slot
    """
    d = data or load()
    demand = d["demand_days"].mean(0) if day is None else d["demand_days"][day]
    od, short, mu, intra = d["od"], d["frac_short"], d["mu"], d["intra"]
    # wrap 12 slots of the next morning so late DR windows + horizon fit in the arrays
    wrap = lambda a: np.concatenate([a, a[:12]])
    demand, od, short = wrap(demand), wrap(od), wrap(short)
    T, n = demand.shape

    avail = 0.7 * fleet                                      # ~30% charging or occupied
    p = np.clip(demand.sum(1) / avail, 0.02, 0.95)           # (T,)
    eye = np.eye(n)
    Pv = p[:, None, None] * short[:, :, None] * od + (1 - p)[:, None, None] * eye
    Po = p[:, None, None] * (1 - short)[:, :, None] * od
    Qv = q_done * od
    Qo = (1 - q_done) * od

    phi = mu + np.diag(intra / 2)          # one charging hub per region
    ports = np.maximum(np.round(ports_total * d["drop_share"]), 1)
    reach = mu <= reach_miles
    return City(n=n, m=n, L=15, L1=1, L2=3, ports=ports, demand=demand,
                Pv=Pv, Po=Po, Qv=Qv, Qo=Qo, mu=mu, phi=phi, vss=mu,
                reach_rr=reach, reach_rs=reach, reach_ss=reach, kwh_per_level=kwh_per_level)


def warm_state(day, fleet):
    """Fleet state at 15:20 after running TRC from 12:00; cached so every
    experiment on the same day and fleet size starts from the same state."""
    import pickle
    from . import policies as P
    from .model import step
    cache = DATA.parent.parent / "results" / f"warm_{fleet}_{day}.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    city = make_city(day, fleet=fleet, ports_total=0.3 * fleet)
    state = initial_state(city, fleet=fleet)
    for t in range(WARMUP_START, PROVISION_START):
        state, _ = step(city, state, P.reference(city, state, t, H).decisions(0), t)
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(pickle.dumps(state))
    return state


def initial_state(city, fleet=13000, seed=0):
    """Spread the fleet over regions by demand and over levels 3..14 (before warm-up)."""
    rng = np.random.default_rng(seed)
    share = city.demand[WARMUP_START] / city.demand[WARMUP_START].sum()
    lv = rng.dirichlet(np.ones(city.L - 3))
    V = np.zeros((city.L, city.n))
    V[3:] = fleet * lv[:, None] * share[None, :]
    return State(V=V, O=np.zeros_like(V), D=np.zeros((city.L, city.m)))
