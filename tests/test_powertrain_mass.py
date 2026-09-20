"""Tests for powertrain mass scaling and battery weight penalty calculations."""

import pytest

from aether.model.cell import Cell_simple
from aether.model.inverter import Inverter
from aether.model.motor import Motor
from aether.model.pack import Pack
from aether.model.powertrain import Powertrain
from aether.model.propeller import Propeller


def make_powertrain():
    cell = Cell_simple(
        chemistry="NMC",
        capacity_ah=3.0,
        r_internal=0.020,
        u_full=4.2,
        u_empty=3.0,
        i_max=35.0,
        mass_kg=0.050,
    )
    pack = Pack(cell, n_series=6, n_parallel=2, r_wiring=0.010)
    inverter = Inverter(name="ESC", i_max=45.0, u_max=30.0, r_ds_on=0.005)
    motor = Motor(name="Motor", k_e=0.0106, R_phase=0.060, i_no_load=0.8,
                  pole_pairs=7, i_max=35.0, v_max=26.0)
    prop = Propeller(name="10x4.5", diameter_in=10.0, pitch_in=4.5, c_t=0.10, c_q=0.0075)
    return Powertrain(pack, inverter, motor, propeller=prop)


def test_hover_thrust_and_power_scales_with_mass():
    pt = make_powertrain()

    t_1kg = pt.hover_thrust_for_mass(1.0, n_rotors=4)
    t_2kg = pt.hover_thrust_for_mass(2.0, n_rotors=4)
    assert t_1kg == pytest.approx(9.81 / 4.0)
    assert t_2kg == pytest.approx(2.0 * t_1kg)

    p_1kg = pt.hover_power_for_mass(1.0, n_rotors=4)
    p_2kg = pt.hover_power_for_mass(2.0, n_rotors=4)

    # Heavier drone draws more current and requires higher throttle duty
    assert p_2kg["i_dc"] > p_1kg["i_dc"]
    assert p_2kg["duty"] > p_1kg["duty"]
    assert p_2kg["p_mech"] > p_1kg["p_mech"]


def test_battery_weight_penalty_isolates_added_losses():
    pt = make_powertrain()

    penalty = pt.battery_weight_penalty(dry_mass_kg=0.800, n_rotors=4)

    assert penalty["dry_mass_kg"] == 0.800
    assert penalty["battery_mass_kg"] == pytest.approx(12 * 0.050 * 1.10)
    assert penalty["total_mass_kg"] == pytest.approx(0.800 + penalty["battery_mass_kg"])

    # Extra thrust must match the battery weight divided by 4 rotors
    expected_delta_thrust = (penalty["battery_mass_kg"] * 9.81) / 4.0
    assert penalty["delta_thrust_per_rotor_n"] == pytest.approx(expected_delta_thrust, rel=1e-5)

    # Additional weight incurs strictly positive electrical and loss penalties
    assert penalty["delta_p_dc_per_rotor_w"] > 0.0
    assert penalty["delta_p_pack_loss_w"] > 0.0
    assert penalty["delta_p_motor_loss_w"] > 0.0
    assert penalty["total_vehicle_delta_power_w"] == pytest.approx(
        4.0 * penalty["delta_p_dc_per_rotor_w"]
    )
