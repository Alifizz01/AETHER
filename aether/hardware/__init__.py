"""Hardware interface module for AETHER."""

from aether.hardware.interface import BenchInterface, SocketBenchClient
from aether.hardware.protocol import (
    ProtocolError,
    decode_ascii_command,
    decode_ascii_telemetry,
    decode_json_frame,
    encode_ascii_command,
    encode_ascii_telemetry,
    encode_json_frame,
)
from aether.hardware.emulator import SocketBenchServer, VirtualBench

__all__ = [
    "BenchInterface",
    "SocketBenchClient",
    "VirtualBench",
    "SocketBenchServer",
    "ProtocolError",
    "encode_ascii_command",
    "decode_ascii_command",
    "encode_ascii_telemetry",
    "decode_ascii_telemetry",
    "encode_json_frame",
    "decode_json_frame",
]
