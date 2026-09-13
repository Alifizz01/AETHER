import math

class Motor:
    def __init__(self, name, k_e, R_phase, i_no_load, pole_pairs, i_max, v_max,
                 r_thermal=0.5):
        self.name = name
        self.k_e = k_e  # Back EMF constant (V/rad/s)
        self.R_phase = R_phase  # Phase resistance (Ohms)
        self.i_no_load = i_no_load  # No-load current (A)
        self.pole_pairs = pole_pairs  # Number of pole pairs
        self.i_max = i_max  # Maximum current (A)
        self.v_max = v_max  # Maximum voltage (V)
        self.k_t = self.k_e  # Torque constant (Nm/A), assuming k_t = k_e for simplicity
        self.r_thermal = r_thermal  # thermal resistance to ambient (degC/W). measure this.
        self.broken_flag = False  # Flag to indicate if the motor is broken
        
    def __str__(self):
        return f"Motor(name={self.name}, k_e={self.k_e}, R_phase={self.R_phase}, i_no_load={self.i_no_load}, pole_pairs={self.pole_pairs}, i_max={self.i_max}, v_max={self.v_max})"
            
    def flag_broken(self):
        self.broken_flag = True
    
    def operating_point(self, rpm, u_terminal):
        # Convert RPM to rad/s
        omega = rpm * 2 * math.pi / 60
        
        # Calculate back EMF
        e_back = self.k_e * omega
        
        # Calculate the voltage drop across the phase resistance
        v_drop = u_terminal - e_back
        
        I = (u_terminal - e_back) / self.R_phase
        
        # Calculate the torque produced by the motor
        torque = self.k_t * (I - self.i_no_load)
        
        # Check if the current exceeds the maximum current
        over_current = I > self.i_max   # report, do not raise. the analysis layer judges.
        
        P_in = u_terminal * I  # Input power (W)
        P_out = torque * omega  # Output power (W)
        P_copper = I**2 * self.R_phase  # Copper losses (W)
        P_noload = self.k_t * self.i_no_load * omega  # friction + iron losses (W)
        eta = P_out / P_in if P_in > 0 else 0  # Efficiency
                
        return {
            "omega": omega,
            "e_back": e_back,
            "v_drop": v_drop,
            "torque": torque,
            "P_in": P_in,
            "P_out": P_out,
            "P_copper": P_copper,
            "P_noload": P_noload,
            "eta": eta,
            "I": I,
            "over_current": over_current
        }
        
    def thermal_model(self, I, ambient_temp=25):
        # Simple thermal model: temperature rise is proportional to I^2 * R_phase
        # simplification: no thermal mass, so this jumps straight to the final value.
        power_loss = I**2 * self.R_phase  # Power loss in watts
        temp_rise = power_loss * self.r_thermal  # Temperature rise in °C
        motor_temp = ambient_temp + temp_rise  # Total motor temperature in °C
        return motor_temp
