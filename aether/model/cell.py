"""One battery cell, Rint model.

Physics direction, and it only goes this way:

    soc  ->  u_ocv  ->  u_terminal = u_ocv - I * r_internal

Going backwards (terminal voltage -> soc) is estimation, not modelling. Under
load the IR drop corrupts it, which is why GAIA uses an Extended Kalman Filter.
That belongs in the BMS, not here.

Series and parallel scaling belongs in Pack. This class is one cell.

Two variants. They differ in ONE method, u_ocv(). Everything else is shared:

    Cell_simple     straight line between u_empty and u_full
    Cell_advanced   interpolated from a measured OCV table
"""
import numpy as np


class Cell_simple:
    def __init__(self, chemistry, capacity_ah, r_internal, u_full, u_empty,
                 i_max, r_thermal=0.1, soc=1.0):
        # --- what the cell is (attributes) ---
        self.chemistry = chemistry        # e.g. "LiPo", "NMC", "LFP". label for traceability
        self.capacity_ah = capacity_ah    # nominal capacity (Ah)
        self.r_internal = r_internal      # internal resistance (ohm)
        self.u_full = u_full              # OCV at soc = 1 (V)
        self.u_empty = u_empty            # OCV at soc = 0 (V)
        self.i_max = i_max                # discharge limit (A)

        # calibration knob: real cells sit in real airflow. measure this, do not trust it.
        self.r_thermal = r_thermal        # thermal resistance to ambient (degC/W)

        # --- what changes while running (state) ---
        self.soc = soc                    # 0.0 to 1.0

    def __repr__(self):
        return (f"{type(self).__name__}({self.chemistry}, {self.capacity_ah} Ah, "
                f"{self.r_internal} ohm, soc={self.soc:.3f})")

    # ------------------------------------------------------------------ model
    def u_ocv(self):
        """Open-circuit voltage from state of charge.

        # simplification: linear OCV. a real LiPo sits near 3.7 V across most of
        # its range then falls off a cliff. use Cell_advanced with a measured
        # table when that matters.
        """
        return self.u_empty + self.soc * (self.u_full - self.u_empty)

    def terminal_voltage(self, i_load):
        """Voltage at the terminals under load. Positive i_load = discharging."""
        return self.u_ocv() - i_load * self.r_internal

    def p_loss(self, i_load):
        """Heat generated inside the cell (W)."""
        return i_load ** 2 * self.r_internal

    def temperature(self, i_load, ambient_c=25.0):
        """Steady-state cell temperature (degC).

        # simplification: no thermal mass, so this jumps instantly to the final
        # value. valid for steady operating points, not for transients.
        """
        return ambient_c + self.p_loss(i_load) * self.r_thermal

    def over_current(self, i_load):
        """True if this current is outside the rating. Reports, does not raise."""
        return abs(i_load) > self.i_max

    # ------------------------------------------------------------------ state
    def discharge(self, i_load, dt):
        """Coulomb counting. Advances soc by dt seconds at i_load amps.

        Positive i_load discharges, negative charges. soc is clamped to [0, 1].
        """
        self.soc -= (i_load * dt) / (self.capacity_ah * 3600.0)
        self.soc = min(1.0, max(0.0, self.soc))
        return self.soc

    def is_empty(self):
        return self.soc <= 0.0


class Cell_advanced(Cell_simple):
    """Same cell, but OCV comes from a measured table instead of a straight line.

    soc_points must be in 0..1 and strictly increasing. ocv_points are the
    open-circuit voltages measured AT REST at those states of charge. Measuring
    them under load gives you u_ocv - I*r, which is not OCV.

    # simplification: no hysteresis (charge OCV sits a few mV above discharge),
    # and the table is valid only at the temperature it was measured at.
    """

    def __init__(self, chemistry, capacity_ah, r_internal, soc_points, ocv_points,
                 i_max, r_thermal=0.1, soc=1.0):
        soc_points = np.asarray(soc_points, dtype=float)
        ocv_points = np.asarray(ocv_points, dtype=float)
        self._validate(soc_points, ocv_points)

        # the ends of the table ARE the full and empty voltages. no None needed.
        super().__init__(chemistry, capacity_ah, r_internal,
                         u_full=float(ocv_points[-1]), u_empty=float(ocv_points[0]),
                         i_max=i_max, r_thermal=r_thermal, soc=soc)

        self.soc_points = soc_points
        self.ocv_points = ocv_points

    @staticmethod
    def _validate(soc_points, ocv_points):
        if soc_points.shape != ocv_points.shape:
            raise ValueError("soc_points and ocv_points must be the same length")
        if soc_points.size < 2:
            raise ValueError("need at least two table points")
        if not np.all(np.diff(soc_points) > 0):
            raise ValueError("soc_points must be strictly increasing (np.interp needs it)")
        if soc_points[0] < 0.0 or soc_points[-1] > 1.0:
            raise ValueError("soc_points must lie in 0..1, not percent")

    def u_ocv(self):
        """Linear interpolation between the measured points.

        np.interp clamps outside the table rather than extrapolating, which is
        what you want: a fit extrapolated past the data is a guess dressed up.
        """
        return float(np.interp(self.soc, self.soc_points, self.ocv_points))
