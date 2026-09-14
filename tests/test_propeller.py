import math

import pytest

from aether.model.propeller import Propeller


def make_prop():
    # a 10x4.5 hobby propeller. c_t and c_q are plausible placeholders,
    # to be replaced by UIUC data or bench measurement.
    return Propeller(name="10x4.5", diameter_in=10.0, pitch_in=4.5,
                     c_t=0.10, c_q=0.0075)


def test_inches_are_converted_once_and_stored_in_metres():
    prop = make_prop()

    assert prop.diameter == pytest.approx(0.254)      # 10 * 0.0254
    assert prop.pitch == pytest.approx(0.1143)
    assert prop.disk_area() == pytest.approx(math.pi * 0.127 ** 2)


def test_the_exponents_are_right():
    """The bug that made the old model useless. Pin every exponent."""
    prop = make_prop()

    assert prop.thrust(4000) / prop.thrust(2000) == pytest.approx(4.0)   # n^2
    assert prop.torque(4000) / prop.torque(2000) == pytest.approx(4.0)   # n^2
    assert prop.power(4000) / prop.power(2000) == pytest.approx(8.0)     # n^3


def test_torque_has_the_units_of_torque():
    """power = 2*pi*n*torque must hold exactly, by definition."""
    prop = make_prop()

    for rpm in (1000, 5000, 9000):
        omega = rpm * 2 * math.pi / 60
        assert prop.power(rpm) == pytest.approx(prop.torque(rpm) * omega)


def test_diameter_scales_thrust_as_d4_and_torque_as_d5():
    """Why a bigger propeller costs torque faster than it buys thrust."""
    small = Propeller("8in", 8.0, 4.0, c_t=0.10, c_q=0.0075)
    big = Propeller("16in", 16.0, 8.0, c_t=0.10, c_q=0.0075)

    assert big.thrust(3000) / small.thrust(3000) == pytest.approx(2 ** 4)
    assert big.torque(3000) / small.torque(3000) == pytest.approx(2 ** 5)


def test_rpm_for_thrust_inverts_thrust():
    prop = make_prop()

    for target in (1.0, 5.0, 12.0):
        rpm = prop.rpm_for_thrust(target)
        assert prop.thrust(rpm) == pytest.approx(target)

    assert prop.rpm_for_thrust(0.0) == 0.0


def test_thinner_air_needs_more_rpm_for_the_same_thrust():
    """Altitude. rho at roughly 3000 m is about 0.9 kg/m^3."""
    prop = make_prop()

    sea = prop.rpm_for_thrust(8.0, rho=1.225)
    high = prop.rpm_for_thrust(8.0, rho=0.900)

    assert high > sea
    assert prop.thrust(sea, rho=0.900) < 8.0


def test_figure_of_merit_is_dimensionless_and_scale_free():
    prop = make_prop()

    fm = prop.figure_of_merit(4000)
    assert 0.0 < fm < 1.0

    # FM depends on the coefficients, not on how fast you spin it
    assert prop.figure_of_merit(8000) == pytest.approx(fm)

    # a propeller needing less torque for the same thrust is better
    better = Propeller("same but efficient", 10.0, 4.5, c_t=0.10, c_q=0.0050)
    assert better.figure_of_merit(4000) > fm


def test_tip_speed_limit_reports_without_raising():
    prop = make_prop()      # 0.254 m, limit 240 m/s

    # tip speed = pi * D * n, so 240 m/s is at about 18000 rpm
    assert prop.tip_speed(18000) == pytest.approx(math.pi * 0.254 * 300.0)
    assert not prop.over_tip_speed(10000)
    assert prop.over_tip_speed(20000)

    assert prop.operating_point(20000)["over_tip_speed"] is True


def test_operating_point_matches_the_individual_methods():
    prop = make_prop()
    op = prop.operating_point(6000)

    assert op["thrust"] == pytest.approx(prop.thrust(6000))
    assert op["torque"] == pytest.approx(prop.torque(6000))
    assert op["power"] == pytest.approx(prop.power(6000))
