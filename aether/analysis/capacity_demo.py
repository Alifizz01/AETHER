"""Why capacity_ah is not the same information as the OCV curve.

Two cells, identical chemistry and identical OCV table, different capacity.
Discharged at the same current. Left plot cannot tell them apart. Right plot
is the whole difference.

Run:  python source/analysis/capacity_demo.py
"""

import matplotlib.pyplot as plt

from aether.model.cell import Cell_advanced

# NMC table from GAIA, soc as a fraction
SOC_PTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
OCV_PTS = [2.50, 3.00, 3.30, 3.50, 3.65, 3.75, 3.85, 3.95, 4.05, 4.15, 4.20]

CURRENT = 6.0        # A, the same for both cells
DT = 1.0             # s


def make(capacity_ah):
    return Cell_advanced(chemistry="NMC", capacity_ah=capacity_ah, r_internal=0.020,
                         soc_points=SOC_PTS, ocv_points=OCV_PTS, i_max=30.0)


def run(cell, current, dt):
    """Discharge until empty, logging time, soc and terminal voltage."""
    t, soc, u = [0.0], [cell.soc], [cell.terminal_voltage(current)]
    while not cell.is_empty():
        cell.discharge(current, dt)
        t.append(t[-1] + dt / 60.0)          # minutes
        soc.append(cell.soc)
        u.append(cell.terminal_voltage(current))
    return t, soc, u


def build():
    small, big = make(1.0), make(3.0)
    t_s, soc_s, u_s = run(small, CURRENT, DT)
    t_b, soc_b, u_b = run(big, CURRENT, DT)

    fig, (ax_soc, ax_t) = plt.subplots(1, 2, figsize=(13, 5.4))

    # ---- left: voltage against SOC. the two are identical -----------------
    ax_soc.plot([s * 100 for s in soc_b], u_b, lw=6, color="#8fb8f0",
                label="3.0 Ah cell")
    ax_soc.plot([s * 100 for s in soc_s], u_s, lw=2, ls="--", color="#d1242f",
                label="1.0 Ah cell")
    ax_soc.set(xlabel="state of charge / %", ylabel="terminal voltage / V",
               title="against SOC: the two cells are indistinguishable",
               xlim=(0, 100), ylim=(2.2, 4.3))
    ax_soc.legend(loc="lower right")
    ax_soc.text(50, 2.5, "the OCV curve knows the SHAPE\nnot the SIZE",
                ha="center", fontsize=11, color="#57606a")

    # ---- right: voltage against time. everything changes ------------------
    ax_t.plot(t_b, u_b, lw=2.4, color="#1f6feb", label="3.0 Ah cell")
    ax_t.plot(t_s, u_s, lw=2.4, color="#d1242f", label="1.0 Ah cell")
    for t_end, col, cap in ((t_s[-1], "#d1242f", 1.0), (t_b[-1], "#1f6feb", 3.0)):
        ax_t.axvline(t_end, color=col, ls=":", lw=1.4)
        ax_t.annotate(f"{cap:.0f} Ah / {CURRENT:.0f} A\n= {t_end:.0f} min",
                      (t_end, 3.6), (t_end - 1.5, 3.9), ha="right",
                      color=col, fontsize=10,
                      arrowprops=dict(arrowstyle="->", color=col))
    ax_t.set(xlabel="time / minutes", ylabel="terminal voltage / V",
             title=f"against TIME, both at {CURRENT:.0f} A: three times the runtime",
             xlim=(0, t_b[-1] * 1.05), ylim=(2.2, 4.3))
    ax_t.legend(loc="lower left")

    for a in (ax_soc, ax_t):
        a.grid(alpha=.25)
        a.set_axisbelow(True)

    fig.suptitle("Voltage tells you WHAT FRACTION is left. Capacity tells you "
                 "how much that fraction is worth.", fontsize=13)
    fig.tight_layout()
    fig.savefig("figures/capacity_vs_ocv.png", dpi=150)

    # ---- checks -----------------------------------------------------------
    assert abs(t_s[-1] - 1.0 / CURRENT * 60) < 0.1, t_s[-1]     # 10 min
    assert abs(t_b[-1] - 3.0 / CURRENT * 60) < 0.1, t_b[-1]     # 30 min
    assert abs(t_b[-1] / t_s[-1] - 3.0) < 0.01                  # exactly 3x
    assert abs(max(u_b) - max(u_s)) < 1e-9                      # same voltages
    print(f"1.0 Ah at {CURRENT:.0f} A -> {t_s[-1]:.1f} min")
    print(f"3.0 Ah at {CURRENT:.0f} A -> {t_b[-1]:.1f} min")
    print("same OCV curve, same voltages, three times the runtime")
    print("\nall checks passed -> figures/capacity_vs_ocv.png")


if __name__ == "__main__":
    build()
