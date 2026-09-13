"""A battery pack: cells wired s in series, p in parallel, plus the metal.

Adds no cell physics. Everything electrical is delegated to Cell. What Pack
owns is the WIRING:

    series   adds volts        u_pack = s * u_cell
    parallel adds amps         i_cell = i_pack / p
    together                   r_pack = r_cell * s / p
    plus                       busbars, connectors, fuse, contactor, lead wire

# simplification: ONE shared Cell object, so every cell is identical and stays
# identical. No imbalance, no weak cell, no per-cell fault, and therefore
# nothing for a balancer to do. Fine for sizing. Swap for a grid of cells when
# imbalance is the question.
"""


class Pack:
    def __init__(self, cell, n_series=1, n_parallel=1, r_wiring=0.0):
        if int(n_series) != n_series or n_series < 1:
            raise ValueError(f"n_series must be a positive integer, got {n_series}")
        if int(n_parallel) != n_parallel or n_parallel < 1:
            raise ValueError(f"n_parallel must be a positive integer, got {n_parallel}")
        if r_wiring < 0:
            raise ValueError(f"r_wiring cannot be negative, got {r_wiring}")

        self.cell = cell
        self.series = int(n_series)
        self.parallel = int(n_parallel)

        # calibration knob: busbars, connectors, fuse, contactor and the lead to
        # the ESC. On a small pack this is easily 10-20 mohm, comparable to the
        # cells themselves. Measure it, do not leave it at zero.
        self.r_wiring = r_wiring          # ohm, in series with the whole pack

    def __repr__(self):
        return (f"Pack({self.series}S{self.parallel}P of {self.cell.chemistry}, "
                f"{self.capacity_ah():.1f} Ah, soc={self.soc():.3f})")

    # ------------------------------------------------------------- electrical
    def cell_current(self, i_load):
        """Parallel splits the pack current between the cells."""
        return i_load / self.parallel

    def u_ocv(self):
        """Pack open-circuit voltage. What you would measure with nothing attached."""
        return self.series * self.cell.u_ocv()

    def terminal_voltage(self, i_load):
        """Voltage at the pack terminals under load. Positive i_load = discharging."""
        return (self.series * self.cell.terminal_voltage(self.cell_current(i_load))
                - i_load * self.r_wiring)

    def sag(self, i_load):
        """How many volts the load costs you. Always positive when discharging."""
        return self.u_ocv() - self.terminal_voltage(i_load)

    def r_internal(self):
        """Total pack resistance, cells plus wiring (ohm)."""
        return self.cell.r_internal * self.series / self.parallel + self.r_wiring

    def p_loss(self, i_load):
        """Heat generated inside the pack, cells plus wiring (W).

        There are series * parallel cells, not just parallel. Each carries
        i_load / parallel. Missing the series factor understates pack heat by s.
        """
        n_cells = self.series * self.parallel
        return (n_cells * self.cell.p_loss(self.cell_current(i_load))
                + i_load ** 2 * self.r_wiring)

    def power(self, i_load):
        """Power delivered out of the terminals (W)."""
        return self.terminal_voltage(i_load) * i_load

    # ------------------------------------------------------------------ sizing
    def capacity_ah(self):
        return self.parallel * self.cell.capacity_ah

    def energy_wh(self):
        """Usable energy, by integrating the OCV curve over the whole SOC range.

        Works for a linear cell and a table cell alike, because it only ever
        asks the cell for u_ocv(). Restores soc afterwards.

        # simplification: open-circuit energy. real deliverable energy is less,
        # by whatever the IR loss is at your actual current.
        """
        saved = self.cell.soc
        n = 101
        try:
            total = 0.0
            for k in range(n):
                self.cell.soc = k / (n - 1)
                total += self.cell.u_ocv()
        finally:
            self.cell.soc = saved
        return self.series * (total / n) * self.capacity_ah()

    # ------------------------------------------------------------------ limits
    @property
    def i_max(self):
        return self.parallel * self.cell.i_max

    def over_current(self, i_load):
        return abs(i_load) > self.i_max

    def temperature(self, i_load, ambient_c=25.0):
        """Cell temperature at this pack current. Wiring heat is not in the cell."""
        return self.cell.temperature(self.cell_current(i_load), ambient_c)

    # ------------------------------------------------------------------- state
    def soc(self):
        return self.cell.soc

    def discharge(self, i_load, dt):
        """Advance the pack by dt seconds at i_load amps.

        Careful: one shared Cell object, so calling this twice in a timestep
        drains the pack twice.
        """
        return self.cell.discharge(self.cell_current(i_load), dt)

    def is_empty(self):
        return self.cell.is_empty()
