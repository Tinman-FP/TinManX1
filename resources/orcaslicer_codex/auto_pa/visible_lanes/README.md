# TinMan Auto PA Visible Lanes

These 3MF objects are slicer-visible placeholders for same-print TinManX1
pressure advance, adaptive pressure advance, and max-flow calibration.

Use one lane object on the same plate as the model before slicing:

- `TINMAN_AUTO_PA_LANE_300_FRONT.3mf`: Qidi Plus 4 front edge.
- `TINMAN_AUTO_PA_LANE_300_REAR.3mf`: Max EZ rear edge.
- `TINMAN_AUTO_PA_LANE_500_REAR.3mf`: RatRig V-Core 4 rear edge.
- `TINMAN_AUTO_PA_LANE_500_FRONT.3mf`: optional 500 mm front-edge variant.

The 300 mm front lane is shortened to 270 mm so it remains in the Qidi Plus 4
front strip while clearing the profile's front-right bed exclusion pocket.
The 300 mm rear lane uses slightly tighter line spacing so Max EZ profiles that
inherit the Qidi rear-left bed exclusion pocket can slice the lane without
collision warnings.

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

When Orca generates a global skirt around the lane and the model, TinManX1
removes only skirt blocks that would leave the bed and clamps the advertised
`PRINT_START` bounds to the configured bed. This keeps the lane inside the
edge strip without needing to move it farther into the printable area.
The same postprocess pass also normalizes `PRINT_START TOTAL_LAYER_COUNT` to
the emitted layer-change stream so printer-side progress and PLR bookkeeping
track the actual G-code. Profiles that report total layers with
`SET_PRINT_STATS_INFO TOTAL_LAYER`, such as Qidi Plus 4, are normalized by the
same pass.

Set `TINMAN_AUTO_PA_AUTO_ADD_VISIBLE_LANE=0` before launching TinManX1 to
temporarily disable automatic lane insertion for debugging.
