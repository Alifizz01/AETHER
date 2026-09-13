import pytest
from aether.model.motor import Motor

def test_motor():
    # Create a  Motor instance with test parameters
    motor = Motor(name="Test Motor", k_e=0.1, R_phase=0.5, i_no_load=0.1, pole_pairs=4, i_max=40, v_max=48)
    
    # Test operating point at 1000 RPM and 24V terminal voltage
    result = motor.operating_point(rpm=1000, u_terminal=24)
    
    # Check that the results are as expected
    assert result["omega"] == pytest.approx(104.719755, rel=1e-5)  # 1000 RPM to rad/s
    assert result["e_back"] == pytest.approx(10.4719755, rel=1e-5)  # Back EMF
    assert result["v_drop"] == pytest.approx(13.5280245, rel=1e-5)  # Voltage drop   
    assert result["torque"] == pytest.approx(2.695605, rel=1e-5)  # Torque
    assert result["I"] == pytest.approx(27.056049, rel=1e-5)       # v_drop / R_phase = 13.528024 / 0.5
    assert result["P_out"] == pytest.approx(282.283085, rel=1e-5)      # torque * omega = 2.695605 * 104.719755
