"""Tests for testbench wire protocol, virtual hardware emulator, and client-server socket interface."""

import pytest
import time

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
from aether.hardware.interface import SocketBenchClient


def test_ascii_command_codec():
    raw = encode_ascii_command(0.45, u_bus=24.5)
    assert raw.endswith(b"\n")
    parsed = decode_ascii_command(raw)
    assert parsed["duty"] == pytest.approx(0.45)
    assert parsed["u_bus"] == pytest.approx(24.5)

    with pytest.raises(ProtocolError):
        encode_ascii_command(1.5)  # Out of range

    with pytest.raises(ProtocolError):
        decode_ascii_command(b"INVALID:DATA\n")


def test_ascii_telemetry_codec():
    raw = encode_ascii_telemetry(u_bus=23.45, i_dc=12.345, rpm=8120.0, temp_c=34.5, status=0)
    assert raw.endswith(b"\n")
    parsed = decode_ascii_telemetry(raw)
    assert parsed["u_bus"] == pytest.approx(23.45)
    assert parsed["i_dc"] == pytest.approx(12.345)
    assert parsed["rpm"] == pytest.approx(8120.0)
    assert parsed["temp_c"] == pytest.approx(34.5)
    assert parsed["status"] == 0


def test_json_frame_codec():
    data = {"duty": 0.6, "command": "sweep", "values": [1, 2, 3]}
    encoded = encode_json_frame(data)
    assert encoded.endswith(b"\n")
    decoded = decode_json_frame(encoded)
    assert decoded == data


def test_virtual_bench_direct_physics_and_noise():
    bench = VirtualBench(seed=123)
    bench.connect()

    # At zero duty, motor does not spin, zero current
    bench.command_duty(0.0, u_bus=24.0)
    tlm_zero = bench.read_telemetry()
    assert tlm_zero["rpm"] == 0.0
    assert tlm_zero["i_dc"] == 0.0

    # At 50% duty, motor spins, draws current, bus sags
    bench.command_duty(0.5, u_bus=24.0)
    tlm_half = bench.read_telemetry()
    assert tlm_half["rpm"] > 4000.0
    assert tlm_half["i_dc"] > 1.0
    assert tlm_half["u_bus"] < 24.0  # Sag observed!

    # At higher duty, RPM, current and temperature rise
    bench.command_duty(0.8, u_bus=24.0)
    tlm_high = bench.read_telemetry()
    assert tlm_high["rpm"] > tlm_half["rpm"]
    assert tlm_high["i_dc"] > tlm_half["i_dc"]
    assert tlm_high["temp_c"] >= tlm_half["temp_c"]

    bench.disconnect()


def test_virtual_bench_fault_injection():
    bench = VirtualBench(seed=123)
    bench.connect()

    bench.command_duty(0.5, u_bus=24.0)
    bench.inject_fault("OPEN_CIRCUIT")
    tlm = bench.read_telemetry()
    assert tlm["status"] != 0
    assert tlm["i_dc"] == 0.0
    assert tlm["rpm"] == 0.0

    bench.inject_fault("NONE")
    tlm_restored = bench.read_telemetry()
    assert tlm_restored["status"] == 0
    assert tlm_restored["rpm"] > 0.0


def test_socket_client_server_sil_loop():
    # Spin up virtual bench server on loopback
    server = SocketBenchServer(host="127.0.0.1", port=9998, mode="ascii")
    server.start()
    time.sleep(0.05)

    client = SocketBenchClient(host="127.0.0.1", port=9998, mode="ascii")
    client.connect()

    try:
        # Command 0.40 duty through TCP socket to emulator
        tlm = client.command_and_read(0.40, u_bus=25.0)
        assert "u_bus" in tlm
        assert "i_dc" in tlm
        assert "rpm" in tlm
        assert tlm["rpm"] > 3000.0
        assert tlm["i_dc"] > 0.0
    finally:
        client.disconnect()
        server.stop()
