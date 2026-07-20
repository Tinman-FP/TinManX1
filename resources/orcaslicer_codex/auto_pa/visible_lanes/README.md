# TinMan Auto PA Visible Lanes

These 3MF objects are slicer-visible placeholders for same-print TinManX1
pressure advance, adaptive pressure advance, and max-flow calibration.

Use one lane object on the same plate as the model before slicing:

- `TINMAN_AUTO_PA_LANE_300_FRONT.3mf`: Qidi Plus 4 front edge.
- `TINMAN_AUTO_PA_LANE_300_REAR.3mf`: Max EZ rear edge.
- `TINMAN_AUTO_PA_LANE_500_REAR.3mf`: RatRig V-Core 4 rear edge.
- `TINMAN_AUTO_PA_LANE_500_FRONT.3mf`: optional 500 mm front-edge variant.

The postprocessor only treats these as calibration lanes when the sliced G-code
contains an `EXCLUDE_OBJECT_DEFINE` entry for the lane, the lane is inside the
configured edge strip, and the lane does not overlap another object footprint.
Without that visible object, calibration is deferred and no hidden pattern is
injected.
