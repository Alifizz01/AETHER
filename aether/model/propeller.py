"""A propeller, on the standard non-dimensional coefficient model.

    n = rpm / 60                        revolutions per SECOND
    thrust = c_t * rho * n^2 * D^4      N
    torque = c_q * rho * n^2 * D^5      Nm
    power  = 2*pi*n*torque ~ n^3        W

c_t and c_q are dimensionless and come from the UIUC propeller database, the
manufacturer's performance files, or your own bench. They are calibration
knobs, not constants of nature.

Note the exponents: thrust goes as D^4, torque as D^5. A bigger propeller
costs torque faster than it buys thrust, which is why large aircraft gear down.

For the powertrain this class is the LOAD LINE. torque ~ rpm^2 crosses the
motor's falling torque-speed line at exactly one point, and that crossing is
where the shaft settles.

# simplification: STATIC coefficients, advance ratio J = 0. Valid for hover and
# for a clamped bench test. In forward flight J = V/(n*D) rises and c_t falls,
# so the cruise leg of a mission needs c_t(J) and c_q(J) as tables.
"""

import math

INCH_TO_M = 0.0254


class Propeller:
    def __init__(self, name, diameter_in, pitch_in, c_t, c_q,
                 tip_speed_max=240.0):
        # --- geometry. converted once, stored in metres ---
        self.name = name
        self.diameter_in = diameter_in          # as sold, e.g. 10 for a "10x4.5"
        self.pitch_in = pitch_in
        self.diameter = diameter_in * INCH_TO_M     # m
        self.pitch = pitch_in * INCH_TO_M           # m

        # --- calibration knobs: measure these or look them up per propeller ---
        self.c_t = c_t                          # thrust coefficient, dimensionless
        self.c_q = c_q                          # torque coefficient, dimensionless

        # roughly Mach 0.7 at sea level. above it the blade tip loses efficiency
        # and gets very loud.
        self.tip_speed_max = tip_speed_max      # m/s

    def __repr__(self):
        return (f"Propeller({self.name}, {self.diameter_in:g}x{self.pitch_in:g} in, "
                f"c_t={self.c_t}, c_q={self.c_q})")

    # --------------------------------------------------------------- geometry
    def disk_area(self):
        """Swept area of the disk (m^2)."""
        return math.pi * (self.diameter / 2.0) ** 2

    @staticmethod
    def _rps(rpm):
        """Revolutions per second. The coefficient model is defined on n, not omega."""
        return rpm / 60.0

    # ---------------------------------------------------------------- physics
    def thrust(self, rpm, rho=1.225):
        return self.c_t * rho * self._rps(rpm) ** 2 * self.diameter ** 4

    def torque(self, rpm, rho=1.225):
        """What the motor has to supply. This is the load line."""
        return self.c_q * rho * self._rps(rpm) ** 2 * self.diameter ** 5

    def power(self, rpm, rho=1.225):
        return 2.0 * math.pi * self._rps(rpm) * self.torque(rpm, rho)

    def rpm_for_thrust(self, thrust, rho=1.225):
        """Invert the thrust law. Closed form, because thrust goes as n^2."""
        if thrust <= 0:
            return 0.0
        n = math.sqrt(thrust / (self.c_t * rho * self.diameter ** 4))
        return n * 60.0

    # ----------------------------------------------------------------- limits
    def tip_speed(self, rpm):
        """Speed of the blade tip through the air (m/s)."""
        return math.pi * self.diameter * self._rps(rpm)

    def over_tip_speed(self, rpm):
        """Reports, does not raise. The analysis layer decides what to do."""
        return self.tip_speed(rpm) > self.tip_speed_max

    # ---------------------------------------------------------------- quality
    def figure_of_merit(self, rpm, rho=1.225):
        """How close this propeller gets to the theoretical best, 0 to 1.

        Momentum theory says the least power that can possibly produce thrust T
        on a disk of area A is

            P_ideal = T^1.5 / sqrt(2 * rho * A)

        FM is that divided by the power actually needed. Real propellers manage
        roughly 0.6 to 0.8. Computed, never assigned.
        """
        t = self.thrust(rpm, rho)
        p = self.power(rpm, rho)
        if t <= 0 or p <= 0:
            return 0.0
        p_ideal = t ** 1.5 / math.sqrt(2.0 * rho * self.disk_area())
        return p_ideal / p

    # ------------------------------------------------------------------ point
    def operating_point(self, rpm, rho=1.225):
        """Everything at one rpm. Same shape as Motor and Inverter: the
        independent variable goes in, a dict comes out."""
        return {
            "rpm": rpm,
            "rho": rho,
            "thrust": self.thrust(rpm, rho),
            "torque": self.torque(rpm, rho),
            "power": self.power(rpm, rho),
            "tip_speed": self.tip_speed(rpm),
            "figure_of_merit": self.figure_of_merit(rpm, rho),
            "over_tip_speed": self.over_tip_speed(rpm),
        }
