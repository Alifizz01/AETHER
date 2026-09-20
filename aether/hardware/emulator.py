"""Realistic synthetic testbench emulator.

Simulates real physical bench phenomena:
1. Physical response (settling time, torque-speed equilibrium)
2. Gaussian measurement noise (shunt current noise, optical tachometer jitter)
3. Sensor calibration offsets and thermal drift (resistance rising with temp)
4. ADC quantization (12-bit voltage and current ADC)
5. Fault injection (broken wire, overheated motor, stuck sensor)
6. Network socket server interface for real-time SiL (Software-in-the-Loop)
"""

import math
import random
import socket
import threading
from typing import Dict, Optional

from aether.hardware.interface import BenchInterface
from aether.hardware.protocol import (
    decode_ascii_command,
    decode_json_frame,
    encode_ascii_telemetry,
    encode_json_frame,
)


class VirtualBench(BenchInterface):
    """Direct in-process emulator of the propulsion testbench."""

    def __init__(
        self,
        # Nominal physical parameters (slightly offset from model constants to test validation)
        k_e: float = 0.0104,          # true back-EMF constant (~2% lower than nominal 0.0106)
        r_phase_20c: float = 0.063,   # true phase resistance at 20 degC (5% higher)
        r_internal_pack: float = 0.065, # true pack internal resistance
        c_q: float = 0.0077,          # true prop torque coefficient
        # Instrumentation tolerances & noise
        noise_i_dc_std: float = 0.08, # Amps RMS noise on shunt
        noise_rpm_std: float = 6.0,   # RPM RMS jitter on optical sensor
        noise_v_std: float = 0.02,    # Volts RMS noise on bus
        adc_bits: int = 12,           # 12-bit ADC quantization
        v_full_scale: float = 30.0,
        i_full_scale: float = 50.0,
        temp_ambient: float = 22.0,
        seed: Optional[int] = 42,
    ):
        self.k_e = k_e
        self.r_phase_20c = r_phase_20c
        self.r_internal_pack = r_internal_pack
        self.c_q = c_q

        self.noise_i_dc_std = noise_i_dc_std
        self.noise_rpm_std = noise_rpm_std
        self.noise_v_std = noise_v_std
        self.adc_v_lsb = v_full_scale / (2 ** adc_bits)
        self.adc_i_lsb = i_full_scale / (2 ** adc_bits)

        self.temp_ambient = temp_ambient
        self.motor_temp = temp_ambient

        self._duty = 0.0
        self._u_bus_source = 24.0
        self._is_connected = False
        self._fault_mode = "NONE"

        if seed is not None:
            self._rng = random.Random(seed)
        else:
            self._rng = random.Random()

    def connect(self) -> None:
        self._is_connected = True

    def disconnect(self) -> None:
        self._duty = 0.0
        self._is_connected = False

    def inject_fault(self, fault_type: str) -> None:
        """Inject faults: 'NONE', 'OPEN_CIRCUIT', 'OVER_TEMPERATURE', 'STUCK_TACH'."""
        self._fault_mode = fault_type.upper()

    def command_duty(self, duty: float, u_bus: float = 24.0) -> None:
        if not self._is_connected:
            raise ConnectionError("VirtualBench: Cannot command duty while disconnected.")
        self._duty = max(0.0, min(1.0, float(duty)))
        self._u_bus_source = float(u_bus)

    def _quantize(self, value: float, lsb: float) -> float:
        return round(value / lsb) * lsb

    def read_telemetry(self) -> Dict[str, float]:
        if not self._is_connected:
            raise ConnectionError("VirtualBench: Cannot read telemetry while disconnected.")

        if self._fault_mode == "OPEN_CIRCUIT":
            return {
                "u_bus": self._u_bus_source,
                "i_dc": 0.0,
                "rpm": 0.0,
                "temp_c": self.temp_ambient,
                "status": 1,  # Fault flag
            }

        duty = self._duty
        u_source = self._u_bus_source

        if duty <= 1e-4:
            # Idle motor at rest
            u_meas = self._quantize(
                u_source + self._rng.gauss(0, self.noise_v_std), self.adc_v_lsb
            )
            return {
                "u_bus": u_meas,
                "i_dc": 0.0,
                "rpm": 0.0,
                "temp_c": self.temp_ambient,
                "status": 0,
            }

        # Copper resistance increases with temperature: alpha = +0.00393 / K
        temp_coeff = 0.00393
        delta_t = max(0.0, self.motor_temp - 20.0)
        r_phase = self.r_phase_20c * (1.0 + temp_coeff * delta_t)

        # Equilibrium solver inside the real physics bench:
        # Find RPM where motor torque == prop torque (including sag)
        rho = 1.225
        D = 10.0 * 0.0254

        # Bisection to find true settling rpm on hardware
        lo, hi = 0.0, (duty * u_source / self.k_e) * 60.0 / (2.0 * math.pi)
        mid_rpm = lo
        for _ in range(40):
            mid_rpm = 0.5 * (lo + hi)
            omega = mid_rpm * 2.0 * math.pi / 60.0
            n_rev_sec = mid_rpm / 60.0

            e_back = self.k_e * omega
            # Instantaneous bus with sag
            i_est = max(0.0, (duty * u_source - e_back) / r_phase)
            i_dc_est = duty * i_est
            u_bus_sag = u_source - i_dc_est * self.r_internal_pack

            u_ac = duty * u_bus_sag
            i_motor = max(0.0, (u_ac - e_back) / r_phase)
            t_motor = self.k_e * max(0.0, i_motor - 0.8)
            t_prop = self.c_q * rho * (n_rev_sec ** 2) * (D ** 5)

            if t_motor > t_prop:
                lo = mid_rpm
            else:
                hi = mid_rpm

        settled_rpm = mid_rpm
        omega_settled = settled_rpm * 2.0 * math.pi / 60.0
        e_back_settled = self.k_e * omega_settled
        u_bus_final = u_source
        i_dc_final = 0.0

        # Refine current with sag
        for _ in range(10):
            u_ac = duty * u_bus_final
            i_motor = max(0.0, (u_ac - e_back_settled) / r_phase)
            i_dc_final = duty * i_motor + 0.15  # 150mA ESC quiescent loss
            u_bus_final = u_source - i_dc_final * self.r_internal_pack

        # Thermal dissipation: motor heating
        p_loss_motor = (i_motor ** 2) * r_phase
        self.motor_temp = self.temp_ambient + p_loss_motor * 0.5

        if self._fault_mode == "OVER_TEMPERATURE":
            self.motor_temp = 125.0

        # Apply realistic instrumentation noise & quantization
        u_bus_noisy = self._quantize(
            u_bus_final + self._rng.gauss(0, self.noise_v_std), self.adc_v_lsb
        )
        i_dc_noisy = self._quantize(
            max(0.0, i_dc_final + self._rng.gauss(0, self.noise_i_dc_std)), self.adc_i_lsb
        )
        rpm_noisy = max(0.0, settled_rpm + self._rng.gauss(0, self.noise_rpm_std))
        if self._fault_mode == "STUCK_TACH":
            rpm_noisy = 0.0

        temp_noisy = round(self.motor_temp + self._rng.gauss(0, 0.2), 1)

        return {
            "u_bus": u_bus_noisy,
            "i_dc": i_dc_noisy,
            "rpm": round(rpm_noisy, 1),
            "temp_c": temp_noisy,
            "status": 0 if self._fault_mode == "NONE" else 2,
        }


