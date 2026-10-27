"""Figures 6-10 of the paper, recreated from results/manhattan.json, plus a
claim-by-claim comparison table (results/claims.md).

Run:  .venv/bin/python make_figures.py                       (13,000-taxi run)
      .venv/bin/python make_figures.py manhattan_3200 3200   (3,200-taxi run)
"""
import sys
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

R = pathlib.Path("results")
NAME = sys.argv[1] if len(sys.argv) > 1 else "manhattan"
FLEET = int(sys.argv[2]) if len(sys.argv) > 2 else 13000
NAMES = {"trc": "TRC", "r2i": "R2I", "tes": "TES", "eflx": "eFlx", "oracle": "Oracle"}
COLORS = {"trc": "#4c72b0", "r2i": "#dd8452", "tes": "#8172b3", "eflx": "#55a868", "oracle": "#c44e52"}


def load():
    rows = json.loads((R / f"{NAME}.json").read_text())
    days = sorted({r["day"] for r in rows})
    get = lambda lim, pol, key: np.array([next(r[key] for r in rows if r["day"] == d and r["limit"] == lim
                                                and r["policy"] == pol) for d in days])
    return rows, days, get


def bars(ax, pols, vals, ylabel, title):
    for k, p in enumerate(pols):
        v = vals[p]
        ax.bar(k, v.mean(), yerr=v.std(ddof=1) if len(v) > 1 else 0, color=COLORS[p], capsize=4)
        ax.scatter(np.full(len(v), k) + np.linspace(-0.15, 0.15, len(v)), v, s=8, color="k", zorder=3)
    ax.set_xticks(range(len(pols)), [NAMES[p] for p in pols])
    ax.set_ylabel(ylabel); ax.set_title(title, fontsize=10)


def pct(a, b):
    """relative difference of the totals over all days, in percent
    (a mean of daily ratios blows up on easy days with near-zero DR charging)"""
    if abs(np.sum(a)) < 1e-6 and abs(np.sum(b)) < 1e-6:
        return None          # both zero: no difference to report
    return 100 * (np.sum(a) - np.sum(b)) / np.sum(b)


def plot_improvement(city):
    """Our P-eFlx vs eFlx / Oracle when the true DR start varies (improvement.py)."""
    f = R / f"improvement_{city}.json"
    if not f.exists():
        return
    rows = json.loads(f.read_text())
    starts = sorted({r["start"] for r in rows})
    names = list(dict.fromkeys(r["policy"] for r in rows))
    cols = ["#4c72b0", "#55a868", "#e17c05", "#f2b134", "#b07aa1", "#c44e52"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    w = 0.8 / len(names)
    for k, n in enumerate(names):
        v = [np.mean([r["dr_charge_kwh"] for r in rows if r["policy"] == n and r["start"] == s]) for s in starts]
        ax.bar(np.arange(len(starts)) + (k - len(names) / 2 + 0.5) * w, np.array(v) / (1e3 if city != "toy" else 1),
               w, label=n, color=cols[k % len(cols)])
    label = (lambda s: f"{s // 3}:{20 * (s % 3):02d}") if city != "toy" else (lambda s: f"slot {s}")
    ax.set_xticks(range(len(starts)), [f"DR starts {label(s)}" for s in starts])
    ax.set_ylabel(f"Charging during DR ({'MWh' if city != 'toy' else 'kWh'})")
    ax.set_title(f"P-eFlx (ours) vs eFlx: true DR start varied ({city}); prior centred on "
                 f"{'17:20' if city != 'toy' else 'slot 6'}", fontsize=10)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12), frameon=False)
    fig.tight_layout(); fig.savefig(R / f"improvement_{city}.png", dpi=150, bbox_inches="tight"); plt.close(fig)


