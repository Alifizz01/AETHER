"""Regenerate the figures embedded in README.md.

    python aether/analysis/readme_figures.py

Every number in these plots comes from running the model. The only synthetic
data is the "measured" series in the validation figure, which is labelled as
such on the plot itself: there is no bench yet.
"""

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aether.model.cell import Cell_simple
from aether.model.pack import Pack
from aether.model.inverter import Inverter
from aether.model.motor import Motor
from aether.model.propeller import Propeller
from aether.model.powertrain import Powertrain

OUT = Path(__file__).resolve().parents[2] / "docs" / "img"
BLUE, RED, GREEN, AMBER, GREY = "#1f6feb", "#d1242f", "#1a7f37", "#bf8700", "#57606a"


def build_powertrain(soc=1.0, c_q=0.0075):
    cell = Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=0.020,
                       u_full=4.2, u_empty=3.3, i_max=30.0, soc=soc)
    pack = Pack(cell, n_series=6, n_parallel=2, r_wiring=0.005)
    inv = Inverter(name="ESC", i_max=60.0, u_max=30.0, r_ds_on=0.005,
                   n_conducting=2, f_sw=16_000.0, e_sw=5e-5,
                   u_sw_ref=25.0, i_sw_ref=40.0)
    mot = Motor(name="drone motor", k_e=0.0106, R_phase=0.060, i_no_load=0.8,
                pole_pairs=7, i_max=60.0, v_max=30.0)
    prop = Propeller(name="10x4.5", diameter_in=10.0, pitch_in=4.5,
                     c_t=0.10, c_q=c_q)
    return Powertrain(pack, inv, mot, propeller=prop)


