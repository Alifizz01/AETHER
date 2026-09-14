# AETHER

**Electric propulsion modelling, pre-sizing and hardware validation.**

Sibling framework to [GAIA](https://github.com/Alifizz01/GAIA). GAIA models the energy
source. AETHER models what it drives.

> In Greek cosmogony Gaia is the earth and Aether is the upper air. Same family,
> different element.

Started 2026-09-11.

---

## The chain

```
   PACK  -->  INVERTER  -->  MOTOR  -->  PROPELLER
   (DC)       (DC->AC)      (AC->Nm)     (load)
     ^                                       |
     +-------- POWERTRAIN solves the loop ---+
                        BMS watches
```

Give it one number, the duty, and it returns everything else:

```python
pt = Powertrain(pack, inverter, motor, propeller=prop)
pt.solve_loaded(duty=0.6)      # -> rpm, thrust, torque, currents, losses, efficiency
pt.duty_for_thrust(4.0)        # -> the duty a perfect controller would hold
```

Each block answers one question about itself. `Powertrain` is the only thing that knows
they are connected, and it solves for the point where all of them agree.

## Status

| Module | State |
|---|---|
| `model/cell.py` | done. Rint cell, linear or measured OCV table |
| `model/pack.py` | done. s/p scaling, wiring resistance, sag, energy |
| `model/motor.py` | done. steady-state PMSM, back-EMF, losses |
| `model/inverter.py` | done. PWM-averaged, conduction + switching losses |
| `model/bms.py` | done. estimation, protection, latching faults |
| `model/powertrain.py` | done. electrical and mechanical loops both solved |
| `model/propeller.py` | done. coefficient model, thrust/torque/FM/tip speed |
| `analysis/validate.py` | done. freeze, compare, bias vs scatter |
| `scenario/spec_1.json` | draft. bench correlation spec, 5 requirements |

74 tests passing.

## Quick start

```
pip install -e .
python -m pytest tests -q

python aether/analysis/capacity_demo.py      # why capacity is not the OCV curve
python aether/analysis/load_types_demo.py    # constant R vs constant I vs constant P
python aether/analysis/inverter_analyser.py  # inverter loss split over a sweep
```

## Layout

```
aether/
  model/      physics. one module per block. returns numbers, never draws.
  analysis/   sweeps, checks and figures. imports model, never the reverse.
  scenario/   missions, bench specs and test points. Phase 2 lives here.
tests/        one runnable check per piece of logic
data/         OCV tables as JSON, five chemistries. no loader yet: read the
              _provenance block before trusting a number
data/raw/     bench measurements, Phase 3, gitignored
figures/      generated PNGs, gitignored because they are reproducible
```

Two rules keep it from rotting:

- **Compute in `model/`, draw in `analysis/`.** A model class never imports matplotlib.
- **Every non-trivial piece of logic leaves a runnable check behind.** Prefer invariants
  (power balance, coulomb round trip) over hand-calculated values. They hold at every
  operating point and they have already caught three real bugs.

## Phases

1. **Model** the chain end to end. Torque-speed demand in, currents, losses and
   temperature rise out.
2. **Pre-size** from a mission profile: climb, cruise, reserve for an electric aircraft.
   Trade-offs stated explicitly, not one answer.
3. **Validate** against a real motor on the bench and quantify where the model is wrong.
4. **Automate** the characterisation: configure, sweep, log, pass/fail, report.

## Safety, not optional

- **Under 60 V DC.** No high-voltage traction setup at home.
- **Motor clamped, no propeller.** Brake or fan load only.
- LiPo charged in a fireproof bag, never unattended.
- Current sensing on the DC bus before anything spins.

## Rules for this repo

- **Never claim anything the code does not do.** This project exists to be evidence.
- Numbers in any write-up come from an actual run, not an estimate.
- Physical models keep a **calibration knob** exposed. Real hardware is not ideal.
- Deliberate simplifications carry a comment naming the ceiling, for example
  `# simplification: no thermal mass, valid for steady operating points`.
- Keep the GAIA licence and attribution consistent with the parent project.
