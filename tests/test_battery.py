import pytest

from aether.model.cell import Cell_simple, Cell_advanced


def make_cell():
    # LiPo, 3.0 Ah, 20 mohm. Numbers chosen so the arithmetic is checkable by hand.
    return Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=0.020,
                u_full=4.2, u_empty=3.3, i_max=30.0)


def test_voltage_at_known_states():
    cell = make_cell()

    assert cell.u_ocv() == pytest.approx(4.2)                 # full
    assert cell.terminal_voltage(0.0) == pytest.approx(4.2)   # no load, no drop
    assert cell.terminal_voltage(10.0) == pytest.approx(4.0)  # 4.2 - 10 * 0.020

    cell.soc = 0.5
    assert cell.u_ocv() == pytest.approx(3.75)                # 3.3 + 0.5 * 0.9

    cell.soc = 0.0
    assert cell.u_ocv() == pytest.approx(3.3)                 # empty


def test_discharge_drains_and_clamps():
    cell = make_cell()

    # 1.5 A for 1800 s = 2700 As of 10800 As total = 0.25 of the capacity
    cell.discharge(1.5, 1800)
    assert cell.soc == pytest.approx(0.75)
    assert cell.u_ocv() == pytest.approx(3.975)               # 3.3 + 0.75 * 0.9

    # draining far past empty must stop at 0, not go negative
    cell.discharge(30.0, 10_000)
    assert cell.soc == 0.0
    assert cell.is_empty()

    # charging past full must stop at 1
    cell.discharge(-30.0, 10_000)
    assert cell.soc == 1.0


def test_coulomb_counting_round_trip():
    """Invariant: take charge out, put the same charge back, land where you started."""
    cell = make_cell()
    cell.soc = 0.6

    cell.discharge(2.0, 600)      # out
    cell.discharge(-2.0, 600)     # back in

    assert cell.soc == pytest.approx(0.6)


def test_heat_and_limits():
    cell = make_cell()

    assert cell.p_loss(10.0) == pytest.approx(2.0)            # 10^2 * 0.020
    # r_thermal is the calibration knob: 2 W * 0.1 degC/W = 0.2 degC rise
    assert cell.temperature(10.0, ambient_c=25.0) == pytest.approx(25.2)

    assert not cell.over_current(29.0)
    assert cell.over_current(31.0)
    assert cell.over_current(-31.0)                           # charging counts too


# ---------------------------------------------------------------- Cell_advanced

def make_table_cell():
    """NMC table from GAIA, soc as a fraction rather than percent."""
    soc = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    ocv = [2.50, 3.00, 3.30, 3.50, 3.65, 3.75, 3.85, 3.95, 4.05, 4.15, 4.20]
    return Cell_advanced(chemistry="NMC", capacity_ah=3.0, r_internal=0.020,
                         soc_points=soc, ocv_points=ocv, i_max=30.0)


def test_table_endpoints_become_u_full_and_u_empty():
    cell = make_table_cell()

    assert cell.u_empty == pytest.approx(2.50)
    assert cell.u_full == pytest.approx(4.20)


def test_table_hits_its_own_points_and_interpolates_between():
    cell = make_table_cell()

    cell.soc = 0.5
    assert cell.u_ocv() == pytest.approx(3.75)      # exactly a table point

    cell.soc = 0.45                                  # halfway between 3.65 and 3.75
    assert cell.u_ocv() == pytest.approx(3.70)


def test_table_captures_the_flat_middle_the_linear_model_misses():
    """The whole reason for the table: a real cell is not a straight line."""
    table = make_table_cell()
    linear = Cell_simple(chemistry="NMC", capacity_ah=3.0, r_internal=0.020,
                         u_full=4.20, u_empty=2.50, i_max=30.0)

    for c in (table, linear):
        c.soc = 0.5

    assert table.u_ocv() == pytest.approx(3.75)
    assert linear.u_ocv() == pytest.approx(3.35)     # 0.4 V too low
    assert table.u_ocv() - linear.u_ocv() > 0.3


def test_everything_else_is_inherited_unchanged():
    cell = make_table_cell()

    cell.soc = 0.5
    assert cell.terminal_voltage(10.0) == pytest.approx(3.55)   # 3.75 - 10*0.020
    assert cell.p_loss(10.0) == pytest.approx(2.0)
    cell.discharge(1.5, 1800)
    assert cell.soc == pytest.approx(0.25)


def test_a_bad_table_is_rejected_at_construction():
    good = dict(chemistry="NMC", capacity_ah=3.0, r_internal=0.020, i_max=30.0)

    with pytest.raises(ValueError):      # not increasing
        Cell_advanced(soc_points=[0.0, 0.5, 0.4], ocv_points=[3.0, 3.5, 4.0], **good)
    with pytest.raises(ValueError):      # length mismatch
        Cell_advanced(soc_points=[0.0, 1.0], ocv_points=[3.0, 3.5, 4.0], **good)
    with pytest.raises(ValueError):      # percent instead of fraction
        Cell_advanced(soc_points=[0.0, 100.0], ocv_points=[3.0, 4.2], **good)
