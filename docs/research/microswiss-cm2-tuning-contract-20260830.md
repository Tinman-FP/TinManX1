# Micro Swiss CM2 Tuning Contract

Date: 2026-08-30

## Installed hardware boundary

TinManX1 treats nozzle construction and melt-zone capability as separate facts.

| Machine | Installed nozzle contract | TinMan volume type |
| --- | --- | --- |
| Bambu Lab X1 Carbon | Micro Swiss FlowTech CHT CM2 | High Flow |
| Creality K2 Plus | Micro Swiss FlowTech CHT CM2 | High Flow |
| Elegoo Centauri Carbon | Micro Swiss CM2, standard geometry | Standard |
| Prusa CORE One L | Micro Swiss CM2, standard geometry | Standard |
| Qidi X-Plus 4 / QidiMaxEz | Micro Swiss CM2, standard geometry | Standard |
| RatRig V-Core 4 IDEX | Micro Swiss CM2, standard geometry | Standard |
| Sovol SV08 MAX | Micro Swiss CM2, standard geometry | Standard |
| FibreSeek Seeker 3 polymer nozzle | Micro Swiss CM2, standard geometry | Standard |
| Bambu Lab H2D | Native Bambu high-flow hardware | High Flow |
| Snapmaker U1 | Native Snapmaker hardware | Standard |

`CM2` identifies the copper-chromium-zirconium body, hardened M2 tip, nickel
plating and WS2 coating. It does not, by itself, identify a high-flow melt
zone. The RepRap V6 CM2 product makes no high-flow claim. FlowTech CHT is the
split-flow product, while HighFlow Volcano is a separate long-nozzle geometry.
No Volcano capability is assigned to another machine without an installed
hardware confirmation.

## Evidence and derived limit

Micro Swiss's controlled FlowTech test used Protopasta HT-PLA at 220 C, a
0.4 mm nozzle, 0.30 mm layers and 0.50 mm line width. Its visible-defect
thresholds were:

- Standard plated brass reference: 22.2 mm3/s
- FlowTech CHT high flow: 34.0 mm3/s
- Same-test improvement: 1.53x

Orca recommends reducing a maximum-volumetric-flow failure point by 10-20% for
production. Applying the conservative 20% margin to the CHT result gives
27.2 mm3/s, or 1.23x the standard reference failure point. This is evidence for
a guarded process-speed opportunity, not permission to assign 27.2 mm3/s to
every material. Polymer chemistry, temperature, nozzle diameter, extruder and
part geometry remain limiting variables.

## TinManX1 implementation rules

1. X1C and K2 profiles select the high-flow member of reviewed Bambu
   standard/high-flow material vectors when an exact material contract exists.
2. Standard CM2 machines select the standard member of those vectors. Existing
   manufacturer recipes and field tunes remain authoritative for analogs.
3. X1C and K2 process profiles spend the guarded CHT headroom mainly on hidden
   paths: inner wall and sparse infill +20%, internal solid/gap/support +15%,
   outer wall/top/small perimeters +5%.
4. Filament maximum volumetric speed remains the final governor, so a process
   speed cannot force a material past its profile ceiling.
5. Motion acceleration, jerk and travel limits do not increase with nozzle
   flow. They remain owned by the machine firmware and validated motion
   envelopes.
6. Field-validated Fiberon PET-CF, X1C PCTG, flexible and high-temperature
   contracts are not replaced by generic multipliers.
7. Pressure advance is never inferred from nozzle marketing. It must be tuned
   for the exact machine, nozzle diameter, material and flow regime.

## Calibration order

The reviewed Orca tuning material converges on this order:

1. Dry the filament and verify mechanics/nozzle diameter.
2. Temperature tower.
3. Flow ratio.
4. Pressure advance.
5. Retraction and tolerance as needed.
6. Maximum volumetric flow, reduced 10-20% from first failure.
7. Cornering, acceleration and input shaping as independent machine tests.

Changing temperature or flow ratio can move the PA and MVS results, so the
sequence matters. Larger nozzles do not automatically permit higher linear
speed; the same MVS is consumed at a lower linear speed as bead area grows.

## Primary sources

- https://store.micro-swiss.com/products/micro-swiss-cm2-reprap-nozzle
- https://store.micro-swiss.com/products/flowtech-high-flow-cht-cm2-nozzle
- https://store.micro-swiss.com/products/micro-swiss-cm2-highflow-nozzle
- https://3d.nice-cdn.com/upload/file/FlowTech_Volumetric_Flow_Rate_Analysis.pdf
- https://github.com/OrcaSlicer/OrcaSlicer/wiki/volumetric_speed_calib
- https://github.com/OrcaSlicer/OrcaSlicer/wiki/material_flow_ratio_and_pressure_advance
- https://github.com/OrcaSlicer/OrcaSlicer/wiki/Calibration

## Video research set

Nineteen Orca tuning/calibration videos were reviewed for workflow agreement,
failure cues and practical sequencing:

`lG-JsElUReo`, `cSWxOY81tf8`, `XqRlV3HpYE8`, `gVU5If1VsAM`,
`FasWH3_gdlY`, `Mnvj6xCzikM`, `oYkQn3bGgBc`, `LcRi2r1j7KE`,
`c7CI6yBTKMc`, `trXzdfWCHI8`, `7rNlBwYd30k`, `7BUJLbQUABY`,
`ck-jpV76Wfk`, `5CVq6DycUOE`, `yky7D0nBeGw`, `U_M6z9C_DvY`,
`QfsH02MRym8`, `MFb5W5EVrA0`, and `hQC3vcWxOx8`.

Video guidance was used only where it agreed with Orca's official calibration
model or illustrated observable failure modes. Product limits and profile
rules are based on primary documentation and resolved profile data.
