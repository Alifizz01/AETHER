"""Time-stepping mission simulator for AETHER powertrains.

Advances a Powertrain through a phased mission over time:
1. Demand: query what thrust is demanded at time t from mission phases
2. Solve: ask Powertrain what duty and operating point satisfy that demand
3. State: discharge the pack by i_dc for dt seconds
4. Stop check: empty pack, duty saturation / thrust unreachable, mission end
5. Log: record full state at each step
"""

from statistics import fmean

from aether.model.powertrain import ThrustUnreachable


class Simulator:
    def __init__(self, powertrain, mission, dt=1.0, rho=1.225):
        self.powertrain = powertrain
        self.mission = mission
        self.dt = float(dt)
        self.rho = float(rho)

        self.t = 0.0
        self.log = []
        self.stopped_because = None

    def reset(self):
        """Reset simulator clock and log.

        Note: Callers must also restore/reset pack/cell state if needed
        prior to repeated runs (e.g. Monte Carlo).
        """
        self.t = 0.0
        self.log = []
        self.stopped_because = None

    def demand(self, t):
        """Walk the phases until t falls inside one.

        Returns (phase_name, thrust_n), or (None, None) if mission finished.
        Accepts duration_s or duration, thrust_n or thrust.
        """
        remaining = t
        for phase in self.mission:
            dur = phase.get("duration_s", phase.get("duration", 0.0))
            if remaining < dur:
                thrust = phase.get("thrust_n", phase.get("thrust", 0.0))
                name = phase.get("name", "unnamed")
                return name, thrust
            remaining -= dur
        return None, None

    def stop_reason(self):
        """Return a string naming why simulation should stop, or None if continuing."""
        if self.stopped_because is not None:
            return self.stopped_because

        if self.powertrain.pack.is_empty():
            return "PACK_EMPTY"

        phase_name, _ = self.demand(self.t)
        if phase_name is None:
            return "MISSION_COMPLETED"

        return None

    def step(self):
        """Advance simulation by exactly one dt step.

        Ordering:
        1. Query demand at current time t
        2. Solve duty and operating point at current state
        3. Record state before advancing
        4. Discharge pack by i_dc for dt seconds
        5. Advance clock t += dt
        """
        if self.stopped_because is not None:
            return None

        phase_name, thrust = self.demand(self.t)
        if phase_name is None:
            self.stopped_because = "MISSION_COMPLETED"
            return None

        t_step = self.t

        try:
            duty = self.powertrain.duty_for_thrust(thrust, rho=self.rho)
            point = self.powertrain.solve_loaded(duty, rho=self.rho)
        except ThrustUnreachable:
            self.stopped_because = "THRUST_UNREACHABLE"
            return None

        # Build snapshot record at instant t before discharging
        record = {
            "t": t_step,
            "phase": phase_name,
            "thrust_demand": thrust,
            "soc": self.powertrain.pack.soc(),
            **point,
        }
        self.log.append(record)

        # Advance state
        self.powertrain.pack.discharge(point["i_dc"], self.dt)
        self.t += self.dt

        # Check stopping conditions after state advance
        if self.powertrain.pack.is_empty():
            self.stopped_because = "PACK_EMPTY"

        return record

    def run(self, max_time=None):
        """Loop step() until stopped_because is set or max_time is reached."""
        while True:
            if max_time is not None and self.t >= max_time:
                if self.stopped_because is None:
                    self.stopped_because = "TIME_LIMIT"
                break

            record = self.step()
            if record is None:
                break

        return self.summarise()

    def summarise(self):
        """Collapse trajectory log into summary KPIs."""
        if not self.log:
            return {
                "endurance_s": 0.0,
                "stopped_because": self.stopped_because or "NO_DATA",
                "energy_wh": 0.0,
                "min_cell_v": 0.0,
                "soc_at_end": self.powertrain.pack.soc(),
                "duty_at_end": 0.0,
                "mean_eta": 0.0,
                "steps": 0,
            }

        first_rec = self.log[0]
        pack = self.powertrain.pack

        endurance = self.log[-1]["t"]
        energy_wh = sum(r["p_pack_in"] for r in self.log) * self.dt / 3600.0
        min_cell_v = min(r["u_dc"] for r in self.log) / pack.series
        soc_at_end = self.powertrain.pack.soc()
        duty_at_end = self.log[-1]["duty"]
        mean_eta = fmean(r["eta_total"] for r in self.log)

        return {
            "endurance_s": endurance,
            "stopped_because": self.stopped_because,
            "energy_wh": energy_wh,
            "min_cell_v": min_cell_v,
            "soc_at_end": soc_at_end,
            "duty_at_end": duty_at_end,
            "mean_eta": mean_eta,
            "steps": len(self.log),
        }
        




        