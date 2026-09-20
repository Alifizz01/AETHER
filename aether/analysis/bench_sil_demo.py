"""Run SPEC-1 hardware validation against the virtual testbench or physical hardware."""

import json
from pathlib import Path

from aether.analysis import validate
from aether.hardware import SocketBenchClient, SocketBenchServer, VirtualBench
from aether.model import cell, inverter, motor, pack, powertrain, propeller

SPEC_PATH = Path(__file__).parent.parent / "missions" / "spec_1.json"
RESULTS_DIR = Path(__file__).parent.parent / "results"


def make_nominal_powertrain():
    """Build nominal AETHER powertrain model."""
    c = cell.Cell_simple("NMC", 3.0, 0.020, 4.2, 3.0, 35.0)
    p = pack.Pack(c, 6, 2, r_wiring=0.010)
    inv = inverter.Inverter("ESC", 45.0, 30.0, 0.005)
    m = motor.Motor("Motor", 0.0106, 0.060, 0.8, 7, 35.0, 26.0)
    prop = propeller.Propeller("10x4.5", 10.0, 4.5, 0.10, 0.0075)
    return powertrain.Powertrain(p, inv, m, prop)


def run_bench_campaign(bench_client, spec, config_name="B"):
    """Execute a sweep of SPEC-1 test points against the bench interface."""
    points = spec["scenario"]["points"]
    measurements = []

    for pt in points:
        duty = pt["duty"]
        u_bus = 24.0
        tlm = bench_client.command_and_read(duty, u_bus=u_bus)

        measurements.append({
            "id": pt["id"],
            "duty": duty,
            "u_bus": tlm["u_bus"],
            "i_dc": tlm["i_dc"],
            "p_dc": tlm["u_bus"] * tlm["i_dc"],
            "rpm": tlm["rpm"],
            "temp_c": tlm["temp_c"],
            "status": tlm.get("status", 0),
        })

    return measurements


def main():
    spec_file = SPEC_PATH
    spec = validate.load_spec(spec_file)
    pt = make_nominal_powertrain()

    # 1. Start virtual bench server (Software-in-the-Loop)
    server = SocketBenchServer(host="127.0.0.1", port=9050, mode="ascii")
    server.start()

    # 2. Connect client
    client = SocketBenchClient(host="127.0.0.1", port=9050, mode="ascii")
    client.connect()

    try:
        # Run test points against Config B
        print("Executing SPEC-1 test points across testbench interface...")
        measured_points = run_bench_campaign(client, spec, config_name="B")
    finally:
        client.disconnect()
        server.stop()

    # 3. Model predictions (frozen payload structure)
    predictions = []
    for pt_spec in spec["scenario"]["points"]:
        duty = pt_spec["duty"]
        solved = pt.solve_loaded(duty)
        predictions.append({
            "id": pt_spec["id"],
            "duty": duty,
            "i_dc": solved["i_dc"],
            "rpm": solved["rpm"],
            "u_bus": solved["u_dc"],
            "temp_c": 25.0,
            "p_dc": solved["i_dc"] * solved["u_dc"],
        })

    frozen_dict = {
        "spec_id": spec["_meta"]["id"],
        "model_fingerprint": "nominal_sil_v1",
        "predictions": predictions,
    }

    # 4. Run AETHER validation compare and report
    rows = validate.compare(frozen_dict, measured_points, spec, config="B")
    summary = validate.summary(rows)
    report_text = validate.format_report(rows, summary, spec, config="B")
    print(report_text)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = RESULTS_DIR / "sil_validation_report.txt"
    report_file.write_text(report_text, encoding="utf-8")
    print(f"\nReport written to: {report_file}")


if __name__ == "__main__":
    main()
