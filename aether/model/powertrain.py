"""Pack -> inverter -> motor, solved so all three agree.

This class adds NO physics. Every equation lives in Pack, Inverter and Motor.
What it adds is the solution to a circular problem:

    i_dc  ->  pack sags   ->  u_dc
    u_dc  ->  inverter    ->  u_ac = duty * u_dc
    u_ac  ->  motor       ->  i_ac
    i_ac  ->  inverter    ->  i_dc        back to the start

Nothing can be computed first, so guess and iterate. The loop is
self-correcting: more current sags the pack, which lowers u_ac, which lowers
the current. Negative feedback, so the iteration contracts, but it OVERSHOOTS
and rings, decaying only about 0.7 per pass on a soft pack. Taking a partial
step instead of the full one (relaxation) kills the ringing and converges in
around ten passes. It also keeps the solver stable if a stiffer motor or a
softer pack ever pushes the raw loop gain past 1, where undamped iteration
would diverge outright.

With a Propeller attached there is a SECOND loop, mechanical this time:

    motor torque falls with rpm        (its torque-speed line)
    propeller torque rises with rpm^2  (its load line)

They cross at exactly one rpm, and that crossing is where the shaft settles.
Bisection finds it: the residual falls monotonically, so it cannot diverge.

# simplification: steady state. No rotor inertia, so no spin-up transient, and
# no PI controller. solve_loaded() lands directly on the equilibrium a perfectly
# tuned controller would reach.
"""

import math


class NotConverged(RuntimeError):
    """The solver ran out of iterations. Do not trust a half-solved point."""


class ThrustUnreachable(RuntimeError):
    """Even full duty cannot produce the demanded thrust.

    Not a solver failure. It is the real end of flight: the pack has sagged far
    enough that the controller has run out of adjustment.
    """


