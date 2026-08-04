# TinManX1 Filament Contract Audit

Date: 2026-08-04

## Scope

- Compared all 452 generated Codex filament profiles with the last known-good
  pre-catalog-cleanup commit (`187ca60735`). Their technical settings are
  semantically unchanged, so the catalog cleanup did not broadly erase tuning.
- Compared the PET-CF work history, bundled Bambu Studio 02.07.01.62 profiles,
  current TinManX1 resources, the installed application, Application Support,
  and active user preset directories.
- Validated all generated Codex profiles for positive price, flow, volumetric
  rate, and nozzle temperatures; coherent active-chamber fields; and the
  field-validated 45C PCTG chamber contract.

## Root Cause

The July 11 Plus 4 print rescue used 300C, flow 1.08, and 4 mm3/s while
diagnosing severe under-extrusion and surface breakup. A later successful
surface-quality tune replaced those emergency values, but its guard covered
only profiles literally named `Bambu PET-CF`. QIDI, Fiberon, generated Codex,
installed-cache, and user copies could therefore retain the rescue settings.

## PET-CF Contract

The final shared field tune is 285C first layer, 280C print, flow 1.00,
3.2 mm3/s maximum volumetric rate, 80C bed, 0-20 percent normal fan,
35 percent overhang fan, 25 second slowdown threshold, and 6 mm/s minimum
slowdown speed.

- Bambu PET-CF pressure advance: 0.022.
- Fiberon PET-CF/PET-CF17 pressure advance: 0.028.
- QIDI PET-CF retains nozzle-specific pressure advance: 0.032 for 0.4 mm and
  0.025 for 0.6/0.8 mm Plus 4 profiles.
- Active chamber control is 50C on QIDI Plus 4 and supported TinMan machine
  families. Direct Bambu profiles follow Bambu Studio's machine capability
  flags: H2D/H2D Pro, H2S, X1E, and X2D are active; A1, P1P, P2S, and X1C are
  inactive. Snapmaker U1 and Elegoo Centauri Codex profiles are inactive.

## Vendor Baselines

- Bambu PET-CF official range is 260-290C with an 80-100C bed and 80C drying
  for 8-12 hours. Bundled Bambu Studio uses a faster generic baseline than the
  TinMan field-quality profile.
- QIDI PET-CF lists 280-320C, an 80C bed, and 100C drying for 4-8 hours. QIDI
  says an actively heated chamber is not required; 50C is an intentional
  TinMan Plus 4 field-quality setting.
- Fiberon PET-CF17 lists 270-300C, a 70-80C bed, fan off, room-temperature
  chamber operation, and 100C drying for 10 hours. The TinMan profile's limited
  cooling and 50C target on capable machines are field overrides.

Sources:

- https://us.store.bambulab.com/en/products/pet-cf
- https://us.qidi3d.com/products/pet-cf-filament
- https://fiberon.polymaker.com/wp-content/uploads/TDS_FIBERON-PET-CF17_V1.0_EN-1.pdf

## Regression Controls

- `repair_tinman_pet_cf_contract.py` applies one contract to repository,
  installed, runtime-cache, and user copies and is safe to run repeatedly.
- `orca_extra_profile_check.py` rejects stale 300C/1.08 rescue values and
  verifies family pressure advance plus machine-specific chamber behavior.
- The deployment manifest covers 866 profile resources across repository,
  application bundle, and Application Support.
- FibreSeek process presets no longer duplicate printer-owned cut/restart
  values, and the generator preserves nested curated TinMan Codex profiles.
