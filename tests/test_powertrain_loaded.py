import pytest

from aether.model.cell import Cell_simple
from aether.model.pack import Pack
from aether.model.inverter import Inverter
from aether.model.motor import Motor
from aether.model.propeller import Propeller
from aether.model.powertrain import Powertrain, ThrustUnreachable


def make_powertrain(c_q=0.0075, n_series=6, soc=1.0):
    cell = Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=0.020,
                       u_full=4.2, u_empty=3.3, i_max=30.0, soc=soc)
    pack = Pack(cell, n_series=n_series, n_parallel=2)
    inv = Inverter(name="ESC", i_max=60.0, u_max=30.0, r_ds_on=0.005,
                   n_conducting=2, f_sw=16_000.0, e_sw=5e-5,
                   u_sw_ref=25.0, i_sw_ref=40.0)
    mot = Motor(name="drone motor", k_e=0.0106, R_phase=0.060, i_no_load=0.8,
                pole_pairs=7, i_max=60.0, v_max=30.0)
    prop = Propeller(name="10x4.5", diameter_in=10.0, pitch_in=4.5,
                     c_t=0.10, c_q=c_q)
    return Powertrain(pack, inv, mot, propeller=prop)


def test_the_torques_balance_at_the_solution():
    """The definition of the operating point. If this fails, nothing else means anything."""
    pt = make_powertrain()

    for duty in (0.3, 0.5, 0.7, 0.9, 1.0):
        point = pt.solve_loaded(duty)
        assert point["torque"] == pytest.approx(point["prop_torque"], rel=1e-6)
        assert abs(point["torque_residual"]) < 1e-6


def test_shaft_power_is_the_same_seen_from_either_side():
    """Invariant: at the crossing the motor's output IS the propeller's input."""
    pt = make_powertrain()

    for duty in (0.4, 0.6, 0.8, 1.0):
        point = pt.solve_loaded(duty)
        assert abs(pt.shaft_power_error(point)) < 1e-6


def test_electrical_power_balance_still_closes_with_the_prop_attached():
    pt = make_powertrain()

    for duty in (0.3, 0.6, 0.9):
        point = pt.solve_loaded(duty)
        assert abs(pt.power_balance_error(point)) < 1e-9


def test_more_duty_gives_more_rpm_thrust_and_current():
    pt = make_powertrain()
    points = [pt.solve_loaded(d) for d in (0.3, 0.5, 0.7, 0.9)]

    for a, b in zip(points, points[1:]):
        assert b["rpm"] > a["rpm"]
        assert b["thrust"] > a["thrust"]
        assert b["i_dc"] > a["i_dc"]


def test_a_heavier_propeller_settles_at_lower_rpm():
    """More load torque, same motor: the crossing moves left."""
    light = make_powertrain(c_q=0.0050).solve_loaded(0.8)
    heavy = make_powertrain(c_q=0.0150).solve_loaded(0.8)

    assert heavy["rpm"] < light["rpm"]
    assert heavy["torque"] > light["torque"]     # and it demands more torque there


def test_zero_duty_does_not_spin():
    pt = make_powertrain()
    point = pt.solve_loaded(0.0)

    assert point["rpm"] == 0.0
    assert point["thrust"] == pytest.approx(0.0)


def test_duty_for_thrust_round_trips():
    pt = make_powertrain()

    for target in (1.0, 3.0, 5.0):
        duty = pt.duty_for_thrust(target)
        assert 0.0 < duty < 1.0
        assert pt.solve_loaded(duty)["thrust"] == pytest.approx(target, rel=1e-6)


def test_unreachable_thrust_is_duty_saturation_not_a_bug():
    pt = make_powertrain()
    ceiling = pt.solve_loaded(1.0)["thrust"]

    with pytest.raises(ThrustUnreachable):
        pt.duty_for_thrust(ceiling * 1.5)


def test_a_drained_pack_needs_more_duty_for_the_same_thrust():
    """The whole reason duty is not fixed during a flight."""
    full = make_powertrain(soc=1.0)
    low = make_powertrain(soc=0.2)

    target = 4.0
    duty_full = full.duty_for_thrust(target)
    duty_low = low.duty_for_thrust(target)

    assert duty_low > duty_full
    # and it costs more current to hold the same thrust on a sagged pack
    assert low.solve_loaded(duty_low)["i_dc"] > full.solve_loaded(duty_full)["i_dc"]


def test_without_a_propeller_the_loaded_solver_refuses():
    cell = Cell_simple("LiPo", 3.0, 0.020, 4.2, 3.3, 30.0)
    pt = Powertrain(Pack(cell, 6, 2),
                    Inverter("ESC", 60.0, 30.0),
                    Motor("m", 0.0106, 0.060, 0.8, 7, 60.0, 30.0))

    with pytest.raises(ValueError, match="no propeller"):
        pt.solve_loaded(0.5)
