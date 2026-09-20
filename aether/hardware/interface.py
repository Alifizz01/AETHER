"""Abstract interface and client implementations for propulsion testbenches."""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import socket

from aether.hardware.protocol import (
    decode_ascii_telemetry,
    decode_json_frame,
    encode_ascii_command,
    encode_json_frame,
)


class BenchInterface(ABC):
    """Abstract base class for all testbench interfaces (virtual or physical)."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the testbench device."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect and put the bench into a safe idle state."""

    @abstractmethod
    def command_duty(self, duty: float, u_bus: float = 24.0) -> None:
        """Send duty throttle demand to the motor speed controller."""

    @abstractmethod
    def read_telemetry(self) -> Dict[str, float]:
        """Read latest synchronized measurement frame (u_bus, i_dc, rpm, temp_c)."""

    def command_and_read(self, duty: float, u_bus: float = 24.0) -> Dict[str, float]:
        """Convenience single-shot: send command, then read and return measurement."""
        self.command_duty(duty, u_bus=u_bus)
        return self.read_telemetry()


class SocketBenchClient(BenchInterface):
    """Client for TCP/IP socket connected benches (hardware bridge or emulator)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8888,
                 mode: str = "ascii", timeout: float = 2.0):
        self.host = host
        self.port = port
        self.mode = mode.lower()
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def connect(self) -> None:
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        self._sock = sock

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                # Command safe zero duty before disconnecting
                self.command_duty(0.0)
            except Exception:
                pass
            finally:
                self._sock.close()
                self._sock = None

    def command_duty(self, duty: float, u_bus: float = 24.0) -> None:
        if self._sock is None:
            raise ConnectionError("Not connected to testbench.")
        if self.mode == "ascii":
            data = encode_ascii_command(duty, u_bus=u_bus)
        else:
            data = encode_json_frame({"duty": duty, "u_bus": u_bus})
        self._sock.sendall(data)

    def read_telemetry(self) -> Dict[str, float]:
        if self._sock is None:
            raise ConnectionError("Not connected to testbench.")

        buffer = bytearray()
        while True:
            chunk = self._sock.recv(256)
            if not chunk:
                raise ConnectionError("Bench connection closed unexpectedly.")
            buffer.extend(chunk)
            if b"\n" in buffer:
                break

        line = bytes(buffer.split(b"\n")[0] + b"\n")
        if self.mode == "ascii":
            return decode_ascii_telemetry(line)
        return decode_json_frame(line)
