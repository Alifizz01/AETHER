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

# simplification: steady state. rpm is imposed from outside, so no propeller
# and no rotor inertia yet. that is the second loop, and it needs Propeller.
"""


class NotConverged(RuntimeError):
    """The solver ran out of iterations. Do not trust a half-solved point."""


class Powertrain:
    def __init__(self, pack, inverter, motor):
        self.pack = pack
        self.inverter = inverter
        self.motor = motor

    def __repr__(self):
        return f"Powertrain({self.pack.series}S{self.pack.parallel}P -> {self.inverter.name} -> {self.motor.name})"

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
