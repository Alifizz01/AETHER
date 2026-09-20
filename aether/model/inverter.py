"""Three-phase inverter, averaged over one PWM period.

The switch node can only sit at u_dc or at 0. You control the fraction of time
it sits up, the duty d. Averaging over a PWM period:

    u_ac = d * u_dc                 voltage scales down by d
    i_dc = d * i_ac                 current scales up by 1/d   (lossless)

Multiply those two and P_dc = P_ac exactly, which is the check that the
averaging was done right. An inverter is a transformer built from a switch.

With losses the DC side has to supply them too:

    i_dc = (u_ac * i_ac + P_loss) / u_dc

u_dc and i_ac are NOT attributes. The pack decides u_dc, the motor decides
i_ac, and both change every timestep. Only the hardware lives on the object.
"""


class Inverter:
    def __init__(self, name, i_max, u_max, r_ds_on=0.010, n_conducting=2,
                 f_sw=10_000.0, e_sw=1.0e-4, u_sw_ref=48.0, i_sw_ref=40.0):
        # --- what the inverter is (hardware) ---
        self.name = name
        self.i_max = i_max                # phase current limit (A)
        self.u_max = u_max                # bus voltage rating (V)

        # --- calibration knobs: fit these to bench data, do not trust datasheets ---
        self.r_ds_on = r_ds_on            # one device on-resistance (ohm)
        self.n_conducting = n_conducting  # devices carrying current at once (2 for six-step)
        self.f_sw = f_sw                  # switching frequency (Hz)
        self.e_sw = e_sw                  # bridge switching energy per cycle (J)
        self.u_sw_ref = u_sw_ref          # bus voltage e_sw was measured at (V)
        self.i_sw_ref = i_sw_ref          # phase current e_sw was measured at (A)

    def __repr__(self):
        return (f"Inverter({self.name}, i_max={self.i_max} A, "
                f"r_ds_on={self.r_ds_on} ohm, f_sw={self.f_sw/1000:.1f} kHz)")

    # ------------------------------------------------------------- conversion
    def ac_voltage(self, u_dc, duty):
        """AC voltage the motor sees, averaged over a PWM period."""
        self._check_duty(duty)
        return duty * u_dc

    output_voltage = ac_voltage

    # ------------------------------------------------------------------ losses
    def p_conduction(self, i_ac):
        """Ohmic loss in the devices that are switched on. Grows with I^2."""
        return self.n_conducting * i_ac ** 2 * self.r_ds_on

    def p_switching(self, u_dc, i_ac):
        """Loss from turning the devices on and off f_sw times a second.

        # simplification: switching energy scales linearly with bus voltage and
        # phase current from the reference point where e_sw was measured.
        # real E_on/E_off are mildly non-linear. good enough to fit a knob to.
        """
        return (self.f_sw * self.e_sw
                * (u_dc / self.u_sw_ref)
                * (abs(i_ac) / self.i_sw_ref))

    def p_loss(self, u_dc, i_ac):
        return self.p_conduction(i_ac) + self.p_switching(u_dc, i_ac)

    # ------------------------------------------------------------------- point
    def operating_point(self, u_dc, duty, i_ac):
        """Everything the inverter does at one instant.

        u_dc  comes from the pack, i_ac comes from the motor, duty is yours.
        """
        self._check_duty(duty)

        u_ac = duty * u_dc
        p_ac = u_ac * i_ac
        p_loss = self.p_loss(u_dc, i_ac)
        p_dc = p_ac + p_loss
        i_dc = p_dc / u_dc if u_dc > 0 else 0.0
        eta = p_ac / p_dc if p_dc > 0 else 0.0

        return {
            "u_ac": u_ac,
            "i_ac": i_ac,
            "i_dc": i_dc,
            "p_ac": p_ac,
            "p_dc": p_dc,
            "p_conduction": self.p_conduction(i_ac),
            "p_switching": self.p_switching(u_dc, i_ac),
            "p_loss": p_loss,
            "eta": eta,
            "over_current": self.over_current(i_ac),
            "over_voltage": u_dc > self.u_max,
        }

    # ------------------------------------------------------------------ limits
    def over_current(self, i_ac):
        """Reports, does not raise. The analysis layer decides what to do."""
        return abs(i_ac) > self.i_max

    @staticmethod
    def _check_duty(duty):
        if not 0.0 <= duty <= 1.0:
            raise ValueError(f"duty must be between 0 and 1, got {duty}")