def main():
    for city in ("toy", "manhattan"):
        plot_improvement(city)
    if not (R / f"{NAME}.json").exists():
        return
    rows, days, get = load()
    lim_p = ["trc", "r2i", "eflx", "oracle"]
    nol_p = ["trc", "r2i", "tes", "eflx"]
    val = lambda lim, pols, key, scale=1e-3: {p: get(lim if p != "trc" else True, p, key) * scale for p in pols}

    for fig_no, key, ylabel in ((6, "flex_kwh", "Flexibility (MWh)"),
                                (7, "service_charge_kwh", "Charging during DR (MWh)"),
                                (9, "provision_charge_kwh", "Charging during provision (MWh)")):
        fig, axs = plt.subplots(1, 2, figsize=(8, 3.2))
        bars(axs[0], lim_p, val(True, lim_p, key), ylabel, "(a) with charging limit")
        bars(axs[1], nol_p, val(False, nol_p, key), ylabel, "(b) without charging limit")
        fig.suptitle(f"Fig. {fig_no} (ours, {FLEET:,} taxis, {len(days)} weekdays, mean ± sd)", fontsize=10)
        fig.tight_layout(); fig.savefig(R / f"{NAME}_fig{fig_no}.png", dpi=150); plt.close(fig)

    # Fig. 10: overhead during provisioning (with charging limit)
    pols10 = ["tes", "trc", "r2i", "eflx", "oracle"]
    idle = {p: get(p != "tes", p, "provision_idle") / FLEET for p in pols10}
    wait = {p: get(p != "tes", p, "provision_wait") * 20 / FLEET for p in pols10}
    fig, axs = plt.subplots(1, 2, figsize=(8, 3.2))
    bars(axs[0], pols10, idle, "Idle driving per taxi (mile)", "(a) idle driving distance")
    bars(axs[1], pols10, wait, "Idle waiting per taxi (min)", "(b) idle waiting time")
    fig.tight_layout(); fig.savefig(R / f"{NAME}_fig10.png", dpi=150); plt.close(fig)

    # Fig. 8: one day, charging power over the DR program
    d0 = days[0]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    for p in lim_p:
        r = next(r for r in rows if r["day"] == d0 and r["limit"] and r["policy"] == p)
        hrs = [s / 3 for s in r["slots"]]
        ax.step(hrs, np.array(r["charging_kw"]) / 1e3, where="post", label=NAMES[p], color=COLORS[p])
    ax.axvspan(17 + 1 / 3, 19 + 1 / 3, color="grey", alpha=0.15, label="DR service stage")
    ax.set_xlabel("time of day (h)"); ax.set_ylabel("charging demand (MW)")
    ax.set_title(f"Fig. 8 (ours): charging during a DR program, weekday #{d0}", fontsize=10)
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(R / f"{NAME}_fig8.png", dpi=150); plt.close(fig)

    # claim-by-claim table
    F = lambda lim, p: get(lim if p != "trc" else True, p, "flex_kwh")
    C = lambda lim, p: get(lim if p != "trc" else True, p, "service_charge_kwh")
    claims = [
        ("Flex gain eFlx vs TRC (limit)", "+5.52%", pct(F(True, "eflx"), F(True, "trc"))),
        ("Flex gain eFlx vs R2I (limit)", "+4.18%", pct(F(True, "eflx"), F(True, "r2i"))),
        ("Flex eFlx vs Oracle (limit)", "-0.52%", pct(F(True, "eflx"), F(True, "oracle"))),
        ("DR charging eFlx vs TRC (limit)", "-19.98%", pct(C(True, "eflx"), C(True, "trc"))),
        ("DR charging eFlx vs R2I (limit)", "-16.36%", pct(C(True, "eflx"), C(True, "r2i"))),
        ("DR charging eFlx vs Oracle (limit)", "+0.51%", pct(C(True, "eflx"), C(True, "oracle"))),
        ("Flex gain eFlx vs TRC (no limit)", "+21.67%", pct(F(False, "eflx"), F(True, "trc"))),
        ("Flex gain eFlx vs R2I (no limit)", "+13.48%", pct(F(False, "eflx"), F(False, "r2i"))),
        ("Flex gain eFlx vs TES (no limit)", "+6.35%", pct(F(False, "eflx"), F(False, "tes"))),
        ("DR charging eFlx vs TRC (no limit)", "-42.97%", pct(C(False, "eflx"), C(True, "trc"))),
        ("DR charging eFlx vs R2I (no limit)", "-24.73%", pct(C(False, "eflx"), C(False, "r2i"))),
        ("DR charging eFlx vs TES (no limit)", "-31.37%", pct(C(False, "eflx"), C(False, "tes"))),
        ("Provision charging eFlx vs TRC (no limit)", "+9.45%",
         pct(get(False, "eflx", "provision_charge_kwh"), get(True, "trc", "provision_charge_kwh"))),
        ("Idle driving eFlx vs TRC (limit)", "+2.06%",
         pct(get(True, "eflx", "provision_idle"), get(True, "trc", "provision_idle"))),
        ("Idle waiting eFlx vs TRC (limit)", "+2.12%",
         pct(get(True, "eflx", "provision_wait"), get(True, "trc", "provision_wait"))),
    ]
    served = min(r["served"] / r["demand"] for r in rows)
    eflx_rows = [r for r in rows if r["policy"] == "eflx"]
    iters = [i for r in eflx_rows for i in r["alg1_iters"]]
    lines = ["| Claim | Paper | Ours (totals over %d days) |" % len(days), "|---|---|---|"]
    lines += [f"| {c} | {p} | {'both 0 MWh' if o is None else f'{o:+.2f}%'} |" for c, p, o in claims]
    lines += ["", f"- Lowest passenger service in any run: {100 * served:.2f}%",
              f"- TRC flexibility: {F(True, 'trc').mean() / 1e3:.1f} ± {F(True, 'trc').std(ddof=1) / 1e3:.1f} MWh "
              f"(paper Fig. 2: 127.86 MWh)",
              f"- Algorithm 1 iterations per slot: mean {np.mean(iters):.1f}, max {max(iters)}",
              f"- eFlx wall time per provision slot: "
              f"{np.mean([r['wall_s'] for r in eflx_rows]) / 6:.0f} s (paper: 254.7 s)"]
    (R / f"{NAME}_claims.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
