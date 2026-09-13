class Motor_analyser:
    def __init__(self, motor):
        self.motor = motor
        
    def sweep(self, rpm_range, u_terminal_range):
        results = []
        for rpm in rpm_range:
            for u_terminal in u_terminal_range:
                try:
                    result = self.motor.operating_point(rpm, u_terminal)
                    results.append({
                        "rpm": rpm,
                        "u_terminal": u_terminal,
                        **result
                    })
                except ValueError as e:
                    results.append({
                        "rpm": rpm,
                        "u_terminal": u_terminal,
                        "error": str(e)
                    })
        return results
    
    def power_balance_error(self, points):
        errors = []
        for point in points:
            if "P_in" not in point:
                continue          # a failed point has no numbers. skip it, do not score it 0.
            P_in = point["P_in"]
            P_out = point["P_out"]
            P_copper = point["P_copper"]
            P_noload = point["P_noload"]
            error = P_in - (P_out + P_copper + P_noload)
            errors.append({
                "rpm": point["rpm"],
                "u_terminal": point["u_terminal"],
                "power_balance_error": error
            })
        return errors
    
    def peak_efficiency(self, points):
        max_eta = 0
        best_point = None
        for point in points:
            eta = point.get("eta", 0)
            if eta > max_eta:
                max_eta = eta
                best_point = point
        return best_point
    
    