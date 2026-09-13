import pytest

from aether.model.motor import Motor
from aether.analysis.motor_analyser import Motor_analyser


def make_analyser():
    motor = Motor(name="Test Motor", k_e=0.1, R_phase=0.5, i_no_load=0.1,
                  pole_pairs=4, i_max=40, v_max=48)
    return Motor_analyser(motor)


def test_sweep_returns_one_point_per_combination():
    """Shape test: the sweep visits every (rpm, u) pair and labels each result."""
    analyser = make_analyser()
    rpm_range = [500, 1000, 1500]
    u_terminal_range = [12, 24, 36]

    results = analyser.sweep(rpm_range, u_terminal_range)

    assert len(results) == len(rpm_range) * len(u_terminal_range)
    for result in results:
        assert "rpm" in result
        assert "u_terminal" in result
        assert "omega" in result or "error" in result


def test_power_balance_closes_on_every_valid_point():
    """Invariant test: energy in must equal energy out plus every loss.

    This one does not need hand-calculated numbers. It must hold at every
    operating point, for any parameter values, or physics is missing.
    """
    analyser = make_analyser()
    points = analyser.sweep(range(200, 2000, 100), [24])

    valid = [p for p in points if "error" not in p]
    assert valid, "sweep produced no usable points"

    worst = max(abs(e["power_balance_error"])
                for e in analyser.power_balance_error(valid))
    assert worst < 1e-9, f"power balance off by {worst:.6f} W, a loss term is missing"
