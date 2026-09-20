"""Tests for the time-stepping mission simulator."""

import pytest

from aether.model.cell import Cell_simple
from aether.model.inverter import Inverter
from aether.model.motor import Motor
from aether.model.pack import Pack
from aether.model.powertrain import Powertrain
from aether.model.propeller import Propeller
from aether.sim.simulator import Simulator


def make_powertrain():
    cell = Cell_simple(
        chemistry="NMC",
        capacity_ah=3.0,
        r_internal=0.020,
        u_full=4.2,
        u_empty=3.0,
        i_max=30.0,
    )
    pack = Pack(cell, n_series=6, n_parallel=2, r_wiring=0.010)
    inverter = Inverter(name="ESC", i_max=60.0, u_max=30.0, r_ds_on=0.005,
                        n_conducting=2, f_sw=16_000.0, e_sw=5e-5,
                        u_sw_ref=25.0, i_sw_ref=40.0)
    motor = Motor(name="drone motor", k_e=0.0106, R_phase=0.060, i_no_load=0.8,
                  pole_pairs=7, i_max=40.0, v_max=30.0)
    prop = Propeller(name="10x4.5", diameter_in=10.0, pitch_in=4.5, c_t=0.10, c_q=0.0075)
    return Powertrain(pack, inverter, motor, propeller=prop)


def test_simulator_demand_lookup():
    pt = make_powertrain()
    mission = [
        {"name": "hover", "duration_s": 10.0, "thrust_n": 3.0},
        {"name": "climb", "duration_s": 5.0, "thrust_n": 6.0},
    ]
    sim = Simulator(pt, mission, dt=1.0)

    assert sim.demand(0.0) == ("hover", 3.0)
    assert sim.demand(9.9) == ("hover", 3.0)
    assert sim.demand(10.0) == ("climb", 6.0)
    assert sim.demand(14.9) == ("climb", 6.0)
    assert sim.demand(15.0) == (None, None)


def test_simulator_step_advances_clock_and_discharges_pack():
    pt = make_powertrain()
    initial_soc = pt.pack.soc()
    mission = [{"name": "hover", "duration_s": 5.0, "thrust_n": 3.0}]
    sim = Simulator(pt, mission, dt=1.0)

    rec = sim.step()
    assert rec is not None
    assert rec["t"] == 0.0
    assert rec["phase"] == "hover"
    assert rec["thrust_demand"] == 3.0
    assert rec["soc"] == pytest.approx(initial_soc)
    assert sim.t == 1.0
    assert pt.pack.soc() < initial_soc
    assert len(sim.log) == 1


def test_simulator_runs_to_mission_completion():
    pt = make_powertrain()
    mission = [
        {"name": "hover", "duration_s": 3.0, "thrust_n": 2.5},
        {"name": "climb", "duration_s": 2.0, "thrust_n": 4.0},
    ]
    sim = Simulator(pt, mission, dt=1.0)
    summary = sim.run()

    assert summary["stopped_because"] == "MISSION_COMPLETED"
    assert summary["steps"] == 5
    assert summary["endurance_s"] == pytest.approx(4.0)
    assert summary["energy_wh"] > 0.0
    assert 0.0 < summary["soc_at_end"] < 1.0


def test_simulator_stops_on_thrust_unreachable():
    pt = make_powertrain()
    # 500 N is far beyond what a 10-inch propeller on a 6S pack can deliver
    mission = [{"name": "impossible_climb", "duration_s": 10.0, "thrust_n": 500.0}]
    sim = Simulator(pt, mission, dt=1.0)
    summary = sim.run()

    assert summary["stopped_because"] == "THRUST_UNREACHABLE"
    assert summary["steps"] == 0