# ------------------------------------------------------------------ figure 1
def operating_point_figure():
    """Where the shaft settles: the motor line crossing the propeller load line."""
    pt = build_powertrain()
    fig, ax = plt.subplots(figsize=(8.5, 5.4))

    rpm = [r for r in range(0, 17000, 100)]
    prop_t = [pt.propeller.torque(r) for r in rpm]
    ax.plot(rpm, prop_t, lw=2.6, color=RED, label="propeller load line  ~ rpm$^2$")

    for duty, shade in ((0.4, 0.45), (0.7, 0.7), (1.0, 1.0)):
        mt, rr = [], []
        for r in rpm:
            t = pt.solve(duty, r)["torque"]
            if t < -0.02:
                break
            rr.append(r)
            mt.append(t)
        ax.plot(rr, mt, lw=1.8, alpha=shade, color=BLUE)

        sol = pt.solve_loaded(duty)
        ax.plot(sol["rpm"], sol["torque"], "o", ms=9, color=GREEN, zorder=5)
        ax.annotate(f"duty {duty:.1f}\n{sol['rpm']:.0f} rpm\n{sol['thrust']:.1f} N",
                    (sol["rpm"], sol["torque"]),
                    (sol["rpm"] - 3100, sol["torque"] + 0.10),
                    color=GREEN, fontsize=9,
                    arrowprops=dict(arrowstyle="->", color=GREEN))

    ax.plot([], [], lw=1.8, color=BLUE, label="motor torque-speed line, per duty")
    ax.plot([], [], "o", color=GREEN, label="where the shaft settles")
    ax.set(xlabel="speed / rpm", ylabel="torque / Nm",
           title="One duty in, one operating point out",
           xlim=(0, 16500), ylim=(0, 0.85))
    ax.grid(alpha=.25)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=9)
    fig.text(0.5, 0.005, "motor torque falls with rpm, propeller torque rises as rpm^2. "
                         "they cross exactly once.", ha="center", fontsize=9, color=GREY)
    fig.subplots_adjust(bottom=0.14)
    fig.savefig(OUT / "operating_point.png", dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ figure 2
def chain_sweep_figure():
    """What the whole chain does as the only input, duty, is swept."""
    pt = build_powertrain()
    duties = [d / 100 for d in range(5, 101, 5)]
    pts = [pt.solve_loaded(d) for d in duties]

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.2))
    (a_rpm, a_thr), (a_cur, a_eff) = axes

    a_rpm.plot(duties, [p["rpm"] for p in pts], lw=2.4, color=BLUE)
    a_rpm.set(ylabel="speed / rpm", title="shaft speed")

    a_thr.plot(duties, [p["thrust"] for p in pts], lw=2.4, color=GREEN)
    a_thr.set(ylabel="thrust / N", title="thrust")

    a_cur.plot(duties, [p["i_dc"] for p in pts], lw=2.4, color=RED, label="pack current")
    a_cur.set(xlabel="duty", ylabel="current / A", title="what it costs the pack")
    a2 = a_cur.twinx()
    a2.plot(duties, [p["u_dc"] for p in pts], lw=1.8, ls="--", color=GREY)
    a2.set_ylabel("bus voltage / V", color=GREY)
    a_cur.text(0.06, max(p["i_dc"] for p in pts) * 0.72,
               "dashed: the pack sagging\nunder its own load", fontsize=9, color=GREY)

    eff = [p["eta_total"] * 100 for p in pts]
    a_eff.plot(duties, eff, lw=2.4, color=AMBER)
    k = eff.index(max(eff))
    a_eff.plot(duties[k], eff[k], "o", ms=9, color=AMBER)
    a_eff.annotate(f"peak {eff[k]:.1f} % at duty {duties[k]:.2f}",
                   (duties[k], eff[k]), (duties[k] + 0.12, eff[k] - 9),
                   color=AMBER, fontsize=9,
                   arrowprops=dict(arrowstyle="->", color=AMBER))
    a_eff.set(xlabel="duty", ylabel="pack to shaft / %",
              title="total efficiency, and it is not monotonic")

    for ax in axes.flat:
        ax.grid(alpha=.25)
        ax.set_axisbelow(True)
    fig.suptitle("6S2P LiPo -> ESC -> 900 Kv motor -> 10x4.5 propeller", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "chain_sweep.png", dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ figure 3
def validation_figure():
    """How a Phase 3 correlation report will read. Measured series is SYNTHETIC."""
    pt = build_powertrain()
    duties = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    pred = [pt.solve_loaded(d) for d in duties]
    i_pred = [p["i_dc"] for p in pred]

    # a plausible defect: winding resistance rises with temperature, the model
    # holds it constant, so measured current runs high and the gap grows with load.
    wobble = (+0.02, -0.03, +0.01, -0.02, +0.03, -0.01, +0.02, -0.02)
    i_meas = [ip * (1 + 0.02 + 0.06 * d + w)
              for ip, d, w in zip(i_pred, duties, wobble)]

    fig, (ax, axr) = plt.subplots(1, 2, figsize=(12, 5.0),
                                  gridspec_kw={"width_ratios": [1.15, 1]})

    band_lo = [v * 0.90 for v in i_pred]
    band_hi = [v * 1.10 for v in i_pred]
    ax.fill_between(duties, band_lo, band_hi, color=GREEN, alpha=.14,
                    label="REQ-01 tolerance, +/- 10 %")
    ax.plot(duties, i_pred, lw=2.4, color=BLUE, label="model prediction (frozen)")
    ax.plot(duties, i_meas, "o--", ms=7, lw=1.4, color=RED, label="measured (SYNTHETIC)")
    ax.set(xlabel="duty", ylabel="pack current / A",
           title="SPEC-1 REQ-01: pack current")
    ax.legend(loc="upper left", fontsize=9)

    err = [(m - p) / p * 100 for m, p in zip(i_meas, i_pred)]
    colours = [RED if abs(e) > 10 else GREEN for e in err]
    axr.bar(range(len(duties)), err, color=colours, alpha=.85)
    axr.axhline(10, color=GREY, ls="--", lw=1.2)
    axr.axhline(-10, color=GREY, ls="--", lw=1.2)
    axr.axhline(sum(err) / len(err), color=BLUE, lw=1.6,
                label=f"mean {sum(err)/len(err):+.1f} %")
    axr.set(xticks=range(len(duties)),
            xticklabels=[f"P{i+1}" for i in range(len(duties))],
            xlabel="operating point", ylabel="error / %",
            title="residual: same sign everywhere = SYSTEMATIC")
    axr.legend(loc="upper left", fontsize=9)
    axr.text(0.1, -8.4, "suspects from spec_1.json:\nR_phase, inverter loss model",
             fontsize=9, color=GREY)

    for a in (ax, axr):
        a.grid(alpha=.25)
        a.set_axisbelow(True)
    fig.suptitle("What a Phase 3 correlation looks like. The measured series here is "
                 "synthetic: there is no bench yet.", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "validation_example.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    operating_point_figure()
    chain_sweep_figure()
    validation_figure()
    for f in sorted(OUT.glob("*.png")):
        print(f"{f.relative_to(OUT.parents[1])}  {f.stat().st_size // 1024} kB")