class Powertrain:
    def __init__(self, pack, inverter, motor, propeller=None):
        self.pack = pack
        self.inverter = inverter
        self.motor = motor
        self.propeller = propeller      # optional: a clamped bench motor has none

    def __repr__(self):
        load = self.propeller.name if self.propeller else "no load"
        return (f"Powertrain({self.pack.series}S{self.pack.parallel}P -> "
                f"{self.inverter.name} -> {self.motor.name} -> {load})")

    def solve(self, duty, rpm, tol=1e-9, max_iter=200, relaxation=0.5):
        """Find the operating point where pack, inverter and motor all agree.

        duty and rpm are the inputs you control. Everything else is solved for.
        relaxation is the fraction of each correction to actually take:
        1.0 is the raw fixed point, lower is slower per step but stabler.
        """
        i_dc = 0.0                      # first guess: no load, pack un-sagged

        for iteration in range(1, max_iter + 1):
            u_dc = self.pack.terminal_voltage(i_dc)
            u_ac = self.inverter.output_voltage(u_dc, duty)

            mot = self.motor.operating_point(rpm, u_ac)
            inv = self.inverter.operating_point(u_dc, duty, mot["I"])

            if abs(inv["i_dc"] - i_dc) < tol:
                return self._assemble(duty, rpm, u_dc, mot, inv, iteration)
            i_dc += relaxation * (inv["i_dc"] - i_dc)

        raise NotConverged(
            f"duty={duty}, rpm={rpm}: i_dc still moving after {max_iter} iterations")

    def _assemble(self, duty, rpm, u_dc, mot, inv, iterations):
        """Collect the converged result. Bookkeeping only, no new physics."""
        p_pack_loss = self.pack.p_loss(inv["i_dc"])
        p_pack_out = inv["p_dc"]                    # what leaves the pack terminals
        p_pack_in = p_pack_out + p_pack_loss        # what the chemistry gave up

        return {
            "duty": duty,
            "rpm": rpm,
            "iterations": iterations,

            # electrical chain, in order
            "u_dc": u_dc,
            "i_dc": inv["i_dc"],
            "u_ac": inv["u_ac"],
            "i_ac": inv["i_ac"],

            # mechanical output
            "torque": mot["torque"],
            "omega": mot["omega"],
            "p_mech": mot["P_out"],

            # where the power went
            "p_pack_in": p_pack_in,
            "p_pack_loss": p_pack_loss,
            "p_inverter_loss": inv["p_loss"],
            "p_motor_loss": mot["P_copper"] + mot["P_noload"],

            # efficiency of each stage and of the whole chain
            "eta_inverter": inv["eta"],
            "eta_motor": mot["eta"],
            "eta_total": mot["P_out"] / p_pack_in if p_pack_in > 0 else 0.0,

            # limits, reported not raised
            "motor_over_current": mot["over_current"],
            "inverter_over_current": inv["over_current"],
        }

    def power_balance_error(self, point):
        """Invariant across the whole chain. Must be ~0 at every operating point."""
        return point["p_pack_in"] - (point["p_mech"]
                                     + point["p_pack_loss"]
                                     + point["p_inverter_loss"]
                                     + point["p_motor_loss"])

    # ----------------------------------------------------- mechanical loop
    def _require_propeller(self):
        if self.propeller is None:
            raise ValueError("no propeller attached. use solve(duty, rpm) instead, "
                             "or construct Powertrain(..., propeller=prop)")

    def _rpm_ceiling(self, duty):
        """An rpm the shaft certainly cannot exceed at this duty.

        Uses the UN-sagged pack voltage, so the real no-load speed is always
        lower and the bracket is guaranteed to contain the crossing.
        """
        u_ac_max = duty * self.pack.u_ocv()
        return u_ac_max / self.motor.k_e * 60.0 / (2.0 * math.pi)

    def torque_residual(self, duty, rpm, rho=1.225):
        """Motor torque minus propeller torque at this rpm.

        Positive means the motor is winning and the shaft accelerates.
        Falls monotonically with rpm, which is what makes bisection safe.
        """
        self._require_propeller()
        return (self.solve(duty, rpm)["torque"]
                - self.propeller.torque(rpm, rho))

    def solve_loaded(self, duty, rho=1.225, tol_rpm=1e-6, max_iter=200):
        """Where the shaft actually settles: motor torque = propeller torque.

        duty is the only input. rpm is no longer given, it is solved for.
        """
        self._require_propeller()
        if not 0.0 <= duty <= 1.0:
            raise ValueError(f"duty must be between 0 and 1, got {duty}")

        lo = 0.0
        if duty == 0.0 or self.torque_residual(duty, lo, rho) <= 0.0:
            # the motor cannot even overcome its own no-load drag. it stays put.
            return self._assemble_loaded(duty, 0.0, rho)

        hi = self._rpm_ceiling(duty)
        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            if self.torque_residual(duty, mid, rho) > 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol_rpm:
                return self._assemble_loaded(duty, 0.5 * (lo + hi), rho)

        raise NotConverged(f"duty={duty}: rpm bracket still {hi - lo:.3g} wide "
                           f"after {max_iter} bisections")

    def _assemble_loaded(self, duty, rpm, rho):
        """Electrical point plus what the propeller is doing at that rpm."""
        point = self.solve(duty, rpm)
        prop = self.propeller.operating_point(rpm, rho)
        point.update({
            "rho": rho,
            "thrust": prop["thrust"],
            "prop_torque": prop["torque"],
            "prop_power": prop["power"],
            "tip_speed": prop["tip_speed"],
            "figure_of_merit": prop["figure_of_merit"],
            "over_tip_speed": prop["over_tip_speed"],
            "torque_residual": point["torque"] - prop["torque"],
        })
        return point

    # --------------------------------------------------------- outer loop
    def duty_for_thrust(self, thrust, rho=1.225, tol=1e-9, max_iter=200):
        """The duty a perfect controller would hold to produce this thrust.

        Raises ThrustUnreachable when even full duty falls short. That is not a
        bug, it is duty saturation: the pack has sagged so far that the
        controller has no adjustment left.
        """
        self._require_propeller()
        if thrust <= 0.0:
            return 0.0

        best = self.solve_loaded(1.0, rho)["thrust"]
        if best < thrust:
            raise ThrustUnreachable(
                f"full duty gives {best:.3f} N, {thrust:.3f} N demanded. "
                f"pack at soc {self.pack.soc():.3f} cannot hold this thrust.")

        lo, hi = 0.0, 1.0
        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            if self.solve_loaded(mid, rho)["thrust"] < thrust:
                lo = mid
            else:
                hi = mid
            if hi - lo < tol:
                return 0.5 * (lo + hi)

        raise NotConverged(f"thrust={thrust}: duty bracket still {hi - lo:.3g} wide")

    def shaft_power_error(self, point):
        """Invariant: at the crossing, the motor's shaft power IS the propeller's.

        If these disagree the bisection did not actually converge.
        """
        return point["p_mech"] - point["prop_power"]
