"""Sweeps and checks for an Inverter. Returns data, never prints or draws."""

from aether.model.inverter import Inverter


def _as_list(x):
    """Accept a scalar or an iterable, always hand back a list."""
    try:
        return list(x)
    except TypeError:
        return [x]


class InverterAnalyser:
    def __init__(self, inverter):
        self.inverter = inverter

    def sweep(self, u_dc, duty_range, i_ac_range):
        """Every combination of duty and phase current at the given bus voltage.

        u_dc, duty_range and i_ac_range each accept a scalar or an iterable.
        """
        points = []
        for u in _as_list(u_dc):
            for duty in _as_list(duty_range):
                for i_ac in _as_list(i_ac_range):
                    op = self.inverter.operating_point(u, duty, i_ac)
                    points.append({"u_dc": u, "duty": duty, **op})
        return points

    def power_balance_error(self, points):
        """Invariant: the DC side supplies the AC side plus every loss.

        Returns the worst absolute error in watts. Must be ~0.
        """
        if not points:
            return 0.0
        return max(abs(p["p_dc"] - (p["p_ac"] + p["p_loss"])) for p in points)

    def peak_efficiency(self, points):
        """The point with the highest efficiency, or None if there is none."""
        usable = [p for p in points if p["eta"] > 0]
        return max(usable, key=lambda p: p["eta"]) if usable else None

    def loss_split(self, points):
        """Where the heat goes, summed over the sweep. Conduction vs switching."""
        cond = sum(p["p_conduction"] for p in points)
        sw = sum(p["p_switching"] for p in points)
        total = cond + sw
        return {
            "p_conduction": cond,
            "p_switching": sw,
            "conduction_share": cond / total if total > 0 else 0.0,
        }

    def within_limits(self, points):
        """Only the points the hardware is actually allowed to reach."""
        return [p for p in points if not (p["over_current"] or p["over_voltage"])]


if __name__ == "__main__":
    # n_conducting = 2 for six-step, 3 for sinusoidal. NOT 6, that is the device count.
    inv = Inverter(name="Demo ESC", i_max=100.0, u_max=400.0, r_ds_on=0.010,
                   n_conducting=2, f_sw=20_000.0, e_sw=1.0e-3,
                   u_sw_ref=400.0, i_sw_ref=50.0)
    an = InverterAnalyser(inv)

    pts = an.sweep(u_dc=400.0, duty_range=[0.1, 0.25, 0.5, 0.75, 1.0],
                   i_ac_range=[10.0, 25.0, 50.0, 100.0])

    print(inv)
    print(f"worst power balance error : {an.power_balance_error(pts):.3e} W")

    best = an.peak_efficiency(pts)
    print(f"peak efficiency           : {best['eta']*100:.2f} % " # type: ignore
          f"at duty {best['duty']}, {best['i_ac']:.0f} A") # type: ignore

    split = an.loss_split(pts)
    print(f"loss split over the sweep : conduction {split['conduction_share']*100:.1f} %, "
          f"switching {100-split['conduction_share']*100:.1f} %")
    print(f"points within limits      : {len(an.within_limits(pts))} of {len(pts)}")
