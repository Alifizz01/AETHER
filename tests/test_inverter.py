import pytest

from aether.model.inverter import Inverter


def make_inverter():
    # e_sw quoted at its reference point, so the scaling factors are 1.0 there.
    return Inverter(name="Test ESC", i_max=40.0, u_max=48.0, r_ds_on=0.010,
                    n_conducting=2, f_sw=10_000.0, e_sw=1.0e-4,
                    u_sw_ref=48.0, i_sw_ref=40.0)


def test_voltage_and_current_scale_by_duty():
    inv = make_inverter()

    assert inv.ac_voltage(48.0, 0.5) == pytest.approx(24.0)
    assert inv.ac_voltage(48.0, 1.0) == pytest.approx(48.0)
    assert inv.ac_voltage(48.0, 0.0) == pytest.approx(0.0)


def test_losses_at_the_reference_point():
    inv = make_inverter()

    # conduction: 2 * 40^2 * 0.010 = 32.0 W
    assert inv.p_conduction(40.0) == pytest.approx(32.0)
    # switching at the reference point: 10000 * 1e-4 * 1.0 * 1.0 = 1.0 W
    assert inv.p_switching(48.0, 40.0) == pytest.approx(1.0)
    # half the bus voltage, half the current -> a quarter of the switching loss
    assert inv.p_switching(24.0, 20.0) == pytest.approx(0.25)

    assert inv.p_loss(48.0, 40.0) == pytest.approx(33.0)


def test_power_balance_closes():
    """Invariant: the DC side supplies the AC side plus every loss."""
    inv = make_inverter()

    for duty in (0.1, 0.25, 0.5, 0.75, 1.0):
        for i_ac in (1.0, 10.0, 25.0, 40.0):
            op = inv.operating_point(u_dc=48.0, duty=duty, i_ac=i_ac)
            assert op["p_dc"] == pytest.approx(op["p_ac"] + op["p_loss"], abs=1e-12)
            assert op["p_dc"] == pytest.approx(op["i_dc"] * 48.0, abs=1e-12)
            assert op["p_loss"] == pytest.approx(
                op["p_conduction"] + op["p_switching"], abs=1e-12)


def test_lossless_case_reduces_to_the_textbook_result():
    """With no losses, i_dc must equal duty * i_ac exactly."""
    ideal = Inverter(name="ideal", i_max=100.0, u_max=48.0,
                     r_ds_on=0.0, e_sw=0.0)

    op = ideal.operating_point(u_dc=48.0, duty=0.5, i_ac=40.0)

    assert op["u_ac"] == pytest.approx(24.0)
    assert op["i_dc"] == pytest.approx(20.0)      # 0.5 * 40
    assert op["eta"] == pytest.approx(1.0)


def test_limits_report_and_duty_is_validated():
    inv = make_inverter()

    assert not inv.over_current(39.0)
    assert inv.over_current(41.0)

    op = inv.operating_point(u_dc=60.0, duty=0.5, i_ac=41.0)
    assert op["over_current"] and op["over_voltage"]

    with pytest.raises(ValueError):
        inv.operating_point(u_dc=48.0, duty=1.5, i_ac=10.0)
    with pytest.raises(ValueError):
        inv.ac_voltage(48.0, -0.1)
