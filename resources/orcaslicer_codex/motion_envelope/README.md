# TinManX1 Machine Capability Envelopes

TinManX1 does not treat a synthetic no-skip result as a printing-speed profile.
This subsystem combines a repeatedly validated, coupled velocity/acceleration
point with an independent quality limit and conservative safety factors.

An envelope can affect a generated profile only when all of these are true:

- Firmware is Klipper and kinematics are CoreXY.
- `minimum_cruise_ratio` was zero during the test.
- The printer was heat soaked.
- The selected velocity and acceleration were tested together for at least 50
  passing iterations.
- A separate quality limit from input-shaper, Shake&Tune, or inspected test
  prints is recorded.
- The envelope status is `active` and its nozzle exactly matches the profile.

Applying an envelope only lowers existing values. It never raises a machine or
process profile, and it does not replace maximum-volumetric-flow, pressure
advance, cooling, or first-layer calibration.

## Workflow

Create a draft:

```bash
python3 motion_envelope.py new \
  --printer-model "QidiMaxEz" \
  --nozzle 0.6 \
  --output qidimaxez-0.6.json
```

Record the exact hardware state before testing. Run coupled motion points with
`minimum_cruise_ratio: 0`, then validate the selected point for at least 50
iterations after the machine is heat soaked. Determine the quality limit
separately from resonance measurements and inspected prints. Set the envelope
to `active` only after both stages pass.

Place approved envelopes in a registry with this shape:

```json
{
  "schema_version": 1,
  "envelopes": []
}
```

Validate and inspect the derived caps:

```bash
python3 motion_envelope.py validate registry.json
python3 motion_envelope.py report registry.json \
  --printer-model "QidiMaxEz" --nozzle 0.6 --mode Quality
```

The shipped registry is intentionally empty. A local approved registry belongs
at `~/.tinmanx1/motion-envelopes/registry.json`; the profile normalizer consumes
it during `--apply-live`. This prevents unmeasured values from shipping as if
they were calibrated facts.
