import pytest

from aether.model.cell import Cell_simple
from aether.model.pack import Pack
from aether.model.bms import BMS


def make_bms(**kw):
    cell = Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=0.020,
                u_full=4.2, u_empty=3.3, i_max=30.0)
    pack = Pack(cell, n_series=6, n_parallel=2)
    defaults = dict(i_max_discharge=50.0, i_max_charge=15.0)
    defaults.update(kw)
    return BMS(pack, **defaults), pack


def test_measures_only_what_a_real_bms_can_read():
    bms, pack = make_bms()

    m = bms.measure(i_pack=0.0)

    assert m["u_pack"] == pytest.approx(25.2)     # 6 * 4.2
    assert m["u_cell"] == pytest.approx(4.2)
    assert m["temp_c"] == pytest.approx(25.0)     # no current, no heat

    # 20 A pack -> 10 A per cell -> 0.2 V drop per cell
    m = bms.measure(i_pack=20.0)
    assert m["u_cell"] == pytest.approx(4.0)
    assert m["u_pack"] == pytest.approx(24.0)


def test_estimator_never_sees_the_true_soc():
    """The BMS must guess. Start it wrong and it stays wrong."""
    bms, pack = make_bms(initial_soc_guess=0.80)

    assert pack.cell.soc == 1.0                   # truth
    assert bms.estimator.soc == 0.80              # the guess
    assert bms.estimation_error() == pytest.approx(-0.20)

    # run the real pack and the estimator through the same current.
    # coulomb counting has no feedback, so the initial error just persists.
    bms.update(i_pack=6.0, dt=60.0)
    pack.cell.discharge(3.0, 60.0)                # 6 A pack / 2 parallel
    assert bms.estimation_error() == pytest.approx(-0.20, abs=1e-9)


def test_coulomb_counting_matches_the_pack_when_started_correctly():
    bms, pack = make_bms()

    # 6 A pack for 1800 s = 3 A per cell for half an hour = 1.5 Ah of 3.0 Ah
    bms.update(i_pack=6.0, dt=1800.0)
    pack.cell.discharge(3.0, 1800.0)

    assert bms.estimator.soc == pytest.approx(0.5)
    assert bms.estimation_error() == pytest.approx(0.0, abs=1e-9)


def test_over_current_latches_and_opens_the_contactor():
    bms, pack = make_bms(i_max_discharge=50.0)

    status = bms.update(i_pack=60.0, dt=1.0)

    assert "OVER_CURRENT_DISCHARGE" in status["faults"]
    assert status["state"] == BMS.FAULT
    assert status["contactor_closed"] is False
    assert status["current_allowed"] == 0.0

    # a fault does not clear itself when the condition goes away
    status = bms.update(i_pack=10.0, dt=1.0)
    assert status["state"] == BMS.FAULT
    assert status["contactor_closed"] is False

    bms.reset_faults()
    status = bms.update(i_pack=10.0, dt=1.0)
    assert status["state"] == BMS.OK
    assert status["current_allowed"] == 50.0


def test_charge_current_limit_is_separate():
    bms, pack = make_bms(i_max_discharge=50.0, i_max_charge=15.0)
    pack.cell.soc = 0.5          # a full cell would trip OVER_VOLTAGE while charging

    assert bms.update(i_pack=-10.0, dt=1.0)["state"] == BMS.OK
    assert "OVER_CURRENT_CHARGE" in bms.update(i_pack=-20.0, dt=1.0)["faults"]


def test_under_voltage_trips():
    bms, pack = make_bms(u_cell_min=3.0)
    pack.cell.soc = 0.0                            # 3.3 V per cell open circuit

    # 60 A pack = 30 A per cell = 0.6 V drop -> 2.7 V per cell
    status = bms.update(i_pack=60.0, dt=1.0)

    assert "UNDER_VOLTAGE" in status["faults"]


def test_low_soc_warns_without_faulting():
    bms, pack = make_bms(soc_warn=0.20, initial_soc_guess=0.15)

    status = bms.update(i_pack=1.0, dt=1.0)

    assert status["state"] == BMS.WARNING
    assert status["contactor_closed"] is True      # warn, do not cut power mid-flight
    assert status["faults"] == []
