# Rocket Slicer 1.3.2.637 FibreSeek Baseline

This is a sanitized TinManX1 reference note for the local Rocket Slicer build
used while tuning FibreSeek Seeker 3 continuous-fiber output. It records only
behavioral values that affect TinManX1 planning and profile generation. It does
not copy Rocket preset JSON, private IDs, UI assets, or proprietary text into
the public TinManX1 release.

## Source Build

- Application: Rocket Slicer
- macOS bundle version: 1.3.2.637
- Reported short version: 1.3.2
- Backend version: 1.3.1
- Backend git commit: 2490a9cecd5c3febea63e636ca0bec6a06164268
- Local preset location reviewed: `/Applications/Rocket Slicer.app/Contents/Resources/backend/resources/Templates/Presets`
- Preset pack counts: 5 composites, 7 plastics, 16 profile groups, 48 profiles

## Common FibreSeek Machine Contract

TinManX1 keeps these as common FibreSeek constraints unless explicit printer
testing proves a change is needed:

- Plastic nozzle families exposed for FibreSeek: 0.4, 0.6, 0.8 mm
- Continuous-fiber nozzle: 0.7 mm
- Continuous-fiber line width baseline: 0.80 mm
- Mechanical minimum route length: 55 mm
- Perimeter minimum route length: 55 mm
- Cut-window floor observed from emitted output: about 54.8 mm
- Default minimum bend radius: 12 mm
- Contact radius: 1.2 mm
- Extended contact radius: 1.8 mm
- Start length: 15 mm unless material tuning overrides it
- Slow length: 10 mm unless material tuning overrides it
- Finish max speed: 15 mm/s

## Material Tuning Adopted

These values are embedded into TinManX1 process presets through
`fiber_reinforcement_payload.material_tuning`. The planner selects them from
the active plastic/fiber material pair and then applies normal user process
overrides on top.

| Material pair | Mode | Min radius | Arc segment | Start length | Slow length | Normal max speed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| PETG + X-CCF | default/light/medium | 12 | 3 | 15 | 10 | 30 |
| PETG + X-CCF | heavy | 10 | 4 | 5 | 5 | 40 |
| PET GF + CGF | default/light/medium/heavy | 12 | 3 | 10 | 10 | 15 |
| PET GF + X-CCF | default/light/medium | 12 | 3 | 15 | 10 | 30 |
| PET GF + X-CCF | heavy | 10 | 4 | 5 | 5 | 40 |
| PA-CF + X-CCF | default/light | 12 | 3 | 15 | 10 | 30 |
| PA-CF + X-CCF | medium | 10 | 4 | 15 | 10 | 30 |
| PA-CF + X-CCF | heavy | 12 | 1 | 15 | 8 | 15 |
| PPS-CF + X-CCF | default/light | 12 | 3 | 15 | 10 | 25 |
| PPS-CF + X-CCF | medium | 12 | 1 | 15 | 10 | 25 |
| PPS-CF + X-CCF | heavy | 12 | 3 | 15 | 5 | 15 |
| PLA + X-CCF | default/light/heavy | 12 | 3 | 15 | 10 | 20 |
| PLA + X-CCF | medium | 10 | 4 | 5 | 5 | 40 |

All rows above retain the 55 mm route-length floor unless future machine testing
produces a safer material-specific value.

## TinManX1 Integration Notes

- The profile generator version carrying this baseline is `02.04.00.15`.
- The linter now requires the Rocket-derived material tuning map in every
  plastic-plus-fiber process profile.
- The native planner writes `fiber_material_tuning` into generated metadata so
  G-code audits can confirm which tuning rule was applied.
