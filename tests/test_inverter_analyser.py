import pytest

from aether.model.inverter import Inverter
from aether.analysis.inverter_analyser import InverterAnalyser


def make_analyser():
    inv = Inverter(name="Test ESC", i_max=40.0, u_max=48.0, r_ds_on=0.010,
                   n_conducting=2, f_sw=10_000.0, e_sw=1.0e-4,
                   u_sw_ref=48.0, i_sw_ref=40.0)
    return InverterAnalyser(inv)


def test_sweep_visits_every_combination():
    an = make_analyser()
    duties = [0.25, 0.5, 0.75]
    currents = [10.0, 20.0]

    points = an.sweep(48.0, duties, currents)

    assert len(points) == len(duties) * len(currents)
    assert {p["duty"] for p in points} == set(duties)


def test_sweep_accepts_scalars():
    an = make_analyser()
    assert len(an.sweep(48.0, 0.5, 20.0)) == 1


def test_power_balance_closes_across_the_sweep():
    """Invariant: no hand-calculated numbers, must hold everywhere."""
    an = make_analyser()
    points = an.sweep(48.0, [0.1, 0.3, 0.5, 0.7, 0.9, 1.0], [1.0, 5.0, 20.0, 40.0])

    assert an.power_balance_error(points) < 1e-9


def test_peak_efficiency_is_a_real_point():
    an = make_analyser()
    points = an.sweep(48.0, [0.1, 0.5, 1.0], [5.0, 20.0, 40.0])

    best = an.peak_efficiency(points)

    assert 0.0 < best["eta"] < 1.0
    assert best in points
    # highest duty and lowest current wastes the least, relatively
    assert best["duty"] == 1.0


def test_loss_split_adds_up():
    an = make_analyser()
    points = an.sweep(48.0, [0.5], [10.0, 30.0])

    split = an.loss_split(points)
    total = sum(p["p_loss"] for p in points)

    assert split["p_conduction"] + split["p_switching"] == pytest.approx(total)
    assert 0.0 <= split["conduction_share"] <= 1.0


def test_within_limits_drops_the_illegal_points():
    an = make_analyser()
    points = an.sweep(48.0, [0.5], [10.0, 41.0])   # 41 A is over i_max = 40

    assert len(points) == 2
    assert len(an.within_limits(points)) == 1
