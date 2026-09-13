import pytest

from aether.model.cell import Cell_simple
from aether.model.pack import Pack


def make_cell():
    return Cell_simple(chemistry="LiPo", capacity_ah=3.0, r_internal=0.020,
                       u_full=4.2, u_empty=3.3, i_max=30.0)


def test_series_adds_volts_parallel_adds_amps():
    pack = Pack(make_cell(), n_series=6, n_parallel=2)

    assert pack.u_ocv() == pytest.approx(25.2)          # 6 * 4.2
    assert pack.capacity_ah() == pytest.approx(6.0)     # 2 * 3.0
    assert pack.i_max == pytest.approx(60.0)            # 2 * 30
    assert pack.cell_current(20.0) == pytest.approx(10.0)


def test_pack_resistance_is_cells_times_s_over_p():
    pack = Pack(make_cell(), n_series=6, n_parallel=2)

    assert pack.r_internal() == pytest.approx(0.060)    # 0.020 * 6 / 2

    # 20 A pack -> 10 A per cell -> 0.2 V per cell -> 1.2 V total
    assert pack.terminal_voltage(20.0) == pytest.approx(24.0)
    assert pack.sag(20.0) == pytest.approx(1.2)
    assert pack.sag(20.0) == pytest.approx(20.0 * pack.r_internal())


def test_wiring_resistance_adds_on_top():
    plain = Pack(make_cell(), n_series=6, n_parallel=2)
    wired = Pack(make_cell(), n_series=6, n_parallel=2, r_wiring=0.015)

    assert wired.r_internal() == pytest.approx(0.075)   # 0.060 + 0.015
    # 20 A over the extra 15 mohm is another 0.3 V
    assert wired.terminal_voltage(20.0) == pytest.approx(plain.terminal_voltage(20.0) - 0.3)
    # and its own heat: 20^2 * 0.015 = 6 W on top
    assert wired.p_loss(20.0) == pytest.approx(plain.p_loss(20.0) + 6.0)


def test_loss_equals_sag_times_current():
    """Invariant: every volt of sag times the current is heat, and nothing else."""
    pack = Pack(make_cell(), n_series=6, n_parallel=2, r_wiring=0.015)

    for i in (0.0, 5.0, 20.0, 55.0):
        assert pack.p_loss(i) == pytest.approx(pack.sag(i) * i, abs=1e-12)


def test_discharge_drains_the_shared_cell():
    pack = Pack(make_cell(), n_series=6, n_parallel=2)

    # 6 A pack for 1800 s = 3 A per cell for half an hour = half of 3.0 Ah
    pack.discharge(6.0, 1800.0)

    assert pack.soc() == pytest.approx(0.5)
    assert pack.u_ocv() == pytest.approx(6 * 3.75)      # 3.3 + 0.5 * 0.9
    assert not pack.is_empty()


def test_energy_matches_the_hand_number_for_a_linear_cell():
    pack = Pack(make_cell(), n_series=6, n_parallel=2)

    # linear OCV averages (4.2 + 3.3) / 2 = 3.75 V per cell
    # 6 * 3.75 * 6.0 Ah = 135 Wh
    assert pack.energy_wh() == pytest.approx(135.0, rel=1e-3)
    assert pack.soc() == 1.0                            # soc restored afterwards


def test_bad_wiring_is_rejected():
    with pytest.raises(ValueError):
        Pack(make_cell(), n_series=0)
    with pytest.raises(ValueError):
        Pack(make_cell(), n_parallel=2.5)
    with pytest.raises(ValueError):
        Pack(make_cell(), r_wiring=-0.01)
