# Wave Overhangs

Wave Overhangs is an experimental source-port lane for reducing or reshaping support needs by propagating wave-style overhang paths from supported geometry.

## Included Work

- native `src/libslic3r/WaveOverhangs/*` source additions in the patch
- Wave Overhang settings page and config keys
- G-code audit markers such as `WAVE_OVERHANG_*`
- support-remainder subtraction hooks
- smoke guard for runtime scaffold checks
- attribution to the OrcaSlicer-WaveOverhangs and PrusaSlicer-WaveOverhangs lineage

## Status

Experimental and opt-in. PLA and strong cooling are the clearest initial material signal from the inspected upstream work. PETG, ABS/ASA, PC, PA/PPA/CF, and chambered engineering materials need local testing before trust.

Wave Overhangs should preserve fallback support paths where coverage is incomplete.
