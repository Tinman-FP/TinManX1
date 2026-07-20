# TinMan Auto PA Visible Lanes

These 3MF objects are slicer-visible placeholders for same-print TinManX1
pressure advance, adaptive pressure advance, and max-flow calibration.

Use one lane object on the same plate as the model before slicing:

- `TINMAN_AUTO_PA_LANE_300_FRONT.3mf`: Qidi Plus 4 front edge.
- `TINMAN_AUTO_PA_LANE_300_REAR.3mf`: Max EZ rear edge.
- `TINMAN_AUTO_PA_LANE_500_REAR.3mf`: RatRig V-Core 4 rear edge.
- `TINMAN_AUTO_PA_LANE_500_FRONT.3mf`: optional 500 mm front-edge variant.

TinManX1 builds with the lane importer patch recognize these object names during
3MF/model import and place them 10 mm from the named bed edge instead of using
the normal bed-center auto-placement pass. Current TinManX1 builds also auto-add
the matching lane before slice/export/send for supported printer profiles when
the active plate has a model but no TinMan auto-PA lane.

The postprocessor only treats these as calibration lanes when the sliced G-code
contains an `EXCLUDE_OBJECT_DEFINE` entry for the lane, the lane is inside the
configured edge strip, and the lane does not overlap another object footprint.
Without that visible object, calibration is deferred and no hidden pattern is
injected.

Set `TINMAN_AUTO_PA_AUTO_ADD_VISIBLE_LANE=0` before launching TinManX1 to
temporarily disable automatic lane insertion for debugging.
