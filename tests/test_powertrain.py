import pytest

from aether.model.cell import Cell_simple
from aether.model.pack import Pack
from aether.model.inverter import Inverter
from aether.model.motor import Motor
from aether.model.powertrain import Powertrain


def make_powertrain(r_internal=0.020):
    cell = Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=r_internal,
                u_full=4.2, u_empty=3.3, i_max=30.0)
    pack = Pack(cell, n_series=6, n_parallel=2)                 # 25.2 V full
    inv = Inverter(name="ESC", i_max=60.0, u_max=30.0, r_ds_on=0.005,
                   n_conducting=2, f_sw=16_000.0, e_sw=5e-5,
                   u_sw_ref=25.0, i_sw_ref=40.0)
    mot = Motor(name="drone motor", k_e=0.0106, R_phase=0.060, i_no_load=0.8,
                pole_pairs=7, i_max=60.0, v_max=30.0)
    return Powertrain(pack, inv, mot)


def test_solver_converges_and_the_pack_actually_sags():
    pt = make_powertrain()

    point = pt.solve(duty=0.8, rpm=8000)

    assert point["iterations"] < 20
    assert point["u_dc"] < 25.2                 # loaded pack sits below open circuit
    assert point["i_dc"] > 0
    assert point["torque"] > 0


def test_power_balance_closes_across_the_whole_chain():
    """Invariant: pack chemistry output = shaft power + every loss in between."""
    pt = make_powertrain()

    for duty in (0.3, 0.5, 0.7, 0.9, 1.0):
        for rpm in (2000, 5000, 8000, 11000):
            point = pt.solve(duty=duty, rpm=rpm)
            assert abs(pt.power_balance_error(point)) < 1e-9, (duty, rpm)


def test_a_stiffer_pack_buys_torque_and_costs_efficiency():
    """Counterintuitive but correct, and worth locking down.

    A stiffer pack sags less, so the motor sees more voltage, so it pulls more
    current and makes more torque. But at FIXED rpm, efficiency falls as
    current rises: copper loss goes as I^2 while useful power goes as I. So the
    stiff pack wins on torque and pack loss, and loses on efficiency.
    Comparing at fixed rpm is comparing two different operating points.
    """
    soft = make_powertrain(r_internal=0.050).solve(duty=0.45, rpm=8000)
    stiff = make_powertrain(r_internal=0.005).solve(duty=0.45, rpm=8000)

    assert not soft["motor_over_current"] and not stiff["motor_over_current"]

    # what the stiff pack wins
    assert stiff["u_dc"] > soft["u_dc"]
    assert stiff["torque"] > soft["torque"]
    assert stiff["p_pack_loss"] < soft["p_pack_loss"]

    # what it costs, because more current at the same speed
    assert stiff["i_ac"] > soft["i_ac"]
    assert stiff["eta_motor"] < soft["eta_motor"]


def test_total_efficiency_is_the_product_of_the_stages():
    pt = make_powertrain()
    point = pt.solve(duty=0.7, rpm=7000)

    eta_pack = point["p_mech"] / point["p_pack_in"] / (
        point["eta_inverter"] * point["eta_motor"])

    assert 0.0 < point["eta_total"] < 1.0
    assert 0.0 < eta_pack <= 1.0                # the leftover factor is the pack's own
    assert point["eta_total"] == pytest.approx(
        eta_pack * point["eta_inverter"] * point["eta_motor"])


def test_zero_duty_produces_no_torque_and_no_current():
    pt = make_powertrain()

    point = pt.solve(duty=0.0, rpm=0)

    assert point["u_ac"] == pytest.approx(0.0)
    assert point["i_ac"] == pytest.approx(0.0)
    assert point["torque"] == pytest.approx(-0.0106 * 0.8)   # only the no-load drag