class SocketBenchServer:
    """Runs VirtualBench behind a real TCP server socket for Software-in-the-Loop."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8888,
                 mode: str = "ascii", bench: Optional[VirtualBench] = None):
        self.host = host
        self.port = port
        self.mode = mode.lower()
        self.bench = bench or VirtualBench()
        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> None:
        self.bench.connect()
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(1)
        self._running = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
            self._server_sock = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.bench.disconnect()

    def _serve_loop(self) -> None:
        while self._running:
            try:
                conn, _ = self._server_sock.accept()
            except Exception:
                break
            with conn:
                buffer = bytearray()
                while self._running:
                    try:
                        chunk = conn.recv(256)
                    except (ConnectionResetError, ConnectionAbortedError, OSError):
                        break
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    while b"\n" in buffer:
                        line, _, remaining = buffer.partition(b"\n")
                        buffer = bytearray(remaining)
                        if not line:
                            continue

                        # Handle command frame
                        if self.mode == "ascii":
                            cmd = decode_ascii_command(bytes(line + b"\n"))
                        else:
                            cmd = decode_json_frame(bytes(line + b"\n"))

                        self.bench.command_duty(cmd["duty"], u_bus=cmd.get("u_bus", 24.0))
                        tlm = self.bench.read_telemetry()

                        # Send response frame
                        if self.mode == "ascii":
                            resp = encode_ascii_telemetry(
                                u_bus=tlm["u_bus"],
                                i_dc=tlm["i_dc"],
                                rpm=tlm["rpm"],
                                temp_c=tlm["temp_c"],
                                status=tlm["status"],
                            )
                        else:
                            resp = encode_json_frame(tlm)
                        conn.sendall(resp)
