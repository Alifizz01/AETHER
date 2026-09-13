"""Battery management system.

Not a physics block. No power flows through it. It reads measurements, guesses
what it cannot measure, and decides what the pack is allowed to do.

    sense  ->  estimate  ->  decide  ->  act

THE RULE: this class may only use what a real BMS can measure.

    allowed    pack terminal voltage, pack current, temperature,
               nameplate capacity (configured at build time)
    forbidden  cell.soc

A real BMS has no SOC sensor. If this class reads the true soc it will look
perfect in simulation and fail on hardware. Because it has to guess, the gap
between its guess and Pack's truth is a real V&V metric.
"""


class CoulombCounter:
    """Default SOC estimator. Integrates measured current, nothing else.

    Drifts, because it never looks at voltage to correct itself. That drift is
    the reason GAIA has an Extended Kalman Filter. Swap this out for
    AdaptiveExtendedKalmanFilterSOC when you want the good one.

    # simplification: no coulombic efficiency, no self-discharge, no drift model.
    """

    def __init__(self, capacity_ah, initial_soc=1.0):
        self.capacity_ah = capacity_ah
        self.soc = initial_soc

    def update(self, current, voltage, dt):
        # voltage is accepted and ignored. a real estimator uses it. that is the point.
        self.soc -= (current * dt) / (self.capacity_ah * 3600.0)
        self.soc = min(1.0, max(0.0, self.soc))
        return self.soc


class BMS:
    OK, WARNING, FAULT = "OK", "WARNING", "FAULT"

    def __init__(self, pack, i_max_discharge, i_max_charge,
                 u_cell_min=3.0, u_cell_max=4.25, temp_max_c=60.0,
                 soc_warn=0.20, estimator=None, initial_soc_guess=1.0):
        self.pack = pack

        # --- limits: what the pack is allowed to do ---
        self.i_max_discharge = i_max_discharge   # A, positive
        self.i_max_charge = i_max_charge         # A, magnitude
        self.u_cell_min = u_cell_min             # V per cell
        self.u_cell_max = u_cell_max             # V per cell
        self.temp_max_c = temp_max_c             # degC
        self.soc_warn = soc_warn                 # warn below this estimated soc

        # --- the estimator. nameplate capacity is configured, not measured ---
        capacity_ah = pack.cell.capacity_ah * pack.parallel
        self.estimator = estimator or CoulombCounter(capacity_ah, initial_soc_guess)

        # --- state ---
        self.contactor_closed = True
        self.latched_faults = []

    def __repr__(self):
        return (f"BMS(state={self.state()}, soc_est={self.estimator.soc:.3f}, "
                f"contactor={'closed' if self.contactor_closed else 'OPEN'})")

    # ------------------------------------------------------------------- sense
    def measure(self, i_pack, ambient_c=25.0):
        """Everything a real BMS can physically read."""
        u_pack = self.pack.terminal_voltage(i_pack)
        return {
            "u_pack": u_pack,
            "u_cell": u_pack / self.pack.series,
            "i_pack": i_pack,
            "temp_c": self.pack.cell.temperature(i_pack / self.pack.parallel, ambient_c),
        }

    # ------------------------------------------------------------------ decide
    def check_limits(self, m, soc_est):
        """Compare measurements against limits. Returns a list of fault names."""
        faults = []
        if m["u_cell"] < self.u_cell_min:
            faults.append("UNDER_VOLTAGE")
        if m["u_cell"] > self.u_cell_max:
            faults.append("OVER_VOLTAGE")
        if m["i_pack"] > self.i_max_discharge:
            faults.append("OVER_CURRENT_DISCHARGE")
        if -m["i_pack"] > self.i_max_charge:
            faults.append("OVER_CURRENT_CHARGE")
        if m["temp_c"] > self.temp_max_c:
            faults.append("OVER_TEMPERATURE")
        return faults

    def current_allowed(self, charging=False):
        """How much current the BMS will permit right now."""
        if not self.contactor_closed:
            return 0.0
        return self.i_max_charge if charging else self.i_max_discharge

    def state(self):
        if self.latched_faults:
            return self.FAULT
        if self.estimator.soc < self.soc_warn:
            return self.WARNING
        return self.OK

    # -------------------------------------------------------------------- loop
    def update(self, i_pack, dt, ambient_c=25.0):
        """One control cycle: sense, estimate, decide, act."""
        m = self.measure(i_pack, ambient_c)
        soc_est = self.estimator.update(i_pack, m["u_pack"], dt)

        faults = self.check_limits(m, soc_est)
        for f in faults:
            if f not in self.latched_faults:
                self.latched_faults.append(f)   # latch: a fault does not clear itself

        if self.latched_faults:
            self.contactor_closed = False       # act

        return {
            **m,
            "soc_estimate": soc_est,
            "faults": list(self.latched_faults),
            "new_faults": faults,
            "state": self.state(),
            "contactor_closed": self.contactor_closed,
            "current_allowed": self.current_allowed(),
        }

    def reset_faults(self):
        """Only a human or a supervisor clears a latched fault."""
        self.latched_faults = []
        self.contactor_closed = True

    # -------------------------------------------------------------------- V&V
    def estimation_error(self):
        """Estimated soc minus the true soc. Only the test harness may call this.

        The BMS itself must never use it. It exists so you can measure how bad
        the estimator is, which is the whole reason a better one is worth having.
        """
        return self.estimator.soc - self.pack.cell.soc
