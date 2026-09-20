"""Pack -> inverter -> motor -> propeller, solved so they all agree."""

import math


class NotConverged(RuntimeError):
    """The solver ran out of iterations."""


class ThrustUnreachable(RuntimeError):
    """Even full duty cannot produce the demanded thrust."""


class Powertrain:
    def __init__(self, pack, inverter, motor, propeller=None):
        self.pack = pack
        self.inverter = inverter
        self.motor = motor
        self.propeller = propeller

    def solve(self, duty, rpm, tol=1e-9, max_iter=200, relaxation=0.5):
        i_dc = 0.0
        for iteration in range(1, max_iter + 1):
            u_dc = self.pack.terminal_voltage(i_dc)
            u_ac = self.inverter.ac_voltage(u_dc, duty)
            mot = self.motor.operating_point(rpm, u_ac)
            inv = self.inverter.operating_point(u_dc, duty, mot["I"])

            if abs(i_dc - inv["i_dc"]) < tol:
                return self._assemble(duty, rpm, u_dc, mot, inv, iteration)
            i_dc = relaxation * inv["i_dc"] + (1 - relaxation) * i_dc

        raise NotConverged(
            f"duty={duty}, rpm={rpm}: i_dc still moving by "
            f"{abs(inv['i_dc'] - i_dc):.3g} A after {max_iter} passes")

    def _assemble(self, duty, rpm, u_dc, mot, inv, iterations):
        """Collect the converged result. Bookkeeping only, no new physics."""
        p_pack_loss = self.pack.p_loss(inv["i_dc"])
        p_pack_in = inv["p_dc"] + p_pack_loss

        return {
            "duty": duty,
            "rpm": rpm,
            "iterations": iterations,

            "u_dc": u_dc,
            "i_dc": inv["i_dc"],
            "u_ac": inv["u_ac"],
            "i_ac": mot["I"],

            "torque": mot["torque"],
            "omega": mot["omega"],
            "p_mech": mot["P_out"],

            "p_pack_in": p_pack_in,
            "p_pack_loss": p_pack_loss,
            "p_inverter_loss": inv["p_loss"],
            "p_motor_loss": mot["P_copper"] + mot["P_noload"],

            "eta_inverter": inv["eta"],
            "eta_motor": mot["eta"],
            "eta_total": mot["P_out"] / p_pack_in if p_pack_in > 0 else 0.0,

            "motor_over_current": mot["over_current"],
            "inverter_over_current": inv["over_current"],
        }

    def power_balance_error(self, point):
        return point["p_pack_in"] - (point["p_mech"]
                                     + point["p_pack_loss"]
                                     + point["p_inverter_loss"]
                                     + point["p_motor_loss"])

    def _require_propeller(self):
        if self.propeller is None:
            raise ValueError("no propeller attached: the mechanical loop cannot close")

    def torque_residual(self, duty, rpm, rho=1.225):
        """Leftover torque at this rpm. Positive means the shaft is still speeding up."""
        self._require_propeller()
        point = self.solve(duty, rpm)
        return point["torque"] - self.propeller.torque(rpm, rho)

    def _no_load_rpm(self, duty):
        """Upper bracket: the speed where back-EMF swallows the whole bus.

        Uses the unsagged pack voltage, so it always overshoots the true
        crossing. Overshooting is what makes it a valid bracket.
        """
        u_ac = self.inverter.ac_voltage(self.pack.terminal_voltage(0.0), duty)
        return (u_ac / self.motor.k_e) * 60.0 / (2.0 * math.pi)

    def solve_loaded(self, duty, rho=1.225, tol_rpm=1e-6, max_iter=200):
        """The rpm where motor torque equals propeller torque. Bisection.

        At rpm = 0 the motor makes stall torque and the propeller eats nothing,
        so the residual is positive. At no-load rpm the motor makes nothing and
        the propeller still eats, so it is negative. The crossing is trapped
        between the two ends and cannot escape.
        """
        self._require_propeller()
        lo, hi = 0.0, self._no_load_rpm(duty)
        mid = lo

        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            if hi - lo < tol_rpm:
                break
            if self.torque_residual(duty, mid, rho) > 0.0:
                lo = mid          # motor still winning, the answer is higher
            else:
                hi = mid
        else:
            raise NotConverged(
                f"duty={duty}: rpm bracket still {hi - lo:.3g} wide "
                f"after {max_iter} halvings")

        return self._with_propeller(self.solve(duty, mid), rho)

    def _with_propeller(self, point, rho):
        """Add the mechanical side to an electrical result. Bookkeeping only."""
        prop = self.propeller.operating_point(point["rpm"], rho)
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

    def shaft_power_error(self, point):
        """The motor's output and the propeller's input are the same watts."""
        return point["p_mech"] - point["prop_power"]

    def duty_for_thrust(self, thrust, rho=1.225, tol=1e-9, max_iter=200):
        """Invert the whole chain. Bisection again, this time on duty.

        Thrust rises monotonically with duty, so the same guessing game works.
        """
        self._require_propeller()
        if thrust <= 0.0:
            return 0.0

        ceiling = self.solve_loaded(1.0, rho)["thrust"]
        if thrust > ceiling:
            raise ThrustUnreachable(
                f"{thrust:.4g} N demanded, {ceiling:.4g} N available at full duty")

        lo, hi = 0.0, 1.0
        for _ in range(max_iter):
            mid = 0.5 * (lo + hi)
            if hi - lo < tol:
                return mid
            if self.solve_loaded(mid, rho)["thrust"] < thrust:
                lo = mid
            else:
                hi = mid

        raise NotConverged(
            f"thrust={thrust}: duty bracket still {hi - lo:.3g} wide "
            f"after {max_iter} halvings")

    # -------------------------------------------------------- mass & sizing
    def hover_thrust_for_mass(self, total_mass_kg, n_rotors=4, g=9.81):
        """Thrust required per rotor to hover an aircraft of given total mass.

        T_rotor = (total_mass * g) / n_rotors
        """
        return (total_mass_kg * g) / n_rotors

    def hover_power_for_mass(self, total_mass_kg, n_rotors=4, rho=1.225, g=9.81):
        """Solve hover operating point for one rotor carrying its share of total_mass.

        Returns the full loaded point dictionary.
        """
        thrust_req = self.hover_thrust_for_mass(total_mass_kg, n_rotors=n_rotors, g=g)
        duty = self.duty_for_thrust(thrust_req, rho=rho)
        point = self.solve_loaded(duty, rho=rho)
        point["thrust_demanded"] = thrust_req
        point["hover_mass_share_kg"] = total_mass_kg / n_rotors
        return point

    def battery_weight_penalty(self, dry_mass_kg, n_rotors=4, rho=1.225,
                               packaging_factor=1.10, g=9.81):
        """Quantify the power and loss penalties caused specifically by the battery weight.

        Compares:
        1. Base aircraft (dry mass only, assuming hypothetical zero-mass energy source)
        2. Real aircraft (dry mass + battery pack mass)

        Returns a dictionary showing:
        - battery_mass_kg: mass added by the battery
        - delta_hover_thrust_n: additional thrust per rotor needed to lift the battery
        - delta_p_electrical_w: extra DC electrical power needed due to battery weight (per rotor)
        - delta_p_pack_loss_w: extra heat in the pack due to the higher current
        - delta_p_motor_loss_w: extra copper/iron loss in the motor
        - total_vehicle_delta_power_w: total extra power across all n_rotors
        """
        pack_m = self.pack.mass_kg(packaging_factor)
        m_total = dry_mass_kg + pack_m

        pt_with_batt = self.hover_power_for_mass(m_total, n_rotors=n_rotors, rho=rho, g=g)
        pt_dry = self.hover_power_for_mass(dry_mass_kg, n_rotors=n_rotors, rho=rho, g=g)

        delta_p_dc = pt_with_batt["i_dc"] * pt_with_batt["u_dc"] - pt_dry["i_dc"] * pt_dry["u_dc"]
        delta_pack_loss = pt_with_batt["p_pack_loss"] - pt_dry["p_pack_loss"]
        delta_motor_loss = pt_with_batt["p_motor_loss"] - pt_dry["p_motor_loss"]
        delta_inv_loss = pt_with_batt["p_inverter_loss"] - pt_dry["p_inverter_loss"]
        delta_thrust = pt_with_batt["thrust"] - pt_dry["thrust"]

        return {
            "dry_mass_kg": dry_mass_kg,
            "battery_mass_kg": pack_m,
            "total_mass_kg": m_total,
            "battery_mass_fraction": pack_m / m_total,
            "delta_thrust_per_rotor_n": delta_thrust,
            "delta_p_dc_per_rotor_w": delta_p_dc,
            "delta_p_pack_loss_w": delta_pack_loss,
            "delta_p_motor_loss_w": delta_motor_loss,
            "delta_p_inverter_loss_w": delta_inv_loss,
            "total_vehicle_delta_power_w": delta_p_dc * n_rotors,
            "hover_point_with_battery": pt_with_batt,
            "hover_point_dry": pt_dry,
        }
