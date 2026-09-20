"""Binary and text wire protocols for the AETHER propulsion testbench.

Supports two framing modes:
1. ASCII / Serial: newline-terminated human-readable text frames (ideal for Arduino/STM32 serial)
     Command:   SET:DUTY=<float>,U_BUS=<float>\n
     Telemetry: TLM:U_BUS=<float>,I_DC=<float>,RPM=<float>,TEMP_C=<float>,STATUS=<int>\n
2. JSON-over-Socket / TCP: structured newline-delimited JSON payloads
"""

import json
import re

ASCII_CMD_PATTERN = re.compile(r"^SET:DUTY=([0-9.]+)(?:,U_BUS=([0-9.]+))?$")
ASCII_TLM_PATTERN = re.compile(
    r"^TLM:U_BUS=([0-9.]+),I_DC=([0-9.-]+),RPM=([0-9.]+),TEMP_C=([0-9.-]+),STATUS=([0-9]+)$"
)


class ProtocolError(ValueError):
    """Raised when wire data violates frame encoding or decoding rules."""


# ------------------------------------------------------------------ ASCII codec
def encode_ascii_command(duty: float, u_bus: float = 24.0) -> bytes:
    """Encode an actuator command to ASCII bytes."""
    if not (0.0 <= duty <= 1.0):
        raise ProtocolError(f"Duty must be within [0.0, 1.0], got {duty}")
    if u_bus < 0.0:
        raise ProtocolError(f"Bus voltage cannot be negative, got {u_bus}")
    return f"SET:DUTY={duty:.4f},U_BUS={u_bus:.2f}\n".encode("ascii")


def decode_ascii_command(raw_bytes: bytes) -> dict:
    """Parse raw incoming command bytes into a command dictionary."""
    text = raw_bytes.decode("ascii").strip()
    match = ASCII_CMD_PATTERN.match(text)
    if not match:
        raise ProtocolError(f"Malformed ASCII command frame: '{text}'")
    duty = float(match.group(1))
    u_bus = float(match.group(2)) if match.group(2) else 24.0
    return {"duty": duty, "u_bus": u_bus}


def encode_ascii_telemetry(u_bus: float, i_dc: float, rpm: float,
                           temp_c: float, status: int = 0) -> bytes:
    """Format measured bench telemetry into ASCII bytes."""
    return (f"TLM:U_BUS={u_bus:.2f},I_DC={i_dc:.3f},RPM={rpm:.1f},"
            f"TEMP_C={temp_c:.1f},STATUS={int(status)}\n").encode("ascii")


def decode_ascii_telemetry(raw_bytes: bytes) -> dict:
    """Decode raw telemetry bytes into a measurement dictionary."""
    text = raw_bytes.decode("ascii").strip()
    match = ASCII_TLM_PATTERN.match(text)
    if not match:
        raise ProtocolError(f"Malformed ASCII telemetry frame: '{text}'")
    return {
        "u_bus": float(match.group(1)),
        "i_dc": float(match.group(2)),
        "rpm": float(match.group(3)),
        "temp_c": float(match.group(4)),
        "status": int(match.group(5)),
    }


# ------------------------------------------------------------------- JSON codec
def encode_json_frame(payload: dict) -> bytes:
    """Serialize dictionary payload to newline-terminated JSON bytes."""
    return (json.dumps(payload) + "\n").encode("utf-8")


def decode_json_frame(raw_bytes: bytes) -> dict:
    """Parse newline-terminated JSON bytes into a dictionary."""
    try:
        return json.loads(raw_bytes.decode("utf-8").strip())
    except Exception as e:
        raise ProtocolError(f"Failed to decode JSON frame: {e}") from e
