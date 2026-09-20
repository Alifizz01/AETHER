import json
from pathlib import Path
import matplotlib.pyplot as plt

from aether.model import cell, inverter, motor, pack, powertrain, propeller
from aether.sim import simulator

project_path = Path(__file__).parent.parent 
mission_path = project_path / "missions" / "mission_demo.json"
result_path = project_path / "results"


def run_mission():
    with open(mission_path, "r", encoding="utf-8") as f:
        mission_data = json.load(f)

    motor_test = motor.Motor(**mission_data["motor"])
    inverter_test = inverter.Inverter(**mission_data["inverter"])
    cell_test = cell.Cell_simple(**mission_data["cell"])

    pack_cfg = dict(mission_data["pack"])
    pack_cfg.pop("name", None)
    pack_test = pack.Pack(cell=cell_test, **pack_cfg)

    propeller_test = propeller.Propeller(**mission_data["propeller"])
    
    powertrain_test = powertrain.Powertrain(
        pack=pack_test,
        inverter=inverter_test,
        motor=motor_test,
        propeller=propeller_test
    )
    
    mission_info = mission_data["mission"]
    phases = mission_info["phases"]
    dt = mission_info.get("dt", 1.0)
    
    sim = simulator.Simulator(powertrain=powertrain_test, mission=phases, dt=dt)
    summary = sim.run()
    
    summary_panel = (
        f"--- Mission Summary: {mission_info.get('name', 'Demo')} ---\n"
        f"Stop Reason:    {summary['stopped_because']}\n"
        f"Endurance:      {summary['endurance_s']:.1f} s ({summary['endurance_s']/60:.2f} min)\n"
        f"Energy Consumed:{summary['energy_wh']:.2f} Wh\n"
        f"Final SOC:      {summary['soc_at_end']*100:.1f} %\n"
        f"Final Duty:     {summary['duty_at_end']*100:.1f} %\n"
        f"Mean Total Eta: {summary['mean_eta']*100:.1f} %\n"
        f"Total Steps:    {summary['steps']}\n"
    )
    print(summary_panel)
    
    result_path.mkdir(parents=True, exist_ok=True)
    with open(result_path / "mission_demo_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    with open(result_path / "mission_demo_log.json", "w", encoding="utf-8") as f:
        json.dump(sim.log, f, indent=2)

    return sim, summary


def plot_mission(sim):
    log = sim.log
    if not log:
        print("No simulation records to plot.")
        return

    t_min = [r["t"] / 60.0 for r in log]
    u_dc = [r["u_dc"] for r in log]
    i_dc = [r["i_dc"] for r in log]
    duty = [r["duty"] * 100.0 for r in log]
    soc = [r["soc"] * 100.0 for r in log]
    thrust_demand = [r["thrust_demand"] for r in log]
    thrust_actual = [r["thrust"] for r in log]
    p_pack = [r["p_pack_loss"] for r in log]
    p_esc = [r["p_inverter_loss"] for r in log]
    p_motor = [r["p_motor_loss"] for r in log]

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))

    # Panel 1: DC Bus Voltage and Current
    color_v = "navy"
    ax1.plot(t_min, u_dc, color=color_v, lw=1.5, label="Bus Voltage (V)")
    ax1.set_ylabel("DC Voltage (V)", color=color_v)
    ax1.tick_params(axis="y", labelcolor=color_v)
    ax1.set_title("DC Bus: Voltage Sag & Current")
    ax1.grid(True, alpha=0.3)

    ax1_twin = ax1.twinx()
    color_i = "firebrick"
    ax1_twin.plot(t_min, i_dc, color=color_i, lw=1.5, label="DC Current (A)")
    ax1_twin.set_ylabel("DC Current (A)", color=color_i)
    ax1_twin.tick_params(axis="y", labelcolor=color_i)

    # Panel 2: Duty Cycle & Battery SOC
    ax2.plot(t_min, duty, color="darkorange", lw=1.5, label="Duty (%)")
    ax2.plot(t_min, soc, color="forestgreen", lw=1.5, ls="--", label="SOC (%)")
    ax2.set_ylabel("Percentage (%)")
    ax2.set_title("Throttle Demand & Battery State")
    ax2.legend(loc="best")
    ax2.grid(True, alpha=0.3)

    # Panel 3: Thrust Tracking (Demand vs Delivered)
    ax3.plot(t_min, thrust_demand, color="black", lw=1.5, ls=":", label="Demanded")
    ax3.plot(t_min, thrust_actual, color="royalblue", lw=1.5, alpha=0.8, label="Delivered")
    ax3.set_ylabel("Thrust (N)")
    ax3.set_xlabel("Time (min)")
    ax3.set_title("Rotor Thrust Tracking")
    ax3.legend(loc="best")
    ax3.grid(True, alpha=0.3)

    # Panel 4: Loss Breakdown
    ax4.plot(t_min, p_motor, color="purple", lw=1.5, label="Motor Loss")
    ax4.plot(t_min, p_esc, color="crimson", lw=1.5, label="Inverter Loss")
    ax4.plot(t_min, p_pack, color="darkgoldenrod", lw=1.5, label="Pack Loss")
    ax4.set_ylabel("Loss Power (W)")
    ax4.set_xlabel("Time (min)")
    ax4.set_title("Loss Distribution (Heat Generation)")
    ax4.legend(loc="best")
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    output_fig = result_path / "mission_demo_analysis.png"
    plt.savefig(output_fig, dpi=150)
    print(f"Plot saved to: {output_fig}")
    plt.close()


if __name__ == "__main__":
    sim, _ = run_mission()
    plot_mission(sim)
        
        
