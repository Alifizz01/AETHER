# Nomenclature

Every symbol used in AETHER: what it is called, its unit, and the variable name in the code.

German terms are given where the word differs enough to be worth knowing.

---

## Power electronics

| Symbol | Name | Unit | In code | What it is |
|---|---|---|---|---|
| `U_dc` | DC bus voltage (Zwischenkreisspannung) | V | `u_dc` | What the pack presents to the inverter, after sag |
| `u_ac` | AC-side voltage, DC-bus equivalent | V | `u_ac` | The averaged voltage the motor effectively sees |
| `d` | **duty cycle** (Tastverhältnis) | — | — | Fraction of one switching period the switch is ON. Varies every period |
| `m` | **modulation index** | — | `duty` | Amplitude of the sine the duty traces. This is the throttle. Constant over an electrical cycle |
| `f_sw` | switching frequency (Schaltfrequenz) | Hz | `f_sw` | How often the transistor chops. 8 to 48 kHz on hobby ESCs |
| `T_sw` | switching period | s | — | `1 / f_sw`. 62.5 µs at 16 kHz |
| `R_DS(on)` | drain-source on-resistance | ohm | `r_ds_on` | Resistance of one MOSFET while conducting. Milliohms |
| `E_sw` | switching energy | J | `e_sw` | Energy burned in one on-off transition. Needs its test conditions to be usable |
| `n_cond` | devices conducting at once | — | `n_conducting` | 2 for six-step, 3 for sinusoidal. NOT 6, which is the device count |
| `t_dead` | dead time (Verriegelungszeit) | s | — | Deliberate gap so both switches in a leg are never on together |
| `L` | inductance (Induktivität) | H | — | Resists a change in current. In a motor it is the winding itself |
| `X_L` | inductive reactance | ohm | — | `2·pi·f·L`. Not modelled: the averaged model only sees resistance |

## Battery

| Symbol | Name | Unit | In code | What it is |
|---|---|---|---|---|
| `soc` | **state of charge** (Ladezustand) | 0 to 1 | `soc` | Fraction of usable charge remaining. Cannot be measured directly |
| `soh` | state of health | 0 to 1 | — | Capacity remaining relative to when new. Ages over hundreds of cycles |
| `u_ocv` | **open-circuit voltage** (Leerlaufspannung) | V | `u_ocv` | What the chemistry offers. Depends on `soc` only. Measurable only at rest |
| `u_term` | terminal voltage (Klemmenspannung) | V | `u_terminal` | What a multimeter reads at the terminals, under load |
| `r_int` | internal resistance (Innenwiderstand) | ohm | `r_internal` | Unavoidable resistance inside the cell. Tens of milliohms |
| `r_wiring` | wiring resistance | ohm | `r_wiring` | Busbars, connectors, fuse, lead. 10 to 20 mohm on a small pack |
| `C` | capacity (Kapazität) | Ah | `capacity_ah` | How much charge the cell holds. The only thing that converts amps into minutes |
| `s` | cells in series | count | `n_series` | Series adds volts |
| `p` | cells in parallel | count | `n_parallel` | Parallel adds amps |
| `sag` | voltage sag (Spannungseinbruch) | V | `sag()` | `I · r_pack`. Instantaneous and reversible. Not the same as SOC falling |
| `C-rate` | charge or discharge rate | 1/h | — | Current divided by capacity. 3 Ah at 30 A is 10 C |
| `r_th` | thermal resistance | degC/W | `r_thermal` | How many degrees it heats up per watt of loss |

## Motor

| Symbol | Name | Unit | In code | What it is |
|---|---|---|---|---|
| `Kv` | **velocity constant** (Drehzahlkonstante) | rpm/V | — | Datasheet number: no-load rpm per volt. Loosely measured, treat as an estimate |
| `k_e` | **back-EMF constant** | V·s/rad | `k_e` | Volts generated per rad/s of speed. `k_e = 60 / (2·pi·Kv)` |
| `k_t` | **torque constant** (Drehmomentkonstante) | Nm/A | `k_t` | Newton-metres per amp. **Numerically identical to `k_e` in SI units** |
| `E` | **back-EMF** (Gegen-EMK) | V | `e_back` | `k_e · omega`. The voltage the motor generates by spinning. Opposes the supply |
| `R_ph` | phase resistance (Wicklungswiderstand) | ohm | `R_phase` | Resistance of the copper winding. Where the heat comes from |
| `I` | phase current | A | `I`, `i_ac` | Current in the motor winding. Sets torque |
| `i_0` | no-load current (Leerlaufstrom) | A | `i_no_load` | Current eaten by bearings, air drag and iron before any torque reaches the shaft |
| `omega` | angular velocity (Winkelgeschwindigkeit) | rad/s | `omega` | `rpm · 2·pi / 60`. Every physics formula wants this, not rpm |
| `n` | rotational speed (Drehzahl) | rpm | `rpm` | The human unit |
| `T` | torque (Drehmoment) | Nm | `torque` | Force times radius at the shaft |
| `T_stall` | stall torque (Stillstandsmoment) | Nm | — | Maximum possible torque, at zero speed, producing zero power |
| `n_0` | no-load speed (Leerlaufdrehzahl) | rpm | — | `u / k_e`. Back-EMF has grown to swallow the whole supply |
| `p` | **pole pairs** (Polpaare) | count | `pole_pairs` | Magnet north-south pairs on the rotor. Magnets divided by two |
| `N` | turns per slot (Windungszahl) | count | — | How many times the wire loops through one slot |
| `B` | magnetic flux density (Flussdichte) | T (tesla) | — | Field strength in the air gap. 0.8 to 1.2 T for neodymium |
| `L_act` | active length | m | — | Length of wire actually inside the field. The iron stack length, not the total wire |
| `r` | radius to the slot | m | — | The lever arm from shaft centre to the copper |
| `sigma` | magnetic shear stress | Pa | — | Tangential force per unit rotor surface. `T ~ 2·sigma·V_rotor` |
| `eta` | efficiency (Wirkungsgrad) | 0 to 1 | `eta` | `P_out / P_in` |

