"""Three ways to load the same cell, and why the current does different things.

The previous demo held current constant. Nothing in nature does that. What
does it is a CONTROLLER measuring current and adjusting. Three real cases:

    constant resistance   a resistor. I = U / R, so current DROOPS as U falls.
    constant current      an electronic load, or a current-controlled drive.
                          a loop actively adjusts to hold I.
    constant power        a drone holding thrust. P fixed, so as U falls,
                          current RISES. this one runs away at the end.

Run:  python source/analysis/load_types_demo.py
"""

import math
import matplotlib.pyplot as plt

from aether.model.cell import Cell_advanced

SOC_PTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
OCV_PTS = [2.50, 3.00, 3.30, 3.50, 3.65, 3.75, 3.85, 3.95, 4.05, 4.15, 4.20]

DT = 1.0            # s
I_START = 6.0       # A, all three start here so the comparison is fair


def make():
    return Cell_advanced(chemistry="NMC", capacity_ah=3.0, r_internal=0.020,
                         soc_points=SOC_PTS, ocv_points=OCV_PTS, i_max=30.0)


def i_constant_resistance(cell, r_load):
    """Resistor: the cell and the load form one series circuit."""
    return cell.u_ocv() / (r_load + cell.r_internal)


def i_constant_power(cell, p_load):
    """Solve U_ocv*I - I^2*r = P for the physical (smaller) root.

    No real root means the cell can no longer deliver that power at any
    current. That is a genuine collapse, not a numerical failure.
    """
    a, b, c = cell.r_internal, -cell.u_ocv(), p_load
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    return (-b - math.sqrt(disc)) / (2 * a)


def run(mode, setpoint):
    cell = make()
    t, i_log, u_log = [0.0], [], []
    while not cell.is_empty():
        if mode == "CR":
            i = i_constant_resistance(cell, setpoint)
        elif mode == "CC":
            i = setpoint
        else:
            i = i_constant_power(cell, setpoint)
            if i is None:
                break                      # cell can no longer hold the power
        u_log.append(cell.terminal_voltage(i))
        i_log.append(i)
        cell.discharge(i, DT)
        t.append(t[-1] + DT / 60.0)
    return t[:-1], i_log, u_log


def build():
    ref = make()
    # all three start at the same 6 A, so the setpoints follow from that
    r_load = ref.u_ocv() / I_START - ref.r_internal
    p_load = ref.terminal_voltage(I_START) * I_START

    runs = {
        "constant resistance": ("CR", r_load, "#1a7f37"),
        "constant current": ("CC", I_START, "#1f6feb"),
        "constant power": ("CP", p_load, "#d1242f"),
    }

    fig, (ax_i, ax_u) = plt.subplots(1, 2, figsize=(13, 5.4))
    results = {}
    for label, (mode, sp, col) in runs.items():
        t, i, u = run(mode, sp)
        results[label] = (t, i, u)
        ax_i.plot(t, i, lw=2.4, color=col, label=f"{label}  ({t[-1]:.1f} min)")
        ax_u.plot(t, u, lw=2.4, color=col, label=label)

    ax_i.axhline(I_START, color="#57606a", ls=":", lw=1.2)
    ax_i.text(0.4, I_START + 0.15, "all three start at 6 A", fontsize=9, color="#57606a")
    ax_i.set(xlabel="time / minutes", ylabel="current / A",
             title="the load type decides what the current does",
             ylim=(0, max(max(i) for _, i, _ in results.values()) * 1.15))
    ax_i.legend(loc="upper left", fontsize=9)

    ax_u.set(xlabel="time / minutes", ylabel="terminal voltage / V",
             title="same cell, same start, three different endings", ylim=(2.2, 4.3))
    ax_u.legend(loc="lower left", fontsize=9)

    ax_i.annotate("power is fixed, so as volts fall\nthe current must RISE",
                  (results["constant power"][0][-1] * 0.85,
                   results["constant power"][1][-1] * 0.9),
                  (2, 9.0), color="#d1242f", fontsize=9.5,
                  arrowprops=dict(arrowstyle="->", color="#d1242f"))
    ax_i.annotate("a resistor just droops",
                  (results["constant resistance"][0][-1] * 0.6,
                   results["constant resistance"][1][int(len(results["constant resistance"][1]) * 0.6)]),
                  (18, 3.0), color="#1a7f37", fontsize=9.5,
                  arrowprops=dict(arrowstyle="->", color="#1a7f37"))

    for a in (ax_i, ax_u):
        a.grid(alpha=.25)
        a.set_axisbelow(True)
    fig.suptitle("Nothing holds current constant by itself. A controller does, "
                 "and a real drone holds POWER instead.", fontsize=13)
    fig.tight_layout()
    fig.savefig("figures/load_types.png", dpi=150)

    # ---- checks -----------------------------------------------------------
    t_cr, i_cr, _ = results["constant resistance"]
    t_cc, i_cc, _ = results["constant current"]
    t_cp, i_cp, _ = results["constant power"]

    assert abs(i_cr[0] - I_START) < 1e-6 and abs(i_cp[0] - I_START) < 1e-6
    assert i_cr[-1] < i_cr[0]                 # resistor droops
    assert i_cp[-1] > i_cp[0]                 # constant power climbs
    assert t_cr[-1] > t_cc[-1] > t_cp[-1]     # and that ordering is the point

    for name in runs:
        t, i, _ = results[name]
        print(f"{name:22s} runtime {t[-1]:5.1f} min   "
              f"current {i[0]:4.1f} -> {i[-1]:4.1f} A")
    print("\nall checks passed -> figures/load_types.png")


if __name__ == "__main__":
    build()