### Motor parts

| Term | German | What it is |
|---|---|---|
| stator | Stator / Ständer | The part that does not move. Holds the copper in a PMSM |
| rotor | Rotor / Läufer | The part that spins. Holds the magnets in a PMSM |
| slot | **Nut** | The notch in the iron. The empty space the copper fills |
| tooth | **Zahn** | The iron left between two slots. Carries the flux |
| yoke | **Joch** | The ring of iron behind the slots, completing the magnetic circuit |
| air gap | **Luftspalt** | The sub-millimetre space between stator and rotor |
| end winding | Wickelkopf | Copper turning round outside the field. Resistance with no torque: pure loss |
| star point | Sternpunkt | Where the three phases join. Floats at the bus midpoint |

## Propeller

| Symbol | Name | Unit | In code | What it is |
|---|---|---|---|---|
| `c_T` | thrust coefficient | — | `c_t` | Dimensionless. From UIUC data, the manufacturer, or your bench |
| `c_Q` | torque coefficient | — | `c_q` | Dimensionless. Sets how hard the propeller resists |
| `D` | diameter | m | `diameter` | **Sold in inches.** Convert once: 1 in = 0.0254 m |
| `pitch` | pitch (Steigung) | m | `pitch` | How far one revolution would advance in a solid. Also sold in inches |
| `rho` | air density (Luftdichte) | kg/m³ | `rho` | 1.225 at sea level. Falls with altitude, so thrust falls too |
| `n` | revolutions per second | 1/s | — | `rpm / 60`. **The coefficient equations want this, not rad/s and not rpm** |
| `A` | disk area | m² | `disk_area()` | `pi·D²/4`. The area the blades sweep |
| `FM` | figure of merit | 0 to 1 | `figure_of_merit` | Ideal hover power divided by actual. Real propellers manage 0.6 to 0.8 |
| `J` | advance ratio | — | — | `V / (n·D)`. Zero in hover. Not modelled: static coefficients only |

## Powers

| Symbol | Name | Unit | In code | What it is |
|---|---|---|---|---|
| `P_in` | input power | W | `P_in`, `p_pack_in` | What you pay: `U · I` |
| `P_out` | output power | W | `P_out`, `p_mech` | What the shaft delivers: `T · omega` |
| `P_cu` | copper loss (Kupferverlust) | W | `P_copper` | `I² · R`. Grows with current squared |
| `P_0` | no-load loss | W | `P_noload` | `k_t · i_0 · omega`. Friction and iron. Grows with speed |
| `P_cond` | conduction loss (Durchlassverlust) | W | `p_conduction` | In the inverter devices while they conduct |
| `P_sw` | switching loss (Schaltverlust) | W | `p_switching` | Energy burned in each transition, times the frequency |

## Numerical

| Symbol | Name | In code | What it is |
|---|---|---|---|
| `alpha` | relaxation factor | `relaxation` | Fraction of each correction actually taken. 0.5 stops the loop ringing |
| `tol` | tolerance | `tol` | How close counts as converged |
| — | fixed point | — | A value that survives the machine unchanged: `x = f(x)` |
| — | bisection | — | Halve the bracket repeatedly. Slow, and cannot diverge |

---

## Symbol collisions, because they are unavoidable

The same letter means different things in different fields. Read the context.

| Letter | Could mean |
|---|---|
| `T` | torque (Nm), period (s), or tesla (the unit of `B`) |
| `n` | rotational speed in rpm, OR revolutions per second in propeller equations, OR a count |
| `p` | pole pairs, OR cells in parallel |
| `J` | rotor inertia (kg·m²), OR propeller advance ratio (dimensionless) |
| `L` | inductance (H), OR active conductor length (m) |
| `I` | current (A), OR second moment of area in mechanics |

In this repo: `n_parallel` and `pole_pairs` are always written out, and `rpm` is never called `n`.

---

## The two identities worth memorising

```
k_e = k_t            same number in SI units. Both reduce to joules per amp.
                     One drill-and-scope measurement gives you both.

k_e = 60 / (2*pi*Kv) converts the datasheet number into the physics one.
                     900 Kv  ->  0.01061 V·s/rad
```
