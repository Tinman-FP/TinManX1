// Configuration store of Slic3r.
//
// The configuration store is either static or dynamic.
// DynamicPrintConfig is used mainly at the user interface. while the StaticPrintConfig is used
// during the slicing and the g-code generation.
//
// The classes derived from StaticPrintConfig form a following hierarchy.
//
// FullPrintConfig
//    PrintObjectConfig
//    PrintRegionConfig
//    PrintConfig
//        GCodeConfig
//

#ifndef slic3r_PrintConfig_hpp_
#define slic3r_PrintConfig_hpp_

#include "libslic3r.h"
#include "CommonDefs.hpp"
#include "Config.hpp"
#include "Polygon.hpp"
#include <boost/preprocessor/facilities/empty.hpp>
#include <boost/preprocessor/punctuation/comma_if.hpp>
#include <boost/preprocessor/seq/for_each.hpp>
#include <boost/preprocessor/seq/for_each_i.hpp>
#include <boost/preprocessor/stringize.hpp>
#include <boost/preprocessor/tuple/elem.hpp>
#include <boost/preprocessor/tuple/to_seq.hpp>

namespace Slic3r {

enum GCodeFlavor : unsigned char {
    gcfMarlinLegacy, 
    gcfKlipper, 
    gcfRepRapFirmware, 
    gcfRepetier, 
    gcfMarlinFirmware, 
    gcfRepRapSprinter, 
    gcfTeacup, 
    gcfMakerWare, 
    gcfSailfish, 
    gcfMach3, 
    gcfMachinekit,
    gcfSmoothie, 
    gcfNoExtrusion
};


enum class FuzzySkinType {
    None,
    External,
    Hole,
    All,
    AllWalls,
    Disabled_fuzzy,
};

enum class FuzzySkinMode {
    Displacement,
    Extrusion,
    Combined,
};

enum class NoiseType {
    Classic,
    Perlin,
    Billow,
    RidgedMulti,
    Voronoi,
    Ripple,
};

enum class WipeTowerType {
    Type1,
    Type2,
};

enum PrintHostType {
    htPrusaLink, htPrusaConnect, htOctoPrint, htDuet, htFlashAir, htAstroBox, htRepetier, htMKS, htESP3D, htCrealityPrint, htObico, htFlashforge, htSimplyPrint, htElegooLink, ht3DPrinterOS, htMoonraker
};

enum WaveOverhangAlgorithm {
    woaAndersons,
    woaKaiser
};

enum WaveOverhangSpacingMode {
    wosmUniform,
    wosmProgressive
};

enum WaveOverhangSeamMode {
    woseAlternating,
    woseAligned,
    woseRandom
};

enum class WaveOverhangPattern : int {
    Monotonic,
    ZigZag,
    Smart
};

enum AuthorizationType {
    atKeyPassword, atUserPassword
};

enum InfillPattern : int {
    ipMonotonic, ipMonotonicLine,
    ipRectilinear, ipAlignedRectilinear, ipZigZag, ipCrossZag, ipLockedZag,
    ipLine, ipGrid,
    ipTriangles, ipStars,
    ipCubic, ipAdaptiveCubic, ipQuarterCubic, ipSupportCubic, ipLightning,
    ipHoneycomb, ip3DHoneycomb, ipLateralHoneycomb, ipLateralLattice,
    ipCrossHatch, ipTpmsD, ipTpmsFK, ipGyroid,
    ipConcentric, ipHilbertCurve, ipArchimedeanChords, ipOctagramSpiral,
    ipSupportBase, ipConcentricInternal,
    ipCount,
};

enum class IroningType {
    NoIroning,
    TopSurfaces,
    TopmostOnly,
    AllSolid,
    Count,
};

//BBS
enum class WallInfillOrder {
    InnerOuterInfill,
    OuterInnerInfill,
    InfillInnerOuter,
    InfillOuterInner,
    InnerOuterInnerInfill,
    Count,
};

enum class BedTempFormula {
    btfFirstFilament,
    btfHighestTemp,
    count,
};

// Orca
enum class PowerLossRecoveryMode {
    PrinterConfiguration,
    Enable,
    Disable,
};

// BBS
enum class WallSequence {
    InnerOuter,
    OuterInner,
    InnerOuterInner,
    Count,
};

// Orca
enum class WallDirection
{
    CounterClockwise,
    Clockwise,
    Count,
};

//BBS
enum class PrintSequence {
    ByLayer,
    ByObject,
    ByDefault,
    Count,
};

enum class PrintOrder
{
    Default,
    AsObjectList,
    Count,
};

enum class SlicingMode
{
    // Regular, applying ClipperLib::pftNonZero rule when creating ExPolygons.
    Regular,
    // Compatible with 3DLabPrint models, applying ClipperLib::pftEvenOdd rule when creating ExPolygons.
    EvenOdd,
    // Orienting all contours CCW, thus closing all holes.
    CloseHoles,
};

enum SupportMaterialPattern {
    smpDefault,
    smpRectilinear, smpRectilinearGrid, smpHoneycomb,
    smpLightning,
    smpNone,
};

enum SupportMaterialStyle {
    smsDefault, smsGrid, smsSnug, smsTreeOrganic, smsTreeSlim, smsTreeStrong, smsTreeHybrid,
};

enum LongRectrationLevel
{
    Disabled=0,
    EnableMachine,
    EnableFilament
};

enum SupportMaterialInterfacePattern {
    smipAuto, smipRectilinear, smipConcentric, smipRectilinearInterlaced, smipGrid
};

// BBS
enum SupportType {
    stNormalAuto, stTreeAuto, stNormal, stTree, stArcAuto, stArc
};
inline bool is_tree(SupportType stype)
{
    return std::set<SupportType>{stTreeAuto, stTree}.count(stype) != 0;
};
inline bool is_arc(SupportType stype)
{
    return std::set<SupportType>{stArcAuto, stArc}.count(stype) != 0;
};
inline bool is_arc_compatible_support_style(SupportMaterialStyle style)
{
    return style == smsDefault || style == smsGrid || style == smsSnug;
}
inline bool is_normal_support(SupportType stype)
{
    return std::set<SupportType>{stNormalAuto, stNormal, stArcAuto, stArc}.count(stype) != 0;
};
inline bool is_normal_auto_support(SupportType stype)
{
    return std::set<SupportType>{stNormalAuto, stArcAuto}.count(stype) != 0;
};
inline bool is_tree_slim(SupportType type, SupportMaterialStyle style)
{
    return is_tree(type) && style==smsTreeSlim;
};
inline bool is_auto(SupportType stype)
{
    return std::set<SupportType>{stNormalAuto, stTreeAuto, stArcAuto}.count(stype) != 0;
};

enum class TinmanSupportStrategy {
    ProfileDefault,
    Normal,
    Tree,
    Arc,
};

enum class TinmanStrengthMaterialModel {
    FilamentPreset,
    Isotropic,
    FdmAnisotropic,
    ContinuousFiber,
};

enum class TinmanStrengthLoadAxis {
    Auto,
    X,
    Y,
    Z,
};

enum class FiberReinforcementMode {
    Light,
    Medium,
    Heavy,
};

enum class FiberManufacturingMode {
    PlasticPlusFiberOverlay,
    CompositeOnly,
};

enum class FiberInfillPattern {
    Solid,
    Rhombic,
    Isogrid,
    Anisogrid,
    Tetragrid,
};

enum class FiberInfillSourcePolicy {
    Explicit,
    GeneratedRibs,
    PlasticTraces,
};

enum class FiberSeamPosition {
    Source,
    Nearest,
    Aligned,
    Rear,
    Random,
};

enum SeamPosition {
    spNearest, spAligned, spAlignedBack, spRear, spRandom
};

// Orca
enum class SeamScarfType {
    None,
    External,
    All,
};

// Orca
enum EnsureVerticalShellThickness {
    evstNone,
    evstCriticalOnly,
    evstModerate,
    evstAll,
};

//Orca
enum InternalBridgeFilter {
    ibfDisabled, ibfLimited, ibfNofilter
};

//Orca
enum EnableExtraBridgeLayer {
    eblDisabled, eblExternalBridgeOnly, eblInternalBridgeOnly, eblApplyToAll
};

//Orca
enum GapFillTarget {
     gftEverywhere, gftTopBottom, gftNowhere
 };


enum LiftType {
    NormalLift,
    SpiralLift,
    SlopeLift
};

enum SLAMaterial {
    slamTough,
    slamFlex,
    slamCasting,
    slamDental,
    slamHeatResistant,
};

enum SLADisplayOrientation {
    sladoLandscape,
    sladoPortrait
};

enum SLAPillarConnectionMode {
    slapcmZigZag,
    slapcmCross,
    slapcmDynamic
};

enum BrimType {
    btAutoBrim,  // BBS
    btEar, // Orca
    btPainted,  // BBS
    btOuterOnly,
    btInnerOnly,
    btOuterAndInner,
    btNoBrim,
};

enum TimelapseType : int {
    tlTraditional = 0,
    tlSmooth
};

enum SkirtType {
    stCombined, stPerObject
};

enum DraftShield {
    dsDisabled, dsEnabled
};

enum class PerimeterGeneratorType
{
    // Classic perimeter generator using Clipper offsets with constant extrusion width.
    Classic,
    // Perimeter generator with variable extrusion width based on the paper
    // "A framework for adaptive width control of dense contour-parallel toolpaths in fused deposition modeling" ported from Cura.
    Arachne
};

// BBS
enum OverhangFanThreshold {
    Overhang_threshold_none = 0,
    Overhang_threshold_1_4,
    Overhang_threshold_2_4,
    Overhang_threshold_3_4,
    Overhang_threshold_4_4,
    Overhang_threshold_bridge
};

// BBS
enum BedType {
    btDefault = 0,
    btPC,
    btEP,
    btPEI,
    btPTE,
    btPCT,
    btSuperTack,
    btCount
};

enum class ExtruderOnlyAreaType:unsigned char {
    btNoArea= 0,
    Engilish,
    Chinese,
    btAreaCount
};

// BBS
enum LayerSeq {
    flsAuto,
    flsCustomize
};

static std::unordered_map<NozzleType, std::string>NozzleTypeEumnToStr = {
    {NozzleType::ntUndefine,        "undefine"},
    {NozzleType::ntHardenedSteel,   "hardened_steel"},
    {NozzleType::ntStainlessSteel,  "stainless_steel"},
    {NozzleType::ntTungstenCarbide, "tungsten_carbide"},
    {NozzleType::ntBrass,           "brass"},
    {NozzleType::ntE3D,             "E3D"}
};

static std::unordered_map<std::string, NozzleType>NozzleTypeStrToEumn = {
    {"undefine", NozzleType::ntUndefine},
    {"hardened_steel", NozzleType::ntHardenedSteel},
    {"stainless_steel", NozzleType::ntStainlessSteel},
    {"tungsten_carbide", NozzleType::ntTungstenCarbide},
    {"brass", NozzleType::ntBrass},
    {"E3D", NozzleType::ntE3D}
};

// BBS
enum PrinterStructure {
    psUndefine=0,
    psCoreXY,
    psI3,
    psHbot,
    psDelta
};

enum class InputShaperType : unsigned char {
    Default = 0,
    MZV,
    ZV,
    ZVD,
    ZVDD,
    ZVDDD,
    EI,
    EI2,
    TwoHumpEI,
    EI3,
    ThreeHumpEI,
    DAA,
    Disable
};

// BBS
enum ZHopType {
    zhtAuto = 0,
    zhtNormal,
    zhtSlope,
    zhtSpiral,
    zhtCount
};

enum RetractLiftEnforceType {
    rletAllSurfaces = 0,
    rletTopOnly,
    rletBottomOnly,
    rletTopAndBottom
};

enum class GCodeThumbnailsFormat {
    PNG, JPG, QOI, BTT_TFT, ColPic
};

enum CounterboreHoleBridgingOption {
    chbNone, chbBridges, chbFilled
};

 enum WipeTowerWallType {
     wtwRectangle = 0,
     wtwCone,
     wtwRib
 };

// BBS
enum ExtruderType {
    etDirectDrive = 0,
    etBowden,
    etMaxExtruderType = etBowden
};

enum NozzleVolumeType {
    nvtStandard = 0,
    nvtHighFlow,
    nvtMaxNozzleVolumeType = nvtHighFlow
};

enum FilamentMapMode {
    fmmAutoForFlush,
    fmmAutoForMatch,
    fmmManual,
    fmmDefault
};

extern std::string get_extruder_variant_string(ExtruderType extruder_type, NozzleVolumeType nozzle_volume_type);

std::string get_nozzle_volume_type_string(NozzleVolumeType nozzle_volume_type);

static std::string bed_type_to_gcode_string(const BedType type)
{
    std::string type_str;

    switch (type) {
    case btSuperTack:
        type_str = "supertack_plate";
        break;
    case btPC:
        type_str = "cool_plate";
        break;
    case btPCT:
        type_str = "textured_cool_plate";
        break;
    case btEP:
        type_str = "eng_plate";
        break;
    case btPEI:
        type_str = "hot_plate";
        break;
    case btPTE:
        type_str = "textured_plate";
        break;
    default:
        type_str = "unknown";
        break;
    }

    return type_str;
}

static std::string get_bed_temp_key(const BedType type)
{
    if (type == btSuperTack)
        return "supertack_plate_temp";

    if (type == btPC)
        return "cool_plate_temp";

    if (type == btPCT)
        return "textured_cool_plate_temp";

    if (type == btEP)
        return "eng_plate_temp";

    if (type == btPEI)
        return "hot_plate_temp";

    if (type == btPTE)
        return "textured_plate_temp";

    return "";
}

static std::string get_bed_temp_1st_layer_key(const BedType type)
{
    if (type == btSuperTack)
        return "supertack_plate_temp_initial_layer";

    if (type == btPC)
        return "cool_plate_temp_initial_layer";

    if (type == btPCT)
        return "textured_cool_plate_temp_initial_layer";

    if (type == btEP)
        return "eng_plate_temp_initial_layer";

    if (type == btPEI)
        return "hot_plate_temp_initial_layer";

    if (type == btPTE)
        return "textured_plate_temp_initial_layer";

    return "";
}

extern const std::vector<std::string> filament_extruder_override_keys;

// for parse extruder_ams_count
extern std::vector<std::map<int, int>> get_extruder_ams_count(const std::vector<std::string> &strs);
extern std::vector<std::string> save_extruder_ams_count_to_string(const std::vector<std::map<int, int>> &extruder_ams_count);

#define CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(NAME) \
    template<> const t_config_enum_names& ConfigOptionEnum<NAME>::get_enum_names(); \
    template<> const t_config_enum_values& ConfigOptionEnum<NAME>::get_enum_values();

CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(PrinterTechnology)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(GCodeFlavor)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FuzzySkinType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FuzzySkinMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WipeTowerType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(NoiseType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(InfillPattern)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(IroningType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SlicingMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SupportMaterialPattern)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SupportMaterialStyle)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SupportMaterialInterfacePattern)
// BBS
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SupportType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SeamPosition)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SeamScarfType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SLADisplayOrientation)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SLAPillarConnectionMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(BrimType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(TimelapseType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(BedType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(SkirtType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(InputShaperType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(DraftShield)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(ForwardCompatibilitySubstitutionRule)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(GCodeThumbnailsFormat)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(CounterboreHoleBridgingOption)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(PrintHostType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WaveOverhangAlgorithm)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WaveOverhangSpacingMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WaveOverhangSeamMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WaveOverhangPattern)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(TinmanSupportStrategy)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(TinmanStrengthMaterialModel)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(TinmanStrengthLoadAxis)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FiberReinforcementMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FiberManufacturingMode)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FiberInfillPattern)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FiberInfillSourcePolicy)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(FiberSeamPosition)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(AuthorizationType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(WipeTowerWallType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(PerimeterGeneratorType)
CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS(PowerLossRecoveryMode)

#undef CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS

class DynamicPrintConfig;

// Defines each and every configuration option of Slic3r, including the properties of the GUI dialogs.
// Does not store the actual values, but defines default values.
class PrintConfigDef : public ConfigDef
{
public:
    PrintConfigDef();

    static void handle_legacy(t_config_option_key &opt_key, std::string &value);
    static void handle_legacy_composite(DynamicPrintConfig &config);

    // Array options growing with the number of extruders
    const std::vector<std::string>& extruder_option_keys() const { return m_extruder_option_keys; }
    // Options defining the extruder retract properties. These keys are sorted lexicographically.
    // The extruder retract keys could be overidden by the same values defined at the Filament level
    // (then the key is further prefixed with the "filament_" prefix).
    const std::vector<std::string>& extruder_retract_keys() const { return m_extruder_retract_keys; }

    // BBS
    const std::vector<std::string>& filament_option_keys() const { return m_filament_option_keys; }
    const std::vector<std::string>& filament_retract_keys() const { return m_filament_retract_keys; }

private:
    void init_common_params();
    void init_fff_params();
    void init_extruder_option_keys();
    void init_sla_params();

    std::vector<std::string>    m_extruder_option_keys;
    std::vector<std::string>    m_extruder_retract_keys;

    // BBS
    void init_filament_option_keys();

    std::vector<std::string>    m_filament_option_keys;
    std::vector<std::string>    m_filament_retract_keys;
};

// The one and only global definition of SLic3r configuration options.
// This definition is constant.
extern const PrintConfigDef print_config_def;

class StaticPrintConfig;

// Minimum object distance for arrangement, based on printer technology.
double min_object_distance(const ConfigBase &cfg);

// Slic3r dynamic configuration, used to override the configuration
// per object, per modification volume or per printing material.
// The dynamic configuration is also used to store user modifications of the print global parameters,
// so the modified configuration values may be diffed against the active configuration
// to invalidate the proper slicing resp. g-code generation processing steps.
class DynamicPrintConfig : public DynamicConfig
{
public:
    DynamicPrintConfig() {}
    DynamicPrintConfig(const DynamicPrintConfig &rhs) : DynamicConfig(rhs) {}
    DynamicPrintConfig(DynamicPrintConfig &&rhs) noexcept : DynamicConfig(std::move(rhs)) {}
    explicit DynamicPrintConfig(const StaticPrintConfig &rhs);
    explicit DynamicPrintConfig(const ConfigBase &rhs) : DynamicConfig(rhs) {}

    DynamicPrintConfig& operator=(const DynamicPrintConfig &rhs) { DynamicConfig::operator=(rhs); return *this; }
    DynamicPrintConfig& operator=(DynamicPrintConfig &&rhs) noexcept { DynamicConfig::operator=(std::move(rhs)); return *this; }

    static DynamicPrintConfig  full_print_config();
    static DynamicPrintConfig* new_from_defaults_keys(const std::vector<std::string> &keys);

    // Overrides ConfigBase::def(). Static configuration definition. Any value stored into this ConfigBase shall have its definition here.
    const ConfigDef*    def() const override { return &print_config_def; }

    void                normalize_fdm(int used_filaments = 0);
    void                normalize_fdm_1();
    //return the changed param set
    t_config_option_keys normalize_fdm_2(int num_objects, int used_filaments = 0);

    size_t              get_parameter_size(const std::string& param_name, size_t extruder_nums);
    void                set_num_extruders(unsigned int num_extruders);

    // BBS
    void                set_num_filaments(unsigned int num_filaments);

    //BBS
    // Validate the PrintConfig. Returns an empty string on success, otherwise an error message is returned.
    std::map<std::string, std::string>         validate(bool under_cli = false);

    // Verify whether the opt_key has not been obsoleted or renamed.
    // Both opt_key and value may be modified by handle_legacy().
    // If the opt_key is no more valid in this version of Slic3r, opt_key is cleared by handle_legacy().
    // handle_legacy() is called internally by set_deserialize().
    void                handle_legacy(t_config_option_key &opt_key, std::string &value) const override
        { PrintConfigDef::handle_legacy(opt_key, value); }

    // Called after a config is loaded as a whole.
    // Perform composite conversions, for example merging multiple keys into one key.
    // For conversion of single options, the handle_legacy() method above is called.
    void                handle_legacy_composite() override
        { PrintConfigDef::handle_legacy_composite(*this); }

    //BBS special case Support G/ Support W
    std::string get_filament_type(std::string &displayed_filament_type, int id = 0);

    //BBS
    bool is_using_different_extruders();
    bool support_different_extruders(int& extruder_count);
    int get_index_for_extruder(int extruder_or_filament_id, std::string id_name, ExtruderType extruder_type, NozzleVolumeType nozzle_volume_type, std::string variant_name, unsigned int stride = 1) const;
    void update_values_to_printer_extruders(DynamicPrintConfig& printer_config, std::set<std::string>& key_set, std::string id_name, std::string variant_name, unsigned int stride = 1, unsigned int extruder_id = 0);
    void update_values_to_printer_extruders_for_multiple_filaments(DynamicPrintConfig& printer_config, std::set<std::string>& key_set, std::string id_name, std::string variant_name);

    void update_non_diff_values_to_base_config(DynamicPrintConfig& new_config, const t_config_option_keys& keys, const std::set<std::string>& different_keys, std::string extruder_id_name, std::string extruder_variant_name,
        std::set<std::string>& key_set1, std::set<std::string>& key_set2);
    void update_diff_values_to_child_config(DynamicPrintConfig& new_config, std::string extruder_id_name, std::string extruder_variant_name, std::set<std::string>& key_set1, std::set<std::string>& key_set2);

    int update_values_from_single_to_multi(DynamicPrintConfig& multi_config, std::set<std::string>& key_set, std::string id_name, std::string variant_name);
    int update_values_from_multi_to_multi(DynamicPrintConfig& new_config, std::set<std::string>& key_set, std::string id_name, std::string variant_name, std::vector<std::string>& extruder_variants);

    //int update_values_from_single_to_multi_2(DynamicPrintConfig& multi_config, std::set<std::string>& key_set);
    //int update_values_from_multi_to_single_2(std::set<std::string>& key_set);

    int update_values_from_multi_to_multi_2(const std::vector<std::string>& src_extruder_variants, const std::vector<std::string>& dst_extruder_variants, const DynamicPrintConfig& dst_config, const std::set<std::string>& key_sets);

public:
    // query filament
    std::string get_filament_vendor() const;
    std::string get_filament_type() const;
};
extern std::set<std::string> printer_extruder_options;
extern std::set<std::string> print_options_with_variant;
extern std::set<std::string> filament_options_with_variant;
extern std::set<std::string> printer_options_with_variant_1;
extern std::set<std::string> printer_options_with_variant_2;
extern std::set<std::string> empty_options;

extern void compute_filament_override_value(const std::string& opt_key, const ConfigOption *opt_old_machine, const ConfigOption *opt_new_machine, const ConfigOption *opt_new_filament, const DynamicPrintConfig& new_full_config,
    t_config_option_keys& diff_keys, DynamicPrintConfig& filament_overrides, std::vector<int>& f_maps);

void handle_legacy_sla(DynamicPrintConfig &config);

class StaticPrintConfig : public StaticConfig
{
public:
    StaticPrintConfig() {}

    // Overrides ConfigBase::def(). Static configuration definition. Any value stored into this ConfigBase shall have its definition here.
    const ConfigDef*    def() const override { return &print_config_def; }
    // Reference to the cached list of keys.
    virtual const t_config_option_keys& keys_ref() const = 0;

protected:
    // Verify whether the opt_key has not been obsoleted or renamed.
    // Both opt_key and value may be modified by handle_legacy().
    // If the opt_key is no more valid in this version of Slic3r, opt_key is cleared by handle_legacy().
    // handle_legacy() is called internally by set_deserialize().
    void                handle_legacy(t_config_option_key &opt_key, std::string &value) const override
        { PrintConfigDef::handle_legacy(opt_key, value); }

    // Internal class for keeping a dynamic map to static options.
    class StaticCacheBase
    {
    public:
        // To be called during the StaticCache setup.
        // Add one ConfigOption into m_map_name_to_offset.
        template<typename T>
        void                opt_add(const std::string &name, const char *base_ptr, const T &opt)
        {
            assert(m_map_name_to_offset.find(name) == m_map_name_to_offset.end());
            m_map_name_to_offset[name] = (const char*)&opt - base_ptr;
        }

    protected:
        std::map<std::string, ptrdiff_t>    m_map_name_to_offset;
    };

    // Parametrized by the type of the topmost class owning the options.
    template<typename T>
    class StaticCache : public StaticCacheBase
    {
    public:
        // Calling the constructor of m_defaults with 0 forces m_defaults to not run the initialization.
        StaticCache() : m_defaults(nullptr) {}
        ~StaticCache() { delete m_defaults; m_defaults = nullptr; }

        bool                initialized() const { return ! m_keys.empty(); }

        ConfigOption*       optptr(const std::string &name, T *owner) const
        {
            const auto it = m_map_name_to_offset.find(name);
            return (it == m_map_name_to_offset.end()) ? nullptr : reinterpret_cast<ConfigOption*>((char*)owner + it->second);
        }

        const ConfigOption* optptr(const std::string &name, const T *owner) const
        {
            const auto it = m_map_name_to_offset.find(name);
            return (it == m_map_name_to_offset.end()) ? nullptr : reinterpret_cast<const ConfigOption*>((const char*)owner + it->second);
        }

        const std::vector<std::string>& keys()      const { return m_keys; }
        const T&                        defaults()  const { return *m_defaults; }

        // To be called during the StaticCache setup.
        // Collect option keys from m_map_name_to_offset,
        // assign default values to m_defaults.
        void                finalize(T *defaults, const ConfigDef *defs)
        {
            assert(defs != nullptr);
            m_defaults = defaults;
            m_keys.clear();
            m_keys.reserve(m_map_name_to_offset.size());
            for (const auto &kvp : defs->options) {
                // Find the option given the option name kvp.first by an offset from (char*)m_defaults.
                ConfigOption *opt = this->optptr(kvp.first, m_defaults);
                if (opt == nullptr)
                    // This option is not defined by the ConfigBase of type T.
                    continue;
                m_keys.emplace_back(kvp.first);
                const ConfigOptionDef *def = defs->get(kvp.first);
                assert(def != nullptr);
                if (def->default_value)
                    opt->set(def->default_value.get());
            }
        }

    private:
        T                                  *m_defaults;
        std::vector<std::string>            m_keys;
    };
};

#define STATIC_PRINT_CONFIG_CACHE_BASE(CLASS_NAME) \
public: \
    /* Overrides ConfigBase::optptr(). Find ando/or create a ConfigOption instance for a given name. */ \
    const ConfigOption*      optptr(const t_config_option_key &opt_key) const override \
        { return s_cache_##CLASS_NAME.optptr(opt_key, this); } \
    /* Overrides ConfigBase::optptr(). Find ando/or create a ConfigOption instance for a given name. */ \
    ConfigOption*            optptr(const t_config_option_key &opt_key, bool create = false) override \
        { return s_cache_##CLASS_NAME.optptr(opt_key, this); } \
    /* Overrides ConfigBase::keys(). Collect names of all configuration values maintained by this configuration store. */ \
    t_config_option_keys     keys() const override { return s_cache_##CLASS_NAME.keys(); } \
    const t_config_option_keys& keys_ref() const override { return s_cache_##CLASS_NAME.keys(); } \
    static const CLASS_NAME& defaults() { assert(s_cache_##CLASS_NAME.initialized()); return s_cache_##CLASS_NAME.defaults(); } \
private: \
    friend int print_config_static_initializer(); \
    static void initialize_cache() \
    { \
        assert(! s_cache_##CLASS_NAME.initialized()); \
        if (! s_cache_##CLASS_NAME.initialized()) { \
            CLASS_NAME *inst = new CLASS_NAME(1); \
            inst->initialize(s_cache_##CLASS_NAME, (const char*)inst); \
            s_cache_##CLASS_NAME.finalize(inst, inst->def()); \
        } \
    } \
    /* Cache object holding a key/option map, a list of option keys and a copy of this static config initialized with the defaults. */ \
    static StaticPrintConfig::StaticCache<CLASS_NAME> s_cache_##CLASS_NAME;

#define STATIC_PRINT_CONFIG_CACHE(CLASS_NAME) \
    STATIC_PRINT_CONFIG_CACHE_BASE(CLASS_NAME) \
public: \
    /* Public default constructor will initialize the key/option cache and the default object copy if needed. */ \
    CLASS_NAME() { assert(s_cache_##CLASS_NAME.initialized()); *this = s_cache_##CLASS_NAME.defaults(); } \
protected: \
    /* Protected constructor to be called when compounded. */ \
    CLASS_NAME(int) {}

#define STATIC_PRINT_CONFIG_CACHE_DERIVED(CLASS_NAME) \
    STATIC_PRINT_CONFIG_CACHE_BASE(CLASS_NAME) \
public: \
    /* Overrides ConfigBase::def(). Static configuration definition. Any value stored into this ConfigBase shall have its definition here. */ \
    const ConfigDef*    def() const override { return &print_config_def; } \
    /* Handle legacy and obsoleted config keys */ \
    void                handle_legacy(t_config_option_key &opt_key, std::string &value) const override \
        { PrintConfigDef::handle_legacy(opt_key, value); }

#define PRINT_CONFIG_CLASS_ELEMENT_DEFINITION(r, data, elem) BOOST_PP_TUPLE_ELEM(0, elem) BOOST_PP_TUPLE_ELEM(1, elem);
#define PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION2(KEY) cache.opt_add(BOOST_PP_STRINGIZE(KEY), base_ptr, this->KEY);
#define PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION(r, data, elem) PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION2(BOOST_PP_TUPLE_ELEM(1, elem))
#define PRINT_CONFIG_CLASS_ELEMENT_HASH(r, data, elem) boost::hash_combine(seed, BOOST_PP_TUPLE_ELEM(1, elem).hash());
#define PRINT_CONFIG_CLASS_ELEMENT_EQUAL(r, data, elem) if (! (BOOST_PP_TUPLE_ELEM(1, elem) == rhs.BOOST_PP_TUPLE_ELEM(1, elem))) return false;
#define PRINT_CONFIG_CLASS_ELEMENT_LOWER(r, data, elem) \
        if (BOOST_PP_TUPLE_ELEM(1, elem) < rhs.BOOST_PP_TUPLE_ELEM(1, elem)) return true; \
        if (! (BOOST_PP_TUPLE_ELEM(1, elem) == rhs.BOOST_PP_TUPLE_ELEM(1, elem))) return false;

#define PRINT_CONFIG_CLASS_DEFINE(CLASS_NAME, PARAMETER_DEFINITION_SEQ) \
class CLASS_NAME : public StaticPrintConfig { \
    STATIC_PRINT_CONFIG_CACHE(CLASS_NAME) \
public: \
    BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_DEFINITION, _, PARAMETER_DEFINITION_SEQ) \
    size_t hash() const throw() \
    { \
        size_t seed = 0; \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_HASH, _, PARAMETER_DEFINITION_SEQ) \
        return seed; \
    } \
    bool operator==(const CLASS_NAME &rhs) const throw() \
    { \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_EQUAL, _, PARAMETER_DEFINITION_SEQ) \
        return true; \
    } \
    bool operator!=(const CLASS_NAME &rhs) const throw() { return ! (*this == rhs); } \
    bool operator<(const CLASS_NAME &rhs) const throw() \
    { \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_LOWER, _, PARAMETER_DEFINITION_SEQ) \
        return false; \
    } \
protected: \
    void initialize(StaticCacheBase &cache, const char *base_ptr) \
    { \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION, _, PARAMETER_DEFINITION_SEQ) \
    } \
};

#define PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST_ITEM(r, data, i, elem) BOOST_PP_COMMA_IF(i) public elem
#define PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST(CLASSES_PARENTS_TUPLE) BOOST_PP_SEQ_FOR_EACH_I(PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST_ITEM, _, BOOST_PP_TUPLE_TO_SEQ(CLASSES_PARENTS_TUPLE))
#define PRINT_CONFIG_CLASS_DERIVED_INITIALIZER_ITEM(r, VALUE, i, elem) BOOST_PP_COMMA_IF(i) elem(VALUE)
#define PRINT_CONFIG_CLASS_DERIVED_INITIALIZER(CLASSES_PARENTS_TUPLE, VALUE) BOOST_PP_SEQ_FOR_EACH_I(PRINT_CONFIG_CLASS_DERIVED_INITIALIZER_ITEM, VALUE, BOOST_PP_TUPLE_TO_SEQ(CLASSES_PARENTS_TUPLE))
#define PRINT_CONFIG_CLASS_DERIVED_INITCACHE_ITEM(r, data, elem) this->elem::initialize(cache, base_ptr);
#define PRINT_CONFIG_CLASS_DERIVED_INITCACHE(CLASSES_PARENTS_TUPLE) BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_DERIVED_INITCACHE_ITEM, _, BOOST_PP_TUPLE_TO_SEQ(CLASSES_PARENTS_TUPLE))
#define PRINT_CONFIG_CLASS_DERIVED_HASH(r, data, elem) boost::hash_combine(seed, static_cast<const elem*>(this)->hash());
#define PRINT_CONFIG_CLASS_DERIVED_EQUAL(r, data, elem) \
    if (! (*static_cast<const elem*>(this) == static_cast<const elem&>(rhs))) return false;

// Generic version, with or without new parameters. Don't use this directly.
#define PRINT_CONFIG_CLASS_DERIVED_DEFINE1(CLASS_NAME, CLASSES_PARENTS_TUPLE, PARAMETER_DEFINITION, PARAMETER_REGISTRATION, PARAMETER_HASHES, PARAMETER_EQUALS) \
class CLASS_NAME : PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST(CLASSES_PARENTS_TUPLE) { \
    STATIC_PRINT_CONFIG_CACHE_DERIVED(CLASS_NAME) \
    CLASS_NAME() : PRINT_CONFIG_CLASS_DERIVED_INITIALIZER(CLASSES_PARENTS_TUPLE, 0) { assert(s_cache_##CLASS_NAME.initialized()); *this = s_cache_##CLASS_NAME.defaults(); } \
public: \
    PARAMETER_DEFINITION \
    size_t hash() const throw() \
    { \
        size_t seed = 0; \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_DERIVED_HASH, _, BOOST_PP_TUPLE_TO_SEQ(CLASSES_PARENTS_TUPLE)) \
        PARAMETER_HASHES \
        return seed; \
    } \
    bool operator==(const CLASS_NAME &rhs) const throw() \
    { \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_DERIVED_EQUAL, _, BOOST_PP_TUPLE_TO_SEQ(CLASSES_PARENTS_TUPLE)) \
        PARAMETER_EQUALS \
        return true; \
    } \
    bool operator!=(const CLASS_NAME &rhs) const throw() { return ! (*this == rhs); } \
protected: \
    CLASS_NAME(int) : PRINT_CONFIG_CLASS_DERIVED_INITIALIZER(CLASSES_PARENTS_TUPLE, 1) {} \
    void initialize(StaticCacheBase &cache, const char* base_ptr) { \
        PRINT_CONFIG_CLASS_DERIVED_INITCACHE(CLASSES_PARENTS_TUPLE) \
        PARAMETER_REGISTRATION \
    } \
};
// Variant without adding new parameters.
#define PRINT_CONFIG_CLASS_DERIVED_DEFINE0(CLASS_NAME, CLASSES_PARENTS_TUPLE) \
    PRINT_CONFIG_CLASS_DERIVED_DEFINE1(CLASS_NAME, CLASSES_PARENTS_TUPLE, BOOST_PP_EMPTY(), BOOST_PP_EMPTY(), BOOST_PP_EMPTY(), BOOST_PP_EMPTY())
// Variant with adding new parameters.
#define PRINT_CONFIG_CLASS_DERIVED_DEFINE(CLASS_NAME, CLASSES_PARENTS_TUPLE, PARAMETER_DEFINITION_SEQ) \
    PRINT_CONFIG_CLASS_DERIVED_DEFINE1(CLASS_NAME, CLASSES_PARENTS_TUPLE, \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_DEFINITION, _, PARAMETER_DEFINITION_SEQ), \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION, _, PARAMETER_DEFINITION_SEQ), \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_HASH, _, PARAMETER_DEFINITION_SEQ), \
        BOOST_PP_SEQ_FOR_EACH(PRINT_CONFIG_CLASS_ELEMENT_EQUAL, _, PARAMETER_DEFINITION_SEQ))

// This object is mapped to Perl as Slic3r::Config::PrintObject.
class PrintObjectConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(PrintObjectConfig)
public:
    ConfigOptionFloat brim_object_gap;
    ConfigOptionFloat brim_flow_ratio;
    ConfigOptionBool brim_use_efc_outline;
    ConfigOptionEnum<BrimType> brim_type;
    ConfigOptionFloat brim_width;
    ConfigOptionFloat brim_ears_detection_length;
    ConfigOptionFloat brim_ears_max_angle;
    ConfigOptionFloat skirt_start_angle;
    ConfigOptionBool bridge_no_support;
    ConfigOptionFloat elefant_foot_compensation;
    ConfigOptionInt elefant_foot_compensation_layers;
    ConfigOptionPercent elefant_foot_layers_density;
    ConfigOptionFloat max_bridge_length;
    ConfigOptionFloatOrPercent line_width;
    ConfigOptionBool interface_shells;
    ConfigOptionFloat layer_height;
    ConfigOptionFloat mmu_segmented_region_max_width;
    ConfigOptionFloat mmu_segmented_region_interlocking_depth;
    ConfigOptionFloat raft_contact_distance;
    ConfigOptionFloat raft_expansion;
    ConfigOptionPercent raft_first_layer_density;
    ConfigOptionFloat raft_first_layer_expansion;
    ConfigOptionInt raft_layers;
    ConfigOptionEnum<SeamPosition> seam_position;
    ConfigOptionBool staggered_inner_seams;
    ConfigOptionFloat slice_closing_radius;
    ConfigOptionEnum<SlicingMode> slicing_mode;
    ConfigOptionBool enable_support;
    ConfigOptionEnum<SupportType> support_type;
    ConfigOptionEnum<TinmanSupportStrategy> tinman_support_strategy;
    ConfigOptionString arc_support_payload;
    ConfigOptionBool arc_support_experimental;
    ConfigOptionBool strength_lens_enabled;
    ConfigOptionEnum<TinmanStrengthMaterialModel> strength_lens_material_model;
    ConfigOptionEnum<TinmanStrengthLoadAxis> strength_lens_load_axis;
    ConfigOptionString strength_lens_payload;
    ConfigOptionFloat support_angle;
    ConfigOptionBool support_on_build_plate_only;
    ConfigOptionBool support_critical_regions_only;
    ConfigOptionBool support_remove_small_overhang;
    ConfigOptionFloat support_top_z_distance;
    ConfigOptionFloat support_bottom_z_distance;
    ConfigOptionInt enforce_support_layers;
    ConfigOptionInt support_filament;
    ConfigOptionFloatOrPercent support_line_width;
    ConfigOptionBool support_interface_not_for_body;
    ConfigOptionBool support_interface_loop_pattern;
    ConfigOptionInt support_interface_filament;
    ConfigOptionInt support_interface_top_layers;
    ConfigOptionInt support_interface_bottom_layers;
    ConfigOptionFloat support_interface_spacing;
    ConfigOptionFloat support_interface_speed;
    ConfigOptionEnum<SupportMaterialPattern> support_base_pattern;
    ConfigOptionEnum<SupportMaterialInterfacePattern> support_interface_pattern;
    ConfigOptionFloat support_base_pattern_spacing;
    ConfigOptionFloat support_expansion;
    ConfigOptionFloat support_speed;
    ConfigOptionEnum<SupportMaterialStyle> support_style;
    ConfigOptionBool set_other_flow_ratios;
    ConfigOptionFloat support_flow_ratio;
    ConfigOptionFloat support_interface_flow_ratio;
    ConfigOptionBool independent_support_layer_height;
    ConfigOptionBool thick_bridges;
    ConfigOptionBool thick_internal_bridges;
    ConfigOptionEnum<InternalBridgeFilter> dont_filter_internal_bridges;
    ConfigOptionEnum<EnableExtraBridgeLayer> enable_extra_bridge_layer;
    ConfigOptionPercent internal_bridge_density;
    ConfigOptionInt support_threshold_angle;
    ConfigOptionFloatOrPercent support_threshold_overlap;
    ConfigOptionFloat support_object_xy_distance;
    ConfigOptionFloat support_object_first_layer_gap;
    ConfigOptionBool support_ironing;
    ConfigOptionEnum<InfillPattern> support_ironing_pattern;
    ConfigOptionPercent support_ironing_flow;
    ConfigOptionFloat support_ironing_spacing;
    ConfigOptionFloat xy_hole_compensation;
    ConfigOptionFloat xy_contour_compensation;
    ConfigOptionBool flush_into_objects;
    ConfigOptionBool flush_into_infill;
    ConfigOptionBool flush_into_support;
    ConfigOptionFloat tree_support_branch_distance;
    ConfigOptionFloat tree_support_tip_diameter;
    ConfigOptionFloat tree_support_branch_diameter;
    ConfigOptionFloat tree_support_branch_angle;
    ConfigOptionFloat tree_support_branch_diameter_angle;
    ConfigOptionFloat tree_support_angle_slow;
    ConfigOptionInt tree_support_wall_count;
    ConfigOptionBool tree_support_auto_brim;
    ConfigOptionFloat tree_support_brim_width;
    ConfigOptionBool detect_narrow_internal_solid_infill;
    ConfigOptionBool adaptive_layer_height;
    ConfigOptionFloat support_bottom_interface_spacing;
    ConfigOptionEnum<PerimeterGeneratorType> wall_generator;
    ConfigOptionPercent wall_transition_length;
    ConfigOptionPercent wall_transition_filter_deviation;
    ConfigOptionFloat wall_transition_angle;
    ConfigOptionInt wall_distribution_count;
    ConfigOptionPercent min_feature_size;
    ConfigOptionPercent initial_layer_min_bead_width;
    ConfigOptionPercent min_bead_width;
    ConfigOptionFloat wall_maximum_resolution;
    ConfigOptionFloat wall_maximum_deviation;
    ConfigOptionFloat make_overhang_printable_angle;
    ConfigOptionFloat make_overhang_printable_hole_size;
    ConfigOptionFloat tree_support_branch_distance_organic;
    ConfigOptionPercent tree_support_top_rate;
    ConfigOptionFloat tree_support_branch_diameter_organic;
    ConfigOptionFloat tree_support_branch_angle_organic;
    ConfigOptionEnum<GapFillTarget> gap_fill_target;
    ConfigOptionFloat min_length_factor;
    ConfigOptionFloat default_acceleration;
    ConfigOptionFloat outer_wall_acceleration;
    ConfigOptionFloat inner_wall_acceleration;
    ConfigOptionFloat top_surface_acceleration;
    ConfigOptionFloat initial_layer_acceleration;
    ConfigOptionFloatOrPercent bridge_acceleration;
    ConfigOptionFloat travel_acceleration;
    ConfigOptionFloatOrPercent sparse_infill_acceleration;
    ConfigOptionFloatOrPercent internal_solid_infill_acceleration;
    ConfigOptionFloat default_jerk;
    ConfigOptionFloat outer_wall_jerk;
    ConfigOptionFloat inner_wall_jerk;
    ConfigOptionFloat infill_jerk;
    ConfigOptionFloat top_surface_jerk;
    ConfigOptionFloat initial_layer_jerk;
    ConfigOptionFloat travel_jerk;
    ConfigOptionBool precise_z_height;
    ConfigOptionFloat default_junction_deviation;
    ConfigOptionBool interlocking_beam;
    ConfigOptionFloat interlocking_beam_width;
    ConfigOptionFloat interlocking_orientation;
    ConfigOptionInt interlocking_beam_layer_count;
    ConfigOptionInt interlocking_depth;
    ConfigOptionInt interlocking_boundary_avoidance;
    ConfigOptionBool calib_flowrate_topinfill_special_order;

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, brim_object_gap.hash());
        boost::hash_combine(seed, brim_flow_ratio.hash());
        boost::hash_combine(seed, brim_use_efc_outline.hash());
        boost::hash_combine(seed, brim_type.hash());
        boost::hash_combine(seed, brim_width.hash());
        boost::hash_combine(seed, brim_ears_detection_length.hash());
        boost::hash_combine(seed, brim_ears_max_angle.hash());
        boost::hash_combine(seed, skirt_start_angle.hash());
        boost::hash_combine(seed, bridge_no_support.hash());
        boost::hash_combine(seed, elefant_foot_compensation.hash());
        boost::hash_combine(seed, elefant_foot_compensation_layers.hash());
        boost::hash_combine(seed, elefant_foot_layers_density.hash());
        boost::hash_combine(seed, max_bridge_length.hash());
        boost::hash_combine(seed, line_width.hash());
        boost::hash_combine(seed, interface_shells.hash());
        boost::hash_combine(seed, layer_height.hash());
        boost::hash_combine(seed, mmu_segmented_region_max_width.hash());
        boost::hash_combine(seed, mmu_segmented_region_interlocking_depth.hash());
        boost::hash_combine(seed, raft_contact_distance.hash());
        boost::hash_combine(seed, raft_expansion.hash());
        boost::hash_combine(seed, raft_first_layer_density.hash());
        boost::hash_combine(seed, raft_first_layer_expansion.hash());
        boost::hash_combine(seed, raft_layers.hash());
        boost::hash_combine(seed, seam_position.hash());
        boost::hash_combine(seed, staggered_inner_seams.hash());
        boost::hash_combine(seed, slice_closing_radius.hash());
        boost::hash_combine(seed, slicing_mode.hash());
        boost::hash_combine(seed, enable_support.hash());
        boost::hash_combine(seed, support_type.hash());
        boost::hash_combine(seed, tinman_support_strategy.hash());
        boost::hash_combine(seed, arc_support_payload.hash());
        boost::hash_combine(seed, arc_support_experimental.hash());
        boost::hash_combine(seed, strength_lens_enabled.hash());
        boost::hash_combine(seed, strength_lens_material_model.hash());
        boost::hash_combine(seed, strength_lens_load_axis.hash());
        boost::hash_combine(seed, strength_lens_payload.hash());
        boost::hash_combine(seed, support_angle.hash());
        boost::hash_combine(seed, support_on_build_plate_only.hash());
        boost::hash_combine(seed, support_critical_regions_only.hash());
        boost::hash_combine(seed, support_remove_small_overhang.hash());
        boost::hash_combine(seed, support_top_z_distance.hash());
        boost::hash_combine(seed, support_bottom_z_distance.hash());
        boost::hash_combine(seed, enforce_support_layers.hash());
        boost::hash_combine(seed, support_filament.hash());
        boost::hash_combine(seed, support_line_width.hash());
        boost::hash_combine(seed, support_interface_not_for_body.hash());
        boost::hash_combine(seed, support_interface_loop_pattern.hash());
        boost::hash_combine(seed, support_interface_filament.hash());
        boost::hash_combine(seed, support_interface_top_layers.hash());
        boost::hash_combine(seed, support_interface_bottom_layers.hash());
        boost::hash_combine(seed, support_interface_spacing.hash());
        boost::hash_combine(seed, support_interface_speed.hash());
        boost::hash_combine(seed, support_base_pattern.hash());
        boost::hash_combine(seed, support_interface_pattern.hash());
        boost::hash_combine(seed, support_base_pattern_spacing.hash());
        boost::hash_combine(seed, support_expansion.hash());
        boost::hash_combine(seed, support_speed.hash());
        boost::hash_combine(seed, support_style.hash());
        boost::hash_combine(seed, set_other_flow_ratios.hash());
        boost::hash_combine(seed, support_flow_ratio.hash());
        boost::hash_combine(seed, support_interface_flow_ratio.hash());
        boost::hash_combine(seed, independent_support_layer_height.hash());
        boost::hash_combine(seed, thick_bridges.hash());
        boost::hash_combine(seed, thick_internal_bridges.hash());
        boost::hash_combine(seed, dont_filter_internal_bridges.hash());
        boost::hash_combine(seed, enable_extra_bridge_layer.hash());
        boost::hash_combine(seed, internal_bridge_density.hash());
        boost::hash_combine(seed, support_threshold_angle.hash());
        boost::hash_combine(seed, support_threshold_overlap.hash());
        boost::hash_combine(seed, support_object_xy_distance.hash());
        boost::hash_combine(seed, support_object_first_layer_gap.hash());
        boost::hash_combine(seed, support_ironing.hash());
        boost::hash_combine(seed, support_ironing_pattern.hash());
        boost::hash_combine(seed, support_ironing_flow.hash());
        boost::hash_combine(seed, support_ironing_spacing.hash());
        boost::hash_combine(seed, xy_hole_compensation.hash());
        boost::hash_combine(seed, xy_contour_compensation.hash());
        boost::hash_combine(seed, flush_into_objects.hash());
        boost::hash_combine(seed, flush_into_infill.hash());
        boost::hash_combine(seed, flush_into_support.hash());
        boost::hash_combine(seed, tree_support_branch_distance.hash());
        boost::hash_combine(seed, tree_support_tip_diameter.hash());
        boost::hash_combine(seed, tree_support_branch_diameter.hash());
        boost::hash_combine(seed, tree_support_branch_angle.hash());
        boost::hash_combine(seed, tree_support_branch_diameter_angle.hash());
        boost::hash_combine(seed, tree_support_angle_slow.hash());
        boost::hash_combine(seed, tree_support_wall_count.hash());
        boost::hash_combine(seed, tree_support_auto_brim.hash());
        boost::hash_combine(seed, tree_support_brim_width.hash());
        boost::hash_combine(seed, detect_narrow_internal_solid_infill.hash());
        boost::hash_combine(seed, adaptive_layer_height.hash());
        boost::hash_combine(seed, support_bottom_interface_spacing.hash());
        boost::hash_combine(seed, wall_generator.hash());
        boost::hash_combine(seed, wall_transition_length.hash());
        boost::hash_combine(seed, wall_transition_filter_deviation.hash());
        boost::hash_combine(seed, wall_transition_angle.hash());
        boost::hash_combine(seed, wall_distribution_count.hash());
        boost::hash_combine(seed, min_feature_size.hash());
        boost::hash_combine(seed, initial_layer_min_bead_width.hash());
        boost::hash_combine(seed, min_bead_width.hash());
        boost::hash_combine(seed, wall_maximum_resolution.hash());
        boost::hash_combine(seed, wall_maximum_deviation.hash());
        boost::hash_combine(seed, make_overhang_printable_angle.hash());
        boost::hash_combine(seed, make_overhang_printable_hole_size.hash());
        boost::hash_combine(seed, tree_support_branch_distance_organic.hash());
        boost::hash_combine(seed, tree_support_top_rate.hash());
        boost::hash_combine(seed, tree_support_branch_diameter_organic.hash());
        boost::hash_combine(seed, tree_support_branch_angle_organic.hash());
        boost::hash_combine(seed, gap_fill_target.hash());
        boost::hash_combine(seed, min_length_factor.hash());
        boost::hash_combine(seed, default_acceleration.hash());
        boost::hash_combine(seed, outer_wall_acceleration.hash());
        boost::hash_combine(seed, inner_wall_acceleration.hash());
        boost::hash_combine(seed, top_surface_acceleration.hash());
        boost::hash_combine(seed, initial_layer_acceleration.hash());
        boost::hash_combine(seed, bridge_acceleration.hash());
        boost::hash_combine(seed, travel_acceleration.hash());
        boost::hash_combine(seed, sparse_infill_acceleration.hash());
        boost::hash_combine(seed, internal_solid_infill_acceleration.hash());
        boost::hash_combine(seed, default_jerk.hash());
        boost::hash_combine(seed, outer_wall_jerk.hash());
        boost::hash_combine(seed, inner_wall_jerk.hash());
        boost::hash_combine(seed, infill_jerk.hash());
        boost::hash_combine(seed, top_surface_jerk.hash());
        boost::hash_combine(seed, initial_layer_jerk.hash());
        boost::hash_combine(seed, travel_jerk.hash());
        boost::hash_combine(seed, precise_z_height.hash());
        boost::hash_combine(seed, default_junction_deviation.hash());
        boost::hash_combine(seed, interlocking_beam.hash());
        boost::hash_combine(seed, interlocking_beam_width.hash());
        boost::hash_combine(seed, interlocking_orientation.hash());
        boost::hash_combine(seed, interlocking_beam_layer_count.hash());
        boost::hash_combine(seed, interlocking_depth.hash());
        boost::hash_combine(seed, interlocking_boundary_avoidance.hash());
        boost::hash_combine(seed, calib_flowrate_topinfill_special_order.hash());
        return seed;
    }

    bool operator==(const PrintObjectConfig &rhs) const throw()
    {
        if (!(brim_object_gap == rhs.brim_object_gap))
            return false;
        if (!(brim_flow_ratio == rhs.brim_flow_ratio))
            return false;
        if (!(brim_use_efc_outline == rhs.brim_use_efc_outline))
            return false;
        if (!(brim_type == rhs.brim_type))
            return false;
        if (!(brim_width == rhs.brim_width))
            return false;
        if (!(brim_ears_detection_length == rhs.brim_ears_detection_length))
            return false;
        if (!(brim_ears_max_angle == rhs.brim_ears_max_angle))
            return false;
        if (!(skirt_start_angle == rhs.skirt_start_angle))
            return false;
        if (!(bridge_no_support == rhs.bridge_no_support))
            return false;
        if (!(elefant_foot_compensation == rhs.elefant_foot_compensation))
            return false;
        if (!(elefant_foot_compensation_layers == rhs.elefant_foot_compensation_layers))
            return false;
        if (!(elefant_foot_layers_density == rhs.elefant_foot_layers_density))
            return false;
        if (!(max_bridge_length == rhs.max_bridge_length))
            return false;
        if (!(line_width == rhs.line_width))
            return false;
        if (!(interface_shells == rhs.interface_shells))
            return false;
        if (!(layer_height == rhs.layer_height))
            return false;
        if (!(mmu_segmented_region_max_width == rhs.mmu_segmented_region_max_width))
            return false;
        if (!(mmu_segmented_region_interlocking_depth == rhs.mmu_segmented_region_interlocking_depth))
            return false;
        if (!(raft_contact_distance == rhs.raft_contact_distance))
            return false;
        if (!(raft_expansion == rhs.raft_expansion))
            return false;
        if (!(raft_first_layer_density == rhs.raft_first_layer_density))
            return false;
        if (!(raft_first_layer_expansion == rhs.raft_first_layer_expansion))
            return false;
        if (!(raft_layers == rhs.raft_layers))
            return false;
        if (!(seam_position == rhs.seam_position))
            return false;
        if (!(staggered_inner_seams == rhs.staggered_inner_seams))
            return false;
        if (!(slice_closing_radius == rhs.slice_closing_radius))
            return false;
        if (!(slicing_mode == rhs.slicing_mode))
            return false;
        if (!(enable_support == rhs.enable_support))
            return false;
        if (!(support_type == rhs.support_type))
            return false;
        if (!(tinman_support_strategy == rhs.tinman_support_strategy))
            return false;
        if (!(arc_support_payload == rhs.arc_support_payload))
            return false;
        if (!(arc_support_experimental == rhs.arc_support_experimental))
            return false;
        if (!(strength_lens_enabled == rhs.strength_lens_enabled))
            return false;
        if (!(strength_lens_material_model == rhs.strength_lens_material_model))
            return false;
        if (!(strength_lens_load_axis == rhs.strength_lens_load_axis))
            return false;
        if (!(strength_lens_payload == rhs.strength_lens_payload))
            return false;
        if (!(support_angle == rhs.support_angle))
            return false;
        if (!(support_on_build_plate_only == rhs.support_on_build_plate_only))
            return false;
        if (!(support_critical_regions_only == rhs.support_critical_regions_only))
            return false;
        if (!(support_remove_small_overhang == rhs.support_remove_small_overhang))
            return false;
        if (!(support_top_z_distance == rhs.support_top_z_distance))
            return false;
        if (!(support_bottom_z_distance == rhs.support_bottom_z_distance))
            return false;
        if (!(enforce_support_layers == rhs.enforce_support_layers))
            return false;
        if (!(support_filament == rhs.support_filament))
            return false;
        if (!(support_line_width == rhs.support_line_width))
            return false;
        if (!(support_interface_not_for_body == rhs.support_interface_not_for_body))
            return false;
        if (!(support_interface_loop_pattern == rhs.support_interface_loop_pattern))
            return false;
        if (!(support_interface_filament == rhs.support_interface_filament))
            return false;
        if (!(support_interface_top_layers == rhs.support_interface_top_layers))
            return false;
        if (!(support_interface_bottom_layers == rhs.support_interface_bottom_layers))
            return false;
        if (!(support_interface_spacing == rhs.support_interface_spacing))
            return false;
        if (!(support_interface_speed == rhs.support_interface_speed))
            return false;
        if (!(support_base_pattern == rhs.support_base_pattern))
            return false;
        if (!(support_interface_pattern == rhs.support_interface_pattern))
            return false;
        if (!(support_base_pattern_spacing == rhs.support_base_pattern_spacing))
            return false;
        if (!(support_expansion == rhs.support_expansion))
            return false;
        if (!(support_speed == rhs.support_speed))
            return false;
        if (!(support_style == rhs.support_style))
            return false;
        if (!(set_other_flow_ratios == rhs.set_other_flow_ratios))
            return false;
        if (!(support_flow_ratio == rhs.support_flow_ratio))
            return false;
        if (!(support_interface_flow_ratio == rhs.support_interface_flow_ratio))
            return false;
        if (!(independent_support_layer_height == rhs.independent_support_layer_height))
            return false;
        if (!(thick_bridges == rhs.thick_bridges))
            return false;
        if (!(thick_internal_bridges == rhs.thick_internal_bridges))
            return false;
        if (!(dont_filter_internal_bridges == rhs.dont_filter_internal_bridges))
            return false;
        if (!(enable_extra_bridge_layer == rhs.enable_extra_bridge_layer))
            return false;
        if (!(internal_bridge_density == rhs.internal_bridge_density))
            return false;
        if (!(support_threshold_angle == rhs.support_threshold_angle))
            return false;
        if (!(support_threshold_overlap == rhs.support_threshold_overlap))
            return false;
        if (!(support_object_xy_distance == rhs.support_object_xy_distance))
            return false;
        if (!(support_object_first_layer_gap == rhs.support_object_first_layer_gap))
            return false;
        if (!(support_ironing == rhs.support_ironing))
            return false;
        if (!(support_ironing_pattern == rhs.support_ironing_pattern))
            return false;
        if (!(support_ironing_flow == rhs.support_ironing_flow))
            return false;
        if (!(support_ironing_spacing == rhs.support_ironing_spacing))
            return false;
        if (!(xy_hole_compensation == rhs.xy_hole_compensation))
            return false;
        if (!(xy_contour_compensation == rhs.xy_contour_compensation))
            return false;
        if (!(flush_into_objects == rhs.flush_into_objects))
            return false;
        if (!(flush_into_infill == rhs.flush_into_infill))
            return false;
        if (!(flush_into_support == rhs.flush_into_support))
            return false;
        if (!(tree_support_branch_distance == rhs.tree_support_branch_distance))
            return false;
        if (!(tree_support_tip_diameter == rhs.tree_support_tip_diameter))
            return false;
        if (!(tree_support_branch_diameter == rhs.tree_support_branch_diameter))
            return false;
        if (!(tree_support_branch_angle == rhs.tree_support_branch_angle))
            return false;
        if (!(tree_support_branch_diameter_angle == rhs.tree_support_branch_diameter_angle))
            return false;
        if (!(tree_support_angle_slow == rhs.tree_support_angle_slow))
            return false;
        if (!(tree_support_wall_count == rhs.tree_support_wall_count))
            return false;
        if (!(tree_support_auto_brim == rhs.tree_support_auto_brim))
            return false;
        if (!(tree_support_brim_width == rhs.tree_support_brim_width))
            return false;
        if (!(detect_narrow_internal_solid_infill == rhs.detect_narrow_internal_solid_infill))
            return false;
        if (!(adaptive_layer_height == rhs.adaptive_layer_height))
            return false;
        if (!(support_bottom_interface_spacing == rhs.support_bottom_interface_spacing))
            return false;
        if (!(wall_generator == rhs.wall_generator))
            return false;
        if (!(wall_transition_length == rhs.wall_transition_length))
            return false;
        if (!(wall_transition_filter_deviation == rhs.wall_transition_filter_deviation))
            return false;
        if (!(wall_transition_angle == rhs.wall_transition_angle))
            return false;
        if (!(wall_distribution_count == rhs.wall_distribution_count))
            return false;
        if (!(min_feature_size == rhs.min_feature_size))
            return false;
        if (!(initial_layer_min_bead_width == rhs.initial_layer_min_bead_width))
            return false;
        if (!(min_bead_width == rhs.min_bead_width))
            return false;
        if (!(wall_maximum_resolution == rhs.wall_maximum_resolution))
            return false;
        if (!(wall_maximum_deviation == rhs.wall_maximum_deviation))
            return false;
        if (!(make_overhang_printable_angle == rhs.make_overhang_printable_angle))
            return false;
        if (!(make_overhang_printable_hole_size == rhs.make_overhang_printable_hole_size))
            return false;
        if (!(tree_support_branch_distance_organic == rhs.tree_support_branch_distance_organic))
            return false;
        if (!(tree_support_top_rate == rhs.tree_support_top_rate))
            return false;
        if (!(tree_support_branch_diameter_organic == rhs.tree_support_branch_diameter_organic))
            return false;
        if (!(tree_support_branch_angle_organic == rhs.tree_support_branch_angle_organic))
            return false;
        if (!(gap_fill_target == rhs.gap_fill_target))
            return false;
        if (!(min_length_factor == rhs.min_length_factor))
            return false;
        if (!(default_acceleration == rhs.default_acceleration))
            return false;
        if (!(outer_wall_acceleration == rhs.outer_wall_acceleration))
            return false;
        if (!(inner_wall_acceleration == rhs.inner_wall_acceleration))
            return false;
        if (!(top_surface_acceleration == rhs.top_surface_acceleration))
            return false;
        if (!(initial_layer_acceleration == rhs.initial_layer_acceleration))
            return false;
        if (!(bridge_acceleration == rhs.bridge_acceleration))
            return false;
        if (!(travel_acceleration == rhs.travel_acceleration))
            return false;
        if (!(sparse_infill_acceleration == rhs.sparse_infill_acceleration))
            return false;
        if (!(internal_solid_infill_acceleration == rhs.internal_solid_infill_acceleration))
            return false;
        if (!(default_jerk == rhs.default_jerk))
            return false;
        if (!(outer_wall_jerk == rhs.outer_wall_jerk))
            return false;
        if (!(inner_wall_jerk == rhs.inner_wall_jerk))
            return false;
        if (!(infill_jerk == rhs.infill_jerk))
            return false;
        if (!(top_surface_jerk == rhs.top_surface_jerk))
            return false;
        if (!(initial_layer_jerk == rhs.initial_layer_jerk))
            return false;
        if (!(travel_jerk == rhs.travel_jerk))
            return false;
        if (!(precise_z_height == rhs.precise_z_height))
            return false;
        if (!(default_junction_deviation == rhs.default_junction_deviation))
            return false;
        if (!(interlocking_beam == rhs.interlocking_beam))
            return false;
        if (!(interlocking_beam_width == rhs.interlocking_beam_width))
            return false;
        if (!(interlocking_orientation == rhs.interlocking_orientation))
            return false;
        if (!(interlocking_beam_layer_count == rhs.interlocking_beam_layer_count))
            return false;
        if (!(interlocking_depth == rhs.interlocking_depth))
            return false;
        if (!(interlocking_boundary_avoidance == rhs.interlocking_boundary_avoidance))
            return false;
        if (!(calib_flowrate_topinfill_special_order == rhs.calib_flowrate_topinfill_special_order))
            return false;
        return true;
    }

    bool operator!=(const PrintObjectConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const PrintObjectConfig &rhs) const throw()
    {
        if (brim_object_gap < rhs.brim_object_gap)
            return true;
        if (!(brim_object_gap == rhs.brim_object_gap))
            return false;
        if (brim_flow_ratio < rhs.brim_flow_ratio)
            return true;
        if (!(brim_flow_ratio == rhs.brim_flow_ratio))
            return false;
        if (brim_use_efc_outline < rhs.brim_use_efc_outline)
            return true;
        if (!(brim_use_efc_outline == rhs.brim_use_efc_outline))
            return false;
        if (brim_type < rhs.brim_type)
            return true;
        if (!(brim_type == rhs.brim_type))
            return false;
        if (brim_width < rhs.brim_width)
            return true;
        if (!(brim_width == rhs.brim_width))
            return false;
        if (brim_ears_detection_length < rhs.brim_ears_detection_length)
            return true;
        if (!(brim_ears_detection_length == rhs.brim_ears_detection_length))
            return false;
        if (brim_ears_max_angle < rhs.brim_ears_max_angle)
            return true;
        if (!(brim_ears_max_angle == rhs.brim_ears_max_angle))
            return false;
        if (skirt_start_angle < rhs.skirt_start_angle)
            return true;
        if (!(skirt_start_angle == rhs.skirt_start_angle))
            return false;
        if (bridge_no_support < rhs.bridge_no_support)
            return true;
        if (!(bridge_no_support == rhs.bridge_no_support))
            return false;
        if (elefant_foot_compensation < rhs.elefant_foot_compensation)
            return true;
        if (!(elefant_foot_compensation == rhs.elefant_foot_compensation))
            return false;
        if (elefant_foot_compensation_layers < rhs.elefant_foot_compensation_layers)
            return true;
        if (!(elefant_foot_compensation_layers == rhs.elefant_foot_compensation_layers))
            return false;
        if (elefant_foot_layers_density < rhs.elefant_foot_layers_density)
            return true;
        if (!(elefant_foot_layers_density == rhs.elefant_foot_layers_density))
            return false;
        if (max_bridge_length < rhs.max_bridge_length)
            return true;
        if (!(max_bridge_length == rhs.max_bridge_length))
            return false;
        if (line_width < rhs.line_width)
            return true;
        if (!(line_width == rhs.line_width))
            return false;
        if (interface_shells < rhs.interface_shells)
            return true;
        if (!(interface_shells == rhs.interface_shells))
            return false;
        if (layer_height < rhs.layer_height)
            return true;
        if (!(layer_height == rhs.layer_height))
            return false;
        if (mmu_segmented_region_max_width < rhs.mmu_segmented_region_max_width)
            return true;
        if (!(mmu_segmented_region_max_width == rhs.mmu_segmented_region_max_width))
            return false;
        if (mmu_segmented_region_interlocking_depth < rhs.mmu_segmented_region_interlocking_depth)
            return true;
        if (!(mmu_segmented_region_interlocking_depth == rhs.mmu_segmented_region_interlocking_depth))
            return false;
        if (raft_contact_distance < rhs.raft_contact_distance)
            return true;
        if (!(raft_contact_distance == rhs.raft_contact_distance))
            return false;
        if (raft_expansion < rhs.raft_expansion)
            return true;
        if (!(raft_expansion == rhs.raft_expansion))
            return false;
        if (raft_first_layer_density < rhs.raft_first_layer_density)
            return true;
        if (!(raft_first_layer_density == rhs.raft_first_layer_density))
            return false;
        if (raft_first_layer_expansion < rhs.raft_first_layer_expansion)
            return true;
        if (!(raft_first_layer_expansion == rhs.raft_first_layer_expansion))
            return false;
        if (raft_layers < rhs.raft_layers)
            return true;
        if (!(raft_layers == rhs.raft_layers))
            return false;
        if (seam_position < rhs.seam_position)
            return true;
        if (!(seam_position == rhs.seam_position))
            return false;
        if (staggered_inner_seams < rhs.staggered_inner_seams)
            return true;
        if (!(staggered_inner_seams == rhs.staggered_inner_seams))
            return false;
        if (slice_closing_radius < rhs.slice_closing_radius)
            return true;
        if (!(slice_closing_radius == rhs.slice_closing_radius))
            return false;
        if (slicing_mode < rhs.slicing_mode)
            return true;
        if (!(slicing_mode == rhs.slicing_mode))
            return false;
        if (enable_support < rhs.enable_support)
            return true;
        if (!(enable_support == rhs.enable_support))
            return false;
        if (support_type < rhs.support_type)
            return true;
        if (!(support_type == rhs.support_type))
            return false;
        if (tinman_support_strategy < rhs.tinman_support_strategy)
            return true;
        if (!(tinman_support_strategy == rhs.tinman_support_strategy))
            return false;
        if (arc_support_payload < rhs.arc_support_payload)
            return true;
        if (!(arc_support_payload == rhs.arc_support_payload))
            return false;
        if (arc_support_experimental < rhs.arc_support_experimental)
            return true;
        if (!(arc_support_experimental == rhs.arc_support_experimental))
            return false;
        if (strength_lens_enabled < rhs.strength_lens_enabled)
            return true;
        if (!(strength_lens_enabled == rhs.strength_lens_enabled))
            return false;
        if (strength_lens_material_model < rhs.strength_lens_material_model)
            return true;
        if (!(strength_lens_material_model == rhs.strength_lens_material_model))
            return false;
        if (strength_lens_load_axis < rhs.strength_lens_load_axis)
            return true;
        if (!(strength_lens_load_axis == rhs.strength_lens_load_axis))
            return false;
        if (strength_lens_payload < rhs.strength_lens_payload)
            return true;
        if (!(strength_lens_payload == rhs.strength_lens_payload))
            return false;
        if (support_angle < rhs.support_angle)
            return true;
        if (!(support_angle == rhs.support_angle))
            return false;
        if (support_on_build_plate_only < rhs.support_on_build_plate_only)
            return true;
        if (!(support_on_build_plate_only == rhs.support_on_build_plate_only))
            return false;
        if (support_critical_regions_only < rhs.support_critical_regions_only)
            return true;
        if (!(support_critical_regions_only == rhs.support_critical_regions_only))
            return false;
        if (support_remove_small_overhang < rhs.support_remove_small_overhang)
            return true;
        if (!(support_remove_small_overhang == rhs.support_remove_small_overhang))
            return false;
        if (support_top_z_distance < rhs.support_top_z_distance)
            return true;
        if (!(support_top_z_distance == rhs.support_top_z_distance))
            return false;
        if (support_bottom_z_distance < rhs.support_bottom_z_distance)
            return true;
        if (!(support_bottom_z_distance == rhs.support_bottom_z_distance))
            return false;
        if (enforce_support_layers < rhs.enforce_support_layers)
            return true;
        if (!(enforce_support_layers == rhs.enforce_support_layers))
            return false;
        if (support_filament < rhs.support_filament)
            return true;
        if (!(support_filament == rhs.support_filament))
            return false;
        if (support_line_width < rhs.support_line_width)
            return true;
        if (!(support_line_width == rhs.support_line_width))
            return false;
        if (support_interface_not_for_body < rhs.support_interface_not_for_body)
            return true;
        if (!(support_interface_not_for_body == rhs.support_interface_not_for_body))
            return false;
        if (support_interface_loop_pattern < rhs.support_interface_loop_pattern)
            return true;
        if (!(support_interface_loop_pattern == rhs.support_interface_loop_pattern))
            return false;
        if (support_interface_filament < rhs.support_interface_filament)
            return true;
        if (!(support_interface_filament == rhs.support_interface_filament))
            return false;
        if (support_interface_top_layers < rhs.support_interface_top_layers)
            return true;
        if (!(support_interface_top_layers == rhs.support_interface_top_layers))
            return false;
        if (support_interface_bottom_layers < rhs.support_interface_bottom_layers)
            return true;
        if (!(support_interface_bottom_layers == rhs.support_interface_bottom_layers))
            return false;
        if (support_interface_spacing < rhs.support_interface_spacing)
            return true;
        if (!(support_interface_spacing == rhs.support_interface_spacing))
            return false;
        if (support_interface_speed < rhs.support_interface_speed)
            return true;
        if (!(support_interface_speed == rhs.support_interface_speed))
            return false;
        if (support_base_pattern < rhs.support_base_pattern)
            return true;
        if (!(support_base_pattern == rhs.support_base_pattern))
            return false;
        if (support_interface_pattern < rhs.support_interface_pattern)
            return true;
        if (!(support_interface_pattern == rhs.support_interface_pattern))
            return false;
        if (support_base_pattern_spacing < rhs.support_base_pattern_spacing)
            return true;
        if (!(support_base_pattern_spacing == rhs.support_base_pattern_spacing))
            return false;
        if (support_expansion < rhs.support_expansion)
            return true;
        if (!(support_expansion == rhs.support_expansion))
            return false;
        if (support_speed < rhs.support_speed)
            return true;
        if (!(support_speed == rhs.support_speed))
            return false;
        if (support_style < rhs.support_style)
            return true;
        if (!(support_style == rhs.support_style))
            return false;
        if (set_other_flow_ratios < rhs.set_other_flow_ratios)
            return true;
        if (!(set_other_flow_ratios == rhs.set_other_flow_ratios))
            return false;
        if (support_flow_ratio < rhs.support_flow_ratio)
            return true;
        if (!(support_flow_ratio == rhs.support_flow_ratio))
            return false;
        if (support_interface_flow_ratio < rhs.support_interface_flow_ratio)
            return true;
        if (!(support_interface_flow_ratio == rhs.support_interface_flow_ratio))
            return false;
        if (independent_support_layer_height < rhs.independent_support_layer_height)
            return true;
        if (!(independent_support_layer_height == rhs.independent_support_layer_height))
            return false;
        if (thick_bridges < rhs.thick_bridges)
            return true;
        if (!(thick_bridges == rhs.thick_bridges))
            return false;
        if (thick_internal_bridges < rhs.thick_internal_bridges)
            return true;
        if (!(thick_internal_bridges == rhs.thick_internal_bridges))
            return false;
        if (dont_filter_internal_bridges < rhs.dont_filter_internal_bridges)
            return true;
        if (!(dont_filter_internal_bridges == rhs.dont_filter_internal_bridges))
            return false;
        if (enable_extra_bridge_layer < rhs.enable_extra_bridge_layer)
            return true;
        if (!(enable_extra_bridge_layer == rhs.enable_extra_bridge_layer))
            return false;
        if (internal_bridge_density < rhs.internal_bridge_density)
            return true;
        if (!(internal_bridge_density == rhs.internal_bridge_density))
            return false;
        if (support_threshold_angle < rhs.support_threshold_angle)
            return true;
        if (!(support_threshold_angle == rhs.support_threshold_angle))
            return false;
        if (support_threshold_overlap < rhs.support_threshold_overlap)
            return true;
        if (!(support_threshold_overlap == rhs.support_threshold_overlap))
            return false;
        if (support_object_xy_distance < rhs.support_object_xy_distance)
            return true;
        if (!(support_object_xy_distance == rhs.support_object_xy_distance))
            return false;
        if (support_object_first_layer_gap < rhs.support_object_first_layer_gap)
            return true;
        if (!(support_object_first_layer_gap == rhs.support_object_first_layer_gap))
            return false;
        if (support_ironing < rhs.support_ironing)
            return true;
        if (!(support_ironing == rhs.support_ironing))
            return false;
        if (support_ironing_pattern < rhs.support_ironing_pattern)
            return true;
        if (!(support_ironing_pattern == rhs.support_ironing_pattern))
            return false;
        if (support_ironing_flow < rhs.support_ironing_flow)
            return true;
        if (!(support_ironing_flow == rhs.support_ironing_flow))
            return false;
        if (support_ironing_spacing < rhs.support_ironing_spacing)
            return true;
        if (!(support_ironing_spacing == rhs.support_ironing_spacing))
            return false;
        if (xy_hole_compensation < rhs.xy_hole_compensation)
            return true;
        if (!(xy_hole_compensation == rhs.xy_hole_compensation))
            return false;
        if (xy_contour_compensation < rhs.xy_contour_compensation)
            return true;
        if (!(xy_contour_compensation == rhs.xy_contour_compensation))
            return false;
        if (flush_into_objects < rhs.flush_into_objects)
            return true;
        if (!(flush_into_objects == rhs.flush_into_objects))
            return false;
        if (flush_into_infill < rhs.flush_into_infill)
            return true;
        if (!(flush_into_infill == rhs.flush_into_infill))
            return false;
        if (flush_into_support < rhs.flush_into_support)
            return true;
        if (!(flush_into_support == rhs.flush_into_support))
            return false;
        if (tree_support_branch_distance < rhs.tree_support_branch_distance)
            return true;
        if (!(tree_support_branch_distance == rhs.tree_support_branch_distance))
            return false;
        if (tree_support_tip_diameter < rhs.tree_support_tip_diameter)
            return true;
        if (!(tree_support_tip_diameter == rhs.tree_support_tip_diameter))
            return false;
        if (tree_support_branch_diameter < rhs.tree_support_branch_diameter)
            return true;
        if (!(tree_support_branch_diameter == rhs.tree_support_branch_diameter))
            return false;
        if (tree_support_branch_angle < rhs.tree_support_branch_angle)
            return true;
        if (!(tree_support_branch_angle == rhs.tree_support_branch_angle))
            return false;
        if (tree_support_branch_diameter_angle < rhs.tree_support_branch_diameter_angle)
            return true;
        if (!(tree_support_branch_diameter_angle == rhs.tree_support_branch_diameter_angle))
            return false;
        if (tree_support_angle_slow < rhs.tree_support_angle_slow)
            return true;
        if (!(tree_support_angle_slow == rhs.tree_support_angle_slow))
            return false;
        if (tree_support_wall_count < rhs.tree_support_wall_count)
            return true;
        if (!(tree_support_wall_count == rhs.tree_support_wall_count))
            return false;
        if (tree_support_auto_brim < rhs.tree_support_auto_brim)
            return true;
        if (!(tree_support_auto_brim == rhs.tree_support_auto_brim))
            return false;
        if (tree_support_brim_width < rhs.tree_support_brim_width)
            return true;
        if (!(tree_support_brim_width == rhs.tree_support_brim_width))
            return false;
        if (detect_narrow_internal_solid_infill < rhs.detect_narrow_internal_solid_infill)
            return true;
        if (!(detect_narrow_internal_solid_infill == rhs.detect_narrow_internal_solid_infill))
            return false;
        if (adaptive_layer_height < rhs.adaptive_layer_height)
            return true;
        if (!(adaptive_layer_height == rhs.adaptive_layer_height))
            return false;
        if (support_bottom_interface_spacing < rhs.support_bottom_interface_spacing)
            return true;
        if (!(support_bottom_interface_spacing == rhs.support_bottom_interface_spacing))
            return false;
        if (wall_generator < rhs.wall_generator)
            return true;
        if (!(wall_generator == rhs.wall_generator))
            return false;
        if (wall_transition_length < rhs.wall_transition_length)
            return true;
        if (!(wall_transition_length == rhs.wall_transition_length))
            return false;
        if (wall_transition_filter_deviation < rhs.wall_transition_filter_deviation)
            return true;
        if (!(wall_transition_filter_deviation == rhs.wall_transition_filter_deviation))
            return false;
        if (wall_transition_angle < rhs.wall_transition_angle)
            return true;
        if (!(wall_transition_angle == rhs.wall_transition_angle))
            return false;
        if (wall_distribution_count < rhs.wall_distribution_count)
            return true;
        if (!(wall_distribution_count == rhs.wall_distribution_count))
            return false;
        if (min_feature_size < rhs.min_feature_size)
            return true;
        if (!(min_feature_size == rhs.min_feature_size))
            return false;
        if (initial_layer_min_bead_width < rhs.initial_layer_min_bead_width)
            return true;
        if (!(initial_layer_min_bead_width == rhs.initial_layer_min_bead_width))
            return false;
        if (min_bead_width < rhs.min_bead_width)
            return true;
        if (!(min_bead_width == rhs.min_bead_width))
            return false;
        if (wall_maximum_resolution < rhs.wall_maximum_resolution)
            return true;
        if (!(wall_maximum_resolution == rhs.wall_maximum_resolution))
            return false;
        if (wall_maximum_deviation < rhs.wall_maximum_deviation)
            return true;
        if (!(wall_maximum_deviation == rhs.wall_maximum_deviation))
            return false;
        if (make_overhang_printable_angle < rhs.make_overhang_printable_angle)
            return true;
        if (!(make_overhang_printable_angle == rhs.make_overhang_printable_angle))
            return false;
        if (make_overhang_printable_hole_size < rhs.make_overhang_printable_hole_size)
            return true;
        if (!(make_overhang_printable_hole_size == rhs.make_overhang_printable_hole_size))
            return false;
        if (tree_support_branch_distance_organic < rhs.tree_support_branch_distance_organic)
            return true;
        if (!(tree_support_branch_distance_organic == rhs.tree_support_branch_distance_organic))
            return false;
        if (tree_support_top_rate < rhs.tree_support_top_rate)
            return true;
        if (!(tree_support_top_rate == rhs.tree_support_top_rate))
            return false;
        if (tree_support_branch_diameter_organic < rhs.tree_support_branch_diameter_organic)
            return true;
        if (!(tree_support_branch_diameter_organic == rhs.tree_support_branch_diameter_organic))
            return false;
        if (tree_support_branch_angle_organic < rhs.tree_support_branch_angle_organic)
            return true;
        if (!(tree_support_branch_angle_organic == rhs.tree_support_branch_angle_organic))
            return false;
        if (gap_fill_target < rhs.gap_fill_target)
            return true;
        if (!(gap_fill_target == rhs.gap_fill_target))
            return false;
        if (min_length_factor < rhs.min_length_factor)
            return true;
        if (!(min_length_factor == rhs.min_length_factor))
            return false;
        if (default_acceleration < rhs.default_acceleration)
            return true;
        if (!(default_acceleration == rhs.default_acceleration))
            return false;
        if (outer_wall_acceleration < rhs.outer_wall_acceleration)
            return true;
        if (!(outer_wall_acceleration == rhs.outer_wall_acceleration))
            return false;
        if (inner_wall_acceleration < rhs.inner_wall_acceleration)
            return true;
        if (!(inner_wall_acceleration == rhs.inner_wall_acceleration))
            return false;
        if (top_surface_acceleration < rhs.top_surface_acceleration)
            return true;
        if (!(top_surface_acceleration == rhs.top_surface_acceleration))
            return false;
        if (initial_layer_acceleration < rhs.initial_layer_acceleration)
            return true;
        if (!(initial_layer_acceleration == rhs.initial_layer_acceleration))
            return false;
        if (bridge_acceleration < rhs.bridge_acceleration)
            return true;
        if (!(bridge_acceleration == rhs.bridge_acceleration))
            return false;
        if (travel_acceleration < rhs.travel_acceleration)
            return true;
        if (!(travel_acceleration == rhs.travel_acceleration))
            return false;
        if (sparse_infill_acceleration < rhs.sparse_infill_acceleration)
            return true;
        if (!(sparse_infill_acceleration == rhs.sparse_infill_acceleration))
            return false;
        if (internal_solid_infill_acceleration < rhs.internal_solid_infill_acceleration)
            return true;
        if (!(internal_solid_infill_acceleration == rhs.internal_solid_infill_acceleration))
            return false;
        if (default_jerk < rhs.default_jerk)
            return true;
        if (!(default_jerk == rhs.default_jerk))
            return false;
        if (outer_wall_jerk < rhs.outer_wall_jerk)
            return true;
        if (!(outer_wall_jerk == rhs.outer_wall_jerk))
            return false;
        if (inner_wall_jerk < rhs.inner_wall_jerk)
            return true;
        if (!(inner_wall_jerk == rhs.inner_wall_jerk))
            return false;
        if (infill_jerk < rhs.infill_jerk)
            return true;
        if (!(infill_jerk == rhs.infill_jerk))
            return false;
        if (top_surface_jerk < rhs.top_surface_jerk)
            return true;
        if (!(top_surface_jerk == rhs.top_surface_jerk))
            return false;
        if (initial_layer_jerk < rhs.initial_layer_jerk)
            return true;
        if (!(initial_layer_jerk == rhs.initial_layer_jerk))
            return false;
        if (travel_jerk < rhs.travel_jerk)
            return true;
        if (!(travel_jerk == rhs.travel_jerk))
            return false;
        if (precise_z_height < rhs.precise_z_height)
            return true;
        if (!(precise_z_height == rhs.precise_z_height))
            return false;
        if (default_junction_deviation < rhs.default_junction_deviation)
            return true;
        if (!(default_junction_deviation == rhs.default_junction_deviation))
            return false;
        if (interlocking_beam < rhs.interlocking_beam)
            return true;
        if (!(interlocking_beam == rhs.interlocking_beam))
            return false;
        if (interlocking_beam_width < rhs.interlocking_beam_width)
            return true;
        if (!(interlocking_beam_width == rhs.interlocking_beam_width))
            return false;
        if (interlocking_orientation < rhs.interlocking_orientation)
            return true;
        if (!(interlocking_orientation == rhs.interlocking_orientation))
            return false;
        if (interlocking_beam_layer_count < rhs.interlocking_beam_layer_count)
            return true;
        if (!(interlocking_beam_layer_count == rhs.interlocking_beam_layer_count))
            return false;
        if (interlocking_depth < rhs.interlocking_depth)
            return true;
        if (!(interlocking_depth == rhs.interlocking_depth))
            return false;
        if (interlocking_boundary_avoidance < rhs.interlocking_boundary_avoidance)
            return true;
        if (!(interlocking_boundary_avoidance == rhs.interlocking_boundary_avoidance))
            return false;
        if (calib_flowrate_topinfill_special_order < rhs.calib_flowrate_topinfill_special_order)
            return true;
        if (!(calib_flowrate_topinfill_special_order == rhs.calib_flowrate_topinfill_special_order))
            return false;
        return false;
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("brim_object_gap", base_ptr, this->brim_object_gap);
        cache.opt_add("brim_flow_ratio", base_ptr, this->brim_flow_ratio);
        cache.opt_add("brim_use_efc_outline", base_ptr, this->brim_use_efc_outline);
        cache.opt_add("brim_type", base_ptr, this->brim_type);
        cache.opt_add("brim_width", base_ptr, this->brim_width);
        cache.opt_add("brim_ears_detection_length", base_ptr, this->brim_ears_detection_length);
        cache.opt_add("brim_ears_max_angle", base_ptr, this->brim_ears_max_angle);
        cache.opt_add("skirt_start_angle", base_ptr, this->skirt_start_angle);
        cache.opt_add("bridge_no_support", base_ptr, this->bridge_no_support);
        cache.opt_add("elefant_foot_compensation", base_ptr, this->elefant_foot_compensation);
        cache.opt_add("elefant_foot_compensation_layers", base_ptr, this->elefant_foot_compensation_layers);
        cache.opt_add("elefant_foot_layers_density", base_ptr, this->elefant_foot_layers_density);
        cache.opt_add("max_bridge_length", base_ptr, this->max_bridge_length);
        cache.opt_add("line_width", base_ptr, this->line_width);
        cache.opt_add("interface_shells", base_ptr, this->interface_shells);
        cache.opt_add("layer_height", base_ptr, this->layer_height);
        cache.opt_add("mmu_segmented_region_max_width", base_ptr, this->mmu_segmented_region_max_width);
        cache.opt_add("mmu_segmented_region_interlocking_depth", base_ptr, this->mmu_segmented_region_interlocking_depth);
        cache.opt_add("raft_contact_distance", base_ptr, this->raft_contact_distance);
        cache.opt_add("raft_expansion", base_ptr, this->raft_expansion);
        cache.opt_add("raft_first_layer_density", base_ptr, this->raft_first_layer_density);
        cache.opt_add("raft_first_layer_expansion", base_ptr, this->raft_first_layer_expansion);
        cache.opt_add("raft_layers", base_ptr, this->raft_layers);
        cache.opt_add("seam_position", base_ptr, this->seam_position);
        cache.opt_add("staggered_inner_seams", base_ptr, this->staggered_inner_seams);
        cache.opt_add("slice_closing_radius", base_ptr, this->slice_closing_radius);
        cache.opt_add("slicing_mode", base_ptr, this->slicing_mode);
        cache.opt_add("enable_support", base_ptr, this->enable_support);
        cache.opt_add("support_type", base_ptr, this->support_type);
        cache.opt_add("tinman_support_strategy", base_ptr, this->tinman_support_strategy);
        cache.opt_add("arc_support_payload", base_ptr, this->arc_support_payload);
        cache.opt_add("arc_support_experimental", base_ptr, this->arc_support_experimental);
        cache.opt_add("strength_lens_enabled", base_ptr, this->strength_lens_enabled);
        cache.opt_add("strength_lens_material_model", base_ptr, this->strength_lens_material_model);
        cache.opt_add("strength_lens_load_axis", base_ptr, this->strength_lens_load_axis);
        cache.opt_add("strength_lens_payload", base_ptr, this->strength_lens_payload);
        cache.opt_add("support_angle", base_ptr, this->support_angle);
        cache.opt_add("support_on_build_plate_only", base_ptr, this->support_on_build_plate_only);
        cache.opt_add("support_critical_regions_only", base_ptr, this->support_critical_regions_only);
        cache.opt_add("support_remove_small_overhang", base_ptr, this->support_remove_small_overhang);
        cache.opt_add("support_top_z_distance", base_ptr, this->support_top_z_distance);
        cache.opt_add("support_bottom_z_distance", base_ptr, this->support_bottom_z_distance);
        cache.opt_add("enforce_support_layers", base_ptr, this->enforce_support_layers);
        cache.opt_add("support_filament", base_ptr, this->support_filament);
        cache.opt_add("support_line_width", base_ptr, this->support_line_width);
        cache.opt_add("support_interface_not_for_body", base_ptr, this->support_interface_not_for_body);
        cache.opt_add("support_interface_loop_pattern", base_ptr, this->support_interface_loop_pattern);
        cache.opt_add("support_interface_filament", base_ptr, this->support_interface_filament);
        cache.opt_add("support_interface_top_layers", base_ptr, this->support_interface_top_layers);
        cache.opt_add("support_interface_bottom_layers", base_ptr, this->support_interface_bottom_layers);
        cache.opt_add("support_interface_spacing", base_ptr, this->support_interface_spacing);
        cache.opt_add("support_interface_speed", base_ptr, this->support_interface_speed);
        cache.opt_add("support_base_pattern", base_ptr, this->support_base_pattern);
        cache.opt_add("support_interface_pattern", base_ptr, this->support_interface_pattern);
        cache.opt_add("support_base_pattern_spacing", base_ptr, this->support_base_pattern_spacing);
        cache.opt_add("support_expansion", base_ptr, this->support_expansion);
        cache.opt_add("support_speed", base_ptr, this->support_speed);
        cache.opt_add("support_style", base_ptr, this->support_style);
        cache.opt_add("set_other_flow_ratios", base_ptr, this->set_other_flow_ratios);
        cache.opt_add("support_flow_ratio", base_ptr, this->support_flow_ratio);
        cache.opt_add("support_interface_flow_ratio", base_ptr, this->support_interface_flow_ratio);
        cache.opt_add("independent_support_layer_height", base_ptr, this->independent_support_layer_height);
        cache.opt_add("thick_bridges", base_ptr, this->thick_bridges);
        cache.opt_add("thick_internal_bridges", base_ptr, this->thick_internal_bridges);
        cache.opt_add("dont_filter_internal_bridges", base_ptr, this->dont_filter_internal_bridges);
        cache.opt_add("enable_extra_bridge_layer", base_ptr, this->enable_extra_bridge_layer);
        cache.opt_add("internal_bridge_density", base_ptr, this->internal_bridge_density);
        cache.opt_add("support_threshold_angle", base_ptr, this->support_threshold_angle);
        cache.opt_add("support_threshold_overlap", base_ptr, this->support_threshold_overlap);
        cache.opt_add("support_object_xy_distance", base_ptr, this->support_object_xy_distance);
        cache.opt_add("support_object_first_layer_gap", base_ptr, this->support_object_first_layer_gap);
        cache.opt_add("support_ironing", base_ptr, this->support_ironing);
        cache.opt_add("support_ironing_pattern", base_ptr, this->support_ironing_pattern);
        cache.opt_add("support_ironing_flow", base_ptr, this->support_ironing_flow);
        cache.opt_add("support_ironing_spacing", base_ptr, this->support_ironing_spacing);
        cache.opt_add("xy_hole_compensation", base_ptr, this->xy_hole_compensation);
        cache.opt_add("xy_contour_compensation", base_ptr, this->xy_contour_compensation);
        cache.opt_add("flush_into_objects", base_ptr, this->flush_into_objects);
        cache.opt_add("flush_into_infill", base_ptr, this->flush_into_infill);
        cache.opt_add("flush_into_support", base_ptr, this->flush_into_support);
        cache.opt_add("tree_support_branch_distance", base_ptr, this->tree_support_branch_distance);
        cache.opt_add("tree_support_tip_diameter", base_ptr, this->tree_support_tip_diameter);
        cache.opt_add("tree_support_branch_diameter", base_ptr, this->tree_support_branch_diameter);
        cache.opt_add("tree_support_branch_angle", base_ptr, this->tree_support_branch_angle);
        cache.opt_add("tree_support_branch_diameter_angle", base_ptr, this->tree_support_branch_diameter_angle);
        cache.opt_add("tree_support_angle_slow", base_ptr, this->tree_support_angle_slow);
        cache.opt_add("tree_support_wall_count", base_ptr, this->tree_support_wall_count);
        cache.opt_add("tree_support_auto_brim", base_ptr, this->tree_support_auto_brim);
        cache.opt_add("tree_support_brim_width", base_ptr, this->tree_support_brim_width);
        cache.opt_add("detect_narrow_internal_solid_infill", base_ptr, this->detect_narrow_internal_solid_infill);
        cache.opt_add("adaptive_layer_height", base_ptr, this->adaptive_layer_height);
        cache.opt_add("support_bottom_interface_spacing", base_ptr, this->support_bottom_interface_spacing);
        cache.opt_add("wall_generator", base_ptr, this->wall_generator);
        cache.opt_add("wall_transition_length", base_ptr, this->wall_transition_length);
        cache.opt_add("wall_transition_filter_deviation", base_ptr, this->wall_transition_filter_deviation);
        cache.opt_add("wall_transition_angle", base_ptr, this->wall_transition_angle);
        cache.opt_add("wall_distribution_count", base_ptr, this->wall_distribution_count);
        cache.opt_add("min_feature_size", base_ptr, this->min_feature_size);
        cache.opt_add("initial_layer_min_bead_width", base_ptr, this->initial_layer_min_bead_width);
        cache.opt_add("min_bead_width", base_ptr, this->min_bead_width);
        cache.opt_add("wall_maximum_resolution", base_ptr, this->wall_maximum_resolution);
        cache.opt_add("wall_maximum_deviation", base_ptr, this->wall_maximum_deviation);
        cache.opt_add("make_overhang_printable_angle", base_ptr, this->make_overhang_printable_angle);
        cache.opt_add("make_overhang_printable_hole_size", base_ptr, this->make_overhang_printable_hole_size);
        cache.opt_add("tree_support_branch_distance_organic", base_ptr, this->tree_support_branch_distance_organic);
        cache.opt_add("tree_support_top_rate", base_ptr, this->tree_support_top_rate);
        cache.opt_add("tree_support_branch_diameter_organic", base_ptr, this->tree_support_branch_diameter_organic);
        cache.opt_add("tree_support_branch_angle_organic", base_ptr, this->tree_support_branch_angle_organic);
        cache.opt_add("gap_fill_target", base_ptr, this->gap_fill_target);
        cache.opt_add("min_length_factor", base_ptr, this->min_length_factor);
        cache.opt_add("default_acceleration", base_ptr, this->default_acceleration);
        cache.opt_add("outer_wall_acceleration", base_ptr, this->outer_wall_acceleration);
        cache.opt_add("inner_wall_acceleration", base_ptr, this->inner_wall_acceleration);
        cache.opt_add("top_surface_acceleration", base_ptr, this->top_surface_acceleration);
        cache.opt_add("initial_layer_acceleration", base_ptr, this->initial_layer_acceleration);
        cache.opt_add("bridge_acceleration", base_ptr, this->bridge_acceleration);
        cache.opt_add("travel_acceleration", base_ptr, this->travel_acceleration);
        cache.opt_add("sparse_infill_acceleration", base_ptr, this->sparse_infill_acceleration);
        cache.opt_add("internal_solid_infill_acceleration", base_ptr, this->internal_solid_infill_acceleration);
        cache.opt_add("default_jerk", base_ptr, this->default_jerk);
        cache.opt_add("outer_wall_jerk", base_ptr, this->outer_wall_jerk);
        cache.opt_add("inner_wall_jerk", base_ptr, this->inner_wall_jerk);
        cache.opt_add("infill_jerk", base_ptr, this->infill_jerk);
        cache.opt_add("top_surface_jerk", base_ptr, this->top_surface_jerk);
        cache.opt_add("initial_layer_jerk", base_ptr, this->initial_layer_jerk);
        cache.opt_add("travel_jerk", base_ptr, this->travel_jerk);
        cache.opt_add("precise_z_height", base_ptr, this->precise_z_height);
        cache.opt_add("default_junction_deviation", base_ptr, this->default_junction_deviation);
        cache.opt_add("interlocking_beam", base_ptr, this->interlocking_beam);
        cache.opt_add("interlocking_beam_width", base_ptr, this->interlocking_beam_width);
        cache.opt_add("interlocking_orientation", base_ptr, this->interlocking_orientation);
        cache.opt_add("interlocking_beam_layer_count", base_ptr, this->interlocking_beam_layer_count);
        cache.opt_add("interlocking_depth", base_ptr, this->interlocking_depth);
        cache.opt_add("interlocking_boundary_avoidance", base_ptr, this->interlocking_boundary_avoidance);
        cache.opt_add("calib_flowrate_topinfill_special_order", base_ptr, this->calib_flowrate_topinfill_special_order);
    }
};


// Core PrintRegion keys. TinManX1 keeps the experimental wave-overhang keys in
// their own base class below so the generated Boost preprocessor sequences stay
// small enough for MSVC.
class PrintRegionCoreConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(PrintRegionCoreConfig)
public:
    ConfigOptionInts print_extruder_id;
    ConfigOptionStrings print_extruder_variant;
    ConfigOptionInt bottom_shell_layers;
    ConfigOptionFloat bottom_shell_thickness;
    ConfigOptionFloat bridge_angle;
    ConfigOptionFloat internal_bridge_angle;
    ConfigOptionBool relative_bridge_angle;
    ConfigOptionFloat bridge_flow;
    ConfigOptionFloatOrPercent bridge_line_width;
    ConfigOptionFloat internal_bridge_flow;
    ConfigOptionFloat bridge_speed;
    ConfigOptionFloatOrPercent internal_bridge_speed;
    ConfigOptionEnum<EnsureVerticalShellThickness> ensure_vertical_shell_thickness;
    ConfigOptionPercent top_surface_density;
    ConfigOptionPercent bottom_surface_density;
    ConfigOptionEnum<InfillPattern> top_surface_pattern;
    ConfigOptionEnum<InfillPattern> bottom_surface_pattern;
    ConfigOptionEnum<InfillPattern> internal_solid_infill_pattern;
    ConfigOptionFloatOrPercent outer_wall_line_width;
    ConfigOptionFloat outer_wall_speed;
    ConfigOptionFloat infill_direction;
    ConfigOptionFloat solid_infill_direction;
    ConfigOptionString solid_infill_rotate_template;
    ConfigOptionBool symmetric_infill_y_axis;
    ConfigOptionFloat infill_shift_step;
    ConfigOptionString sparse_infill_rotate_template;
    ConfigOptionPercent sparse_infill_density;
    ConfigOptionEnum<InfillPattern> sparse_infill_pattern;
    ConfigOptionFloat lateral_lattice_angle_1;
    ConfigOptionFloat lateral_lattice_angle_2;
    ConfigOptionFloat infill_overhang_angle;
    ConfigOptionFloat lightning_overhang_angle;
    ConfigOptionFloat lightning_prune_angle;
    ConfigOptionFloat lightning_straightening_angle;
    ConfigOptionBool align_infill_direction_to_model;
    ConfigOptionString extra_solid_infills;
    ConfigOptionEnum<FuzzySkinType> fuzzy_skin;
    ConfigOptionFloat fuzzy_skin_thickness;
    ConfigOptionFloat fuzzy_skin_point_distance;
    ConfigOptionBool fuzzy_skin_first_layer;
    ConfigOptionEnum<NoiseType> fuzzy_skin_noise_type;
    ConfigOptionEnum<FuzzySkinMode> fuzzy_skin_mode;
    ConfigOptionFloat fuzzy_skin_scale;
    ConfigOptionInt fuzzy_skin_octaves;
    ConfigOptionFloat fuzzy_skin_persistence;
    ConfigOptionInt fuzzy_skin_ripples_per_layer;
    ConfigOptionPercent fuzzy_skin_ripple_offset;
    ConfigOptionInt fuzzy_skin_layers_between_ripple_offset;
    ConfigOptionFloat gap_infill_speed;
    ConfigOptionInt sparse_infill_filament_id;
    ConfigOptionFloatOrPercent sparse_infill_line_width;
    ConfigOptionPercent infill_wall_overlap;
    ConfigOptionPercent top_bottom_infill_wall_overlap;
    ConfigOptionFloat sparse_infill_speed;
    ConfigOptionPercent skeleton_infill_density;
    ConfigOptionPercent skin_infill_density;
    ConfigOptionFloat infill_lock_depth;
    ConfigOptionFloat skin_infill_depth;
    ConfigOptionFloatOrPercent skin_infill_line_width;
    ConfigOptionFloatOrPercent skeleton_infill_line_width;
    ConfigOptionBool infill_combination;
    ConfigOptionFloatOrPercent infill_combination_max_layer_height;
    ConfigOptionInt fill_multiline;
    ConfigOptionBool gyroid_optimized;
    ConfigOptionEnum<IroningType> ironing_type;
    ConfigOptionEnum<InfillPattern> ironing_pattern;
    ConfigOptionPercent ironing_flow;
    ConfigOptionFloat ironing_spacing;
    ConfigOptionFloat ironing_inset;
    ConfigOptionFloat ironing_direction;
    ConfigOptionFloat ironing_speed;
    ConfigOptionFloat ironing_angle;
    ConfigOptionBool ironing_angle_fixed;
    ConfigOptionPercentsNullable filament_ironing_flow;
    ConfigOptionFloatsNullable filament_ironing_spacing;
    ConfigOptionFloatsNullable filament_ironing_inset;
    ConfigOptionFloatsNullable filament_ironing_speed;
    ConfigOptionBool detect_overhang_wall;
    ConfigOptionInt outer_wall_filament_id;
    ConfigOptionInt inner_wall_filament_id;
    ConfigOptionFloatOrPercent inner_wall_line_width;
    ConfigOptionFloat inner_wall_speed;
    ConfigOptionInt wall_loops;
    ConfigOptionBool alternate_extra_wall;
    ConfigOptionFloat minimum_sparse_infill_area;
    ConfigOptionInt internal_solid_filament_id;
    ConfigOptionInt top_surface_filament_id;
    ConfigOptionInt bottom_surface_filament_id;
    ConfigOptionFloatOrPercent internal_solid_infill_line_width;
    ConfigOptionFloat internal_solid_infill_speed;
    ConfigOptionBool detect_thin_wall;
    ConfigOptionFloatOrPercent top_surface_line_width;
    ConfigOptionInt top_shell_layers;
    ConfigOptionFloat top_shell_thickness;
    ConfigOptionFloat top_surface_speed;
    ConfigOptionBool enable_overhang_speed;
    ConfigOptionFloatOrPercent overhang_1_4_speed;
    ConfigOptionFloatOrPercent overhang_2_4_speed;
    ConfigOptionFloatOrPercent overhang_3_4_speed;
    ConfigOptionFloatOrPercent overhang_4_4_speed;
    ConfigOptionBool only_one_wall_top;
    ConfigOptionFloatOrPercent min_width_top_surface;
    ConfigOptionBool only_one_wall_first_layer;
    ConfigOptionFloat print_flow_ratio;
    ConfigOptionFloatOrPercent seam_gap;
    ConfigOptionBool role_based_wipe_speed;
    ConfigOptionFloatOrPercent wipe_speed;
    ConfigOptionBool wipe_on_loops;
    ConfigOptionBool wipe_before_external_loop;
    ConfigOptionEnum<WallInfillOrder> wall_infill_order;
    ConfigOptionBool precise_outer_wall;
    ConfigOptionPercent bridge_density;
    ConfigOptionFloat filter_out_gap_fill;
    ConfigOptionFloatOrPercent small_perimeter_speed;
    ConfigOptionFloat small_perimeter_threshold;
    ConfigOptionFloat top_solid_infill_flow_ratio;
    ConfigOptionFloat bottom_solid_infill_flow_ratio;
    ConfigOptionFloatOrPercent infill_anchor;
    ConfigOptionFloatOrPercent infill_anchor_max;
    ConfigOptionBool make_overhang_printable;
    ConfigOptionBool extra_perimeters_on_overhangs;
    ConfigOptionBool slowdown_for_curled_perimeters;
    ConfigOptionBool hole_to_polyhole;
    ConfigOptionFloatOrPercent hole_to_polyhole_threshold;
    ConfigOptionBool hole_to_polyhole_twisted;
    ConfigOptionBool overhang_reverse;
    ConfigOptionBool overhang_reverse_internal_only;
    ConfigOptionFloatOrPercent overhang_reverse_threshold;
    ConfigOptionEnum<CounterboreHoleBridgingOption> counterbore_hole_bridging;
    ConfigOptionEnum<WallSequence> wall_sequence;
    ConfigOptionBool is_infill_first;
    ConfigOptionBool small_area_infill_flow_compensation;
    ConfigOptionEnum<WallDirection> wall_direction;
    ConfigOptionFloat first_layer_flow_ratio;
    ConfigOptionFloat outer_wall_flow_ratio;
    ConfigOptionFloat inner_wall_flow_ratio;
    ConfigOptionFloat overhang_flow_ratio;
    ConfigOptionFloat sparse_infill_flow_ratio;
    ConfigOptionFloat internal_solid_infill_flow_ratio;
    ConfigOptionFloat gap_fill_flow_ratio;
    ConfigOptionEnum<SeamScarfType> seam_slope_type;
    ConfigOptionBool seam_slope_conditional;
    ConfigOptionInt scarf_angle_threshold;
    ConfigOptionFloatOrPercent seam_slope_start_height;
    ConfigOptionBool seam_slope_entire_loop;
    ConfigOptionFloat seam_slope_min_length;
    ConfigOptionInt seam_slope_steps;
    ConfigOptionBool seam_slope_inner_walls;
    ConfigOptionFloatOrPercent scarf_joint_speed;
    ConfigOptionFloat scarf_joint_flow_ratio;
    ConfigOptionPercent scarf_overhang_threshold;
    ConfigOptionBool zaa_enabled;
    ConfigOptionBool zaa_dont_alternate_fill_direction;
    ConfigOptionFloat zaa_min_z;
    ConfigOptionFloat zaa_minimize_perimeter_height;

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, print_extruder_id.hash());
        boost::hash_combine(seed, print_extruder_variant.hash());
        boost::hash_combine(seed, bottom_shell_layers.hash());
        boost::hash_combine(seed, bottom_shell_thickness.hash());
        boost::hash_combine(seed, bridge_angle.hash());
        boost::hash_combine(seed, internal_bridge_angle.hash());
        boost::hash_combine(seed, relative_bridge_angle.hash());
        boost::hash_combine(seed, bridge_flow.hash());
        boost::hash_combine(seed, bridge_line_width.hash());
        boost::hash_combine(seed, internal_bridge_flow.hash());
        boost::hash_combine(seed, bridge_speed.hash());
        boost::hash_combine(seed, internal_bridge_speed.hash());
        boost::hash_combine(seed, ensure_vertical_shell_thickness.hash());
        boost::hash_combine(seed, top_surface_density.hash());
        boost::hash_combine(seed, bottom_surface_density.hash());
        boost::hash_combine(seed, top_surface_pattern.hash());
        boost::hash_combine(seed, bottom_surface_pattern.hash());
        boost::hash_combine(seed, internal_solid_infill_pattern.hash());
        boost::hash_combine(seed, outer_wall_line_width.hash());
        boost::hash_combine(seed, outer_wall_speed.hash());
        boost::hash_combine(seed, infill_direction.hash());
        boost::hash_combine(seed, solid_infill_direction.hash());
        boost::hash_combine(seed, solid_infill_rotate_template.hash());
        boost::hash_combine(seed, symmetric_infill_y_axis.hash());
        boost::hash_combine(seed, infill_shift_step.hash());
        boost::hash_combine(seed, sparse_infill_rotate_template.hash());
        boost::hash_combine(seed, sparse_infill_density.hash());
        boost::hash_combine(seed, sparse_infill_pattern.hash());
        boost::hash_combine(seed, lateral_lattice_angle_1.hash());
        boost::hash_combine(seed, lateral_lattice_angle_2.hash());
        boost::hash_combine(seed, infill_overhang_angle.hash());
        boost::hash_combine(seed, lightning_overhang_angle.hash());
        boost::hash_combine(seed, lightning_prune_angle.hash());
        boost::hash_combine(seed, lightning_straightening_angle.hash());
        boost::hash_combine(seed, align_infill_direction_to_model.hash());
        boost::hash_combine(seed, extra_solid_infills.hash());
        boost::hash_combine(seed, fuzzy_skin.hash());
        boost::hash_combine(seed, fuzzy_skin_thickness.hash());
        boost::hash_combine(seed, fuzzy_skin_point_distance.hash());
        boost::hash_combine(seed, fuzzy_skin_first_layer.hash());
        boost::hash_combine(seed, fuzzy_skin_noise_type.hash());
        boost::hash_combine(seed, fuzzy_skin_mode.hash());
        boost::hash_combine(seed, fuzzy_skin_scale.hash());
        boost::hash_combine(seed, fuzzy_skin_octaves.hash());
        boost::hash_combine(seed, fuzzy_skin_persistence.hash());
        boost::hash_combine(seed, fuzzy_skin_ripples_per_layer.hash());
        boost::hash_combine(seed, fuzzy_skin_ripple_offset.hash());
        boost::hash_combine(seed, fuzzy_skin_layers_between_ripple_offset.hash());
        boost::hash_combine(seed, gap_infill_speed.hash());
        boost::hash_combine(seed, sparse_infill_filament_id.hash());
        boost::hash_combine(seed, sparse_infill_line_width.hash());
        boost::hash_combine(seed, infill_wall_overlap.hash());
        boost::hash_combine(seed, top_bottom_infill_wall_overlap.hash());
        boost::hash_combine(seed, sparse_infill_speed.hash());
        boost::hash_combine(seed, skeleton_infill_density.hash());
        boost::hash_combine(seed, skin_infill_density.hash());
        boost::hash_combine(seed, infill_lock_depth.hash());
        boost::hash_combine(seed, skin_infill_depth.hash());
        boost::hash_combine(seed, skin_infill_line_width.hash());
        boost::hash_combine(seed, skeleton_infill_line_width.hash());
        boost::hash_combine(seed, infill_combination.hash());
        boost::hash_combine(seed, infill_combination_max_layer_height.hash());
        boost::hash_combine(seed, fill_multiline.hash());
        boost::hash_combine(seed, gyroid_optimized.hash());
        boost::hash_combine(seed, ironing_type.hash());
        boost::hash_combine(seed, ironing_pattern.hash());
        boost::hash_combine(seed, ironing_flow.hash());
        boost::hash_combine(seed, ironing_spacing.hash());
        boost::hash_combine(seed, ironing_inset.hash());
        boost::hash_combine(seed, ironing_direction.hash());
        boost::hash_combine(seed, ironing_speed.hash());
        boost::hash_combine(seed, ironing_angle.hash());
        boost::hash_combine(seed, ironing_angle_fixed.hash());
        boost::hash_combine(seed, filament_ironing_flow.hash());
        boost::hash_combine(seed, filament_ironing_spacing.hash());
        boost::hash_combine(seed, filament_ironing_inset.hash());
        boost::hash_combine(seed, filament_ironing_speed.hash());
        boost::hash_combine(seed, detect_overhang_wall.hash());
        boost::hash_combine(seed, outer_wall_filament_id.hash());
        boost::hash_combine(seed, inner_wall_filament_id.hash());
        boost::hash_combine(seed, inner_wall_line_width.hash());
        boost::hash_combine(seed, inner_wall_speed.hash());
        boost::hash_combine(seed, wall_loops.hash());
        boost::hash_combine(seed, alternate_extra_wall.hash());
        boost::hash_combine(seed, minimum_sparse_infill_area.hash());
        boost::hash_combine(seed, internal_solid_filament_id.hash());
        boost::hash_combine(seed, top_surface_filament_id.hash());
        boost::hash_combine(seed, bottom_surface_filament_id.hash());
        boost::hash_combine(seed, internal_solid_infill_line_width.hash());
        boost::hash_combine(seed, internal_solid_infill_speed.hash());
        boost::hash_combine(seed, detect_thin_wall.hash());
        boost::hash_combine(seed, top_surface_line_width.hash());
        boost::hash_combine(seed, top_shell_layers.hash());
        boost::hash_combine(seed, top_shell_thickness.hash());
        boost::hash_combine(seed, top_surface_speed.hash());
        boost::hash_combine(seed, enable_overhang_speed.hash());
        boost::hash_combine(seed, overhang_1_4_speed.hash());
        boost::hash_combine(seed, overhang_2_4_speed.hash());
        boost::hash_combine(seed, overhang_3_4_speed.hash());
        boost::hash_combine(seed, overhang_4_4_speed.hash());
        boost::hash_combine(seed, only_one_wall_top.hash());
        boost::hash_combine(seed, min_width_top_surface.hash());
        boost::hash_combine(seed, only_one_wall_first_layer.hash());
        boost::hash_combine(seed, print_flow_ratio.hash());
        boost::hash_combine(seed, seam_gap.hash());
        boost::hash_combine(seed, role_based_wipe_speed.hash());
        boost::hash_combine(seed, wipe_speed.hash());
        boost::hash_combine(seed, wipe_on_loops.hash());
        boost::hash_combine(seed, wipe_before_external_loop.hash());
        boost::hash_combine(seed, wall_infill_order.hash());
        boost::hash_combine(seed, precise_outer_wall.hash());
        boost::hash_combine(seed, bridge_density.hash());
        boost::hash_combine(seed, filter_out_gap_fill.hash());
        boost::hash_combine(seed, small_perimeter_speed.hash());
        boost::hash_combine(seed, small_perimeter_threshold.hash());
        boost::hash_combine(seed, top_solid_infill_flow_ratio.hash());
        boost::hash_combine(seed, bottom_solid_infill_flow_ratio.hash());
        boost::hash_combine(seed, infill_anchor.hash());
        boost::hash_combine(seed, infill_anchor_max.hash());
        boost::hash_combine(seed, make_overhang_printable.hash());
        boost::hash_combine(seed, extra_perimeters_on_overhangs.hash());
        boost::hash_combine(seed, slowdown_for_curled_perimeters.hash());
        boost::hash_combine(seed, hole_to_polyhole.hash());
        boost::hash_combine(seed, hole_to_polyhole_threshold.hash());
        boost::hash_combine(seed, hole_to_polyhole_twisted.hash());
        boost::hash_combine(seed, overhang_reverse.hash());
        boost::hash_combine(seed, overhang_reverse_internal_only.hash());
        boost::hash_combine(seed, overhang_reverse_threshold.hash());
        boost::hash_combine(seed, counterbore_hole_bridging.hash());
        boost::hash_combine(seed, wall_sequence.hash());
        boost::hash_combine(seed, is_infill_first.hash());
        boost::hash_combine(seed, small_area_infill_flow_compensation.hash());
        boost::hash_combine(seed, wall_direction.hash());
        boost::hash_combine(seed, first_layer_flow_ratio.hash());
        boost::hash_combine(seed, outer_wall_flow_ratio.hash());
        boost::hash_combine(seed, inner_wall_flow_ratio.hash());
        boost::hash_combine(seed, overhang_flow_ratio.hash());
        boost::hash_combine(seed, sparse_infill_flow_ratio.hash());
        boost::hash_combine(seed, internal_solid_infill_flow_ratio.hash());
        boost::hash_combine(seed, gap_fill_flow_ratio.hash());
        boost::hash_combine(seed, seam_slope_type.hash());
        boost::hash_combine(seed, seam_slope_conditional.hash());
        boost::hash_combine(seed, scarf_angle_threshold.hash());
        boost::hash_combine(seed, seam_slope_start_height.hash());
        boost::hash_combine(seed, seam_slope_entire_loop.hash());
        boost::hash_combine(seed, seam_slope_min_length.hash());
        boost::hash_combine(seed, seam_slope_steps.hash());
        boost::hash_combine(seed, seam_slope_inner_walls.hash());
        boost::hash_combine(seed, scarf_joint_speed.hash());
        boost::hash_combine(seed, scarf_joint_flow_ratio.hash());
        boost::hash_combine(seed, scarf_overhang_threshold.hash());
        boost::hash_combine(seed, zaa_enabled.hash());
        boost::hash_combine(seed, zaa_dont_alternate_fill_direction.hash());
        boost::hash_combine(seed, zaa_min_z.hash());
        boost::hash_combine(seed, zaa_minimize_perimeter_height.hash());
        return seed;
    }

    bool operator==(const PrintRegionCoreConfig &rhs) const throw()
    {
        if (!(print_extruder_id == rhs.print_extruder_id))
            return false;
        if (!(print_extruder_variant == rhs.print_extruder_variant))
            return false;
        if (!(bottom_shell_layers == rhs.bottom_shell_layers))
            return false;
        if (!(bottom_shell_thickness == rhs.bottom_shell_thickness))
            return false;
        if (!(bridge_angle == rhs.bridge_angle))
            return false;
        if (!(internal_bridge_angle == rhs.internal_bridge_angle))
            return false;
        if (!(relative_bridge_angle == rhs.relative_bridge_angle))
            return false;
        if (!(bridge_flow == rhs.bridge_flow))
            return false;
        if (!(bridge_line_width == rhs.bridge_line_width))
            return false;
        if (!(internal_bridge_flow == rhs.internal_bridge_flow))
            return false;
        if (!(bridge_speed == rhs.bridge_speed))
            return false;
        if (!(internal_bridge_speed == rhs.internal_bridge_speed))
            return false;
        if (!(ensure_vertical_shell_thickness == rhs.ensure_vertical_shell_thickness))
            return false;
        if (!(top_surface_density == rhs.top_surface_density))
            return false;
        if (!(bottom_surface_density == rhs.bottom_surface_density))
            return false;
        if (!(top_surface_pattern == rhs.top_surface_pattern))
            return false;
        if (!(bottom_surface_pattern == rhs.bottom_surface_pattern))
            return false;
        if (!(internal_solid_infill_pattern == rhs.internal_solid_infill_pattern))
            return false;
        if (!(outer_wall_line_width == rhs.outer_wall_line_width))
            return false;
        if (!(outer_wall_speed == rhs.outer_wall_speed))
            return false;
        if (!(infill_direction == rhs.infill_direction))
            return false;
        if (!(solid_infill_direction == rhs.solid_infill_direction))
            return false;
        if (!(solid_infill_rotate_template == rhs.solid_infill_rotate_template))
            return false;
        if (!(symmetric_infill_y_axis == rhs.symmetric_infill_y_axis))
            return false;
        if (!(infill_shift_step == rhs.infill_shift_step))
            return false;
        if (!(sparse_infill_rotate_template == rhs.sparse_infill_rotate_template))
            return false;
        if (!(sparse_infill_density == rhs.sparse_infill_density))
            return false;
        if (!(sparse_infill_pattern == rhs.sparse_infill_pattern))
            return false;
        if (!(lateral_lattice_angle_1 == rhs.lateral_lattice_angle_1))
            return false;
        if (!(lateral_lattice_angle_2 == rhs.lateral_lattice_angle_2))
            return false;
        if (!(infill_overhang_angle == rhs.infill_overhang_angle))
            return false;
        if (!(lightning_overhang_angle == rhs.lightning_overhang_angle))
            return false;
        if (!(lightning_prune_angle == rhs.lightning_prune_angle))
            return false;
        if (!(lightning_straightening_angle == rhs.lightning_straightening_angle))
            return false;
        if (!(align_infill_direction_to_model == rhs.align_infill_direction_to_model))
            return false;
        if (!(extra_solid_infills == rhs.extra_solid_infills))
            return false;
        if (!(fuzzy_skin == rhs.fuzzy_skin))
            return false;
        if (!(fuzzy_skin_thickness == rhs.fuzzy_skin_thickness))
            return false;
        if (!(fuzzy_skin_point_distance == rhs.fuzzy_skin_point_distance))
            return false;
        if (!(fuzzy_skin_first_layer == rhs.fuzzy_skin_first_layer))
            return false;
        if (!(fuzzy_skin_noise_type == rhs.fuzzy_skin_noise_type))
            return false;
        if (!(fuzzy_skin_mode == rhs.fuzzy_skin_mode))
            return false;
        if (!(fuzzy_skin_scale == rhs.fuzzy_skin_scale))
            return false;
        if (!(fuzzy_skin_octaves == rhs.fuzzy_skin_octaves))
            return false;
        if (!(fuzzy_skin_persistence == rhs.fuzzy_skin_persistence))
            return false;
        if (!(fuzzy_skin_ripples_per_layer == rhs.fuzzy_skin_ripples_per_layer))
            return false;
        if (!(fuzzy_skin_ripple_offset == rhs.fuzzy_skin_ripple_offset))
            return false;
        if (!(fuzzy_skin_layers_between_ripple_offset == rhs.fuzzy_skin_layers_between_ripple_offset))
            return false;
        if (!(gap_infill_speed == rhs.gap_infill_speed))
            return false;
        if (!(sparse_infill_filament_id == rhs.sparse_infill_filament_id))
            return false;
        if (!(sparse_infill_line_width == rhs.sparse_infill_line_width))
            return false;
        if (!(infill_wall_overlap == rhs.infill_wall_overlap))
            return false;
        if (!(top_bottom_infill_wall_overlap == rhs.top_bottom_infill_wall_overlap))
            return false;
        if (!(sparse_infill_speed == rhs.sparse_infill_speed))
            return false;
        if (!(skeleton_infill_density == rhs.skeleton_infill_density))
            return false;
        if (!(skin_infill_density == rhs.skin_infill_density))
            return false;
        if (!(infill_lock_depth == rhs.infill_lock_depth))
            return false;
        if (!(skin_infill_depth == rhs.skin_infill_depth))
            return false;
        if (!(skin_infill_line_width == rhs.skin_infill_line_width))
            return false;
        if (!(skeleton_infill_line_width == rhs.skeleton_infill_line_width))
            return false;
        if (!(infill_combination == rhs.infill_combination))
            return false;
        if (!(infill_combination_max_layer_height == rhs.infill_combination_max_layer_height))
            return false;
        if (!(fill_multiline == rhs.fill_multiline))
            return false;
        if (!(gyroid_optimized == rhs.gyroid_optimized))
            return false;
        if (!(ironing_type == rhs.ironing_type))
            return false;
        if (!(ironing_pattern == rhs.ironing_pattern))
            return false;
        if (!(ironing_flow == rhs.ironing_flow))
            return false;
        if (!(ironing_spacing == rhs.ironing_spacing))
            return false;
        if (!(ironing_inset == rhs.ironing_inset))
            return false;
        if (!(ironing_direction == rhs.ironing_direction))
            return false;
        if (!(ironing_speed == rhs.ironing_speed))
            return false;
        if (!(ironing_angle == rhs.ironing_angle))
            return false;
        if (!(ironing_angle_fixed == rhs.ironing_angle_fixed))
            return false;
        if (!(filament_ironing_flow == rhs.filament_ironing_flow))
            return false;
        if (!(filament_ironing_spacing == rhs.filament_ironing_spacing))
            return false;
        if (!(filament_ironing_inset == rhs.filament_ironing_inset))
            return false;
        if (!(filament_ironing_speed == rhs.filament_ironing_speed))
            return false;
        if (!(detect_overhang_wall == rhs.detect_overhang_wall))
            return false;
        if (!(outer_wall_filament_id == rhs.outer_wall_filament_id))
            return false;
        if (!(inner_wall_filament_id == rhs.inner_wall_filament_id))
            return false;
        if (!(inner_wall_line_width == rhs.inner_wall_line_width))
            return false;
        if (!(inner_wall_speed == rhs.inner_wall_speed))
            return false;
        if (!(wall_loops == rhs.wall_loops))
            return false;
        if (!(alternate_extra_wall == rhs.alternate_extra_wall))
            return false;
        if (!(minimum_sparse_infill_area == rhs.minimum_sparse_infill_area))
            return false;
        if (!(internal_solid_filament_id == rhs.internal_solid_filament_id))
            return false;
        if (!(top_surface_filament_id == rhs.top_surface_filament_id))
            return false;
        if (!(bottom_surface_filament_id == rhs.bottom_surface_filament_id))
            return false;
        if (!(internal_solid_infill_line_width == rhs.internal_solid_infill_line_width))
            return false;
        if (!(internal_solid_infill_speed == rhs.internal_solid_infill_speed))
            return false;
        if (!(detect_thin_wall == rhs.detect_thin_wall))
            return false;
        if (!(top_surface_line_width == rhs.top_surface_line_width))
            return false;
        if (!(top_shell_layers == rhs.top_shell_layers))
            return false;
        if (!(top_shell_thickness == rhs.top_shell_thickness))
            return false;
        if (!(top_surface_speed == rhs.top_surface_speed))
            return false;
        if (!(enable_overhang_speed == rhs.enable_overhang_speed))
            return false;
        if (!(overhang_1_4_speed == rhs.overhang_1_4_speed))
            return false;
        if (!(overhang_2_4_speed == rhs.overhang_2_4_speed))
            return false;
        if (!(overhang_3_4_speed == rhs.overhang_3_4_speed))
            return false;
        if (!(overhang_4_4_speed == rhs.overhang_4_4_speed))
            return false;
        if (!(only_one_wall_top == rhs.only_one_wall_top))
            return false;
        if (!(min_width_top_surface == rhs.min_width_top_surface))
            return false;
        if (!(only_one_wall_first_layer == rhs.only_one_wall_first_layer))
            return false;
        if (!(print_flow_ratio == rhs.print_flow_ratio))
            return false;
        if (!(seam_gap == rhs.seam_gap))
            return false;
        if (!(role_based_wipe_speed == rhs.role_based_wipe_speed))
            return false;
        if (!(wipe_speed == rhs.wipe_speed))
            return false;
        if (!(wipe_on_loops == rhs.wipe_on_loops))
            return false;
        if (!(wipe_before_external_loop == rhs.wipe_before_external_loop))
            return false;
        if (!(wall_infill_order == rhs.wall_infill_order))
            return false;
        if (!(precise_outer_wall == rhs.precise_outer_wall))
            return false;
        if (!(bridge_density == rhs.bridge_density))
            return false;
        if (!(filter_out_gap_fill == rhs.filter_out_gap_fill))
            return false;
        if (!(small_perimeter_speed == rhs.small_perimeter_speed))
            return false;
        if (!(small_perimeter_threshold == rhs.small_perimeter_threshold))
            return false;
        if (!(top_solid_infill_flow_ratio == rhs.top_solid_infill_flow_ratio))
            return false;
        if (!(bottom_solid_infill_flow_ratio == rhs.bottom_solid_infill_flow_ratio))
            return false;
        if (!(infill_anchor == rhs.infill_anchor))
            return false;
        if (!(infill_anchor_max == rhs.infill_anchor_max))
            return false;
        if (!(make_overhang_printable == rhs.make_overhang_printable))
            return false;
        if (!(extra_perimeters_on_overhangs == rhs.extra_perimeters_on_overhangs))
            return false;
        if (!(slowdown_for_curled_perimeters == rhs.slowdown_for_curled_perimeters))
            return false;
        if (!(hole_to_polyhole == rhs.hole_to_polyhole))
            return false;
        if (!(hole_to_polyhole_threshold == rhs.hole_to_polyhole_threshold))
            return false;
        if (!(hole_to_polyhole_twisted == rhs.hole_to_polyhole_twisted))
            return false;
        if (!(overhang_reverse == rhs.overhang_reverse))
            return false;
        if (!(overhang_reverse_internal_only == rhs.overhang_reverse_internal_only))
            return false;
        if (!(overhang_reverse_threshold == rhs.overhang_reverse_threshold))
            return false;
        if (!(counterbore_hole_bridging == rhs.counterbore_hole_bridging))
            return false;
        if (!(wall_sequence == rhs.wall_sequence))
            return false;
        if (!(is_infill_first == rhs.is_infill_first))
            return false;
        if (!(small_area_infill_flow_compensation == rhs.small_area_infill_flow_compensation))
            return false;
        if (!(wall_direction == rhs.wall_direction))
            return false;
        if (!(first_layer_flow_ratio == rhs.first_layer_flow_ratio))
            return false;
        if (!(outer_wall_flow_ratio == rhs.outer_wall_flow_ratio))
            return false;
        if (!(inner_wall_flow_ratio == rhs.inner_wall_flow_ratio))
            return false;
        if (!(overhang_flow_ratio == rhs.overhang_flow_ratio))
            return false;
        if (!(sparse_infill_flow_ratio == rhs.sparse_infill_flow_ratio))
            return false;
        if (!(internal_solid_infill_flow_ratio == rhs.internal_solid_infill_flow_ratio))
            return false;
        if (!(gap_fill_flow_ratio == rhs.gap_fill_flow_ratio))
            return false;
        if (!(seam_slope_type == rhs.seam_slope_type))
            return false;
        if (!(seam_slope_conditional == rhs.seam_slope_conditional))
            return false;
        if (!(scarf_angle_threshold == rhs.scarf_angle_threshold))
            return false;
        if (!(seam_slope_start_height == rhs.seam_slope_start_height))
            return false;
        if (!(seam_slope_entire_loop == rhs.seam_slope_entire_loop))
            return false;
        if (!(seam_slope_min_length == rhs.seam_slope_min_length))
            return false;
        if (!(seam_slope_steps == rhs.seam_slope_steps))
            return false;
        if (!(seam_slope_inner_walls == rhs.seam_slope_inner_walls))
            return false;
        if (!(scarf_joint_speed == rhs.scarf_joint_speed))
            return false;
        if (!(scarf_joint_flow_ratio == rhs.scarf_joint_flow_ratio))
            return false;
        if (!(scarf_overhang_threshold == rhs.scarf_overhang_threshold))
            return false;
        if (!(zaa_enabled == rhs.zaa_enabled))
            return false;
        if (!(zaa_dont_alternate_fill_direction == rhs.zaa_dont_alternate_fill_direction))
            return false;
        if (!(zaa_min_z == rhs.zaa_min_z))
            return false;
        if (!(zaa_minimize_perimeter_height == rhs.zaa_minimize_perimeter_height))
            return false;
        return true;
    }

    bool operator!=(const PrintRegionCoreConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const PrintRegionCoreConfig &rhs) const throw()
    {
        if (print_extruder_id < rhs.print_extruder_id)
            return true;
        if (!(print_extruder_id == rhs.print_extruder_id))
            return false;
        if (print_extruder_variant < rhs.print_extruder_variant)
            return true;
        if (!(print_extruder_variant == rhs.print_extruder_variant))
            return false;
        if (bottom_shell_layers < rhs.bottom_shell_layers)
            return true;
        if (!(bottom_shell_layers == rhs.bottom_shell_layers))
            return false;
        if (bottom_shell_thickness < rhs.bottom_shell_thickness)
            return true;
        if (!(bottom_shell_thickness == rhs.bottom_shell_thickness))
            return false;
        if (bridge_angle < rhs.bridge_angle)
            return true;
        if (!(bridge_angle == rhs.bridge_angle))
            return false;
        if (internal_bridge_angle < rhs.internal_bridge_angle)
            return true;
        if (!(internal_bridge_angle == rhs.internal_bridge_angle))
            return false;
        if (relative_bridge_angle < rhs.relative_bridge_angle)
            return true;
        if (!(relative_bridge_angle == rhs.relative_bridge_angle))
            return false;
        if (bridge_flow < rhs.bridge_flow)
            return true;
        if (!(bridge_flow == rhs.bridge_flow))
            return false;
        if (bridge_line_width < rhs.bridge_line_width)
            return true;
        if (!(bridge_line_width == rhs.bridge_line_width))
            return false;
        if (internal_bridge_flow < rhs.internal_bridge_flow)
            return true;
        if (!(internal_bridge_flow == rhs.internal_bridge_flow))
            return false;
        if (bridge_speed < rhs.bridge_speed)
            return true;
        if (!(bridge_speed == rhs.bridge_speed))
            return false;
        if (internal_bridge_speed < rhs.internal_bridge_speed)
            return true;
        if (!(internal_bridge_speed == rhs.internal_bridge_speed))
            return false;
        if (ensure_vertical_shell_thickness < rhs.ensure_vertical_shell_thickness)
            return true;
        if (!(ensure_vertical_shell_thickness == rhs.ensure_vertical_shell_thickness))
            return false;
        if (top_surface_density < rhs.top_surface_density)
            return true;
        if (!(top_surface_density == rhs.top_surface_density))
            return false;
        if (bottom_surface_density < rhs.bottom_surface_density)
            return true;
        if (!(bottom_surface_density == rhs.bottom_surface_density))
            return false;
        if (top_surface_pattern < rhs.top_surface_pattern)
            return true;
        if (!(top_surface_pattern == rhs.top_surface_pattern))
            return false;
        if (bottom_surface_pattern < rhs.bottom_surface_pattern)
            return true;
        if (!(bottom_surface_pattern == rhs.bottom_surface_pattern))
            return false;
        if (internal_solid_infill_pattern < rhs.internal_solid_infill_pattern)
            return true;
        if (!(internal_solid_infill_pattern == rhs.internal_solid_infill_pattern))
            return false;
        if (outer_wall_line_width < rhs.outer_wall_line_width)
            return true;
        if (!(outer_wall_line_width == rhs.outer_wall_line_width))
            return false;
        if (outer_wall_speed < rhs.outer_wall_speed)
            return true;
        if (!(outer_wall_speed == rhs.outer_wall_speed))
            return false;
        if (infill_direction < rhs.infill_direction)
            return true;
        if (!(infill_direction == rhs.infill_direction))
            return false;
        if (solid_infill_direction < rhs.solid_infill_direction)
            return true;
        if (!(solid_infill_direction == rhs.solid_infill_direction))
            return false;
        if (solid_infill_rotate_template < rhs.solid_infill_rotate_template)
            return true;
        if (!(solid_infill_rotate_template == rhs.solid_infill_rotate_template))
            return false;
        if (symmetric_infill_y_axis < rhs.symmetric_infill_y_axis)
            return true;
        if (!(symmetric_infill_y_axis == rhs.symmetric_infill_y_axis))
            return false;
        if (infill_shift_step < rhs.infill_shift_step)
            return true;
        if (!(infill_shift_step == rhs.infill_shift_step))
            return false;
        if (sparse_infill_rotate_template < rhs.sparse_infill_rotate_template)
            return true;
        if (!(sparse_infill_rotate_template == rhs.sparse_infill_rotate_template))
            return false;
        if (sparse_infill_density < rhs.sparse_infill_density)
            return true;
        if (!(sparse_infill_density == rhs.sparse_infill_density))
            return false;
        if (sparse_infill_pattern < rhs.sparse_infill_pattern)
            return true;
        if (!(sparse_infill_pattern == rhs.sparse_infill_pattern))
            return false;
        if (lateral_lattice_angle_1 < rhs.lateral_lattice_angle_1)
            return true;
        if (!(lateral_lattice_angle_1 == rhs.lateral_lattice_angle_1))
            return false;
        if (lateral_lattice_angle_2 < rhs.lateral_lattice_angle_2)
            return true;
        if (!(lateral_lattice_angle_2 == rhs.lateral_lattice_angle_2))
            return false;
        if (infill_overhang_angle < rhs.infill_overhang_angle)
            return true;
        if (!(infill_overhang_angle == rhs.infill_overhang_angle))
            return false;
        if (lightning_overhang_angle < rhs.lightning_overhang_angle)
            return true;
        if (!(lightning_overhang_angle == rhs.lightning_overhang_angle))
            return false;
        if (lightning_prune_angle < rhs.lightning_prune_angle)
            return true;
        if (!(lightning_prune_angle == rhs.lightning_prune_angle))
            return false;
        if (lightning_straightening_angle < rhs.lightning_straightening_angle)
            return true;
        if (!(lightning_straightening_angle == rhs.lightning_straightening_angle))
            return false;
        if (align_infill_direction_to_model < rhs.align_infill_direction_to_model)
            return true;
        if (!(align_infill_direction_to_model == rhs.align_infill_direction_to_model))
            return false;
        if (extra_solid_infills < rhs.extra_solid_infills)
            return true;
        if (!(extra_solid_infills == rhs.extra_solid_infills))
            return false;
        if (fuzzy_skin < rhs.fuzzy_skin)
            return true;
        if (!(fuzzy_skin == rhs.fuzzy_skin))
            return false;
        if (fuzzy_skin_thickness < rhs.fuzzy_skin_thickness)
            return true;
        if (!(fuzzy_skin_thickness == rhs.fuzzy_skin_thickness))
            return false;
        if (fuzzy_skin_point_distance < rhs.fuzzy_skin_point_distance)
            return true;
        if (!(fuzzy_skin_point_distance == rhs.fuzzy_skin_point_distance))
            return false;
        if (fuzzy_skin_first_layer < rhs.fuzzy_skin_first_layer)
            return true;
        if (!(fuzzy_skin_first_layer == rhs.fuzzy_skin_first_layer))
            return false;
        if (fuzzy_skin_noise_type < rhs.fuzzy_skin_noise_type)
            return true;
        if (!(fuzzy_skin_noise_type == rhs.fuzzy_skin_noise_type))
            return false;
        if (fuzzy_skin_mode < rhs.fuzzy_skin_mode)
            return true;
        if (!(fuzzy_skin_mode == rhs.fuzzy_skin_mode))
            return false;
        if (fuzzy_skin_scale < rhs.fuzzy_skin_scale)
            return true;
        if (!(fuzzy_skin_scale == rhs.fuzzy_skin_scale))
            return false;
        if (fuzzy_skin_octaves < rhs.fuzzy_skin_octaves)
            return true;
        if (!(fuzzy_skin_octaves == rhs.fuzzy_skin_octaves))
            return false;
        if (fuzzy_skin_persistence < rhs.fuzzy_skin_persistence)
            return true;
        if (!(fuzzy_skin_persistence == rhs.fuzzy_skin_persistence))
            return false;
        if (fuzzy_skin_ripples_per_layer < rhs.fuzzy_skin_ripples_per_layer)
            return true;
        if (!(fuzzy_skin_ripples_per_layer == rhs.fuzzy_skin_ripples_per_layer))
            return false;
        if (fuzzy_skin_ripple_offset < rhs.fuzzy_skin_ripple_offset)
            return true;
        if (!(fuzzy_skin_ripple_offset == rhs.fuzzy_skin_ripple_offset))
            return false;
        if (fuzzy_skin_layers_between_ripple_offset < rhs.fuzzy_skin_layers_between_ripple_offset)
            return true;
        if (!(fuzzy_skin_layers_between_ripple_offset == rhs.fuzzy_skin_layers_between_ripple_offset))
            return false;
        if (gap_infill_speed < rhs.gap_infill_speed)
            return true;
        if (!(gap_infill_speed == rhs.gap_infill_speed))
            return false;
        if (sparse_infill_filament_id < rhs.sparse_infill_filament_id)
            return true;
        if (!(sparse_infill_filament_id == rhs.sparse_infill_filament_id))
            return false;
        if (sparse_infill_line_width < rhs.sparse_infill_line_width)
            return true;
        if (!(sparse_infill_line_width == rhs.sparse_infill_line_width))
            return false;
        if (infill_wall_overlap < rhs.infill_wall_overlap)
            return true;
        if (!(infill_wall_overlap == rhs.infill_wall_overlap))
            return false;
        if (top_bottom_infill_wall_overlap < rhs.top_bottom_infill_wall_overlap)
            return true;
        if (!(top_bottom_infill_wall_overlap == rhs.top_bottom_infill_wall_overlap))
            return false;
        if (sparse_infill_speed < rhs.sparse_infill_speed)
            return true;
        if (!(sparse_infill_speed == rhs.sparse_infill_speed))
            return false;
        if (skeleton_infill_density < rhs.skeleton_infill_density)
            return true;
        if (!(skeleton_infill_density == rhs.skeleton_infill_density))
            return false;
        if (skin_infill_density < rhs.skin_infill_density)
            return true;
        if (!(skin_infill_density == rhs.skin_infill_density))
            return false;
        if (infill_lock_depth < rhs.infill_lock_depth)
            return true;
        if (!(infill_lock_depth == rhs.infill_lock_depth))
            return false;
        if (skin_infill_depth < rhs.skin_infill_depth)
            return true;
        if (!(skin_infill_depth == rhs.skin_infill_depth))
            return false;
        if (skin_infill_line_width < rhs.skin_infill_line_width)
            return true;
        if (!(skin_infill_line_width == rhs.skin_infill_line_width))
            return false;
        if (skeleton_infill_line_width < rhs.skeleton_infill_line_width)
            return true;
        if (!(skeleton_infill_line_width == rhs.skeleton_infill_line_width))
            return false;
        if (infill_combination < rhs.infill_combination)
            return true;
        if (!(infill_combination == rhs.infill_combination))
            return false;
        if (infill_combination_max_layer_height < rhs.infill_combination_max_layer_height)
            return true;
        if (!(infill_combination_max_layer_height == rhs.infill_combination_max_layer_height))
            return false;
        if (fill_multiline < rhs.fill_multiline)
            return true;
        if (!(fill_multiline == rhs.fill_multiline))
            return false;
        if (gyroid_optimized < rhs.gyroid_optimized)
            return true;
        if (!(gyroid_optimized == rhs.gyroid_optimized))
            return false;
        if (ironing_type < rhs.ironing_type)
            return true;
        if (!(ironing_type == rhs.ironing_type))
            return false;
        if (ironing_pattern < rhs.ironing_pattern)
            return true;
        if (!(ironing_pattern == rhs.ironing_pattern))
            return false;
        if (ironing_flow < rhs.ironing_flow)
            return true;
        if (!(ironing_flow == rhs.ironing_flow))
            return false;
        if (ironing_spacing < rhs.ironing_spacing)
            return true;
        if (!(ironing_spacing == rhs.ironing_spacing))
            return false;
        if (ironing_inset < rhs.ironing_inset)
            return true;
        if (!(ironing_inset == rhs.ironing_inset))
            return false;
        if (ironing_direction < rhs.ironing_direction)
            return true;
        if (!(ironing_direction == rhs.ironing_direction))
            return false;
        if (ironing_speed < rhs.ironing_speed)
            return true;
        if (!(ironing_speed == rhs.ironing_speed))
            return false;
        if (ironing_angle < rhs.ironing_angle)
            return true;
        if (!(ironing_angle == rhs.ironing_angle))
            return false;
        if (ironing_angle_fixed < rhs.ironing_angle_fixed)
            return true;
        if (!(ironing_angle_fixed == rhs.ironing_angle_fixed))
            return false;
        if (filament_ironing_flow < rhs.filament_ironing_flow)
            return true;
        if (!(filament_ironing_flow == rhs.filament_ironing_flow))
            return false;
        if (filament_ironing_spacing < rhs.filament_ironing_spacing)
            return true;
        if (!(filament_ironing_spacing == rhs.filament_ironing_spacing))
            return false;
        if (filament_ironing_inset < rhs.filament_ironing_inset)
            return true;
        if (!(filament_ironing_inset == rhs.filament_ironing_inset))
            return false;
        if (filament_ironing_speed < rhs.filament_ironing_speed)
            return true;
        if (!(filament_ironing_speed == rhs.filament_ironing_speed))
            return false;
        if (detect_overhang_wall < rhs.detect_overhang_wall)
            return true;
        if (!(detect_overhang_wall == rhs.detect_overhang_wall))
            return false;
        if (outer_wall_filament_id < rhs.outer_wall_filament_id)
            return true;
        if (!(outer_wall_filament_id == rhs.outer_wall_filament_id))
            return false;
        if (inner_wall_filament_id < rhs.inner_wall_filament_id)
            return true;
        if (!(inner_wall_filament_id == rhs.inner_wall_filament_id))
            return false;
        if (inner_wall_line_width < rhs.inner_wall_line_width)
            return true;
        if (!(inner_wall_line_width == rhs.inner_wall_line_width))
            return false;
        if (inner_wall_speed < rhs.inner_wall_speed)
            return true;
        if (!(inner_wall_speed == rhs.inner_wall_speed))
            return false;
        if (wall_loops < rhs.wall_loops)
            return true;
        if (!(wall_loops == rhs.wall_loops))
            return false;
        if (alternate_extra_wall < rhs.alternate_extra_wall)
            return true;
        if (!(alternate_extra_wall == rhs.alternate_extra_wall))
            return false;
        if (minimum_sparse_infill_area < rhs.minimum_sparse_infill_area)
            return true;
        if (!(minimum_sparse_infill_area == rhs.minimum_sparse_infill_area))
            return false;
        if (internal_solid_filament_id < rhs.internal_solid_filament_id)
            return true;
        if (!(internal_solid_filament_id == rhs.internal_solid_filament_id))
            return false;
        if (top_surface_filament_id < rhs.top_surface_filament_id)
            return true;
        if (!(top_surface_filament_id == rhs.top_surface_filament_id))
            return false;
        if (bottom_surface_filament_id < rhs.bottom_surface_filament_id)
            return true;
        if (!(bottom_surface_filament_id == rhs.bottom_surface_filament_id))
            return false;
        if (internal_solid_infill_line_width < rhs.internal_solid_infill_line_width)
            return true;
        if (!(internal_solid_infill_line_width == rhs.internal_solid_infill_line_width))
            return false;
        if (internal_solid_infill_speed < rhs.internal_solid_infill_speed)
            return true;
        if (!(internal_solid_infill_speed == rhs.internal_solid_infill_speed))
            return false;
        if (detect_thin_wall < rhs.detect_thin_wall)
            return true;
        if (!(detect_thin_wall == rhs.detect_thin_wall))
            return false;
        if (top_surface_line_width < rhs.top_surface_line_width)
            return true;
        if (!(top_surface_line_width == rhs.top_surface_line_width))
            return false;
        if (top_shell_layers < rhs.top_shell_layers)
            return true;
        if (!(top_shell_layers == rhs.top_shell_layers))
            return false;
        if (top_shell_thickness < rhs.top_shell_thickness)
            return true;
        if (!(top_shell_thickness == rhs.top_shell_thickness))
            return false;
        if (top_surface_speed < rhs.top_surface_speed)
            return true;
        if (!(top_surface_speed == rhs.top_surface_speed))
            return false;
        if (enable_overhang_speed < rhs.enable_overhang_speed)
            return true;
        if (!(enable_overhang_speed == rhs.enable_overhang_speed))
            return false;
        if (overhang_1_4_speed < rhs.overhang_1_4_speed)
            return true;
        if (!(overhang_1_4_speed == rhs.overhang_1_4_speed))
            return false;
        if (overhang_2_4_speed < rhs.overhang_2_4_speed)
            return true;
        if (!(overhang_2_4_speed == rhs.overhang_2_4_speed))
            return false;
        if (overhang_3_4_speed < rhs.overhang_3_4_speed)
            return true;
        if (!(overhang_3_4_speed == rhs.overhang_3_4_speed))
            return false;
        if (overhang_4_4_speed < rhs.overhang_4_4_speed)
            return true;
        if (!(overhang_4_4_speed == rhs.overhang_4_4_speed))
            return false;
        if (only_one_wall_top < rhs.only_one_wall_top)
            return true;
        if (!(only_one_wall_top == rhs.only_one_wall_top))
            return false;
        if (min_width_top_surface < rhs.min_width_top_surface)
            return true;
        if (!(min_width_top_surface == rhs.min_width_top_surface))
            return false;
        if (only_one_wall_first_layer < rhs.only_one_wall_first_layer)
            return true;
        if (!(only_one_wall_first_layer == rhs.only_one_wall_first_layer))
            return false;
        if (print_flow_ratio < rhs.print_flow_ratio)
            return true;
        if (!(print_flow_ratio == rhs.print_flow_ratio))
            return false;
        if (seam_gap < rhs.seam_gap)
            return true;
        if (!(seam_gap == rhs.seam_gap))
            return false;
        if (role_based_wipe_speed < rhs.role_based_wipe_speed)
            return true;
        if (!(role_based_wipe_speed == rhs.role_based_wipe_speed))
            return false;
        if (wipe_speed < rhs.wipe_speed)
            return true;
        if (!(wipe_speed == rhs.wipe_speed))
            return false;
        if (wipe_on_loops < rhs.wipe_on_loops)
            return true;
        if (!(wipe_on_loops == rhs.wipe_on_loops))
            return false;
        if (wipe_before_external_loop < rhs.wipe_before_external_loop)
            return true;
        if (!(wipe_before_external_loop == rhs.wipe_before_external_loop))
            return false;
        if (wall_infill_order < rhs.wall_infill_order)
            return true;
        if (!(wall_infill_order == rhs.wall_infill_order))
            return false;
        if (precise_outer_wall < rhs.precise_outer_wall)
            return true;
        if (!(precise_outer_wall == rhs.precise_outer_wall))
            return false;
        if (bridge_density < rhs.bridge_density)
            return true;
        if (!(bridge_density == rhs.bridge_density))
            return false;
        if (filter_out_gap_fill < rhs.filter_out_gap_fill)
            return true;
        if (!(filter_out_gap_fill == rhs.filter_out_gap_fill))
            return false;
        if (small_perimeter_speed < rhs.small_perimeter_speed)
            return true;
        if (!(small_perimeter_speed == rhs.small_perimeter_speed))
            return false;
        if (small_perimeter_threshold < rhs.small_perimeter_threshold)
            return true;
        if (!(small_perimeter_threshold == rhs.small_perimeter_threshold))
            return false;
        if (top_solid_infill_flow_ratio < rhs.top_solid_infill_flow_ratio)
            return true;
        if (!(top_solid_infill_flow_ratio == rhs.top_solid_infill_flow_ratio))
            return false;
        if (bottom_solid_infill_flow_ratio < rhs.bottom_solid_infill_flow_ratio)
            return true;
        if (!(bottom_solid_infill_flow_ratio == rhs.bottom_solid_infill_flow_ratio))
            return false;
        if (infill_anchor < rhs.infill_anchor)
            return true;
        if (!(infill_anchor == rhs.infill_anchor))
            return false;
        if (infill_anchor_max < rhs.infill_anchor_max)
            return true;
        if (!(infill_anchor_max == rhs.infill_anchor_max))
            return false;
        if (make_overhang_printable < rhs.make_overhang_printable)
            return true;
        if (!(make_overhang_printable == rhs.make_overhang_printable))
            return false;
        if (extra_perimeters_on_overhangs < rhs.extra_perimeters_on_overhangs)
            return true;
        if (!(extra_perimeters_on_overhangs == rhs.extra_perimeters_on_overhangs))
            return false;
        if (slowdown_for_curled_perimeters < rhs.slowdown_for_curled_perimeters)
            return true;
        if (!(slowdown_for_curled_perimeters == rhs.slowdown_for_curled_perimeters))
            return false;
        if (hole_to_polyhole < rhs.hole_to_polyhole)
            return true;
        if (!(hole_to_polyhole == rhs.hole_to_polyhole))
            return false;
        if (hole_to_polyhole_threshold < rhs.hole_to_polyhole_threshold)
            return true;
        if (!(hole_to_polyhole_threshold == rhs.hole_to_polyhole_threshold))
            return false;
        if (hole_to_polyhole_twisted < rhs.hole_to_polyhole_twisted)
            return true;
        if (!(hole_to_polyhole_twisted == rhs.hole_to_polyhole_twisted))
            return false;
        if (overhang_reverse < rhs.overhang_reverse)
            return true;
        if (!(overhang_reverse == rhs.overhang_reverse))
            return false;
        if (overhang_reverse_internal_only < rhs.overhang_reverse_internal_only)
            return true;
        if (!(overhang_reverse_internal_only == rhs.overhang_reverse_internal_only))
            return false;
        if (overhang_reverse_threshold < rhs.overhang_reverse_threshold)
            return true;
        if (!(overhang_reverse_threshold == rhs.overhang_reverse_threshold))
            return false;
        if (counterbore_hole_bridging < rhs.counterbore_hole_bridging)
            return true;
        if (!(counterbore_hole_bridging == rhs.counterbore_hole_bridging))
            return false;
        if (wall_sequence < rhs.wall_sequence)
            return true;
        if (!(wall_sequence == rhs.wall_sequence))
            return false;
        if (is_infill_first < rhs.is_infill_first)
            return true;
        if (!(is_infill_first == rhs.is_infill_first))
            return false;
        if (small_area_infill_flow_compensation < rhs.small_area_infill_flow_compensation)
            return true;
        if (!(small_area_infill_flow_compensation == rhs.small_area_infill_flow_compensation))
            return false;
        if (wall_direction < rhs.wall_direction)
            return true;
        if (!(wall_direction == rhs.wall_direction))
            return false;
        if (first_layer_flow_ratio < rhs.first_layer_flow_ratio)
            return true;
        if (!(first_layer_flow_ratio == rhs.first_layer_flow_ratio))
            return false;
        if (outer_wall_flow_ratio < rhs.outer_wall_flow_ratio)
            return true;
        if (!(outer_wall_flow_ratio == rhs.outer_wall_flow_ratio))
            return false;
        if (inner_wall_flow_ratio < rhs.inner_wall_flow_ratio)
            return true;
        if (!(inner_wall_flow_ratio == rhs.inner_wall_flow_ratio))
            return false;
        if (overhang_flow_ratio < rhs.overhang_flow_ratio)
            return true;
        if (!(overhang_flow_ratio == rhs.overhang_flow_ratio))
            return false;
        if (sparse_infill_flow_ratio < rhs.sparse_infill_flow_ratio)
            return true;
        if (!(sparse_infill_flow_ratio == rhs.sparse_infill_flow_ratio))
            return false;
        if (internal_solid_infill_flow_ratio < rhs.internal_solid_infill_flow_ratio)
            return true;
        if (!(internal_solid_infill_flow_ratio == rhs.internal_solid_infill_flow_ratio))
            return false;
        if (gap_fill_flow_ratio < rhs.gap_fill_flow_ratio)
            return true;
        if (!(gap_fill_flow_ratio == rhs.gap_fill_flow_ratio))
            return false;
        if (seam_slope_type < rhs.seam_slope_type)
            return true;
        if (!(seam_slope_type == rhs.seam_slope_type))
            return false;
        if (seam_slope_conditional < rhs.seam_slope_conditional)
            return true;
        if (!(seam_slope_conditional == rhs.seam_slope_conditional))
            return false;
        if (scarf_angle_threshold < rhs.scarf_angle_threshold)
            return true;
        if (!(scarf_angle_threshold == rhs.scarf_angle_threshold))
            return false;
        if (seam_slope_start_height < rhs.seam_slope_start_height)
            return true;
        if (!(seam_slope_start_height == rhs.seam_slope_start_height))
            return false;
        if (seam_slope_entire_loop < rhs.seam_slope_entire_loop)
            return true;
        if (!(seam_slope_entire_loop == rhs.seam_slope_entire_loop))
            return false;
        if (seam_slope_min_length < rhs.seam_slope_min_length)
            return true;
        if (!(seam_slope_min_length == rhs.seam_slope_min_length))
            return false;
        if (seam_slope_steps < rhs.seam_slope_steps)
            return true;
        if (!(seam_slope_steps == rhs.seam_slope_steps))
            return false;
        if (seam_slope_inner_walls < rhs.seam_slope_inner_walls)
            return true;
        if (!(seam_slope_inner_walls == rhs.seam_slope_inner_walls))
            return false;
        if (scarf_joint_speed < rhs.scarf_joint_speed)
            return true;
        if (!(scarf_joint_speed == rhs.scarf_joint_speed))
            return false;
        if (scarf_joint_flow_ratio < rhs.scarf_joint_flow_ratio)
            return true;
        if (!(scarf_joint_flow_ratio == rhs.scarf_joint_flow_ratio))
            return false;
        if (scarf_overhang_threshold < rhs.scarf_overhang_threshold)
            return true;
        if (!(scarf_overhang_threshold == rhs.scarf_overhang_threshold))
            return false;
        if (zaa_enabled < rhs.zaa_enabled)
            return true;
        if (!(zaa_enabled == rhs.zaa_enabled))
            return false;
        if (zaa_dont_alternate_fill_direction < rhs.zaa_dont_alternate_fill_direction)
            return true;
        if (!(zaa_dont_alternate_fill_direction == rhs.zaa_dont_alternate_fill_direction))
            return false;
        if (zaa_min_z < rhs.zaa_min_z)
            return true;
        if (!(zaa_min_z == rhs.zaa_min_z))
            return false;
        if (zaa_minimize_perimeter_height < rhs.zaa_minimize_perimeter_height)
            return true;
        if (!(zaa_minimize_perimeter_height == rhs.zaa_minimize_perimeter_height))
            return false;
        return false;
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("print_extruder_id", base_ptr, this->print_extruder_id);
        cache.opt_add("print_extruder_variant", base_ptr, this->print_extruder_variant);
        cache.opt_add("bottom_shell_layers", base_ptr, this->bottom_shell_layers);
        cache.opt_add("bottom_shell_thickness", base_ptr, this->bottom_shell_thickness);
        cache.opt_add("bridge_angle", base_ptr, this->bridge_angle);
        cache.opt_add("internal_bridge_angle", base_ptr, this->internal_bridge_angle);
        cache.opt_add("relative_bridge_angle", base_ptr, this->relative_bridge_angle);
        cache.opt_add("bridge_flow", base_ptr, this->bridge_flow);
        cache.opt_add("bridge_line_width", base_ptr, this->bridge_line_width);
        cache.opt_add("internal_bridge_flow", base_ptr, this->internal_bridge_flow);
        cache.opt_add("bridge_speed", base_ptr, this->bridge_speed);
        cache.opt_add("internal_bridge_speed", base_ptr, this->internal_bridge_speed);
        cache.opt_add("ensure_vertical_shell_thickness", base_ptr, this->ensure_vertical_shell_thickness);
        cache.opt_add("top_surface_density", base_ptr, this->top_surface_density);
        cache.opt_add("bottom_surface_density", base_ptr, this->bottom_surface_density);
        cache.opt_add("top_surface_pattern", base_ptr, this->top_surface_pattern);
        cache.opt_add("bottom_surface_pattern", base_ptr, this->bottom_surface_pattern);
        cache.opt_add("internal_solid_infill_pattern", base_ptr, this->internal_solid_infill_pattern);
        cache.opt_add("outer_wall_line_width", base_ptr, this->outer_wall_line_width);
        cache.opt_add("outer_wall_speed", base_ptr, this->outer_wall_speed);
        cache.opt_add("infill_direction", base_ptr, this->infill_direction);
        cache.opt_add("solid_infill_direction", base_ptr, this->solid_infill_direction);
        cache.opt_add("solid_infill_rotate_template", base_ptr, this->solid_infill_rotate_template);
        cache.opt_add("symmetric_infill_y_axis", base_ptr, this->symmetric_infill_y_axis);
        cache.opt_add("infill_shift_step", base_ptr, this->infill_shift_step);
        cache.opt_add("sparse_infill_rotate_template", base_ptr, this->sparse_infill_rotate_template);
        cache.opt_add("sparse_infill_density", base_ptr, this->sparse_infill_density);
        cache.opt_add("sparse_infill_pattern", base_ptr, this->sparse_infill_pattern);
        cache.opt_add("lateral_lattice_angle_1", base_ptr, this->lateral_lattice_angle_1);
        cache.opt_add("lateral_lattice_angle_2", base_ptr, this->lateral_lattice_angle_2);
        cache.opt_add("infill_overhang_angle", base_ptr, this->infill_overhang_angle);
        cache.opt_add("lightning_overhang_angle", base_ptr, this->lightning_overhang_angle);
        cache.opt_add("lightning_prune_angle", base_ptr, this->lightning_prune_angle);
        cache.opt_add("lightning_straightening_angle", base_ptr, this->lightning_straightening_angle);
        cache.opt_add("align_infill_direction_to_model", base_ptr, this->align_infill_direction_to_model);
        cache.opt_add("extra_solid_infills", base_ptr, this->extra_solid_infills);
        cache.opt_add("fuzzy_skin", base_ptr, this->fuzzy_skin);
        cache.opt_add("fuzzy_skin_thickness", base_ptr, this->fuzzy_skin_thickness);
        cache.opt_add("fuzzy_skin_point_distance", base_ptr, this->fuzzy_skin_point_distance);
        cache.opt_add("fuzzy_skin_first_layer", base_ptr, this->fuzzy_skin_first_layer);
        cache.opt_add("fuzzy_skin_noise_type", base_ptr, this->fuzzy_skin_noise_type);
        cache.opt_add("fuzzy_skin_mode", base_ptr, this->fuzzy_skin_mode);
        cache.opt_add("fuzzy_skin_scale", base_ptr, this->fuzzy_skin_scale);
        cache.opt_add("fuzzy_skin_octaves", base_ptr, this->fuzzy_skin_octaves);
        cache.opt_add("fuzzy_skin_persistence", base_ptr, this->fuzzy_skin_persistence);
        cache.opt_add("fuzzy_skin_ripples_per_layer", base_ptr, this->fuzzy_skin_ripples_per_layer);
        cache.opt_add("fuzzy_skin_ripple_offset", base_ptr, this->fuzzy_skin_ripple_offset);
        cache.opt_add("fuzzy_skin_layers_between_ripple_offset", base_ptr, this->fuzzy_skin_layers_between_ripple_offset);
        cache.opt_add("gap_infill_speed", base_ptr, this->gap_infill_speed);
        cache.opt_add("sparse_infill_filament_id", base_ptr, this->sparse_infill_filament_id);
        cache.opt_add("sparse_infill_line_width", base_ptr, this->sparse_infill_line_width);
        cache.opt_add("infill_wall_overlap", base_ptr, this->infill_wall_overlap);
        cache.opt_add("top_bottom_infill_wall_overlap", base_ptr, this->top_bottom_infill_wall_overlap);
        cache.opt_add("sparse_infill_speed", base_ptr, this->sparse_infill_speed);
        cache.opt_add("skeleton_infill_density", base_ptr, this->skeleton_infill_density);
        cache.opt_add("skin_infill_density", base_ptr, this->skin_infill_density);
        cache.opt_add("infill_lock_depth", base_ptr, this->infill_lock_depth);
        cache.opt_add("skin_infill_depth", base_ptr, this->skin_infill_depth);
        cache.opt_add("skin_infill_line_width", base_ptr, this->skin_infill_line_width);
        cache.opt_add("skeleton_infill_line_width", base_ptr, this->skeleton_infill_line_width);
        cache.opt_add("infill_combination", base_ptr, this->infill_combination);
        cache.opt_add("infill_combination_max_layer_height", base_ptr, this->infill_combination_max_layer_height);
        cache.opt_add("fill_multiline", base_ptr, this->fill_multiline);
        cache.opt_add("gyroid_optimized", base_ptr, this->gyroid_optimized);
        cache.opt_add("ironing_type", base_ptr, this->ironing_type);
        cache.opt_add("ironing_pattern", base_ptr, this->ironing_pattern);
        cache.opt_add("ironing_flow", base_ptr, this->ironing_flow);
        cache.opt_add("ironing_spacing", base_ptr, this->ironing_spacing);
        cache.opt_add("ironing_inset", base_ptr, this->ironing_inset);
        cache.opt_add("ironing_direction", base_ptr, this->ironing_direction);
        cache.opt_add("ironing_speed", base_ptr, this->ironing_speed);
        cache.opt_add("ironing_angle", base_ptr, this->ironing_angle);
        cache.opt_add("ironing_angle_fixed", base_ptr, this->ironing_angle_fixed);
        cache.opt_add("filament_ironing_flow", base_ptr, this->filament_ironing_flow);
        cache.opt_add("filament_ironing_spacing", base_ptr, this->filament_ironing_spacing);
        cache.opt_add("filament_ironing_inset", base_ptr, this->filament_ironing_inset);
        cache.opt_add("filament_ironing_speed", base_ptr, this->filament_ironing_speed);
        cache.opt_add("detect_overhang_wall", base_ptr, this->detect_overhang_wall);
        cache.opt_add("outer_wall_filament_id", base_ptr, this->outer_wall_filament_id);
        cache.opt_add("inner_wall_filament_id", base_ptr, this->inner_wall_filament_id);
        cache.opt_add("inner_wall_line_width", base_ptr, this->inner_wall_line_width);
        cache.opt_add("inner_wall_speed", base_ptr, this->inner_wall_speed);
        cache.opt_add("wall_loops", base_ptr, this->wall_loops);
        cache.opt_add("alternate_extra_wall", base_ptr, this->alternate_extra_wall);
        cache.opt_add("minimum_sparse_infill_area", base_ptr, this->minimum_sparse_infill_area);
        cache.opt_add("internal_solid_filament_id", base_ptr, this->internal_solid_filament_id);
        cache.opt_add("top_surface_filament_id", base_ptr, this->top_surface_filament_id);
        cache.opt_add("bottom_surface_filament_id", base_ptr, this->bottom_surface_filament_id);
        cache.opt_add("internal_solid_infill_line_width", base_ptr, this->internal_solid_infill_line_width);
        cache.opt_add("internal_solid_infill_speed", base_ptr, this->internal_solid_infill_speed);
        cache.opt_add("detect_thin_wall", base_ptr, this->detect_thin_wall);
        cache.opt_add("top_surface_line_width", base_ptr, this->top_surface_line_width);
        cache.opt_add("top_shell_layers", base_ptr, this->top_shell_layers);
        cache.opt_add("top_shell_thickness", base_ptr, this->top_shell_thickness);
        cache.opt_add("top_surface_speed", base_ptr, this->top_surface_speed);
        cache.opt_add("enable_overhang_speed", base_ptr, this->enable_overhang_speed);
        cache.opt_add("overhang_1_4_speed", base_ptr, this->overhang_1_4_speed);
        cache.opt_add("overhang_2_4_speed", base_ptr, this->overhang_2_4_speed);
        cache.opt_add("overhang_3_4_speed", base_ptr, this->overhang_3_4_speed);
        cache.opt_add("overhang_4_4_speed", base_ptr, this->overhang_4_4_speed);
        cache.opt_add("only_one_wall_top", base_ptr, this->only_one_wall_top);
        cache.opt_add("min_width_top_surface", base_ptr, this->min_width_top_surface);
        cache.opt_add("only_one_wall_first_layer", base_ptr, this->only_one_wall_first_layer);
        cache.opt_add("print_flow_ratio", base_ptr, this->print_flow_ratio);
        cache.opt_add("seam_gap", base_ptr, this->seam_gap);
        cache.opt_add("role_based_wipe_speed", base_ptr, this->role_based_wipe_speed);
        cache.opt_add("wipe_speed", base_ptr, this->wipe_speed);
        cache.opt_add("wipe_on_loops", base_ptr, this->wipe_on_loops);
        cache.opt_add("wipe_before_external_loop", base_ptr, this->wipe_before_external_loop);
        cache.opt_add("wall_infill_order", base_ptr, this->wall_infill_order);
        cache.opt_add("precise_outer_wall", base_ptr, this->precise_outer_wall);
        cache.opt_add("bridge_density", base_ptr, this->bridge_density);
        cache.opt_add("filter_out_gap_fill", base_ptr, this->filter_out_gap_fill);
        cache.opt_add("small_perimeter_speed", base_ptr, this->small_perimeter_speed);
        cache.opt_add("small_perimeter_threshold", base_ptr, this->small_perimeter_threshold);
        cache.opt_add("top_solid_infill_flow_ratio", base_ptr, this->top_solid_infill_flow_ratio);
        cache.opt_add("bottom_solid_infill_flow_ratio", base_ptr, this->bottom_solid_infill_flow_ratio);
        cache.opt_add("infill_anchor", base_ptr, this->infill_anchor);
        cache.opt_add("infill_anchor_max", base_ptr, this->infill_anchor_max);
        cache.opt_add("make_overhang_printable", base_ptr, this->make_overhang_printable);
        cache.opt_add("extra_perimeters_on_overhangs", base_ptr, this->extra_perimeters_on_overhangs);
        cache.opt_add("slowdown_for_curled_perimeters", base_ptr, this->slowdown_for_curled_perimeters);
        cache.opt_add("hole_to_polyhole", base_ptr, this->hole_to_polyhole);
        cache.opt_add("hole_to_polyhole_threshold", base_ptr, this->hole_to_polyhole_threshold);
        cache.opt_add("hole_to_polyhole_twisted", base_ptr, this->hole_to_polyhole_twisted);
        cache.opt_add("overhang_reverse", base_ptr, this->overhang_reverse);
        cache.opt_add("overhang_reverse_internal_only", base_ptr, this->overhang_reverse_internal_only);
        cache.opt_add("overhang_reverse_threshold", base_ptr, this->overhang_reverse_threshold);
        cache.opt_add("counterbore_hole_bridging", base_ptr, this->counterbore_hole_bridging);
        cache.opt_add("wall_sequence", base_ptr, this->wall_sequence);
        cache.opt_add("is_infill_first", base_ptr, this->is_infill_first);
        cache.opt_add("small_area_infill_flow_compensation", base_ptr, this->small_area_infill_flow_compensation);
        cache.opt_add("wall_direction", base_ptr, this->wall_direction);
        cache.opt_add("first_layer_flow_ratio", base_ptr, this->first_layer_flow_ratio);
        cache.opt_add("outer_wall_flow_ratio", base_ptr, this->outer_wall_flow_ratio);
        cache.opt_add("inner_wall_flow_ratio", base_ptr, this->inner_wall_flow_ratio);
        cache.opt_add("overhang_flow_ratio", base_ptr, this->overhang_flow_ratio);
        cache.opt_add("sparse_infill_flow_ratio", base_ptr, this->sparse_infill_flow_ratio);
        cache.opt_add("internal_solid_infill_flow_ratio", base_ptr, this->internal_solid_infill_flow_ratio);
        cache.opt_add("gap_fill_flow_ratio", base_ptr, this->gap_fill_flow_ratio);
        cache.opt_add("seam_slope_type", base_ptr, this->seam_slope_type);
        cache.opt_add("seam_slope_conditional", base_ptr, this->seam_slope_conditional);
        cache.opt_add("scarf_angle_threshold", base_ptr, this->scarf_angle_threshold);
        cache.opt_add("seam_slope_start_height", base_ptr, this->seam_slope_start_height);
        cache.opt_add("seam_slope_entire_loop", base_ptr, this->seam_slope_entire_loop);
        cache.opt_add("seam_slope_min_length", base_ptr, this->seam_slope_min_length);
        cache.opt_add("seam_slope_steps", base_ptr, this->seam_slope_steps);
        cache.opt_add("seam_slope_inner_walls", base_ptr, this->seam_slope_inner_walls);
        cache.opt_add("scarf_joint_speed", base_ptr, this->scarf_joint_speed);
        cache.opt_add("scarf_joint_flow_ratio", base_ptr, this->scarf_joint_flow_ratio);
        cache.opt_add("scarf_overhang_threshold", base_ptr, this->scarf_overhang_threshold);
        cache.opt_add("zaa_enabled", base_ptr, this->zaa_enabled);
        cache.opt_add("zaa_dont_alternate_fill_direction", base_ptr, this->zaa_dont_alternate_fill_direction);
        cache.opt_add("zaa_min_z", base_ptr, this->zaa_min_z);
        cache.opt_add("zaa_minimize_perimeter_height", base_ptr, this->zaa_minimize_perimeter_height);
    }
};


template <typename Option>
inline void tinman_config_hash_combine(size_t &seed, const Option &option)
{
    boost::hash_combine(seed, option.hash());
}

inline bool tinman_config_equal()
{
    return true;
}

template <typename Option, typename... Rest>
inline bool tinman_config_equal(const Option &lhs, const Option &rhs, const Rest&... rest)
{
    return lhs == rhs && tinman_config_equal(rest...);
}

inline bool tinman_config_less()
{
    return false;
}

template <typename Option, typename... Rest>
inline bool tinman_config_less(const Option &lhs, const Option &rhs, const Rest&... rest)
{
    if (lhs < rhs)
        return true;
    if (!(lhs == rhs))
        return false;
    return tinman_config_less(rest...);
}

// TinManX option groups are written out as plain C++ classes so MSVC does not
// repeatedly expand large generated config macros in every libslic3r source.
class WaveOverhangCoreConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(WaveOverhangCoreConfig)
public:
    ConfigOptionBool wave_overhangs;
    ConfigOptionBool wave_overhangs_instead_of_bridges;
    ConfigOptionInt wave_overhang_outer_perimeters;
    ConfigOptionFloat wave_overhang_perimeter_overlap;
    ConfigOptionFloat wave_overhang_minimum_width;
    ConfigOptionEnum<WaveOverhangPattern> wave_overhang_pattern;
    ConfigOptionFloat wave_overhang_line_spacing;
    ConfigOptionFloat wave_overhang_flow_mm3_per_mm;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, wave_overhangs);
        tinman_config_hash_combine(seed, wave_overhangs_instead_of_bridges);
        tinman_config_hash_combine(seed, wave_overhang_outer_perimeters);
        tinman_config_hash_combine(seed, wave_overhang_perimeter_overlap);
        tinman_config_hash_combine(seed, wave_overhang_minimum_width);
        tinman_config_hash_combine(seed, wave_overhang_pattern);
        tinman_config_hash_combine(seed, wave_overhang_line_spacing);
        tinman_config_hash_combine(seed, wave_overhang_flow_mm3_per_mm);
        return seed;
    }

    bool operator==(const WaveOverhangCoreConfig &rhs) const throw()
    {
        return tinman_config_equal(
            wave_overhangs, rhs.wave_overhangs,
            wave_overhangs_instead_of_bridges, rhs.wave_overhangs_instead_of_bridges,
            wave_overhang_outer_perimeters, rhs.wave_overhang_outer_perimeters,
            wave_overhang_perimeter_overlap, rhs.wave_overhang_perimeter_overlap,
            wave_overhang_minimum_width, rhs.wave_overhang_minimum_width,
            wave_overhang_pattern, rhs.wave_overhang_pattern,
            wave_overhang_line_spacing, rhs.wave_overhang_line_spacing,
            wave_overhang_flow_mm3_per_mm, rhs.wave_overhang_flow_mm3_per_mm);
    }

    bool operator!=(const WaveOverhangCoreConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const WaveOverhangCoreConfig &rhs) const throw()
    {
        return tinman_config_less(
            wave_overhangs, rhs.wave_overhangs,
            wave_overhangs_instead_of_bridges, rhs.wave_overhangs_instead_of_bridges,
            wave_overhang_outer_perimeters, rhs.wave_overhang_outer_perimeters,
            wave_overhang_perimeter_overlap, rhs.wave_overhang_perimeter_overlap,
            wave_overhang_minimum_width, rhs.wave_overhang_minimum_width,
            wave_overhang_pattern, rhs.wave_overhang_pattern,
            wave_overhang_line_spacing, rhs.wave_overhang_line_spacing,
            wave_overhang_flow_mm3_per_mm, rhs.wave_overhang_flow_mm3_per_mm);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("wave_overhangs", base_ptr, this->wave_overhangs);
        cache.opt_add("wave_overhangs_instead_of_bridges", base_ptr, this->wave_overhangs_instead_of_bridges);
        cache.opt_add("wave_overhang_outer_perimeters", base_ptr, this->wave_overhang_outer_perimeters);
        cache.opt_add("wave_overhang_perimeter_overlap", base_ptr, this->wave_overhang_perimeter_overlap);
        cache.opt_add("wave_overhang_minimum_width", base_ptr, this->wave_overhang_minimum_width);
        cache.opt_add("wave_overhang_pattern", base_ptr, this->wave_overhang_pattern);
        cache.opt_add("wave_overhang_line_spacing", base_ptr, this->wave_overhang_line_spacing);
        cache.opt_add("wave_overhang_flow_mm3_per_mm", base_ptr, this->wave_overhang_flow_mm3_per_mm);
    }
};

class WaveOverhangSpeedConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(WaveOverhangSpeedConfig)
public:
    ConfigOptionFloat wave_overhang_print_speed;
    ConfigOptionFloat wave_overhang_perimeter_speed;
    ConfigOptionFloat wave_overhang_travel_speed;
    ConfigOptionInt wave_overhang_fan_speed;
    ConfigOptionInt wave_overhang_floor_layers;
    ConfigOptionBool wave_overhang_floor_use_hilbert;
    ConfigOptionInt wave_overhang_floor_hilbert_layers;
    ConfigOptionInt wave_overhang_floor_hilbert_density;
    ConfigOptionFloat wave_overhang_floor_print_speed;
    ConfigOptionFloat wave_overhang_floor_perimeter_speed;
    ConfigOptionInt wave_overhang_floor_fan_speed;
    ConfigOptionInt wave_overhang_nozzle_temp;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, wave_overhang_print_speed);
        tinman_config_hash_combine(seed, wave_overhang_perimeter_speed);
        tinman_config_hash_combine(seed, wave_overhang_travel_speed);
        tinman_config_hash_combine(seed, wave_overhang_fan_speed);
        tinman_config_hash_combine(seed, wave_overhang_floor_layers);
        tinman_config_hash_combine(seed, wave_overhang_floor_use_hilbert);
        tinman_config_hash_combine(seed, wave_overhang_floor_hilbert_layers);
        tinman_config_hash_combine(seed, wave_overhang_floor_hilbert_density);
        tinman_config_hash_combine(seed, wave_overhang_floor_print_speed);
        tinman_config_hash_combine(seed, wave_overhang_floor_perimeter_speed);
        tinman_config_hash_combine(seed, wave_overhang_floor_fan_speed);
        tinman_config_hash_combine(seed, wave_overhang_nozzle_temp);
        return seed;
    }

    bool operator==(const WaveOverhangSpeedConfig &rhs) const throw()
    {
        return tinman_config_equal(
            wave_overhang_print_speed, rhs.wave_overhang_print_speed,
            wave_overhang_perimeter_speed, rhs.wave_overhang_perimeter_speed,
            wave_overhang_travel_speed, rhs.wave_overhang_travel_speed,
            wave_overhang_fan_speed, rhs.wave_overhang_fan_speed,
            wave_overhang_floor_layers, rhs.wave_overhang_floor_layers,
            wave_overhang_floor_use_hilbert, rhs.wave_overhang_floor_use_hilbert,
            wave_overhang_floor_hilbert_layers, rhs.wave_overhang_floor_hilbert_layers,
            wave_overhang_floor_hilbert_density, rhs.wave_overhang_floor_hilbert_density,
            wave_overhang_floor_print_speed, rhs.wave_overhang_floor_print_speed,
            wave_overhang_floor_perimeter_speed, rhs.wave_overhang_floor_perimeter_speed,
            wave_overhang_floor_fan_speed, rhs.wave_overhang_floor_fan_speed,
            wave_overhang_nozzle_temp, rhs.wave_overhang_nozzle_temp);
    }

    bool operator!=(const WaveOverhangSpeedConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const WaveOverhangSpeedConfig &rhs) const throw()
    {
        return tinman_config_less(
            wave_overhang_print_speed, rhs.wave_overhang_print_speed,
            wave_overhang_perimeter_speed, rhs.wave_overhang_perimeter_speed,
            wave_overhang_travel_speed, rhs.wave_overhang_travel_speed,
            wave_overhang_fan_speed, rhs.wave_overhang_fan_speed,
            wave_overhang_floor_layers, rhs.wave_overhang_floor_layers,
            wave_overhang_floor_use_hilbert, rhs.wave_overhang_floor_use_hilbert,
            wave_overhang_floor_hilbert_layers, rhs.wave_overhang_floor_hilbert_layers,
            wave_overhang_floor_hilbert_density, rhs.wave_overhang_floor_hilbert_density,
            wave_overhang_floor_print_speed, rhs.wave_overhang_floor_print_speed,
            wave_overhang_floor_perimeter_speed, rhs.wave_overhang_floor_perimeter_speed,
            wave_overhang_floor_fan_speed, rhs.wave_overhang_floor_fan_speed,
            wave_overhang_nozzle_temp, rhs.wave_overhang_nozzle_temp);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("wave_overhang_print_speed", base_ptr, this->wave_overhang_print_speed);
        cache.opt_add("wave_overhang_perimeter_speed", base_ptr, this->wave_overhang_perimeter_speed);
        cache.opt_add("wave_overhang_travel_speed", base_ptr, this->wave_overhang_travel_speed);
        cache.opt_add("wave_overhang_fan_speed", base_ptr, this->wave_overhang_fan_speed);
        cache.opt_add("wave_overhang_floor_layers", base_ptr, this->wave_overhang_floor_layers);
        cache.opt_add("wave_overhang_floor_use_hilbert", base_ptr, this->wave_overhang_floor_use_hilbert);
        cache.opt_add("wave_overhang_floor_hilbert_layers", base_ptr, this->wave_overhang_floor_hilbert_layers);
        cache.opt_add("wave_overhang_floor_hilbert_density", base_ptr, this->wave_overhang_floor_hilbert_density);
        cache.opt_add("wave_overhang_floor_print_speed", base_ptr, this->wave_overhang_floor_print_speed);
        cache.opt_add("wave_overhang_floor_perimeter_speed", base_ptr, this->wave_overhang_floor_perimeter_speed);
        cache.opt_add("wave_overhang_floor_fan_speed", base_ptr, this->wave_overhang_floor_fan_speed);
        cache.opt_add("wave_overhang_nozzle_temp", base_ptr, this->wave_overhang_nozzle_temp);
    }
};

class WaveOverhangPlannerConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(WaveOverhangPlannerConfig)
public:
    ConfigOptionFloat wave_overhang_min_wave_time;
    ConfigOptionFloat wave_overhang_min_layer_time;
    ConfigOptionEnum<WaveOverhangAlgorithm> wave_overhang_algorithm;
    ConfigOptionFloat wave_overhang_ring_overlap;
    ConfigOptionFloat wave_overhang_min_angle;
    ConfigOptionEnum<WaveOverhangSpacingMode> wave_overhang_spacing_mode;
    ConfigOptionEnum<WaveOverhangSeamMode> wave_overhang_seam_mode;
    ConfigOptionBool wave_overhang_debug_gcode;
    ConfigOptionFloat wave_overhang_min_length;
    ConfigOptionInt wave_overhang_max_iterations;
    ConfigOptionFloat wave_overhang_min_new_area;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, wave_overhang_min_wave_time);
        tinman_config_hash_combine(seed, wave_overhang_min_layer_time);
        tinman_config_hash_combine(seed, wave_overhang_algorithm);
        tinman_config_hash_combine(seed, wave_overhang_ring_overlap);
        tinman_config_hash_combine(seed, wave_overhang_min_angle);
        tinman_config_hash_combine(seed, wave_overhang_spacing_mode);
        tinman_config_hash_combine(seed, wave_overhang_seam_mode);
        tinman_config_hash_combine(seed, wave_overhang_debug_gcode);
        tinman_config_hash_combine(seed, wave_overhang_min_length);
        tinman_config_hash_combine(seed, wave_overhang_max_iterations);
        tinman_config_hash_combine(seed, wave_overhang_min_new_area);
        return seed;
    }

    bool operator==(const WaveOverhangPlannerConfig &rhs) const throw()
    {
        return tinman_config_equal(
            wave_overhang_min_wave_time, rhs.wave_overhang_min_wave_time,
            wave_overhang_min_layer_time, rhs.wave_overhang_min_layer_time,
            wave_overhang_algorithm, rhs.wave_overhang_algorithm,
            wave_overhang_ring_overlap, rhs.wave_overhang_ring_overlap,
            wave_overhang_min_angle, rhs.wave_overhang_min_angle,
            wave_overhang_spacing_mode, rhs.wave_overhang_spacing_mode,
            wave_overhang_seam_mode, rhs.wave_overhang_seam_mode,
            wave_overhang_debug_gcode, rhs.wave_overhang_debug_gcode,
            wave_overhang_min_length, rhs.wave_overhang_min_length,
            wave_overhang_max_iterations, rhs.wave_overhang_max_iterations,
            wave_overhang_min_new_area, rhs.wave_overhang_min_new_area);
    }

    bool operator!=(const WaveOverhangPlannerConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const WaveOverhangPlannerConfig &rhs) const throw()
    {
        return tinman_config_less(
            wave_overhang_min_wave_time, rhs.wave_overhang_min_wave_time,
            wave_overhang_min_layer_time, rhs.wave_overhang_min_layer_time,
            wave_overhang_algorithm, rhs.wave_overhang_algorithm,
            wave_overhang_ring_overlap, rhs.wave_overhang_ring_overlap,
            wave_overhang_min_angle, rhs.wave_overhang_min_angle,
            wave_overhang_spacing_mode, rhs.wave_overhang_spacing_mode,
            wave_overhang_seam_mode, rhs.wave_overhang_seam_mode,
            wave_overhang_debug_gcode, rhs.wave_overhang_debug_gcode,
            wave_overhang_min_length, rhs.wave_overhang_min_length,
            wave_overhang_max_iterations, rhs.wave_overhang_max_iterations,
            wave_overhang_min_new_area, rhs.wave_overhang_min_new_area);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("wave_overhang_min_wave_time", base_ptr, this->wave_overhang_min_wave_time);
        cache.opt_add("wave_overhang_min_layer_time", base_ptr, this->wave_overhang_min_layer_time);
        cache.opt_add("wave_overhang_algorithm", base_ptr, this->wave_overhang_algorithm);
        cache.opt_add("wave_overhang_ring_overlap", base_ptr, this->wave_overhang_ring_overlap);
        cache.opt_add("wave_overhang_min_angle", base_ptr, this->wave_overhang_min_angle);
        cache.opt_add("wave_overhang_spacing_mode", base_ptr, this->wave_overhang_spacing_mode);
        cache.opt_add("wave_overhang_seam_mode", base_ptr, this->wave_overhang_seam_mode);
        cache.opt_add("wave_overhang_debug_gcode", base_ptr, this->wave_overhang_debug_gcode);
        cache.opt_add("wave_overhang_min_length", base_ptr, this->wave_overhang_min_length);
        cache.opt_add("wave_overhang_max_iterations", base_ptr, this->wave_overhang_max_iterations);
        cache.opt_add("wave_overhang_min_new_area", base_ptr, this->wave_overhang_min_new_area);
    }
};

class WaveOverhangFringeConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(WaveOverhangFringeConfig)
public:
    ConfigOptionFloat wave_overhang_fringe_reinforcement_max_cover_to_real;
    ConfigOptionFloat wave_overhang_fringe_reinforcement_max_cover_area;
    ConfigOptionFloat wave_overhang_fringe_contact_compensation_max_over_cap;
    ConfigOptionBool wave_overhang_corner_taper_enable;
    ConfigOptionFloat wave_overhang_line_spacing_corner;
    ConfigOptionFloat wave_overhang_corner_taper_distance;
    ConfigOptionFloat wave_overhang_corner_angle_threshold;
    ConfigOptionFloat wave_overhang_end_retract_length;
    ConfigOptionBool support_remaining_areas_after_wave_overhangs;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, wave_overhang_fringe_reinforcement_max_cover_to_real);
        tinman_config_hash_combine(seed, wave_overhang_fringe_reinforcement_max_cover_area);
        tinman_config_hash_combine(seed, wave_overhang_fringe_contact_compensation_max_over_cap);
        tinman_config_hash_combine(seed, wave_overhang_corner_taper_enable);
        tinman_config_hash_combine(seed, wave_overhang_line_spacing_corner);
        tinman_config_hash_combine(seed, wave_overhang_corner_taper_distance);
        tinman_config_hash_combine(seed, wave_overhang_corner_angle_threshold);
        tinman_config_hash_combine(seed, wave_overhang_end_retract_length);
        tinman_config_hash_combine(seed, support_remaining_areas_after_wave_overhangs);
        return seed;
    }

    bool operator==(const WaveOverhangFringeConfig &rhs) const throw()
    {
        return tinman_config_equal(
            wave_overhang_fringe_reinforcement_max_cover_to_real, rhs.wave_overhang_fringe_reinforcement_max_cover_to_real,
            wave_overhang_fringe_reinforcement_max_cover_area, rhs.wave_overhang_fringe_reinforcement_max_cover_area,
            wave_overhang_fringe_contact_compensation_max_over_cap, rhs.wave_overhang_fringe_contact_compensation_max_over_cap,
            wave_overhang_corner_taper_enable, rhs.wave_overhang_corner_taper_enable,
            wave_overhang_line_spacing_corner, rhs.wave_overhang_line_spacing_corner,
            wave_overhang_corner_taper_distance, rhs.wave_overhang_corner_taper_distance,
            wave_overhang_corner_angle_threshold, rhs.wave_overhang_corner_angle_threshold,
            wave_overhang_end_retract_length, rhs.wave_overhang_end_retract_length,
            support_remaining_areas_after_wave_overhangs, rhs.support_remaining_areas_after_wave_overhangs);
    }

    bool operator!=(const WaveOverhangFringeConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const WaveOverhangFringeConfig &rhs) const throw()
    {
        return tinman_config_less(
            wave_overhang_fringe_reinforcement_max_cover_to_real, rhs.wave_overhang_fringe_reinforcement_max_cover_to_real,
            wave_overhang_fringe_reinforcement_max_cover_area, rhs.wave_overhang_fringe_reinforcement_max_cover_area,
            wave_overhang_fringe_contact_compensation_max_over_cap, rhs.wave_overhang_fringe_contact_compensation_max_over_cap,
            wave_overhang_corner_taper_enable, rhs.wave_overhang_corner_taper_enable,
            wave_overhang_line_spacing_corner, rhs.wave_overhang_line_spacing_corner,
            wave_overhang_corner_taper_distance, rhs.wave_overhang_corner_taper_distance,
            wave_overhang_corner_angle_threshold, rhs.wave_overhang_corner_angle_threshold,
            wave_overhang_end_retract_length, rhs.wave_overhang_end_retract_length,
            support_remaining_areas_after_wave_overhangs, rhs.support_remaining_areas_after_wave_overhangs);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("wave_overhang_fringe_reinforcement_max_cover_to_real", base_ptr, this->wave_overhang_fringe_reinforcement_max_cover_to_real);
        cache.opt_add("wave_overhang_fringe_reinforcement_max_cover_area", base_ptr, this->wave_overhang_fringe_reinforcement_max_cover_area);
        cache.opt_add("wave_overhang_fringe_contact_compensation_max_over_cap", base_ptr, this->wave_overhang_fringe_contact_compensation_max_over_cap);
        cache.opt_add("wave_overhang_corner_taper_enable", base_ptr, this->wave_overhang_corner_taper_enable);
        cache.opt_add("wave_overhang_line_spacing_corner", base_ptr, this->wave_overhang_line_spacing_corner);
        cache.opt_add("wave_overhang_corner_taper_distance", base_ptr, this->wave_overhang_corner_taper_distance);
        cache.opt_add("wave_overhang_corner_angle_threshold", base_ptr, this->wave_overhang_corner_angle_threshold);
        cache.opt_add("wave_overhang_end_retract_length", base_ptr, this->wave_overhang_end_retract_length);
        cache.opt_add("support_remaining_areas_after_wave_overhangs", base_ptr, this->support_remaining_areas_after_wave_overhangs);
    }
};

class WaveOverhangRegionConfig : public WaveOverhangCoreConfig, public WaveOverhangSpeedConfig, public WaveOverhangPlannerConfig, public WaveOverhangFringeConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(WaveOverhangRegionConfig)
public:
    WaveOverhangRegionConfig() : WaveOverhangCoreConfig(0), WaveOverhangSpeedConfig(0), WaveOverhangPlannerConfig(0), WaveOverhangFringeConfig(0) { assert(s_cache_WaveOverhangRegionConfig.initialized()); *this = s_cache_WaveOverhangRegionConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const WaveOverhangCoreConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const WaveOverhangSpeedConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const WaveOverhangPlannerConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const WaveOverhangFringeConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const WaveOverhangRegionConfig &rhs) const throw()
    {
        if (!(*static_cast<const WaveOverhangCoreConfig*>(this) == static_cast<const WaveOverhangCoreConfig&>(rhs)))
            return false;
        if (!(*static_cast<const WaveOverhangSpeedConfig*>(this) == static_cast<const WaveOverhangSpeedConfig&>(rhs)))
            return false;
        if (!(*static_cast<const WaveOverhangPlannerConfig*>(this) == static_cast<const WaveOverhangPlannerConfig&>(rhs)))
            return false;
        if (!(*static_cast<const WaveOverhangFringeConfig*>(this) == static_cast<const WaveOverhangFringeConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const WaveOverhangRegionConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const WaveOverhangRegionConfig &rhs) const throw()
    {
        const auto &lhs_core = static_cast<const WaveOverhangCoreConfig&>(*this);
        const auto &rhs_core = static_cast<const WaveOverhangCoreConfig&>(rhs);
        if (lhs_core < rhs_core)
            return true;
        if (!(lhs_core == rhs_core))
            return false;

        const auto &lhs_speed = static_cast<const WaveOverhangSpeedConfig&>(*this);
        const auto &rhs_speed = static_cast<const WaveOverhangSpeedConfig&>(rhs);
        if (lhs_speed < rhs_speed)
            return true;
        if (!(lhs_speed == rhs_speed))
            return false;

        const auto &lhs_planner = static_cast<const WaveOverhangPlannerConfig&>(*this);
        const auto &rhs_planner = static_cast<const WaveOverhangPlannerConfig&>(rhs);
        if (lhs_planner < rhs_planner)
            return true;
        if (!(lhs_planner == rhs_planner))
            return false;

        const auto &lhs_fringe = static_cast<const WaveOverhangFringeConfig&>(*this);
        const auto &rhs_fringe = static_cast<const WaveOverhangFringeConfig&>(rhs);
        if (lhs_fringe < rhs_fringe)
            return true;
        if (!(lhs_fringe == rhs_fringe))
            return false;

        return false;
    }

protected:
    WaveOverhangRegionConfig(int) : WaveOverhangCoreConfig(1), WaveOverhangSpeedConfig(1), WaveOverhangPlannerConfig(1), WaveOverhangFringeConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->WaveOverhangCoreConfig::initialize(cache, base_ptr);
        this->WaveOverhangSpeedConfig::initialize(cache, base_ptr);
        this->WaveOverhangPlannerConfig::initialize(cache, base_ptr);
        this->WaveOverhangFringeConfig::initialize(cache, base_ptr);
    }
};

// This object is mapped to Perl as Slic3r::Config::PrintRegion.
class PrintRegionConfig : public PrintRegionCoreConfig, public WaveOverhangRegionConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(PrintRegionConfig)
public:
    PrintRegionConfig() : PrintRegionCoreConfig(0), WaveOverhangRegionConfig(0) { assert(s_cache_PrintRegionConfig.initialized()); *this = s_cache_PrintRegionConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const PrintRegionCoreConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const WaveOverhangRegionConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const PrintRegionConfig &rhs) const throw()
    {
        if (!(*static_cast<const PrintRegionCoreConfig*>(this) == static_cast<const PrintRegionCoreConfig&>(rhs)))
            return false;
        if (!(*static_cast<const WaveOverhangRegionConfig*>(this) == static_cast<const WaveOverhangRegionConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const PrintRegionConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const PrintRegionConfig &rhs) const throw()
    {
        const auto &lhs_core = static_cast<const PrintRegionCoreConfig&>(*this);
        const auto &rhs_core = static_cast<const PrintRegionCoreConfig&>(rhs);
        if (lhs_core < rhs_core)
            return true;
        if (!(lhs_core == rhs_core))
            return false;

        const auto &lhs_wave = static_cast<const WaveOverhangRegionConfig&>(*this);
        const auto &rhs_wave = static_cast<const WaveOverhangRegionConfig&>(rhs);
        if (lhs_wave < rhs_wave)
            return true;
        if (!(lhs_wave == rhs_wave))
            return false;

        return false;
    }

protected:
    PrintRegionConfig(int) : PrintRegionCoreConfig(1), WaveOverhangRegionConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->PrintRegionCoreConfig::initialize(cache, base_ptr);
        this->WaveOverhangRegionConfig::initialize(cache, base_ptr);
    }
};

class FiberReinforcementModeConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementModeConfig)
public:
    ConfigOptionEnum<FiberManufacturingMode> fiber_manufacturing_mode;
    ConfigOptionEnum<FiberReinforcementMode> fiber_reinforcement_mode;
    ConfigOptionBool fiber_generate_perimeters;
    ConfigOptionBool fiber_generate_infill;
    ConfigOptionInt fiber_start_layer;
    ConfigOptionInt fiber_print_order_code;
    ConfigOptionFloat fiber_min_radius;
    ConfigOptionFloat fiber_max_arc_segment_length;
    ConfigOptionFloat fiber_start_length;
    ConfigOptionFloat fiber_slow_length;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_manufacturing_mode);
        tinman_config_hash_combine(seed, fiber_reinforcement_mode);
        tinman_config_hash_combine(seed, fiber_generate_perimeters);
        tinman_config_hash_combine(seed, fiber_generate_infill);
        tinman_config_hash_combine(seed, fiber_start_layer);
        tinman_config_hash_combine(seed, fiber_print_order_code);
        tinman_config_hash_combine(seed, fiber_min_radius);
        tinman_config_hash_combine(seed, fiber_max_arc_segment_length);
        tinman_config_hash_combine(seed, fiber_start_length);
        tinman_config_hash_combine(seed, fiber_slow_length);
        return seed;
    }

    bool operator==(const FiberReinforcementModeConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_manufacturing_mode, rhs.fiber_manufacturing_mode,
            fiber_reinforcement_mode, rhs.fiber_reinforcement_mode,
            fiber_generate_perimeters, rhs.fiber_generate_perimeters,
            fiber_generate_infill, rhs.fiber_generate_infill,
            fiber_start_layer, rhs.fiber_start_layer,
            fiber_print_order_code, rhs.fiber_print_order_code,
            fiber_min_radius, rhs.fiber_min_radius,
            fiber_max_arc_segment_length, rhs.fiber_max_arc_segment_length,
            fiber_start_length, rhs.fiber_start_length,
            fiber_slow_length, rhs.fiber_slow_length);
    }

    bool operator!=(const FiberReinforcementModeConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementModeConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_manufacturing_mode, rhs.fiber_manufacturing_mode,
            fiber_reinforcement_mode, rhs.fiber_reinforcement_mode,
            fiber_generate_perimeters, rhs.fiber_generate_perimeters,
            fiber_generate_infill, rhs.fiber_generate_infill,
            fiber_start_layer, rhs.fiber_start_layer,
            fiber_print_order_code, rhs.fiber_print_order_code,
            fiber_min_radius, rhs.fiber_min_radius,
            fiber_max_arc_segment_length, rhs.fiber_max_arc_segment_length,
            fiber_start_length, rhs.fiber_start_length,
            fiber_slow_length, rhs.fiber_slow_length);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_manufacturing_mode", base_ptr, this->fiber_manufacturing_mode);
        cache.opt_add("fiber_reinforcement_mode", base_ptr, this->fiber_reinforcement_mode);
        cache.opt_add("fiber_generate_perimeters", base_ptr, this->fiber_generate_perimeters);
        cache.opt_add("fiber_generate_infill", base_ptr, this->fiber_generate_infill);
        cache.opt_add("fiber_start_layer", base_ptr, this->fiber_start_layer);
        cache.opt_add("fiber_print_order_code", base_ptr, this->fiber_print_order_code);
        cache.opt_add("fiber_min_radius", base_ptr, this->fiber_min_radius);
        cache.opt_add("fiber_max_arc_segment_length", base_ptr, this->fiber_max_arc_segment_length);
        cache.opt_add("fiber_start_length", base_ptr, this->fiber_start_length);
        cache.opt_add("fiber_slow_length", base_ptr, this->fiber_slow_length);
    }
};

class FiberReinforcementMotionConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementMotionConfig)
public:
    ConfigOptionFloat fiber_tension_length;
    ConfigOptionFloat fiber_tension_feedrate;
    ConfigOptionFloat fiber_tension_release_fraction;
    ConfigOptionFloat fiber_feedrate_percent;
    ConfigOptionFloat fiber_start_max_speed;
    ConfigOptionFloat fiber_start_min_speed;
    ConfigOptionFloat fiber_start_min_limit_speed;
    ConfigOptionFloat fiber_normal_max_speed;
    ConfigOptionFloat fiber_normal_min_speed;
    ConfigOptionFloat fiber_normal_min_limit_speed;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_tension_length);
        tinman_config_hash_combine(seed, fiber_tension_feedrate);
        tinman_config_hash_combine(seed, fiber_tension_release_fraction);
        tinman_config_hash_combine(seed, fiber_feedrate_percent);
        tinman_config_hash_combine(seed, fiber_start_max_speed);
        tinman_config_hash_combine(seed, fiber_start_min_speed);
        tinman_config_hash_combine(seed, fiber_start_min_limit_speed);
        tinman_config_hash_combine(seed, fiber_normal_max_speed);
        tinman_config_hash_combine(seed, fiber_normal_min_speed);
        tinman_config_hash_combine(seed, fiber_normal_min_limit_speed);
        return seed;
    }

    bool operator==(const FiberReinforcementMotionConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_tension_length, rhs.fiber_tension_length,
            fiber_tension_feedrate, rhs.fiber_tension_feedrate,
            fiber_tension_release_fraction, rhs.fiber_tension_release_fraction,
            fiber_feedrate_percent, rhs.fiber_feedrate_percent,
            fiber_start_max_speed, rhs.fiber_start_max_speed,
            fiber_start_min_speed, rhs.fiber_start_min_speed,
            fiber_start_min_limit_speed, rhs.fiber_start_min_limit_speed,
            fiber_normal_max_speed, rhs.fiber_normal_max_speed,
            fiber_normal_min_speed, rhs.fiber_normal_min_speed,
            fiber_normal_min_limit_speed, rhs.fiber_normal_min_limit_speed);
    }

    bool operator!=(const FiberReinforcementMotionConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementMotionConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_tension_length, rhs.fiber_tension_length,
            fiber_tension_feedrate, rhs.fiber_tension_feedrate,
            fiber_tension_release_fraction, rhs.fiber_tension_release_fraction,
            fiber_feedrate_percent, rhs.fiber_feedrate_percent,
            fiber_start_max_speed, rhs.fiber_start_max_speed,
            fiber_start_min_speed, rhs.fiber_start_min_speed,
            fiber_start_min_limit_speed, rhs.fiber_start_min_limit_speed,
            fiber_normal_max_speed, rhs.fiber_normal_max_speed,
            fiber_normal_min_speed, rhs.fiber_normal_min_speed,
            fiber_normal_min_limit_speed, rhs.fiber_normal_min_limit_speed);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_tension_length", base_ptr, this->fiber_tension_length);
        cache.opt_add("fiber_tension_feedrate", base_ptr, this->fiber_tension_feedrate);
        cache.opt_add("fiber_tension_release_fraction", base_ptr, this->fiber_tension_release_fraction);
        cache.opt_add("fiber_feedrate_percent", base_ptr, this->fiber_feedrate_percent);
        cache.opt_add("fiber_start_max_speed", base_ptr, this->fiber_start_max_speed);
        cache.opt_add("fiber_start_min_speed", base_ptr, this->fiber_start_min_speed);
        cache.opt_add("fiber_start_min_limit_speed", base_ptr, this->fiber_start_min_limit_speed);
        cache.opt_add("fiber_normal_max_speed", base_ptr, this->fiber_normal_max_speed);
        cache.opt_add("fiber_normal_min_speed", base_ptr, this->fiber_normal_min_speed);
        cache.opt_add("fiber_normal_min_limit_speed", base_ptr, this->fiber_normal_min_limit_speed);
    }
};

class FiberReinforcementFinishConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementFinishConfig)
public:
    ConfigOptionFloat fiber_finish_max_speed;
    ConfigOptionFloat fiber_finish_min_speed;
    ConfigOptionFloat fiber_finish_min_limit_speed;
    ConfigOptionBool fiber_override_correction_speed;
    ConfigOptionFloat fiber_correction_move_speed;
    ConfigOptionFloat fiber_correction_move_feedrate_percent;
    ConfigOptionFloat fiber_after_cut_plastic_extrusion_multiplier;
    ConfigOptionBool fiber_z_hop_after_cut;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_finish_max_speed);
        tinman_config_hash_combine(seed, fiber_finish_min_speed);
        tinman_config_hash_combine(seed, fiber_finish_min_limit_speed);
        tinman_config_hash_combine(seed, fiber_override_correction_speed);
        tinman_config_hash_combine(seed, fiber_correction_move_speed);
        tinman_config_hash_combine(seed, fiber_correction_move_feedrate_percent);
        tinman_config_hash_combine(seed, fiber_after_cut_plastic_extrusion_multiplier);
        tinman_config_hash_combine(seed, fiber_z_hop_after_cut);
        return seed;
    }

    bool operator==(const FiberReinforcementFinishConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_finish_max_speed, rhs.fiber_finish_max_speed,
            fiber_finish_min_speed, rhs.fiber_finish_min_speed,
            fiber_finish_min_limit_speed, rhs.fiber_finish_min_limit_speed,
            fiber_override_correction_speed, rhs.fiber_override_correction_speed,
            fiber_correction_move_speed, rhs.fiber_correction_move_speed,
            fiber_correction_move_feedrate_percent, rhs.fiber_correction_move_feedrate_percent,
            fiber_after_cut_plastic_extrusion_multiplier, rhs.fiber_after_cut_plastic_extrusion_multiplier,
            fiber_z_hop_after_cut, rhs.fiber_z_hop_after_cut);
    }

    bool operator!=(const FiberReinforcementFinishConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementFinishConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_finish_max_speed, rhs.fiber_finish_max_speed,
            fiber_finish_min_speed, rhs.fiber_finish_min_speed,
            fiber_finish_min_limit_speed, rhs.fiber_finish_min_limit_speed,
            fiber_override_correction_speed, rhs.fiber_override_correction_speed,
            fiber_correction_move_speed, rhs.fiber_correction_move_speed,
            fiber_correction_move_feedrate_percent, rhs.fiber_correction_move_feedrate_percent,
            fiber_after_cut_plastic_extrusion_multiplier, rhs.fiber_after_cut_plastic_extrusion_multiplier,
            fiber_z_hop_after_cut, rhs.fiber_z_hop_after_cut);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_finish_max_speed", base_ptr, this->fiber_finish_max_speed);
        cache.opt_add("fiber_finish_min_speed", base_ptr, this->fiber_finish_min_speed);
        cache.opt_add("fiber_finish_min_limit_speed", base_ptr, this->fiber_finish_min_limit_speed);
        cache.opt_add("fiber_override_correction_speed", base_ptr, this->fiber_override_correction_speed);
        cache.opt_add("fiber_correction_move_speed", base_ptr, this->fiber_correction_move_speed);
        cache.opt_add("fiber_correction_move_feedrate_percent", base_ptr, this->fiber_correction_move_feedrate_percent);
        cache.opt_add("fiber_after_cut_plastic_extrusion_multiplier", base_ptr, this->fiber_after_cut_plastic_extrusion_multiplier);
        cache.opt_add("fiber_z_hop_after_cut", base_ptr, this->fiber_z_hop_after_cut);
    }
};

class FiberReinforcementHardwareConfig : public FiberReinforcementModeConfig, public FiberReinforcementMotionConfig, public FiberReinforcementFinishConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(FiberReinforcementHardwareConfig)
public:
    FiberReinforcementHardwareConfig() : FiberReinforcementModeConfig(0), FiberReinforcementMotionConfig(0), FiberReinforcementFinishConfig(0) { assert(s_cache_FiberReinforcementHardwareConfig.initialized()); *this = s_cache_FiberReinforcementHardwareConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const FiberReinforcementModeConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementMotionConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementFinishConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const FiberReinforcementHardwareConfig &rhs) const throw()
    {
        if (!(*static_cast<const FiberReinforcementModeConfig*>(this) == static_cast<const FiberReinforcementModeConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementMotionConfig*>(this) == static_cast<const FiberReinforcementMotionConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementFinishConfig*>(this) == static_cast<const FiberReinforcementFinishConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const FiberReinforcementHardwareConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    FiberReinforcementHardwareConfig(int) : FiberReinforcementModeConfig(1), FiberReinforcementMotionConfig(1), FiberReinforcementFinishConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->FiberReinforcementModeConfig::initialize(cache, base_ptr);
        this->FiberReinforcementMotionConfig::initialize(cache, base_ptr);
        this->FiberReinforcementFinishConfig::initialize(cache, base_ptr);
    }
};

class FiberReinforcementInfillConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementInfillConfig)
public:
    ConfigOptionFloat fiber_first_layer_flow_ratio;
    ConfigOptionFloat fiber_first_layer_line_width;
    ConfigOptionFloat fiber_first_layer_height;
    ConfigOptionFloat fiber_first_layer_speed_ratio;
    ConfigOptionEnum<FiberInfillPattern> fiber_infill_pattern;
    ConfigOptionPercent fiber_infill_density;
    ConfigOptionString fiber_infill_angles;
    ConfigOptionEnum<FiberInfillSourcePolicy> fiber_infill_source_policy;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_first_layer_flow_ratio);
        tinman_config_hash_combine(seed, fiber_first_layer_line_width);
        tinman_config_hash_combine(seed, fiber_first_layer_height);
        tinman_config_hash_combine(seed, fiber_first_layer_speed_ratio);
        tinman_config_hash_combine(seed, fiber_infill_pattern);
        tinman_config_hash_combine(seed, fiber_infill_density);
        tinman_config_hash_combine(seed, fiber_infill_angles);
        tinman_config_hash_combine(seed, fiber_infill_source_policy);
        return seed;
    }

    bool operator==(const FiberReinforcementInfillConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_first_layer_flow_ratio, rhs.fiber_first_layer_flow_ratio,
            fiber_first_layer_line_width, rhs.fiber_first_layer_line_width,
            fiber_first_layer_height, rhs.fiber_first_layer_height,
            fiber_first_layer_speed_ratio, rhs.fiber_first_layer_speed_ratio,
            fiber_infill_pattern, rhs.fiber_infill_pattern,
            fiber_infill_density, rhs.fiber_infill_density,
            fiber_infill_angles, rhs.fiber_infill_angles,
            fiber_infill_source_policy, rhs.fiber_infill_source_policy);
    }

    bool operator!=(const FiberReinforcementInfillConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementInfillConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_first_layer_flow_ratio, rhs.fiber_first_layer_flow_ratio,
            fiber_first_layer_line_width, rhs.fiber_first_layer_line_width,
            fiber_first_layer_height, rhs.fiber_first_layer_height,
            fiber_first_layer_speed_ratio, rhs.fiber_first_layer_speed_ratio,
            fiber_infill_pattern, rhs.fiber_infill_pattern,
            fiber_infill_density, rhs.fiber_infill_density,
            fiber_infill_angles, rhs.fiber_infill_angles,
            fiber_infill_source_policy, rhs.fiber_infill_source_policy);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_first_layer_flow_ratio", base_ptr, this->fiber_first_layer_flow_ratio);
        cache.opt_add("fiber_first_layer_line_width", base_ptr, this->fiber_first_layer_line_width);
        cache.opt_add("fiber_first_layer_height", base_ptr, this->fiber_first_layer_height);
        cache.opt_add("fiber_first_layer_speed_ratio", base_ptr, this->fiber_first_layer_speed_ratio);
        cache.opt_add("fiber_infill_pattern", base_ptr, this->fiber_infill_pattern);
        cache.opt_add("fiber_infill_density", base_ptr, this->fiber_infill_density);
        cache.opt_add("fiber_infill_angles", base_ptr, this->fiber_infill_angles);
        cache.opt_add("fiber_infill_source_policy", base_ptr, this->fiber_infill_source_policy);
    }
};

class FiberReinforcementSeamConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementSeamConfig)
public:
    ConfigOptionEnum<FiberSeamPosition> fiber_seam_position;
    ConfigOptionFloat fiber_seam_angle;
    ConfigOptionFloat fiber_line_width;
    ConfigOptionFloat fiber_infill_spacing;
    ConfigOptionFloat fiber_macro_layer_height;
    ConfigOptionInt fiber_layer_step;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_seam_position);
        tinman_config_hash_combine(seed, fiber_seam_angle);
        tinman_config_hash_combine(seed, fiber_line_width);
        tinman_config_hash_combine(seed, fiber_infill_spacing);
        tinman_config_hash_combine(seed, fiber_macro_layer_height);
        tinman_config_hash_combine(seed, fiber_layer_step);
        return seed;
    }

    bool operator==(const FiberReinforcementSeamConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_seam_position, rhs.fiber_seam_position,
            fiber_seam_angle, rhs.fiber_seam_angle,
            fiber_line_width, rhs.fiber_line_width,
            fiber_infill_spacing, rhs.fiber_infill_spacing,
            fiber_macro_layer_height, rhs.fiber_macro_layer_height,
            fiber_layer_step, rhs.fiber_layer_step);
    }

    bool operator!=(const FiberReinforcementSeamConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementSeamConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_seam_position, rhs.fiber_seam_position,
            fiber_seam_angle, rhs.fiber_seam_angle,
            fiber_line_width, rhs.fiber_line_width,
            fiber_infill_spacing, rhs.fiber_infill_spacing,
            fiber_macro_layer_height, rhs.fiber_macro_layer_height,
            fiber_layer_step, rhs.fiber_layer_step);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_seam_position", base_ptr, this->fiber_seam_position);
        cache.opt_add("fiber_seam_angle", base_ptr, this->fiber_seam_angle);
        cache.opt_add("fiber_line_width", base_ptr, this->fiber_line_width);
        cache.opt_add("fiber_infill_spacing", base_ptr, this->fiber_infill_spacing);
        cache.opt_add("fiber_macro_layer_height", base_ptr, this->fiber_macro_layer_height);
        cache.opt_add("fiber_layer_step", base_ptr, this->fiber_layer_step);
    }
};

class FiberReinforcementPatternConfig : public FiberReinforcementInfillConfig, public FiberReinforcementSeamConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(FiberReinforcementPatternConfig)
public:
    FiberReinforcementPatternConfig() : FiberReinforcementInfillConfig(0), FiberReinforcementSeamConfig(0) { assert(s_cache_FiberReinforcementPatternConfig.initialized()); *this = s_cache_FiberReinforcementPatternConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const FiberReinforcementInfillConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementSeamConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const FiberReinforcementPatternConfig &rhs) const throw()
    {
        if (!(*static_cast<const FiberReinforcementInfillConfig*>(this) == static_cast<const FiberReinforcementInfillConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementSeamConfig*>(this) == static_cast<const FiberReinforcementSeamConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const FiberReinforcementPatternConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    FiberReinforcementPatternConfig(int) : FiberReinforcementInfillConfig(1), FiberReinforcementSeamConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->FiberReinforcementInfillConfig::initialize(cache, base_ptr);
        this->FiberReinforcementSeamConfig::initialize(cache, base_ptr);
    }
};

class FiberReinforcementRouteLimitConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementRouteLimitConfig)
public:
    ConfigOptionFloat fiber_min_route_length;
    ConfigOptionFloat fiber_perimeter_min_route_length;
    ConfigOptionFloat fiber_mechanical_min_route_length;
    ConfigOptionFloat fiber_perimeter_inset;
    ConfigOptionFloat fiber_infill_inset;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_min_route_length);
        tinman_config_hash_combine(seed, fiber_perimeter_min_route_length);
        tinman_config_hash_combine(seed, fiber_mechanical_min_route_length);
        tinman_config_hash_combine(seed, fiber_perimeter_inset);
        tinman_config_hash_combine(seed, fiber_infill_inset);
        return seed;
    }

    bool operator==(const FiberReinforcementRouteLimitConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_min_route_length, rhs.fiber_min_route_length,
            fiber_perimeter_min_route_length, rhs.fiber_perimeter_min_route_length,
            fiber_mechanical_min_route_length, rhs.fiber_mechanical_min_route_length,
            fiber_perimeter_inset, rhs.fiber_perimeter_inset,
            fiber_infill_inset, rhs.fiber_infill_inset);
    }

    bool operator!=(const FiberReinforcementRouteLimitConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementRouteLimitConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_min_route_length, rhs.fiber_min_route_length,
            fiber_perimeter_min_route_length, rhs.fiber_perimeter_min_route_length,
            fiber_mechanical_min_route_length, rhs.fiber_mechanical_min_route_length,
            fiber_perimeter_inset, rhs.fiber_perimeter_inset,
            fiber_infill_inset, rhs.fiber_infill_inset);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_min_route_length", base_ptr, this->fiber_min_route_length);
        cache.opt_add("fiber_perimeter_min_route_length", base_ptr, this->fiber_perimeter_min_route_length);
        cache.opt_add("fiber_mechanical_min_route_length", base_ptr, this->fiber_mechanical_min_route_length);
        cache.opt_add("fiber_perimeter_inset", base_ptr, this->fiber_perimeter_inset);
        cache.opt_add("fiber_infill_inset", base_ptr, this->fiber_infill_inset);
    }
};

class FiberReinforcementRouteOutputConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(FiberReinforcementRouteOutputConfig)
public:
    ConfigOptionFloat fiber_print_speed;
    ConfigOptionFloat fiber_start_speed;
    ConfigOptionInt fiber_max_routes_per_layer;
    ConfigOptionInt fiber_routes_per_cut;
    ConfigOptionInt fiber_outer_perimeter_loops;
    ConfigOptionInt fiber_inner_perimeter_loops;
    ConfigOptionInt fiber_plastic_outer_loops_with_fiber;
    ConfigOptionInt fiber_plastic_inner_loops_with_fiber;
    ConfigOptionString fiber_reinforcement_payload;
    ConfigOptionString fiber_infill_solid_payload;

    size_t hash() const throw()
    {
        size_t seed = 0;
        tinman_config_hash_combine(seed, fiber_print_speed);
        tinman_config_hash_combine(seed, fiber_start_speed);
        tinman_config_hash_combine(seed, fiber_max_routes_per_layer);
        tinman_config_hash_combine(seed, fiber_routes_per_cut);
        tinman_config_hash_combine(seed, fiber_outer_perimeter_loops);
        tinman_config_hash_combine(seed, fiber_inner_perimeter_loops);
        tinman_config_hash_combine(seed, fiber_plastic_outer_loops_with_fiber);
        tinman_config_hash_combine(seed, fiber_plastic_inner_loops_with_fiber);
        tinman_config_hash_combine(seed, fiber_reinforcement_payload);
        tinman_config_hash_combine(seed, fiber_infill_solid_payload);
        return seed;
    }

    bool operator==(const FiberReinforcementRouteOutputConfig &rhs) const throw()
    {
        return tinman_config_equal(
            fiber_print_speed, rhs.fiber_print_speed,
            fiber_start_speed, rhs.fiber_start_speed,
            fiber_max_routes_per_layer, rhs.fiber_max_routes_per_layer,
            fiber_routes_per_cut, rhs.fiber_routes_per_cut,
            fiber_outer_perimeter_loops, rhs.fiber_outer_perimeter_loops,
            fiber_inner_perimeter_loops, rhs.fiber_inner_perimeter_loops,
            fiber_plastic_outer_loops_with_fiber, rhs.fiber_plastic_outer_loops_with_fiber,
            fiber_plastic_inner_loops_with_fiber, rhs.fiber_plastic_inner_loops_with_fiber,
            fiber_reinforcement_payload, rhs.fiber_reinforcement_payload,
            fiber_infill_solid_payload, rhs.fiber_infill_solid_payload);
    }

    bool operator!=(const FiberReinforcementRouteOutputConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const FiberReinforcementRouteOutputConfig &rhs) const throw()
    {
        return tinman_config_less(
            fiber_print_speed, rhs.fiber_print_speed,
            fiber_start_speed, rhs.fiber_start_speed,
            fiber_max_routes_per_layer, rhs.fiber_max_routes_per_layer,
            fiber_routes_per_cut, rhs.fiber_routes_per_cut,
            fiber_outer_perimeter_loops, rhs.fiber_outer_perimeter_loops,
            fiber_inner_perimeter_loops, rhs.fiber_inner_perimeter_loops,
            fiber_plastic_outer_loops_with_fiber, rhs.fiber_plastic_outer_loops_with_fiber,
            fiber_plastic_inner_loops_with_fiber, rhs.fiber_plastic_inner_loops_with_fiber,
            fiber_reinforcement_payload, rhs.fiber_reinforcement_payload,
            fiber_infill_solid_payload, rhs.fiber_infill_solid_payload);
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("fiber_print_speed", base_ptr, this->fiber_print_speed);
        cache.opt_add("fiber_start_speed", base_ptr, this->fiber_start_speed);
        cache.opt_add("fiber_max_routes_per_layer", base_ptr, this->fiber_max_routes_per_layer);
        cache.opt_add("fiber_routes_per_cut", base_ptr, this->fiber_routes_per_cut);
        cache.opt_add("fiber_outer_perimeter_loops", base_ptr, this->fiber_outer_perimeter_loops);
        cache.opt_add("fiber_inner_perimeter_loops", base_ptr, this->fiber_inner_perimeter_loops);
        cache.opt_add("fiber_plastic_outer_loops_with_fiber", base_ptr, this->fiber_plastic_outer_loops_with_fiber);
        cache.opt_add("fiber_plastic_inner_loops_with_fiber", base_ptr, this->fiber_plastic_inner_loops_with_fiber);
        cache.opt_add("fiber_reinforcement_payload", base_ptr, this->fiber_reinforcement_payload);
        cache.opt_add("fiber_infill_solid_payload", base_ptr, this->fiber_infill_solid_payload);
    }
};

class FiberReinforcementRoutingConfig : public FiberReinforcementRouteLimitConfig, public FiberReinforcementRouteOutputConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(FiberReinforcementRoutingConfig)
public:
    FiberReinforcementRoutingConfig() : FiberReinforcementRouteLimitConfig(0), FiberReinforcementRouteOutputConfig(0) { assert(s_cache_FiberReinforcementRoutingConfig.initialized()); *this = s_cache_FiberReinforcementRoutingConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const FiberReinforcementRouteLimitConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementRouteOutputConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const FiberReinforcementRoutingConfig &rhs) const throw()
    {
        if (!(*static_cast<const FiberReinforcementRouteLimitConfig*>(this) == static_cast<const FiberReinforcementRouteLimitConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementRouteOutputConfig*>(this) == static_cast<const FiberReinforcementRouteOutputConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const FiberReinforcementRoutingConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    FiberReinforcementRoutingConfig(int) : FiberReinforcementRouteLimitConfig(1), FiberReinforcementRouteOutputConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->FiberReinforcementRouteLimitConfig::initialize(cache, base_ptr);
        this->FiberReinforcementRouteOutputConfig::initialize(cache, base_ptr);
    }
};

class FiberReinforcementConfig : public FiberReinforcementHardwareConfig, public FiberReinforcementPatternConfig, public FiberReinforcementRoutingConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(FiberReinforcementConfig)
public:
    FiberReinforcementConfig() : FiberReinforcementHardwareConfig(0), FiberReinforcementPatternConfig(0), FiberReinforcementRoutingConfig(0) { assert(s_cache_FiberReinforcementConfig.initialized()); *this = s_cache_FiberReinforcementConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const FiberReinforcementHardwareConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementPatternConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementRoutingConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const FiberReinforcementConfig &rhs) const throw()
    {
        if (!(*static_cast<const FiberReinforcementHardwareConfig*>(this) == static_cast<const FiberReinforcementHardwareConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementPatternConfig*>(this) == static_cast<const FiberReinforcementPatternConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementRoutingConfig*>(this) == static_cast<const FiberReinforcementRoutingConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const FiberReinforcementConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    FiberReinforcementConfig(int) : FiberReinforcementHardwareConfig(1), FiberReinforcementPatternConfig(1), FiberReinforcementRoutingConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->FiberReinforcementHardwareConfig::initialize(cache, base_ptr);
        this->FiberReinforcementPatternConfig::initialize(cache, base_ptr);
        this->FiberReinforcementRoutingConfig::initialize(cache, base_ptr);
    }
};

class MachineEnvelopeConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(MachineEnvelopeConfig)
public:
    ConfigOptionBool emit_machine_limits_to_gcode;
    ConfigOptionFloats machine_max_acceleration_x;
    ConfigOptionFloats machine_max_acceleration_y;
    ConfigOptionFloats machine_max_acceleration_z;
    ConfigOptionFloats machine_max_acceleration_e;
    ConfigOptionFloats machine_max_speed_x;
    ConfigOptionFloats machine_max_speed_y;
    ConfigOptionFloats machine_max_speed_z;
    ConfigOptionFloats machine_max_speed_e;
    ConfigOptionFloats machine_max_acceleration_extruding;
    ConfigOptionFloats machine_max_acceleration_retracting;
    ConfigOptionFloats machine_max_acceleration_travel;
    ConfigOptionFloats machine_max_jerk_x;
    ConfigOptionFloats machine_max_jerk_y;
    ConfigOptionFloats machine_max_jerk_z;
    ConfigOptionFloats machine_max_jerk_e;
    ConfigOptionFloats machine_max_junction_deviation;
    ConfigOptionFloats machine_min_travel_rate;
    ConfigOptionFloats machine_min_extruding_rate;
    ConfigOptionBool resonance_avoidance;
    ConfigOptionFloat min_resonance_avoidance_speed;
    ConfigOptionFloat max_resonance_avoidance_speed;
    ConfigOptionBool input_shaping_emit;
    ConfigOptionEnum<InputShaperType> input_shaping_type;
    ConfigOptionFloat input_shaping_freq_x;
    ConfigOptionFloat input_shaping_freq_y;
    ConfigOptionFloat input_shaping_damp_x;
    ConfigOptionFloat input_shaping_damp_y;

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, emit_machine_limits_to_gcode.hash());
        boost::hash_combine(seed, machine_max_acceleration_x.hash());
        boost::hash_combine(seed, machine_max_acceleration_y.hash());
        boost::hash_combine(seed, machine_max_acceleration_z.hash());
        boost::hash_combine(seed, machine_max_acceleration_e.hash());
        boost::hash_combine(seed, machine_max_speed_x.hash());
        boost::hash_combine(seed, machine_max_speed_y.hash());
        boost::hash_combine(seed, machine_max_speed_z.hash());
        boost::hash_combine(seed, machine_max_speed_e.hash());
        boost::hash_combine(seed, machine_max_acceleration_extruding.hash());
        boost::hash_combine(seed, machine_max_acceleration_retracting.hash());
        boost::hash_combine(seed, machine_max_acceleration_travel.hash());
        boost::hash_combine(seed, machine_max_jerk_x.hash());
        boost::hash_combine(seed, machine_max_jerk_y.hash());
        boost::hash_combine(seed, machine_max_jerk_z.hash());
        boost::hash_combine(seed, machine_max_jerk_e.hash());
        boost::hash_combine(seed, machine_max_junction_deviation.hash());
        boost::hash_combine(seed, machine_min_travel_rate.hash());
        boost::hash_combine(seed, machine_min_extruding_rate.hash());
        boost::hash_combine(seed, resonance_avoidance.hash());
        boost::hash_combine(seed, min_resonance_avoidance_speed.hash());
        boost::hash_combine(seed, max_resonance_avoidance_speed.hash());
        boost::hash_combine(seed, input_shaping_emit.hash());
        boost::hash_combine(seed, input_shaping_type.hash());
        boost::hash_combine(seed, input_shaping_freq_x.hash());
        boost::hash_combine(seed, input_shaping_freq_y.hash());
        boost::hash_combine(seed, input_shaping_damp_x.hash());
        boost::hash_combine(seed, input_shaping_damp_y.hash());
        return seed;
    }

    bool operator==(const MachineEnvelopeConfig &rhs) const throw()
    {
        if (!(emit_machine_limits_to_gcode == rhs.emit_machine_limits_to_gcode))
            return false;
        if (!(machine_max_acceleration_x == rhs.machine_max_acceleration_x))
            return false;
        if (!(machine_max_acceleration_y == rhs.machine_max_acceleration_y))
            return false;
        if (!(machine_max_acceleration_z == rhs.machine_max_acceleration_z))
            return false;
        if (!(machine_max_acceleration_e == rhs.machine_max_acceleration_e))
            return false;
        if (!(machine_max_speed_x == rhs.machine_max_speed_x))
            return false;
        if (!(machine_max_speed_y == rhs.machine_max_speed_y))
            return false;
        if (!(machine_max_speed_z == rhs.machine_max_speed_z))
            return false;
        if (!(machine_max_speed_e == rhs.machine_max_speed_e))
            return false;
        if (!(machine_max_acceleration_extruding == rhs.machine_max_acceleration_extruding))
            return false;
        if (!(machine_max_acceleration_retracting == rhs.machine_max_acceleration_retracting))
            return false;
        if (!(machine_max_acceleration_travel == rhs.machine_max_acceleration_travel))
            return false;
        if (!(machine_max_jerk_x == rhs.machine_max_jerk_x))
            return false;
        if (!(machine_max_jerk_y == rhs.machine_max_jerk_y))
            return false;
        if (!(machine_max_jerk_z == rhs.machine_max_jerk_z))
            return false;
        if (!(machine_max_jerk_e == rhs.machine_max_jerk_e))
            return false;
        if (!(machine_max_junction_deviation == rhs.machine_max_junction_deviation))
            return false;
        if (!(machine_min_travel_rate == rhs.machine_min_travel_rate))
            return false;
        if (!(machine_min_extruding_rate == rhs.machine_min_extruding_rate))
            return false;
        if (!(resonance_avoidance == rhs.resonance_avoidance))
            return false;
        if (!(min_resonance_avoidance_speed == rhs.min_resonance_avoidance_speed))
            return false;
        if (!(max_resonance_avoidance_speed == rhs.max_resonance_avoidance_speed))
            return false;
        if (!(input_shaping_emit == rhs.input_shaping_emit))
            return false;
        if (!(input_shaping_type == rhs.input_shaping_type))
            return false;
        if (!(input_shaping_freq_x == rhs.input_shaping_freq_x))
            return false;
        if (!(input_shaping_freq_y == rhs.input_shaping_freq_y))
            return false;
        if (!(input_shaping_damp_x == rhs.input_shaping_damp_x))
            return false;
        if (!(input_shaping_damp_y == rhs.input_shaping_damp_y))
            return false;
        return true;
    }

    bool operator!=(const MachineEnvelopeConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const MachineEnvelopeConfig &rhs) const throw()
    {
        if (emit_machine_limits_to_gcode < rhs.emit_machine_limits_to_gcode)
            return true;
        if (!(emit_machine_limits_to_gcode == rhs.emit_machine_limits_to_gcode))
            return false;
        if (machine_max_acceleration_x < rhs.machine_max_acceleration_x)
            return true;
        if (!(machine_max_acceleration_x == rhs.machine_max_acceleration_x))
            return false;
        if (machine_max_acceleration_y < rhs.machine_max_acceleration_y)
            return true;
        if (!(machine_max_acceleration_y == rhs.machine_max_acceleration_y))
            return false;
        if (machine_max_acceleration_z < rhs.machine_max_acceleration_z)
            return true;
        if (!(machine_max_acceleration_z == rhs.machine_max_acceleration_z))
            return false;
        if (machine_max_acceleration_e < rhs.machine_max_acceleration_e)
            return true;
        if (!(machine_max_acceleration_e == rhs.machine_max_acceleration_e))
            return false;
        if (machine_max_speed_x < rhs.machine_max_speed_x)
            return true;
        if (!(machine_max_speed_x == rhs.machine_max_speed_x))
            return false;
        if (machine_max_speed_y < rhs.machine_max_speed_y)
            return true;
        if (!(machine_max_speed_y == rhs.machine_max_speed_y))
            return false;
        if (machine_max_speed_z < rhs.machine_max_speed_z)
            return true;
        if (!(machine_max_speed_z == rhs.machine_max_speed_z))
            return false;
        if (machine_max_speed_e < rhs.machine_max_speed_e)
            return true;
        if (!(machine_max_speed_e == rhs.machine_max_speed_e))
            return false;
        if (machine_max_acceleration_extruding < rhs.machine_max_acceleration_extruding)
            return true;
        if (!(machine_max_acceleration_extruding == rhs.machine_max_acceleration_extruding))
            return false;
        if (machine_max_acceleration_retracting < rhs.machine_max_acceleration_retracting)
            return true;
        if (!(machine_max_acceleration_retracting == rhs.machine_max_acceleration_retracting))
            return false;
        if (machine_max_acceleration_travel < rhs.machine_max_acceleration_travel)
            return true;
        if (!(machine_max_acceleration_travel == rhs.machine_max_acceleration_travel))
            return false;
        if (machine_max_jerk_x < rhs.machine_max_jerk_x)
            return true;
        if (!(machine_max_jerk_x == rhs.machine_max_jerk_x))
            return false;
        if (machine_max_jerk_y < rhs.machine_max_jerk_y)
            return true;
        if (!(machine_max_jerk_y == rhs.machine_max_jerk_y))
            return false;
        if (machine_max_jerk_z < rhs.machine_max_jerk_z)
            return true;
        if (!(machine_max_jerk_z == rhs.machine_max_jerk_z))
            return false;
        if (machine_max_jerk_e < rhs.machine_max_jerk_e)
            return true;
        if (!(machine_max_jerk_e == rhs.machine_max_jerk_e))
            return false;
        if (machine_max_junction_deviation < rhs.machine_max_junction_deviation)
            return true;
        if (!(machine_max_junction_deviation == rhs.machine_max_junction_deviation))
            return false;
        if (machine_min_travel_rate < rhs.machine_min_travel_rate)
            return true;
        if (!(machine_min_travel_rate == rhs.machine_min_travel_rate))
            return false;
        if (machine_min_extruding_rate < rhs.machine_min_extruding_rate)
            return true;
        if (!(machine_min_extruding_rate == rhs.machine_min_extruding_rate))
            return false;
        if (resonance_avoidance < rhs.resonance_avoidance)
            return true;
        if (!(resonance_avoidance == rhs.resonance_avoidance))
            return false;
        if (min_resonance_avoidance_speed < rhs.min_resonance_avoidance_speed)
            return true;
        if (!(min_resonance_avoidance_speed == rhs.min_resonance_avoidance_speed))
            return false;
        if (max_resonance_avoidance_speed < rhs.max_resonance_avoidance_speed)
            return true;
        if (!(max_resonance_avoidance_speed == rhs.max_resonance_avoidance_speed))
            return false;
        if (input_shaping_emit < rhs.input_shaping_emit)
            return true;
        if (!(input_shaping_emit == rhs.input_shaping_emit))
            return false;
        if (input_shaping_type < rhs.input_shaping_type)
            return true;
        if (!(input_shaping_type == rhs.input_shaping_type))
            return false;
        if (input_shaping_freq_x < rhs.input_shaping_freq_x)
            return true;
        if (!(input_shaping_freq_x == rhs.input_shaping_freq_x))
            return false;
        if (input_shaping_freq_y < rhs.input_shaping_freq_y)
            return true;
        if (!(input_shaping_freq_y == rhs.input_shaping_freq_y))
            return false;
        if (input_shaping_damp_x < rhs.input_shaping_damp_x)
            return true;
        if (!(input_shaping_damp_x == rhs.input_shaping_damp_x))
            return false;
        if (input_shaping_damp_y < rhs.input_shaping_damp_y)
            return true;
        if (!(input_shaping_damp_y == rhs.input_shaping_damp_y))
            return false;
        return false;
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("emit_machine_limits_to_gcode", base_ptr, this->emit_machine_limits_to_gcode);
        cache.opt_add("machine_max_acceleration_x", base_ptr, this->machine_max_acceleration_x);
        cache.opt_add("machine_max_acceleration_y", base_ptr, this->machine_max_acceleration_y);
        cache.opt_add("machine_max_acceleration_z", base_ptr, this->machine_max_acceleration_z);
        cache.opt_add("machine_max_acceleration_e", base_ptr, this->machine_max_acceleration_e);
        cache.opt_add("machine_max_speed_x", base_ptr, this->machine_max_speed_x);
        cache.opt_add("machine_max_speed_y", base_ptr, this->machine_max_speed_y);
        cache.opt_add("machine_max_speed_z", base_ptr, this->machine_max_speed_z);
        cache.opt_add("machine_max_speed_e", base_ptr, this->machine_max_speed_e);
        cache.opt_add("machine_max_acceleration_extruding", base_ptr, this->machine_max_acceleration_extruding);
        cache.opt_add("machine_max_acceleration_retracting", base_ptr, this->machine_max_acceleration_retracting);
        cache.opt_add("machine_max_acceleration_travel", base_ptr, this->machine_max_acceleration_travel);
        cache.opt_add("machine_max_jerk_x", base_ptr, this->machine_max_jerk_x);
        cache.opt_add("machine_max_jerk_y", base_ptr, this->machine_max_jerk_y);
        cache.opt_add("machine_max_jerk_z", base_ptr, this->machine_max_jerk_z);
        cache.opt_add("machine_max_jerk_e", base_ptr, this->machine_max_jerk_e);
        cache.opt_add("machine_max_junction_deviation", base_ptr, this->machine_max_junction_deviation);
        cache.opt_add("machine_min_travel_rate", base_ptr, this->machine_min_travel_rate);
        cache.opt_add("machine_min_extruding_rate", base_ptr, this->machine_min_extruding_rate);
        cache.opt_add("resonance_avoidance", base_ptr, this->resonance_avoidance);
        cache.opt_add("min_resonance_avoidance_speed", base_ptr, this->min_resonance_avoidance_speed);
        cache.opt_add("max_resonance_avoidance_speed", base_ptr, this->max_resonance_avoidance_speed);
        cache.opt_add("input_shaping_emit", base_ptr, this->input_shaping_emit);
        cache.opt_add("input_shaping_type", base_ptr, this->input_shaping_type);
        cache.opt_add("input_shaping_freq_x", base_ptr, this->input_shaping_freq_x);
        cache.opt_add("input_shaping_freq_y", base_ptr, this->input_shaping_freq_y);
        cache.opt_add("input_shaping_damp_x", base_ptr, this->input_shaping_damp_x);
        cache.opt_add("input_shaping_damp_y", base_ptr, this->input_shaping_damp_y);
    }
};

// This object is mapped to Perl as Slic3r::Config::GCode.
class GCodeConfig : public StaticPrintConfig {
    STATIC_PRINT_CONFIG_CACHE(GCodeConfig)
public:
    ConfigOptionString before_layer_change_gcode;
    ConfigOptionString printing_by_object_gcode;
    ConfigOptionFloats deretraction_speed;
    ConfigOptionBool enable_arc_fitting;
    ConfigOptionString machine_end_gcode;
    ConfigOptionStrings filament_end_gcode;
    ConfigOptionFloatsNullable filament_flow_ratio;
    ConfigOptionBools enable_pressure_advance;
    ConfigOptionFloats pressure_advance;
    ConfigOptionBools adaptive_pressure_advance;
    ConfigOptionBools adaptive_pressure_advance_overhangs;
    ConfigOptionStrings adaptive_pressure_advance_model;
    ConfigOptionFloats adaptive_pressure_advance_bridges;
    ConfigOptionFloat fan_kickstart;
    ConfigOptionBool fan_speedup_overhangs;
    ConfigOptionFloat fan_speedup_time;
    ConfigOptionInt part_cooling_fan_min_pwm;
    ConfigOptionFloats filament_diameter;
    ConfigOptionBoolsNullable filament_adaptive_volumetric_speed;
    ConfigOptionStrings volumetric_speed_coefficients;
    ConfigOptionInts filament_adhesiveness_category;
    ConfigOptionFloats filament_density;
    ConfigOptionStrings filament_type;
    ConfigOptionBools filament_soluble;
    ConfigOptionStrings filament_ids;
    ConfigOptionStrings filament_colour;
    ConfigOptionBools composite_enabled;
    ConfigOptionStrings fiber_name;
    ConfigOptionStrings fiber_type;
    ConfigOptionStrings fiber_manufacturer;
    ConfigOptionFloats fiber_diameter;
    ConfigOptionFloats fiber_linear_density;
    ConfigOptionFloats fiber_spool_length_km;
    ConfigOptionFloats fiber_cost;
    ConfigOptionStrings fiber_plastic_name;
    ConfigOptionStrings fiber_plastic_type;
    ConfigOptionStrings fiber_plastic_manufacturer;
    ConfigOptionFloats fiber_plastic_diameter;
    ConfigOptionFloats fiber_plastic_density;
    ConfigOptionFloats fiber_plastic_cost;
    ConfigOptionFloats fiber_plastic_spool_weight;
    ConfigOptionInts fiber_nozzle_temperature_preheat;
    ConfigOptionInts fiber_nozzle_temperature_standby;
    ConfigOptionFloats fiber_first_layers_height;
    ConfigOptionFloats fiber_plastic_extrusion_speed;
    ConfigOptionFloats fiber_extrusion_speed;
    ConfigOptionFloats fiber_restart_pause;
    ConfigOptionFloats plastic_spool_weight;
    ConfigOptionFloats fiber_finish_ironing_distance;
    ConfigOptionFloats fiber_priming_line_height;
    ConfigOptionStrings fiber_material_kind;
    ConfigOptionStrings fiber_source_material_id;
    ConfigOptionStrings filament_vendor;
    ConfigOptionBools filament_is_support;
    ConfigOptionInts filament_printable;
    ConfigOptionFloats filament_change_length;
    ConfigOptionFloats filament_cost;
    ConfigOptionStrings default_filament_colour;
    ConfigOptionInts temperature_vitrification;
    ConfigOptionFloats filament_max_volumetric_speed;
    ConfigOptionInts required_nozzle_HRC;
    ConfigOptionEnum<FilamentMapMode> filament_map_mode;
    ConfigOptionInts filament_map;
    ConfigOptionInts filament_extruder_id;
    ConfigOptionStrings filament_extruder_variant;
    ConfigOptionBool support_object_skip_flush;
    ConfigOptionEnum<BedTempFormula> bed_temperature_formula;
    ConfigOptionInts physical_extruder_map;
    ConfigOptionIntsNullable nozzle_flush_dataset;
    ConfigOptionFloatsNullable filament_flush_volumetric_speed;
    ConfigOptionIntsNullable filament_flush_temp;
    ConfigOptionBool scan_first_layer;
    ConfigOptionEnum<PowerLossRecoveryMode> enable_power_loss_recovery;
    ConfigOptionBool enable_wrapping_detection;
    ConfigOptionInt wrapping_detection_layers;
    ConfigOptionPoints wrapping_exclude_area;
    ConfigOptionPoints thumbnail_size;
    ConfigOptionBool spaghetti_detector;
    ConfigOptionBool gcode_add_line_number;
    ConfigOptionBool bbl_bed_temperature_gcode;
    ConfigOptionEnum<GCodeFlavor> gcode_flavor;
    ConfigOptionFloat time_cost;
    ConfigOptionString layer_change_gcode;
    ConfigOptionString time_lapse_gcode;
    ConfigOptionString wrapping_detection_gcode;
    ConfigOptionFloat max_volumetric_extrusion_rate_slope;
    ConfigOptionFloat max_volumetric_extrusion_rate_slope_segment_length;
    ConfigOptionBool extrusion_rate_smoothing_external_perimeter_only;
    ConfigOptionPercents retract_before_wipe;
    ConfigOptionFloats retraction_length;
    ConfigOptionFloats retract_length_toolchange;
    ConfigOptionInt enable_long_retraction_when_cut;
    ConfigOptionFloats retraction_distances_when_cut;
    ConfigOptionBools long_retractions_when_cut;
    ConfigOptionFloatsNullable retraction_distances_when_ec;
    ConfigOptionBoolsNullable long_retractions_when_ec;
    ConfigOptionFloats z_hop;
    ConfigOptionEnumsGeneric z_hop_types;
    ConfigOptionFloats travel_slope;
    ConfigOptionFloats retract_lift_above;
    ConfigOptionFloats retract_lift_below;
    ConfigOptionEnumsGeneric retract_lift_enforce;
    ConfigOptionFloats retract_restart_extra;
    ConfigOptionFloats retract_restart_extra_toolchange;
    ConfigOptionFloats retraction_speed;
    ConfigOptionString file_start_gcode;
    ConfigOptionString machine_start_gcode;
    ConfigOptionStrings filament_start_gcode;
    ConfigOptionBool single_extruder_multi_material;
    ConfigOptionBool manual_filament_change;
    ConfigOptionBool single_extruder_multi_material_priming;
    ConfigOptionBool wipe_tower_no_sparse_layers;
    ConfigOptionString change_filament_gcode;
    ConfigOptionString change_extrusion_role_gcode;
    ConfigOptionString process_change_extrusion_role_gcode;
    ConfigOptionStrings filament_change_extrusion_role_gcode;
    ConfigOptionFloat travel_speed;
    ConfigOptionFloat travel_speed_z;
    ConfigOptionBool silent_mode;
    ConfigOptionString machine_pause_gcode;
    ConfigOptionString template_custom_gcode;
    ConfigOptionEnumsGenericNullable nozzle_type;
    ConfigOptionInt nozzle_hrc;
    ConfigOptionBool auxiliary_fan;
    ConfigOptionBool support_air_filtration;
    ConfigOptionEnum<PrinterStructure> printer_structure;
    ConfigOptionBool support_chamber_temp_control;
    ConfigOptionEnumsGeneric extruder_type;
    ConfigOptionEnumsGeneric nozzle_volume_type;
    ConfigOptionStrings extruder_ams_count;
    ConfigOptionInts printer_extruder_id;
    ConfigOptionInt master_extruder_id;
    ConfigOptionStrings printer_extruder_variant;
    ConfigOptionBool use_firmware_retraction;
    ConfigOptionBool use_relative_e_distances;
    ConfigOptionBool accel_to_decel_enable;
    ConfigOptionPercent accel_to_decel_factor;
    ConfigOptionFloatOrPercent initial_layer_travel_speed;
    ConfigOptionFloatOrPercent initial_layer_travel_acceleration;
    ConfigOptionFloatOrPercent initial_layer_travel_jerk;
    ConfigOptionBool bbl_calib_mark_logo;
    ConfigOptionBool disable_m73;
    ConfigOptionFloat cooling_tube_retraction;
    ConfigOptionFloat cooling_tube_length;
    ConfigOptionBool high_current_on_filament_swap;
    ConfigOptionFloat parking_pos_retraction;
    ConfigOptionFloat extra_loading_move;
    ConfigOptionFloat machine_load_filament_time;
    ConfigOptionFloat machine_tool_change_time;
    ConfigOptionFloat machine_unload_filament_time;
    ConfigOptionFloats filament_loading_speed;
    ConfigOptionFloats filament_loading_speed_start;
    ConfigOptionFloats filament_unloading_speed;
    ConfigOptionFloats filament_unloading_speed_start;
    ConfigOptionFloats filament_toolchange_delay;
    ConfigOptionInts filament_cooling_moves;
    ConfigOptionFloats filament_cooling_initial_speed;
    ConfigOptionFloats filament_minimal_purge_on_wipe_tower;
    ConfigOptionFloatsNullable filament_cooling_before_tower;
    ConfigOptionFloats filament_tower_interface_pre_extrusion_dist;
    ConfigOptionFloats filament_tower_interface_pre_extrusion_length;
    ConfigOptionFloats filament_tower_ironing_area;
    ConfigOptionFloats filament_tower_interface_purge_volume;
    ConfigOptionInts filament_tower_interface_print_temp;
    ConfigOptionFloats filament_cooling_final_speed;
    ConfigOptionStrings filament_ramming_parameters;
    ConfigOptionBools filament_multitool_ramming;
    ConfigOptionFloats filament_multitool_ramming_volume;
    ConfigOptionFloats filament_multitool_ramming_flow;
    ConfigOptionFloats filament_stamping_loading_speed;
    ConfigOptionFloats filament_stamping_distance;
    ConfigOptionEnum<WipeTowerType> wipe_tower_type;
    ConfigOptionBool purge_in_prime_tower;
    ConfigOptionBool enable_filament_ramming;
    ConfigOptionBool tool_change_on_wipe_tower;
    ConfigOptionBool support_multi_bed_types;
    ConfigOptionBool use_3mf;
    ConfigOptionStrings small_area_infill_flow_compensation_model;
    ConfigOptionBool has_scarf_joint_seam;

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, before_layer_change_gcode.hash());
        boost::hash_combine(seed, printing_by_object_gcode.hash());
        boost::hash_combine(seed, deretraction_speed.hash());
        boost::hash_combine(seed, enable_arc_fitting.hash());
        boost::hash_combine(seed, machine_end_gcode.hash());
        boost::hash_combine(seed, filament_end_gcode.hash());
        boost::hash_combine(seed, filament_flow_ratio.hash());
        boost::hash_combine(seed, enable_pressure_advance.hash());
        boost::hash_combine(seed, pressure_advance.hash());
        boost::hash_combine(seed, adaptive_pressure_advance.hash());
        boost::hash_combine(seed, adaptive_pressure_advance_overhangs.hash());
        boost::hash_combine(seed, adaptive_pressure_advance_model.hash());
        boost::hash_combine(seed, adaptive_pressure_advance_bridges.hash());
        boost::hash_combine(seed, fan_kickstart.hash());
        boost::hash_combine(seed, fan_speedup_overhangs.hash());
        boost::hash_combine(seed, fan_speedup_time.hash());
        boost::hash_combine(seed, part_cooling_fan_min_pwm.hash());
        boost::hash_combine(seed, filament_diameter.hash());
        boost::hash_combine(seed, filament_adaptive_volumetric_speed.hash());
        boost::hash_combine(seed, volumetric_speed_coefficients.hash());
        boost::hash_combine(seed, filament_adhesiveness_category.hash());
        boost::hash_combine(seed, filament_density.hash());
        boost::hash_combine(seed, filament_type.hash());
        boost::hash_combine(seed, filament_soluble.hash());
        boost::hash_combine(seed, filament_ids.hash());
        boost::hash_combine(seed, filament_colour.hash());
        boost::hash_combine(seed, composite_enabled.hash());
        boost::hash_combine(seed, fiber_name.hash());
        boost::hash_combine(seed, fiber_type.hash());
        boost::hash_combine(seed, fiber_manufacturer.hash());
        boost::hash_combine(seed, fiber_diameter.hash());
        boost::hash_combine(seed, fiber_linear_density.hash());
        boost::hash_combine(seed, fiber_spool_length_km.hash());
        boost::hash_combine(seed, fiber_cost.hash());
        boost::hash_combine(seed, fiber_plastic_name.hash());
        boost::hash_combine(seed, fiber_plastic_type.hash());
        boost::hash_combine(seed, fiber_plastic_manufacturer.hash());
        boost::hash_combine(seed, fiber_plastic_diameter.hash());
        boost::hash_combine(seed, fiber_plastic_density.hash());
        boost::hash_combine(seed, fiber_plastic_cost.hash());
        boost::hash_combine(seed, fiber_plastic_spool_weight.hash());
        boost::hash_combine(seed, fiber_nozzle_temperature_preheat.hash());
        boost::hash_combine(seed, fiber_nozzle_temperature_standby.hash());
        boost::hash_combine(seed, fiber_first_layers_height.hash());
        boost::hash_combine(seed, fiber_plastic_extrusion_speed.hash());
        boost::hash_combine(seed, fiber_extrusion_speed.hash());
        boost::hash_combine(seed, fiber_restart_pause.hash());
        boost::hash_combine(seed, plastic_spool_weight.hash());
        boost::hash_combine(seed, fiber_finish_ironing_distance.hash());
        boost::hash_combine(seed, fiber_priming_line_height.hash());
        boost::hash_combine(seed, fiber_material_kind.hash());
        boost::hash_combine(seed, fiber_source_material_id.hash());
        boost::hash_combine(seed, filament_vendor.hash());
        boost::hash_combine(seed, filament_is_support.hash());
        boost::hash_combine(seed, filament_printable.hash());
        boost::hash_combine(seed, filament_change_length.hash());
        boost::hash_combine(seed, filament_cost.hash());
        boost::hash_combine(seed, default_filament_colour.hash());
        boost::hash_combine(seed, temperature_vitrification.hash());
        boost::hash_combine(seed, filament_max_volumetric_speed.hash());
        boost::hash_combine(seed, required_nozzle_HRC.hash());
        boost::hash_combine(seed, filament_map_mode.hash());
        boost::hash_combine(seed, filament_map.hash());
        boost::hash_combine(seed, filament_extruder_id.hash());
        boost::hash_combine(seed, filament_extruder_variant.hash());
        boost::hash_combine(seed, support_object_skip_flush.hash());
        boost::hash_combine(seed, bed_temperature_formula.hash());
        boost::hash_combine(seed, physical_extruder_map.hash());
        boost::hash_combine(seed, nozzle_flush_dataset.hash());
        boost::hash_combine(seed, filament_flush_volumetric_speed.hash());
        boost::hash_combine(seed, filament_flush_temp.hash());
        boost::hash_combine(seed, scan_first_layer.hash());
        boost::hash_combine(seed, enable_power_loss_recovery.hash());
        boost::hash_combine(seed, enable_wrapping_detection.hash());
        boost::hash_combine(seed, wrapping_detection_layers.hash());
        boost::hash_combine(seed, wrapping_exclude_area.hash());
        boost::hash_combine(seed, thumbnail_size.hash());
        boost::hash_combine(seed, spaghetti_detector.hash());
        boost::hash_combine(seed, gcode_add_line_number.hash());
        boost::hash_combine(seed, bbl_bed_temperature_gcode.hash());
        boost::hash_combine(seed, gcode_flavor.hash());
        boost::hash_combine(seed, time_cost.hash());
        boost::hash_combine(seed, layer_change_gcode.hash());
        boost::hash_combine(seed, time_lapse_gcode.hash());
        boost::hash_combine(seed, wrapping_detection_gcode.hash());
        boost::hash_combine(seed, max_volumetric_extrusion_rate_slope.hash());
        boost::hash_combine(seed, max_volumetric_extrusion_rate_slope_segment_length.hash());
        boost::hash_combine(seed, extrusion_rate_smoothing_external_perimeter_only.hash());
        boost::hash_combine(seed, retract_before_wipe.hash());
        boost::hash_combine(seed, retraction_length.hash());
        boost::hash_combine(seed, retract_length_toolchange.hash());
        boost::hash_combine(seed, enable_long_retraction_when_cut.hash());
        boost::hash_combine(seed, retraction_distances_when_cut.hash());
        boost::hash_combine(seed, long_retractions_when_cut.hash());
        boost::hash_combine(seed, retraction_distances_when_ec.hash());
        boost::hash_combine(seed, long_retractions_when_ec.hash());
        boost::hash_combine(seed, z_hop.hash());
        boost::hash_combine(seed, z_hop_types.hash());
        boost::hash_combine(seed, travel_slope.hash());
        boost::hash_combine(seed, retract_lift_above.hash());
        boost::hash_combine(seed, retract_lift_below.hash());
        boost::hash_combine(seed, retract_lift_enforce.hash());
        boost::hash_combine(seed, retract_restart_extra.hash());
        boost::hash_combine(seed, retract_restart_extra_toolchange.hash());
        boost::hash_combine(seed, retraction_speed.hash());
        boost::hash_combine(seed, file_start_gcode.hash());
        boost::hash_combine(seed, machine_start_gcode.hash());
        boost::hash_combine(seed, filament_start_gcode.hash());
        boost::hash_combine(seed, single_extruder_multi_material.hash());
        boost::hash_combine(seed, manual_filament_change.hash());
        boost::hash_combine(seed, single_extruder_multi_material_priming.hash());
        boost::hash_combine(seed, wipe_tower_no_sparse_layers.hash());
        boost::hash_combine(seed, change_filament_gcode.hash());
        boost::hash_combine(seed, change_extrusion_role_gcode.hash());
        boost::hash_combine(seed, process_change_extrusion_role_gcode.hash());
        boost::hash_combine(seed, filament_change_extrusion_role_gcode.hash());
        boost::hash_combine(seed, travel_speed.hash());
        boost::hash_combine(seed, travel_speed_z.hash());
        boost::hash_combine(seed, silent_mode.hash());
        boost::hash_combine(seed, machine_pause_gcode.hash());
        boost::hash_combine(seed, template_custom_gcode.hash());
        boost::hash_combine(seed, nozzle_type.hash());
        boost::hash_combine(seed, nozzle_hrc.hash());
        boost::hash_combine(seed, auxiliary_fan.hash());
        boost::hash_combine(seed, support_air_filtration.hash());
        boost::hash_combine(seed, printer_structure.hash());
        boost::hash_combine(seed, support_chamber_temp_control.hash());
        boost::hash_combine(seed, extruder_type.hash());
        boost::hash_combine(seed, nozzle_volume_type.hash());
        boost::hash_combine(seed, extruder_ams_count.hash());
        boost::hash_combine(seed, printer_extruder_id.hash());
        boost::hash_combine(seed, master_extruder_id.hash());
        boost::hash_combine(seed, printer_extruder_variant.hash());
        boost::hash_combine(seed, use_firmware_retraction.hash());
        boost::hash_combine(seed, use_relative_e_distances.hash());
        boost::hash_combine(seed, accel_to_decel_enable.hash());
        boost::hash_combine(seed, accel_to_decel_factor.hash());
        boost::hash_combine(seed, initial_layer_travel_speed.hash());
        boost::hash_combine(seed, initial_layer_travel_acceleration.hash());
        boost::hash_combine(seed, initial_layer_travel_jerk.hash());
        boost::hash_combine(seed, bbl_calib_mark_logo.hash());
        boost::hash_combine(seed, disable_m73.hash());
        boost::hash_combine(seed, cooling_tube_retraction.hash());
        boost::hash_combine(seed, cooling_tube_length.hash());
        boost::hash_combine(seed, high_current_on_filament_swap.hash());
        boost::hash_combine(seed, parking_pos_retraction.hash());
        boost::hash_combine(seed, extra_loading_move.hash());
        boost::hash_combine(seed, machine_load_filament_time.hash());
        boost::hash_combine(seed, machine_tool_change_time.hash());
        boost::hash_combine(seed, machine_unload_filament_time.hash());
        boost::hash_combine(seed, filament_loading_speed.hash());
        boost::hash_combine(seed, filament_loading_speed_start.hash());
        boost::hash_combine(seed, filament_unloading_speed.hash());
        boost::hash_combine(seed, filament_unloading_speed_start.hash());
        boost::hash_combine(seed, filament_toolchange_delay.hash());
        boost::hash_combine(seed, filament_cooling_moves.hash());
        boost::hash_combine(seed, filament_cooling_initial_speed.hash());
        boost::hash_combine(seed, filament_minimal_purge_on_wipe_tower.hash());
        boost::hash_combine(seed, filament_cooling_before_tower.hash());
        boost::hash_combine(seed, filament_tower_interface_pre_extrusion_dist.hash());
        boost::hash_combine(seed, filament_tower_interface_pre_extrusion_length.hash());
        boost::hash_combine(seed, filament_tower_ironing_area.hash());
        boost::hash_combine(seed, filament_tower_interface_purge_volume.hash());
        boost::hash_combine(seed, filament_tower_interface_print_temp.hash());
        boost::hash_combine(seed, filament_cooling_final_speed.hash());
        boost::hash_combine(seed, filament_ramming_parameters.hash());
        boost::hash_combine(seed, filament_multitool_ramming.hash());
        boost::hash_combine(seed, filament_multitool_ramming_volume.hash());
        boost::hash_combine(seed, filament_multitool_ramming_flow.hash());
        boost::hash_combine(seed, filament_stamping_loading_speed.hash());
        boost::hash_combine(seed, filament_stamping_distance.hash());
        boost::hash_combine(seed, wipe_tower_type.hash());
        boost::hash_combine(seed, purge_in_prime_tower.hash());
        boost::hash_combine(seed, enable_filament_ramming.hash());
        boost::hash_combine(seed, tool_change_on_wipe_tower.hash());
        boost::hash_combine(seed, support_multi_bed_types.hash());
        boost::hash_combine(seed, use_3mf.hash());
        boost::hash_combine(seed, small_area_infill_flow_compensation_model.hash());
        boost::hash_combine(seed, has_scarf_joint_seam.hash());
        return seed;
    }

    bool operator==(const GCodeConfig &rhs) const throw()
    {
        if (!(before_layer_change_gcode == rhs.before_layer_change_gcode))
            return false;
        if (!(printing_by_object_gcode == rhs.printing_by_object_gcode))
            return false;
        if (!(deretraction_speed == rhs.deretraction_speed))
            return false;
        if (!(enable_arc_fitting == rhs.enable_arc_fitting))
            return false;
        if (!(machine_end_gcode == rhs.machine_end_gcode))
            return false;
        if (!(filament_end_gcode == rhs.filament_end_gcode))
            return false;
        if (!(filament_flow_ratio == rhs.filament_flow_ratio))
            return false;
        if (!(enable_pressure_advance == rhs.enable_pressure_advance))
            return false;
        if (!(pressure_advance == rhs.pressure_advance))
            return false;
        if (!(adaptive_pressure_advance == rhs.adaptive_pressure_advance))
            return false;
        if (!(adaptive_pressure_advance_overhangs == rhs.adaptive_pressure_advance_overhangs))
            return false;
        if (!(adaptive_pressure_advance_model == rhs.adaptive_pressure_advance_model))
            return false;
        if (!(adaptive_pressure_advance_bridges == rhs.adaptive_pressure_advance_bridges))
            return false;
        if (!(fan_kickstart == rhs.fan_kickstart))
            return false;
        if (!(fan_speedup_overhangs == rhs.fan_speedup_overhangs))
            return false;
        if (!(fan_speedup_time == rhs.fan_speedup_time))
            return false;
        if (!(part_cooling_fan_min_pwm == rhs.part_cooling_fan_min_pwm))
            return false;
        if (!(filament_diameter == rhs.filament_diameter))
            return false;
        if (!(filament_adaptive_volumetric_speed == rhs.filament_adaptive_volumetric_speed))
            return false;
        if (!(volumetric_speed_coefficients == rhs.volumetric_speed_coefficients))
            return false;
        if (!(filament_adhesiveness_category == rhs.filament_adhesiveness_category))
            return false;
        if (!(filament_density == rhs.filament_density))
            return false;
        if (!(filament_type == rhs.filament_type))
            return false;
        if (!(filament_soluble == rhs.filament_soluble))
            return false;
        if (!(filament_ids == rhs.filament_ids))
            return false;
        if (!(filament_colour == rhs.filament_colour))
            return false;
        if (!(composite_enabled == rhs.composite_enabled))
            return false;
        if (!(fiber_name == rhs.fiber_name))
            return false;
        if (!(fiber_type == rhs.fiber_type))
            return false;
        if (!(fiber_manufacturer == rhs.fiber_manufacturer))
            return false;
        if (!(fiber_diameter == rhs.fiber_diameter))
            return false;
        if (!(fiber_linear_density == rhs.fiber_linear_density))
            return false;
        if (!(fiber_spool_length_km == rhs.fiber_spool_length_km))
            return false;
        if (!(fiber_cost == rhs.fiber_cost))
            return false;
        if (!(fiber_plastic_name == rhs.fiber_plastic_name))
            return false;
        if (!(fiber_plastic_type == rhs.fiber_plastic_type))
            return false;
        if (!(fiber_plastic_manufacturer == rhs.fiber_plastic_manufacturer))
            return false;
        if (!(fiber_plastic_diameter == rhs.fiber_plastic_diameter))
            return false;
        if (!(fiber_plastic_density == rhs.fiber_plastic_density))
            return false;
        if (!(fiber_plastic_cost == rhs.fiber_plastic_cost))
            return false;
        if (!(fiber_plastic_spool_weight == rhs.fiber_plastic_spool_weight))
            return false;
        if (!(fiber_nozzle_temperature_preheat == rhs.fiber_nozzle_temperature_preheat))
            return false;
        if (!(fiber_nozzle_temperature_standby == rhs.fiber_nozzle_temperature_standby))
            return false;
        if (!(fiber_first_layers_height == rhs.fiber_first_layers_height))
            return false;
        if (!(fiber_plastic_extrusion_speed == rhs.fiber_plastic_extrusion_speed))
            return false;
        if (!(fiber_extrusion_speed == rhs.fiber_extrusion_speed))
            return false;
        if (!(fiber_restart_pause == rhs.fiber_restart_pause))
            return false;
        if (!(plastic_spool_weight == rhs.plastic_spool_weight))
            return false;
        if (!(fiber_finish_ironing_distance == rhs.fiber_finish_ironing_distance))
            return false;
        if (!(fiber_priming_line_height == rhs.fiber_priming_line_height))
            return false;
        if (!(fiber_material_kind == rhs.fiber_material_kind))
            return false;
        if (!(fiber_source_material_id == rhs.fiber_source_material_id))
            return false;
        if (!(filament_vendor == rhs.filament_vendor))
            return false;
        if (!(filament_is_support == rhs.filament_is_support))
            return false;
        if (!(filament_printable == rhs.filament_printable))
            return false;
        if (!(filament_change_length == rhs.filament_change_length))
            return false;
        if (!(filament_cost == rhs.filament_cost))
            return false;
        if (!(default_filament_colour == rhs.default_filament_colour))
            return false;
        if (!(temperature_vitrification == rhs.temperature_vitrification))
            return false;
        if (!(filament_max_volumetric_speed == rhs.filament_max_volumetric_speed))
            return false;
        if (!(required_nozzle_HRC == rhs.required_nozzle_HRC))
            return false;
        if (!(filament_map_mode == rhs.filament_map_mode))
            return false;
        if (!(filament_map == rhs.filament_map))
            return false;
        if (!(filament_extruder_id == rhs.filament_extruder_id))
            return false;
        if (!(filament_extruder_variant == rhs.filament_extruder_variant))
            return false;
        if (!(support_object_skip_flush == rhs.support_object_skip_flush))
            return false;
        if (!(bed_temperature_formula == rhs.bed_temperature_formula))
            return false;
        if (!(physical_extruder_map == rhs.physical_extruder_map))
            return false;
        if (!(nozzle_flush_dataset == rhs.nozzle_flush_dataset))
            return false;
        if (!(filament_flush_volumetric_speed == rhs.filament_flush_volumetric_speed))
            return false;
        if (!(filament_flush_temp == rhs.filament_flush_temp))
            return false;
        if (!(scan_first_layer == rhs.scan_first_layer))
            return false;
        if (!(enable_power_loss_recovery == rhs.enable_power_loss_recovery))
            return false;
        if (!(enable_wrapping_detection == rhs.enable_wrapping_detection))
            return false;
        if (!(wrapping_detection_layers == rhs.wrapping_detection_layers))
            return false;
        if (!(wrapping_exclude_area == rhs.wrapping_exclude_area))
            return false;
        if (!(thumbnail_size == rhs.thumbnail_size))
            return false;
        if (!(spaghetti_detector == rhs.spaghetti_detector))
            return false;
        if (!(gcode_add_line_number == rhs.gcode_add_line_number))
            return false;
        if (!(bbl_bed_temperature_gcode == rhs.bbl_bed_temperature_gcode))
            return false;
        if (!(gcode_flavor == rhs.gcode_flavor))
            return false;
        if (!(time_cost == rhs.time_cost))
            return false;
        if (!(layer_change_gcode == rhs.layer_change_gcode))
            return false;
        if (!(time_lapse_gcode == rhs.time_lapse_gcode))
            return false;
        if (!(wrapping_detection_gcode == rhs.wrapping_detection_gcode))
            return false;
        if (!(max_volumetric_extrusion_rate_slope == rhs.max_volumetric_extrusion_rate_slope))
            return false;
        if (!(max_volumetric_extrusion_rate_slope_segment_length == rhs.max_volumetric_extrusion_rate_slope_segment_length))
            return false;
        if (!(extrusion_rate_smoothing_external_perimeter_only == rhs.extrusion_rate_smoothing_external_perimeter_only))
            return false;
        if (!(retract_before_wipe == rhs.retract_before_wipe))
            return false;
        if (!(retraction_length == rhs.retraction_length))
            return false;
        if (!(retract_length_toolchange == rhs.retract_length_toolchange))
            return false;
        if (!(enable_long_retraction_when_cut == rhs.enable_long_retraction_when_cut))
            return false;
        if (!(retraction_distances_when_cut == rhs.retraction_distances_when_cut))
            return false;
        if (!(long_retractions_when_cut == rhs.long_retractions_when_cut))
            return false;
        if (!(retraction_distances_when_ec == rhs.retraction_distances_when_ec))
            return false;
        if (!(long_retractions_when_ec == rhs.long_retractions_when_ec))
            return false;
        if (!(z_hop == rhs.z_hop))
            return false;
        if (!(z_hop_types == rhs.z_hop_types))
            return false;
        if (!(travel_slope == rhs.travel_slope))
            return false;
        if (!(retract_lift_above == rhs.retract_lift_above))
            return false;
        if (!(retract_lift_below == rhs.retract_lift_below))
            return false;
        if (!(retract_lift_enforce == rhs.retract_lift_enforce))
            return false;
        if (!(retract_restart_extra == rhs.retract_restart_extra))
            return false;
        if (!(retract_restart_extra_toolchange == rhs.retract_restart_extra_toolchange))
            return false;
        if (!(retraction_speed == rhs.retraction_speed))
            return false;
        if (!(file_start_gcode == rhs.file_start_gcode))
            return false;
        if (!(machine_start_gcode == rhs.machine_start_gcode))
            return false;
        if (!(filament_start_gcode == rhs.filament_start_gcode))
            return false;
        if (!(single_extruder_multi_material == rhs.single_extruder_multi_material))
            return false;
        if (!(manual_filament_change == rhs.manual_filament_change))
            return false;
        if (!(single_extruder_multi_material_priming == rhs.single_extruder_multi_material_priming))
            return false;
        if (!(wipe_tower_no_sparse_layers == rhs.wipe_tower_no_sparse_layers))
            return false;
        if (!(change_filament_gcode == rhs.change_filament_gcode))
            return false;
        if (!(change_extrusion_role_gcode == rhs.change_extrusion_role_gcode))
            return false;
        if (!(process_change_extrusion_role_gcode == rhs.process_change_extrusion_role_gcode))
            return false;
        if (!(filament_change_extrusion_role_gcode == rhs.filament_change_extrusion_role_gcode))
            return false;
        if (!(travel_speed == rhs.travel_speed))
            return false;
        if (!(travel_speed_z == rhs.travel_speed_z))
            return false;
        if (!(silent_mode == rhs.silent_mode))
            return false;
        if (!(machine_pause_gcode == rhs.machine_pause_gcode))
            return false;
        if (!(template_custom_gcode == rhs.template_custom_gcode))
            return false;
        if (!(nozzle_type == rhs.nozzle_type))
            return false;
        if (!(nozzle_hrc == rhs.nozzle_hrc))
            return false;
        if (!(auxiliary_fan == rhs.auxiliary_fan))
            return false;
        if (!(support_air_filtration == rhs.support_air_filtration))
            return false;
        if (!(printer_structure == rhs.printer_structure))
            return false;
        if (!(support_chamber_temp_control == rhs.support_chamber_temp_control))
            return false;
        if (!(extruder_type == rhs.extruder_type))
            return false;
        if (!(nozzle_volume_type == rhs.nozzle_volume_type))
            return false;
        if (!(extruder_ams_count == rhs.extruder_ams_count))
            return false;
        if (!(printer_extruder_id == rhs.printer_extruder_id))
            return false;
        if (!(master_extruder_id == rhs.master_extruder_id))
            return false;
        if (!(printer_extruder_variant == rhs.printer_extruder_variant))
            return false;
        if (!(use_firmware_retraction == rhs.use_firmware_retraction))
            return false;
        if (!(use_relative_e_distances == rhs.use_relative_e_distances))
            return false;
        if (!(accel_to_decel_enable == rhs.accel_to_decel_enable))
            return false;
        if (!(accel_to_decel_factor == rhs.accel_to_decel_factor))
            return false;
        if (!(initial_layer_travel_speed == rhs.initial_layer_travel_speed))
            return false;
        if (!(initial_layer_travel_acceleration == rhs.initial_layer_travel_acceleration))
            return false;
        if (!(initial_layer_travel_jerk == rhs.initial_layer_travel_jerk))
            return false;
        if (!(bbl_calib_mark_logo == rhs.bbl_calib_mark_logo))
            return false;
        if (!(disable_m73 == rhs.disable_m73))
            return false;
        if (!(cooling_tube_retraction == rhs.cooling_tube_retraction))
            return false;
        if (!(cooling_tube_length == rhs.cooling_tube_length))
            return false;
        if (!(high_current_on_filament_swap == rhs.high_current_on_filament_swap))
            return false;
        if (!(parking_pos_retraction == rhs.parking_pos_retraction))
            return false;
        if (!(extra_loading_move == rhs.extra_loading_move))
            return false;
        if (!(machine_load_filament_time == rhs.machine_load_filament_time))
            return false;
        if (!(machine_tool_change_time == rhs.machine_tool_change_time))
            return false;
        if (!(machine_unload_filament_time == rhs.machine_unload_filament_time))
            return false;
        if (!(filament_loading_speed == rhs.filament_loading_speed))
            return false;
        if (!(filament_loading_speed_start == rhs.filament_loading_speed_start))
            return false;
        if (!(filament_unloading_speed == rhs.filament_unloading_speed))
            return false;
        if (!(filament_unloading_speed_start == rhs.filament_unloading_speed_start))
            return false;
        if (!(filament_toolchange_delay == rhs.filament_toolchange_delay))
            return false;
        if (!(filament_cooling_moves == rhs.filament_cooling_moves))
            return false;
        if (!(filament_cooling_initial_speed == rhs.filament_cooling_initial_speed))
            return false;
        if (!(filament_minimal_purge_on_wipe_tower == rhs.filament_minimal_purge_on_wipe_tower))
            return false;
        if (!(filament_cooling_before_tower == rhs.filament_cooling_before_tower))
            return false;
        if (!(filament_tower_interface_pre_extrusion_dist == rhs.filament_tower_interface_pre_extrusion_dist))
            return false;
        if (!(filament_tower_interface_pre_extrusion_length == rhs.filament_tower_interface_pre_extrusion_length))
            return false;
        if (!(filament_tower_ironing_area == rhs.filament_tower_ironing_area))
            return false;
        if (!(filament_tower_interface_purge_volume == rhs.filament_tower_interface_purge_volume))
            return false;
        if (!(filament_tower_interface_print_temp == rhs.filament_tower_interface_print_temp))
            return false;
        if (!(filament_cooling_final_speed == rhs.filament_cooling_final_speed))
            return false;
        if (!(filament_ramming_parameters == rhs.filament_ramming_parameters))
            return false;
        if (!(filament_multitool_ramming == rhs.filament_multitool_ramming))
            return false;
        if (!(filament_multitool_ramming_volume == rhs.filament_multitool_ramming_volume))
            return false;
        if (!(filament_multitool_ramming_flow == rhs.filament_multitool_ramming_flow))
            return false;
        if (!(filament_stamping_loading_speed == rhs.filament_stamping_loading_speed))
            return false;
        if (!(filament_stamping_distance == rhs.filament_stamping_distance))
            return false;
        if (!(wipe_tower_type == rhs.wipe_tower_type))
            return false;
        if (!(purge_in_prime_tower == rhs.purge_in_prime_tower))
            return false;
        if (!(enable_filament_ramming == rhs.enable_filament_ramming))
            return false;
        if (!(tool_change_on_wipe_tower == rhs.tool_change_on_wipe_tower))
            return false;
        if (!(support_multi_bed_types == rhs.support_multi_bed_types))
            return false;
        if (!(use_3mf == rhs.use_3mf))
            return false;
        if (!(small_area_infill_flow_compensation_model == rhs.small_area_infill_flow_compensation_model))
            return false;
        if (!(has_scarf_joint_seam == rhs.has_scarf_joint_seam))
            return false;
        return true;
    }

    bool operator!=(const GCodeConfig &rhs) const throw() { return !(*this == rhs); }

    bool operator<(const GCodeConfig &rhs) const throw()
    {
        if (before_layer_change_gcode < rhs.before_layer_change_gcode)
            return true;
        if (!(before_layer_change_gcode == rhs.before_layer_change_gcode))
            return false;
        if (printing_by_object_gcode < rhs.printing_by_object_gcode)
            return true;
        if (!(printing_by_object_gcode == rhs.printing_by_object_gcode))
            return false;
        if (deretraction_speed < rhs.deretraction_speed)
            return true;
        if (!(deretraction_speed == rhs.deretraction_speed))
            return false;
        if (enable_arc_fitting < rhs.enable_arc_fitting)
            return true;
        if (!(enable_arc_fitting == rhs.enable_arc_fitting))
            return false;
        if (machine_end_gcode < rhs.machine_end_gcode)
            return true;
        if (!(machine_end_gcode == rhs.machine_end_gcode))
            return false;
        if (filament_end_gcode < rhs.filament_end_gcode)
            return true;
        if (!(filament_end_gcode == rhs.filament_end_gcode))
            return false;
        if (filament_flow_ratio < rhs.filament_flow_ratio)
            return true;
        if (!(filament_flow_ratio == rhs.filament_flow_ratio))
            return false;
        if (enable_pressure_advance < rhs.enable_pressure_advance)
            return true;
        if (!(enable_pressure_advance == rhs.enable_pressure_advance))
            return false;
        if (pressure_advance < rhs.pressure_advance)
            return true;
        if (!(pressure_advance == rhs.pressure_advance))
            return false;
        if (adaptive_pressure_advance < rhs.adaptive_pressure_advance)
            return true;
        if (!(adaptive_pressure_advance == rhs.adaptive_pressure_advance))
            return false;
        if (adaptive_pressure_advance_overhangs < rhs.adaptive_pressure_advance_overhangs)
            return true;
        if (!(adaptive_pressure_advance_overhangs == rhs.adaptive_pressure_advance_overhangs))
            return false;
        if (adaptive_pressure_advance_model < rhs.adaptive_pressure_advance_model)
            return true;
        if (!(adaptive_pressure_advance_model == rhs.adaptive_pressure_advance_model))
            return false;
        if (adaptive_pressure_advance_bridges < rhs.adaptive_pressure_advance_bridges)
            return true;
        if (!(adaptive_pressure_advance_bridges == rhs.adaptive_pressure_advance_bridges))
            return false;
        if (fan_kickstart < rhs.fan_kickstart)
            return true;
        if (!(fan_kickstart == rhs.fan_kickstart))
            return false;
        if (fan_speedup_overhangs < rhs.fan_speedup_overhangs)
            return true;
        if (!(fan_speedup_overhangs == rhs.fan_speedup_overhangs))
            return false;
        if (fan_speedup_time < rhs.fan_speedup_time)
            return true;
        if (!(fan_speedup_time == rhs.fan_speedup_time))
            return false;
        if (part_cooling_fan_min_pwm < rhs.part_cooling_fan_min_pwm)
            return true;
        if (!(part_cooling_fan_min_pwm == rhs.part_cooling_fan_min_pwm))
            return false;
        if (filament_diameter < rhs.filament_diameter)
            return true;
        if (!(filament_diameter == rhs.filament_diameter))
            return false;
        if (filament_adaptive_volumetric_speed < rhs.filament_adaptive_volumetric_speed)
            return true;
        if (!(filament_adaptive_volumetric_speed == rhs.filament_adaptive_volumetric_speed))
            return false;
        if (volumetric_speed_coefficients < rhs.volumetric_speed_coefficients)
            return true;
        if (!(volumetric_speed_coefficients == rhs.volumetric_speed_coefficients))
            return false;
        if (filament_adhesiveness_category < rhs.filament_adhesiveness_category)
            return true;
        if (!(filament_adhesiveness_category == rhs.filament_adhesiveness_category))
            return false;
        if (filament_density < rhs.filament_density)
            return true;
        if (!(filament_density == rhs.filament_density))
            return false;
        if (filament_type < rhs.filament_type)
            return true;
        if (!(filament_type == rhs.filament_type))
            return false;
        if (filament_soluble < rhs.filament_soluble)
            return true;
        if (!(filament_soluble == rhs.filament_soluble))
            return false;
        if (filament_ids < rhs.filament_ids)
            return true;
        if (!(filament_ids == rhs.filament_ids))
            return false;
        if (filament_colour < rhs.filament_colour)
            return true;
        if (!(filament_colour == rhs.filament_colour))
            return false;
        if (composite_enabled < rhs.composite_enabled)
            return true;
        if (!(composite_enabled == rhs.composite_enabled))
            return false;
        if (fiber_name < rhs.fiber_name)
            return true;
        if (!(fiber_name == rhs.fiber_name))
            return false;
        if (fiber_type < rhs.fiber_type)
            return true;
        if (!(fiber_type == rhs.fiber_type))
            return false;
        if (fiber_manufacturer < rhs.fiber_manufacturer)
            return true;
        if (!(fiber_manufacturer == rhs.fiber_manufacturer))
            return false;
        if (fiber_diameter < rhs.fiber_diameter)
            return true;
        if (!(fiber_diameter == rhs.fiber_diameter))
            return false;
        if (fiber_linear_density < rhs.fiber_linear_density)
            return true;
        if (!(fiber_linear_density == rhs.fiber_linear_density))
            return false;
        if (fiber_spool_length_km < rhs.fiber_spool_length_km)
            return true;
        if (!(fiber_spool_length_km == rhs.fiber_spool_length_km))
            return false;
        if (fiber_cost < rhs.fiber_cost)
            return true;
        if (!(fiber_cost == rhs.fiber_cost))
            return false;
        if (fiber_plastic_name < rhs.fiber_plastic_name)
            return true;
        if (!(fiber_plastic_name == rhs.fiber_plastic_name))
            return false;
        if (fiber_plastic_type < rhs.fiber_plastic_type)
            return true;
        if (!(fiber_plastic_type == rhs.fiber_plastic_type))
            return false;
        if (fiber_plastic_manufacturer < rhs.fiber_plastic_manufacturer)
            return true;
        if (!(fiber_plastic_manufacturer == rhs.fiber_plastic_manufacturer))
            return false;
        if (fiber_plastic_diameter < rhs.fiber_plastic_diameter)
            return true;
        if (!(fiber_plastic_diameter == rhs.fiber_plastic_diameter))
            return false;
        if (fiber_plastic_density < rhs.fiber_plastic_density)
            return true;
        if (!(fiber_plastic_density == rhs.fiber_plastic_density))
            return false;
        if (fiber_plastic_cost < rhs.fiber_plastic_cost)
            return true;
        if (!(fiber_plastic_cost == rhs.fiber_plastic_cost))
            return false;
        if (fiber_plastic_spool_weight < rhs.fiber_plastic_spool_weight)
            return true;
        if (!(fiber_plastic_spool_weight == rhs.fiber_plastic_spool_weight))
            return false;
        if (fiber_nozzle_temperature_preheat < rhs.fiber_nozzle_temperature_preheat)
            return true;
        if (!(fiber_nozzle_temperature_preheat == rhs.fiber_nozzle_temperature_preheat))
            return false;
        if (fiber_nozzle_temperature_standby < rhs.fiber_nozzle_temperature_standby)
            return true;
        if (!(fiber_nozzle_temperature_standby == rhs.fiber_nozzle_temperature_standby))
            return false;
        if (fiber_first_layers_height < rhs.fiber_first_layers_height)
            return true;
        if (!(fiber_first_layers_height == rhs.fiber_first_layers_height))
            return false;
        if (fiber_plastic_extrusion_speed < rhs.fiber_plastic_extrusion_speed)
            return true;
        if (!(fiber_plastic_extrusion_speed == rhs.fiber_plastic_extrusion_speed))
            return false;
        if (fiber_extrusion_speed < rhs.fiber_extrusion_speed)
            return true;
        if (!(fiber_extrusion_speed == rhs.fiber_extrusion_speed))
            return false;
        if (fiber_restart_pause < rhs.fiber_restart_pause)
            return true;
        if (!(fiber_restart_pause == rhs.fiber_restart_pause))
            return false;
        if (plastic_spool_weight < rhs.plastic_spool_weight)
            return true;
        if (!(plastic_spool_weight == rhs.plastic_spool_weight))
            return false;
        if (fiber_finish_ironing_distance < rhs.fiber_finish_ironing_distance)
            return true;
        if (!(fiber_finish_ironing_distance == rhs.fiber_finish_ironing_distance))
            return false;
        if (fiber_priming_line_height < rhs.fiber_priming_line_height)
            return true;
        if (!(fiber_priming_line_height == rhs.fiber_priming_line_height))
            return false;
        if (fiber_material_kind < rhs.fiber_material_kind)
            return true;
        if (!(fiber_material_kind == rhs.fiber_material_kind))
            return false;
        if (fiber_source_material_id < rhs.fiber_source_material_id)
            return true;
        if (!(fiber_source_material_id == rhs.fiber_source_material_id))
            return false;
        if (filament_vendor < rhs.filament_vendor)
            return true;
        if (!(filament_vendor == rhs.filament_vendor))
            return false;
        if (filament_is_support < rhs.filament_is_support)
            return true;
        if (!(filament_is_support == rhs.filament_is_support))
            return false;
        if (filament_printable < rhs.filament_printable)
            return true;
        if (!(filament_printable == rhs.filament_printable))
            return false;
        if (filament_change_length < rhs.filament_change_length)
            return true;
        if (!(filament_change_length == rhs.filament_change_length))
            return false;
        if (filament_cost < rhs.filament_cost)
            return true;
        if (!(filament_cost == rhs.filament_cost))
            return false;
        if (default_filament_colour < rhs.default_filament_colour)
            return true;
        if (!(default_filament_colour == rhs.default_filament_colour))
            return false;
        if (temperature_vitrification < rhs.temperature_vitrification)
            return true;
        if (!(temperature_vitrification == rhs.temperature_vitrification))
            return false;
        if (filament_max_volumetric_speed < rhs.filament_max_volumetric_speed)
            return true;
        if (!(filament_max_volumetric_speed == rhs.filament_max_volumetric_speed))
            return false;
        if (required_nozzle_HRC < rhs.required_nozzle_HRC)
            return true;
        if (!(required_nozzle_HRC == rhs.required_nozzle_HRC))
            return false;
        if (filament_map_mode < rhs.filament_map_mode)
            return true;
        if (!(filament_map_mode == rhs.filament_map_mode))
            return false;
        if (filament_map < rhs.filament_map)
            return true;
        if (!(filament_map == rhs.filament_map))
            return false;
        if (filament_extruder_id < rhs.filament_extruder_id)
            return true;
        if (!(filament_extruder_id == rhs.filament_extruder_id))
            return false;
        if (filament_extruder_variant < rhs.filament_extruder_variant)
            return true;
        if (!(filament_extruder_variant == rhs.filament_extruder_variant))
            return false;
        if (support_object_skip_flush < rhs.support_object_skip_flush)
            return true;
        if (!(support_object_skip_flush == rhs.support_object_skip_flush))
            return false;
        if (bed_temperature_formula < rhs.bed_temperature_formula)
            return true;
        if (!(bed_temperature_formula == rhs.bed_temperature_formula))
            return false;
        if (physical_extruder_map < rhs.physical_extruder_map)
            return true;
        if (!(physical_extruder_map == rhs.physical_extruder_map))
            return false;
        if (nozzle_flush_dataset < rhs.nozzle_flush_dataset)
            return true;
        if (!(nozzle_flush_dataset == rhs.nozzle_flush_dataset))
            return false;
        if (filament_flush_volumetric_speed < rhs.filament_flush_volumetric_speed)
            return true;
        if (!(filament_flush_volumetric_speed == rhs.filament_flush_volumetric_speed))
            return false;
        if (filament_flush_temp < rhs.filament_flush_temp)
            return true;
        if (!(filament_flush_temp == rhs.filament_flush_temp))
            return false;
        if (scan_first_layer < rhs.scan_first_layer)
            return true;
        if (!(scan_first_layer == rhs.scan_first_layer))
            return false;
        if (enable_power_loss_recovery < rhs.enable_power_loss_recovery)
            return true;
        if (!(enable_power_loss_recovery == rhs.enable_power_loss_recovery))
            return false;
        if (enable_wrapping_detection < rhs.enable_wrapping_detection)
            return true;
        if (!(enable_wrapping_detection == rhs.enable_wrapping_detection))
            return false;
        if (wrapping_detection_layers < rhs.wrapping_detection_layers)
            return true;
        if (!(wrapping_detection_layers == rhs.wrapping_detection_layers))
            return false;
        if (wrapping_exclude_area < rhs.wrapping_exclude_area)
            return true;
        if (!(wrapping_exclude_area == rhs.wrapping_exclude_area))
            return false;
        if (thumbnail_size < rhs.thumbnail_size)
            return true;
        if (!(thumbnail_size == rhs.thumbnail_size))
            return false;
        if (spaghetti_detector < rhs.spaghetti_detector)
            return true;
        if (!(spaghetti_detector == rhs.spaghetti_detector))
            return false;
        if (gcode_add_line_number < rhs.gcode_add_line_number)
            return true;
        if (!(gcode_add_line_number == rhs.gcode_add_line_number))
            return false;
        if (bbl_bed_temperature_gcode < rhs.bbl_bed_temperature_gcode)
            return true;
        if (!(bbl_bed_temperature_gcode == rhs.bbl_bed_temperature_gcode))
            return false;
        if (gcode_flavor < rhs.gcode_flavor)
            return true;
        if (!(gcode_flavor == rhs.gcode_flavor))
            return false;
        if (time_cost < rhs.time_cost)
            return true;
        if (!(time_cost == rhs.time_cost))
            return false;
        if (layer_change_gcode < rhs.layer_change_gcode)
            return true;
        if (!(layer_change_gcode == rhs.layer_change_gcode))
            return false;
        if (time_lapse_gcode < rhs.time_lapse_gcode)
            return true;
        if (!(time_lapse_gcode == rhs.time_lapse_gcode))
            return false;
        if (wrapping_detection_gcode < rhs.wrapping_detection_gcode)
            return true;
        if (!(wrapping_detection_gcode == rhs.wrapping_detection_gcode))
            return false;
        if (max_volumetric_extrusion_rate_slope < rhs.max_volumetric_extrusion_rate_slope)
            return true;
        if (!(max_volumetric_extrusion_rate_slope == rhs.max_volumetric_extrusion_rate_slope))
            return false;
        if (max_volumetric_extrusion_rate_slope_segment_length < rhs.max_volumetric_extrusion_rate_slope_segment_length)
            return true;
        if (!(max_volumetric_extrusion_rate_slope_segment_length == rhs.max_volumetric_extrusion_rate_slope_segment_length))
            return false;
        if (extrusion_rate_smoothing_external_perimeter_only < rhs.extrusion_rate_smoothing_external_perimeter_only)
            return true;
        if (!(extrusion_rate_smoothing_external_perimeter_only == rhs.extrusion_rate_smoothing_external_perimeter_only))
            return false;
        if (retract_before_wipe < rhs.retract_before_wipe)
            return true;
        if (!(retract_before_wipe == rhs.retract_before_wipe))
            return false;
        if (retraction_length < rhs.retraction_length)
            return true;
        if (!(retraction_length == rhs.retraction_length))
            return false;
        if (retract_length_toolchange < rhs.retract_length_toolchange)
            return true;
        if (!(retract_length_toolchange == rhs.retract_length_toolchange))
            return false;
        if (enable_long_retraction_when_cut < rhs.enable_long_retraction_when_cut)
            return true;
        if (!(enable_long_retraction_when_cut == rhs.enable_long_retraction_when_cut))
            return false;
        if (retraction_distances_when_cut < rhs.retraction_distances_when_cut)
            return true;
        if (!(retraction_distances_when_cut == rhs.retraction_distances_when_cut))
            return false;
        if (long_retractions_when_cut < rhs.long_retractions_when_cut)
            return true;
        if (!(long_retractions_when_cut == rhs.long_retractions_when_cut))
            return false;
        if (retraction_distances_when_ec < rhs.retraction_distances_when_ec)
            return true;
        if (!(retraction_distances_when_ec == rhs.retraction_distances_when_ec))
            return false;
        if (long_retractions_when_ec < rhs.long_retractions_when_ec)
            return true;
        if (!(long_retractions_when_ec == rhs.long_retractions_when_ec))
            return false;
        if (z_hop < rhs.z_hop)
            return true;
        if (!(z_hop == rhs.z_hop))
            return false;
        if (z_hop_types < rhs.z_hop_types)
            return true;
        if (!(z_hop_types == rhs.z_hop_types))
            return false;
        if (travel_slope < rhs.travel_slope)
            return true;
        if (!(travel_slope == rhs.travel_slope))
            return false;
        if (retract_lift_above < rhs.retract_lift_above)
            return true;
        if (!(retract_lift_above == rhs.retract_lift_above))
            return false;
        if (retract_lift_below < rhs.retract_lift_below)
            return true;
        if (!(retract_lift_below == rhs.retract_lift_below))
            return false;
        if (retract_lift_enforce < rhs.retract_lift_enforce)
            return true;
        if (!(retract_lift_enforce == rhs.retract_lift_enforce))
            return false;
        if (retract_restart_extra < rhs.retract_restart_extra)
            return true;
        if (!(retract_restart_extra == rhs.retract_restart_extra))
            return false;
        if (retract_restart_extra_toolchange < rhs.retract_restart_extra_toolchange)
            return true;
        if (!(retract_restart_extra_toolchange == rhs.retract_restart_extra_toolchange))
            return false;
        if (retraction_speed < rhs.retraction_speed)
            return true;
        if (!(retraction_speed == rhs.retraction_speed))
            return false;
        if (file_start_gcode < rhs.file_start_gcode)
            return true;
        if (!(file_start_gcode == rhs.file_start_gcode))
            return false;
        if (machine_start_gcode < rhs.machine_start_gcode)
            return true;
        if (!(machine_start_gcode == rhs.machine_start_gcode))
            return false;
        if (filament_start_gcode < rhs.filament_start_gcode)
            return true;
        if (!(filament_start_gcode == rhs.filament_start_gcode))
            return false;
        if (single_extruder_multi_material < rhs.single_extruder_multi_material)
            return true;
        if (!(single_extruder_multi_material == rhs.single_extruder_multi_material))
            return false;
        if (manual_filament_change < rhs.manual_filament_change)
            return true;
        if (!(manual_filament_change == rhs.manual_filament_change))
            return false;
        if (single_extruder_multi_material_priming < rhs.single_extruder_multi_material_priming)
            return true;
        if (!(single_extruder_multi_material_priming == rhs.single_extruder_multi_material_priming))
            return false;
        if (wipe_tower_no_sparse_layers < rhs.wipe_tower_no_sparse_layers)
            return true;
        if (!(wipe_tower_no_sparse_layers == rhs.wipe_tower_no_sparse_layers))
            return false;
        if (change_filament_gcode < rhs.change_filament_gcode)
            return true;
        if (!(change_filament_gcode == rhs.change_filament_gcode))
            return false;
        if (change_extrusion_role_gcode < rhs.change_extrusion_role_gcode)
            return true;
        if (!(change_extrusion_role_gcode == rhs.change_extrusion_role_gcode))
            return false;
        if (process_change_extrusion_role_gcode < rhs.process_change_extrusion_role_gcode)
            return true;
        if (!(process_change_extrusion_role_gcode == rhs.process_change_extrusion_role_gcode))
            return false;
        if (filament_change_extrusion_role_gcode < rhs.filament_change_extrusion_role_gcode)
            return true;
        if (!(filament_change_extrusion_role_gcode == rhs.filament_change_extrusion_role_gcode))
            return false;
        if (travel_speed < rhs.travel_speed)
            return true;
        if (!(travel_speed == rhs.travel_speed))
            return false;
        if (travel_speed_z < rhs.travel_speed_z)
            return true;
        if (!(travel_speed_z == rhs.travel_speed_z))
            return false;
        if (silent_mode < rhs.silent_mode)
            return true;
        if (!(silent_mode == rhs.silent_mode))
            return false;
        if (machine_pause_gcode < rhs.machine_pause_gcode)
            return true;
        if (!(machine_pause_gcode == rhs.machine_pause_gcode))
            return false;
        if (template_custom_gcode < rhs.template_custom_gcode)
            return true;
        if (!(template_custom_gcode == rhs.template_custom_gcode))
            return false;
        if (nozzle_type < rhs.nozzle_type)
            return true;
        if (!(nozzle_type == rhs.nozzle_type))
            return false;
        if (nozzle_hrc < rhs.nozzle_hrc)
            return true;
        if (!(nozzle_hrc == rhs.nozzle_hrc))
            return false;
        if (auxiliary_fan < rhs.auxiliary_fan)
            return true;
        if (!(auxiliary_fan == rhs.auxiliary_fan))
            return false;
        if (support_air_filtration < rhs.support_air_filtration)
            return true;
        if (!(support_air_filtration == rhs.support_air_filtration))
            return false;
        if (printer_structure < rhs.printer_structure)
            return true;
        if (!(printer_structure == rhs.printer_structure))
            return false;
        if (support_chamber_temp_control < rhs.support_chamber_temp_control)
            return true;
        if (!(support_chamber_temp_control == rhs.support_chamber_temp_control))
            return false;
        if (extruder_type < rhs.extruder_type)
            return true;
        if (!(extruder_type == rhs.extruder_type))
            return false;
        if (nozzle_volume_type < rhs.nozzle_volume_type)
            return true;
        if (!(nozzle_volume_type == rhs.nozzle_volume_type))
            return false;
        if (extruder_ams_count < rhs.extruder_ams_count)
            return true;
        if (!(extruder_ams_count == rhs.extruder_ams_count))
            return false;
        if (printer_extruder_id < rhs.printer_extruder_id)
            return true;
        if (!(printer_extruder_id == rhs.printer_extruder_id))
            return false;
        if (master_extruder_id < rhs.master_extruder_id)
            return true;
        if (!(master_extruder_id == rhs.master_extruder_id))
            return false;
        if (printer_extruder_variant < rhs.printer_extruder_variant)
            return true;
        if (!(printer_extruder_variant == rhs.printer_extruder_variant))
            return false;
        if (use_firmware_retraction < rhs.use_firmware_retraction)
            return true;
        if (!(use_firmware_retraction == rhs.use_firmware_retraction))
            return false;
        if (use_relative_e_distances < rhs.use_relative_e_distances)
            return true;
        if (!(use_relative_e_distances == rhs.use_relative_e_distances))
            return false;
        if (accel_to_decel_enable < rhs.accel_to_decel_enable)
            return true;
        if (!(accel_to_decel_enable == rhs.accel_to_decel_enable))
            return false;
        if (accel_to_decel_factor < rhs.accel_to_decel_factor)
            return true;
        if (!(accel_to_decel_factor == rhs.accel_to_decel_factor))
            return false;
        if (initial_layer_travel_speed < rhs.initial_layer_travel_speed)
            return true;
        if (!(initial_layer_travel_speed == rhs.initial_layer_travel_speed))
            return false;
        if (initial_layer_travel_acceleration < rhs.initial_layer_travel_acceleration)
            return true;
        if (!(initial_layer_travel_acceleration == rhs.initial_layer_travel_acceleration))
            return false;
        if (initial_layer_travel_jerk < rhs.initial_layer_travel_jerk)
            return true;
        if (!(initial_layer_travel_jerk == rhs.initial_layer_travel_jerk))
            return false;
        if (bbl_calib_mark_logo < rhs.bbl_calib_mark_logo)
            return true;
        if (!(bbl_calib_mark_logo == rhs.bbl_calib_mark_logo))
            return false;
        if (disable_m73 < rhs.disable_m73)
            return true;
        if (!(disable_m73 == rhs.disable_m73))
            return false;
        if (cooling_tube_retraction < rhs.cooling_tube_retraction)
            return true;
        if (!(cooling_tube_retraction == rhs.cooling_tube_retraction))
            return false;
        if (cooling_tube_length < rhs.cooling_tube_length)
            return true;
        if (!(cooling_tube_length == rhs.cooling_tube_length))
            return false;
        if (high_current_on_filament_swap < rhs.high_current_on_filament_swap)
            return true;
        if (!(high_current_on_filament_swap == rhs.high_current_on_filament_swap))
            return false;
        if (parking_pos_retraction < rhs.parking_pos_retraction)
            return true;
        if (!(parking_pos_retraction == rhs.parking_pos_retraction))
            return false;
        if (extra_loading_move < rhs.extra_loading_move)
            return true;
        if (!(extra_loading_move == rhs.extra_loading_move))
            return false;
        if (machine_load_filament_time < rhs.machine_load_filament_time)
            return true;
        if (!(machine_load_filament_time == rhs.machine_load_filament_time))
            return false;
        if (machine_tool_change_time < rhs.machine_tool_change_time)
            return true;
        if (!(machine_tool_change_time == rhs.machine_tool_change_time))
            return false;
        if (machine_unload_filament_time < rhs.machine_unload_filament_time)
            return true;
        if (!(machine_unload_filament_time == rhs.machine_unload_filament_time))
            return false;
        if (filament_loading_speed < rhs.filament_loading_speed)
            return true;
        if (!(filament_loading_speed == rhs.filament_loading_speed))
            return false;
        if (filament_loading_speed_start < rhs.filament_loading_speed_start)
            return true;
        if (!(filament_loading_speed_start == rhs.filament_loading_speed_start))
            return false;
        if (filament_unloading_speed < rhs.filament_unloading_speed)
            return true;
        if (!(filament_unloading_speed == rhs.filament_unloading_speed))
            return false;
        if (filament_unloading_speed_start < rhs.filament_unloading_speed_start)
            return true;
        if (!(filament_unloading_speed_start == rhs.filament_unloading_speed_start))
            return false;
        if (filament_toolchange_delay < rhs.filament_toolchange_delay)
            return true;
        if (!(filament_toolchange_delay == rhs.filament_toolchange_delay))
            return false;
        if (filament_cooling_moves < rhs.filament_cooling_moves)
            return true;
        if (!(filament_cooling_moves == rhs.filament_cooling_moves))
            return false;
        if (filament_cooling_initial_speed < rhs.filament_cooling_initial_speed)
            return true;
        if (!(filament_cooling_initial_speed == rhs.filament_cooling_initial_speed))
            return false;
        if (filament_minimal_purge_on_wipe_tower < rhs.filament_minimal_purge_on_wipe_tower)
            return true;
        if (!(filament_minimal_purge_on_wipe_tower == rhs.filament_minimal_purge_on_wipe_tower))
            return false;
        if (filament_cooling_before_tower < rhs.filament_cooling_before_tower)
            return true;
        if (!(filament_cooling_before_tower == rhs.filament_cooling_before_tower))
            return false;
        if (filament_tower_interface_pre_extrusion_dist < rhs.filament_tower_interface_pre_extrusion_dist)
            return true;
        if (!(filament_tower_interface_pre_extrusion_dist == rhs.filament_tower_interface_pre_extrusion_dist))
            return false;
        if (filament_tower_interface_pre_extrusion_length < rhs.filament_tower_interface_pre_extrusion_length)
            return true;
        if (!(filament_tower_interface_pre_extrusion_length == rhs.filament_tower_interface_pre_extrusion_length))
            return false;
        if (filament_tower_ironing_area < rhs.filament_tower_ironing_area)
            return true;
        if (!(filament_tower_ironing_area == rhs.filament_tower_ironing_area))
            return false;
        if (filament_tower_interface_purge_volume < rhs.filament_tower_interface_purge_volume)
            return true;
        if (!(filament_tower_interface_purge_volume == rhs.filament_tower_interface_purge_volume))
            return false;
        if (filament_tower_interface_print_temp < rhs.filament_tower_interface_print_temp)
            return true;
        if (!(filament_tower_interface_print_temp == rhs.filament_tower_interface_print_temp))
            return false;
        if (filament_cooling_final_speed < rhs.filament_cooling_final_speed)
            return true;
        if (!(filament_cooling_final_speed == rhs.filament_cooling_final_speed))
            return false;
        if (filament_ramming_parameters < rhs.filament_ramming_parameters)
            return true;
        if (!(filament_ramming_parameters == rhs.filament_ramming_parameters))
            return false;
        if (filament_multitool_ramming < rhs.filament_multitool_ramming)
            return true;
        if (!(filament_multitool_ramming == rhs.filament_multitool_ramming))
            return false;
        if (filament_multitool_ramming_volume < rhs.filament_multitool_ramming_volume)
            return true;
        if (!(filament_multitool_ramming_volume == rhs.filament_multitool_ramming_volume))
            return false;
        if (filament_multitool_ramming_flow < rhs.filament_multitool_ramming_flow)
            return true;
        if (!(filament_multitool_ramming_flow == rhs.filament_multitool_ramming_flow))
            return false;
        if (filament_stamping_loading_speed < rhs.filament_stamping_loading_speed)
            return true;
        if (!(filament_stamping_loading_speed == rhs.filament_stamping_loading_speed))
            return false;
        if (filament_stamping_distance < rhs.filament_stamping_distance)
            return true;
        if (!(filament_stamping_distance == rhs.filament_stamping_distance))
            return false;
        if (wipe_tower_type < rhs.wipe_tower_type)
            return true;
        if (!(wipe_tower_type == rhs.wipe_tower_type))
            return false;
        if (purge_in_prime_tower < rhs.purge_in_prime_tower)
            return true;
        if (!(purge_in_prime_tower == rhs.purge_in_prime_tower))
            return false;
        if (enable_filament_ramming < rhs.enable_filament_ramming)
            return true;
        if (!(enable_filament_ramming == rhs.enable_filament_ramming))
            return false;
        if (tool_change_on_wipe_tower < rhs.tool_change_on_wipe_tower)
            return true;
        if (!(tool_change_on_wipe_tower == rhs.tool_change_on_wipe_tower))
            return false;
        if (support_multi_bed_types < rhs.support_multi_bed_types)
            return true;
        if (!(support_multi_bed_types == rhs.support_multi_bed_types))
            return false;
        if (use_3mf < rhs.use_3mf)
            return true;
        if (!(use_3mf == rhs.use_3mf))
            return false;
        if (small_area_infill_flow_compensation_model < rhs.small_area_infill_flow_compensation_model)
            return true;
        if (!(small_area_infill_flow_compensation_model == rhs.small_area_infill_flow_compensation_model))
            return false;
        if (has_scarf_joint_seam < rhs.has_scarf_joint_seam)
            return true;
        if (!(has_scarf_joint_seam == rhs.has_scarf_joint_seam))
            return false;
        return false;
    }

protected:
    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        cache.opt_add("before_layer_change_gcode", base_ptr, this->before_layer_change_gcode);
        cache.opt_add("printing_by_object_gcode", base_ptr, this->printing_by_object_gcode);
        cache.opt_add("deretraction_speed", base_ptr, this->deretraction_speed);
        cache.opt_add("enable_arc_fitting", base_ptr, this->enable_arc_fitting);
        cache.opt_add("machine_end_gcode", base_ptr, this->machine_end_gcode);
        cache.opt_add("filament_end_gcode", base_ptr, this->filament_end_gcode);
        cache.opt_add("filament_flow_ratio", base_ptr, this->filament_flow_ratio);
        cache.opt_add("enable_pressure_advance", base_ptr, this->enable_pressure_advance);
        cache.opt_add("pressure_advance", base_ptr, this->pressure_advance);
        cache.opt_add("adaptive_pressure_advance", base_ptr, this->adaptive_pressure_advance);
        cache.opt_add("adaptive_pressure_advance_overhangs", base_ptr, this->adaptive_pressure_advance_overhangs);
        cache.opt_add("adaptive_pressure_advance_model", base_ptr, this->adaptive_pressure_advance_model);
        cache.opt_add("adaptive_pressure_advance_bridges", base_ptr, this->adaptive_pressure_advance_bridges);
        cache.opt_add("fan_kickstart", base_ptr, this->fan_kickstart);
        cache.opt_add("fan_speedup_overhangs", base_ptr, this->fan_speedup_overhangs);
        cache.opt_add("fan_speedup_time", base_ptr, this->fan_speedup_time);
        cache.opt_add("part_cooling_fan_min_pwm", base_ptr, this->part_cooling_fan_min_pwm);
        cache.opt_add("filament_diameter", base_ptr, this->filament_diameter);
        cache.opt_add("filament_adaptive_volumetric_speed", base_ptr, this->filament_adaptive_volumetric_speed);
        cache.opt_add("volumetric_speed_coefficients", base_ptr, this->volumetric_speed_coefficients);
        cache.opt_add("filament_adhesiveness_category", base_ptr, this->filament_adhesiveness_category);
        cache.opt_add("filament_density", base_ptr, this->filament_density);
        cache.opt_add("filament_type", base_ptr, this->filament_type);
        cache.opt_add("filament_soluble", base_ptr, this->filament_soluble);
        cache.opt_add("filament_ids", base_ptr, this->filament_ids);
        cache.opt_add("filament_colour", base_ptr, this->filament_colour);
        cache.opt_add("composite_enabled", base_ptr, this->composite_enabled);
        cache.opt_add("fiber_name", base_ptr, this->fiber_name);
        cache.opt_add("fiber_type", base_ptr, this->fiber_type);
        cache.opt_add("fiber_manufacturer", base_ptr, this->fiber_manufacturer);
        cache.opt_add("fiber_diameter", base_ptr, this->fiber_diameter);
        cache.opt_add("fiber_linear_density", base_ptr, this->fiber_linear_density);
        cache.opt_add("fiber_spool_length_km", base_ptr, this->fiber_spool_length_km);
        cache.opt_add("fiber_cost", base_ptr, this->fiber_cost);
        cache.opt_add("fiber_plastic_name", base_ptr, this->fiber_plastic_name);
        cache.opt_add("fiber_plastic_type", base_ptr, this->fiber_plastic_type);
        cache.opt_add("fiber_plastic_manufacturer", base_ptr, this->fiber_plastic_manufacturer);
        cache.opt_add("fiber_plastic_diameter", base_ptr, this->fiber_plastic_diameter);
        cache.opt_add("fiber_plastic_density", base_ptr, this->fiber_plastic_density);
        cache.opt_add("fiber_plastic_cost", base_ptr, this->fiber_plastic_cost);
        cache.opt_add("fiber_plastic_spool_weight", base_ptr, this->fiber_plastic_spool_weight);
        cache.opt_add("fiber_nozzle_temperature_preheat", base_ptr, this->fiber_nozzle_temperature_preheat);
        cache.opt_add("fiber_nozzle_temperature_standby", base_ptr, this->fiber_nozzle_temperature_standby);
        cache.opt_add("fiber_first_layers_height", base_ptr, this->fiber_first_layers_height);
        cache.opt_add("fiber_plastic_extrusion_speed", base_ptr, this->fiber_plastic_extrusion_speed);
        cache.opt_add("fiber_extrusion_speed", base_ptr, this->fiber_extrusion_speed);
        cache.opt_add("fiber_restart_pause", base_ptr, this->fiber_restart_pause);
        cache.opt_add("plastic_spool_weight", base_ptr, this->plastic_spool_weight);
        cache.opt_add("fiber_finish_ironing_distance", base_ptr, this->fiber_finish_ironing_distance);
        cache.opt_add("fiber_priming_line_height", base_ptr, this->fiber_priming_line_height);
        cache.opt_add("fiber_material_kind", base_ptr, this->fiber_material_kind);
        cache.opt_add("fiber_source_material_id", base_ptr, this->fiber_source_material_id);
        cache.opt_add("filament_vendor", base_ptr, this->filament_vendor);
        cache.opt_add("filament_is_support", base_ptr, this->filament_is_support);
        cache.opt_add("filament_printable", base_ptr, this->filament_printable);
        cache.opt_add("filament_change_length", base_ptr, this->filament_change_length);
        cache.opt_add("filament_cost", base_ptr, this->filament_cost);
        cache.opt_add("default_filament_colour", base_ptr, this->default_filament_colour);
        cache.opt_add("temperature_vitrification", base_ptr, this->temperature_vitrification);
        cache.opt_add("filament_max_volumetric_speed", base_ptr, this->filament_max_volumetric_speed);
        cache.opt_add("required_nozzle_HRC", base_ptr, this->required_nozzle_HRC);
        cache.opt_add("filament_map_mode", base_ptr, this->filament_map_mode);
        cache.opt_add("filament_map", base_ptr, this->filament_map);
        cache.opt_add("filament_extruder_id", base_ptr, this->filament_extruder_id);
        cache.opt_add("filament_extruder_variant", base_ptr, this->filament_extruder_variant);
        cache.opt_add("support_object_skip_flush", base_ptr, this->support_object_skip_flush);
        cache.opt_add("bed_temperature_formula", base_ptr, this->bed_temperature_formula);
        cache.opt_add("physical_extruder_map", base_ptr, this->physical_extruder_map);
        cache.opt_add("nozzle_flush_dataset", base_ptr, this->nozzle_flush_dataset);
        cache.opt_add("filament_flush_volumetric_speed", base_ptr, this->filament_flush_volumetric_speed);
        cache.opt_add("filament_flush_temp", base_ptr, this->filament_flush_temp);
        cache.opt_add("scan_first_layer", base_ptr, this->scan_first_layer);
        cache.opt_add("enable_power_loss_recovery", base_ptr, this->enable_power_loss_recovery);
        cache.opt_add("enable_wrapping_detection", base_ptr, this->enable_wrapping_detection);
        cache.opt_add("wrapping_detection_layers", base_ptr, this->wrapping_detection_layers);
        cache.opt_add("wrapping_exclude_area", base_ptr, this->wrapping_exclude_area);
        cache.opt_add("thumbnail_size", base_ptr, this->thumbnail_size);
        cache.opt_add("spaghetti_detector", base_ptr, this->spaghetti_detector);
        cache.opt_add("gcode_add_line_number", base_ptr, this->gcode_add_line_number);
        cache.opt_add("bbl_bed_temperature_gcode", base_ptr, this->bbl_bed_temperature_gcode);
        cache.opt_add("gcode_flavor", base_ptr, this->gcode_flavor);
        cache.opt_add("time_cost", base_ptr, this->time_cost);
        cache.opt_add("layer_change_gcode", base_ptr, this->layer_change_gcode);
        cache.opt_add("time_lapse_gcode", base_ptr, this->time_lapse_gcode);
        cache.opt_add("wrapping_detection_gcode", base_ptr, this->wrapping_detection_gcode);
        cache.opt_add("max_volumetric_extrusion_rate_slope", base_ptr, this->max_volumetric_extrusion_rate_slope);
        cache.opt_add("max_volumetric_extrusion_rate_slope_segment_length", base_ptr, this->max_volumetric_extrusion_rate_slope_segment_length);
        cache.opt_add("extrusion_rate_smoothing_external_perimeter_only", base_ptr, this->extrusion_rate_smoothing_external_perimeter_only);
        cache.opt_add("retract_before_wipe", base_ptr, this->retract_before_wipe);
        cache.opt_add("retraction_length", base_ptr, this->retraction_length);
        cache.opt_add("retract_length_toolchange", base_ptr, this->retract_length_toolchange);
        cache.opt_add("enable_long_retraction_when_cut", base_ptr, this->enable_long_retraction_when_cut);
        cache.opt_add("retraction_distances_when_cut", base_ptr, this->retraction_distances_when_cut);
        cache.opt_add("long_retractions_when_cut", base_ptr, this->long_retractions_when_cut);
        cache.opt_add("retraction_distances_when_ec", base_ptr, this->retraction_distances_when_ec);
        cache.opt_add("long_retractions_when_ec", base_ptr, this->long_retractions_when_ec);
        cache.opt_add("z_hop", base_ptr, this->z_hop);
        cache.opt_add("z_hop_types", base_ptr, this->z_hop_types);
        cache.opt_add("travel_slope", base_ptr, this->travel_slope);
        cache.opt_add("retract_lift_above", base_ptr, this->retract_lift_above);
        cache.opt_add("retract_lift_below", base_ptr, this->retract_lift_below);
        cache.opt_add("retract_lift_enforce", base_ptr, this->retract_lift_enforce);
        cache.opt_add("retract_restart_extra", base_ptr, this->retract_restart_extra);
        cache.opt_add("retract_restart_extra_toolchange", base_ptr, this->retract_restart_extra_toolchange);
        cache.opt_add("retraction_speed", base_ptr, this->retraction_speed);
        cache.opt_add("file_start_gcode", base_ptr, this->file_start_gcode);
        cache.opt_add("machine_start_gcode", base_ptr, this->machine_start_gcode);
        cache.opt_add("filament_start_gcode", base_ptr, this->filament_start_gcode);
        cache.opt_add("single_extruder_multi_material", base_ptr, this->single_extruder_multi_material);
        cache.opt_add("manual_filament_change", base_ptr, this->manual_filament_change);
        cache.opt_add("single_extruder_multi_material_priming", base_ptr, this->single_extruder_multi_material_priming);
        cache.opt_add("wipe_tower_no_sparse_layers", base_ptr, this->wipe_tower_no_sparse_layers);
        cache.opt_add("change_filament_gcode", base_ptr, this->change_filament_gcode);
        cache.opt_add("change_extrusion_role_gcode", base_ptr, this->change_extrusion_role_gcode);
        cache.opt_add("process_change_extrusion_role_gcode", base_ptr, this->process_change_extrusion_role_gcode);
        cache.opt_add("filament_change_extrusion_role_gcode", base_ptr, this->filament_change_extrusion_role_gcode);
        cache.opt_add("travel_speed", base_ptr, this->travel_speed);
        cache.opt_add("travel_speed_z", base_ptr, this->travel_speed_z);
        cache.opt_add("silent_mode", base_ptr, this->silent_mode);
        cache.opt_add("machine_pause_gcode", base_ptr, this->machine_pause_gcode);
        cache.opt_add("template_custom_gcode", base_ptr, this->template_custom_gcode);
        cache.opt_add("nozzle_type", base_ptr, this->nozzle_type);
        cache.opt_add("nozzle_hrc", base_ptr, this->nozzle_hrc);
        cache.opt_add("auxiliary_fan", base_ptr, this->auxiliary_fan);
        cache.opt_add("support_air_filtration", base_ptr, this->support_air_filtration);
        cache.opt_add("printer_structure", base_ptr, this->printer_structure);
        cache.opt_add("support_chamber_temp_control", base_ptr, this->support_chamber_temp_control);
        cache.opt_add("extruder_type", base_ptr, this->extruder_type);
        cache.opt_add("nozzle_volume_type", base_ptr, this->nozzle_volume_type);
        cache.opt_add("extruder_ams_count", base_ptr, this->extruder_ams_count);
        cache.opt_add("printer_extruder_id", base_ptr, this->printer_extruder_id);
        cache.opt_add("master_extruder_id", base_ptr, this->master_extruder_id);
        cache.opt_add("printer_extruder_variant", base_ptr, this->printer_extruder_variant);
        cache.opt_add("use_firmware_retraction", base_ptr, this->use_firmware_retraction);
        cache.opt_add("use_relative_e_distances", base_ptr, this->use_relative_e_distances);
        cache.opt_add("accel_to_decel_enable", base_ptr, this->accel_to_decel_enable);
        cache.opt_add("accel_to_decel_factor", base_ptr, this->accel_to_decel_factor);
        cache.opt_add("initial_layer_travel_speed", base_ptr, this->initial_layer_travel_speed);
        cache.opt_add("initial_layer_travel_acceleration", base_ptr, this->initial_layer_travel_acceleration);
        cache.opt_add("initial_layer_travel_jerk", base_ptr, this->initial_layer_travel_jerk);
        cache.opt_add("bbl_calib_mark_logo", base_ptr, this->bbl_calib_mark_logo);
        cache.opt_add("disable_m73", base_ptr, this->disable_m73);
        cache.opt_add("cooling_tube_retraction", base_ptr, this->cooling_tube_retraction);
        cache.opt_add("cooling_tube_length", base_ptr, this->cooling_tube_length);
        cache.opt_add("high_current_on_filament_swap", base_ptr, this->high_current_on_filament_swap);
        cache.opt_add("parking_pos_retraction", base_ptr, this->parking_pos_retraction);
        cache.opt_add("extra_loading_move", base_ptr, this->extra_loading_move);
        cache.opt_add("machine_load_filament_time", base_ptr, this->machine_load_filament_time);
        cache.opt_add("machine_tool_change_time", base_ptr, this->machine_tool_change_time);
        cache.opt_add("machine_unload_filament_time", base_ptr, this->machine_unload_filament_time);
        cache.opt_add("filament_loading_speed", base_ptr, this->filament_loading_speed);
        cache.opt_add("filament_loading_speed_start", base_ptr, this->filament_loading_speed_start);
        cache.opt_add("filament_unloading_speed", base_ptr, this->filament_unloading_speed);
        cache.opt_add("filament_unloading_speed_start", base_ptr, this->filament_unloading_speed_start);
        cache.opt_add("filament_toolchange_delay", base_ptr, this->filament_toolchange_delay);
        cache.opt_add("filament_cooling_moves", base_ptr, this->filament_cooling_moves);
        cache.opt_add("filament_cooling_initial_speed", base_ptr, this->filament_cooling_initial_speed);
        cache.opt_add("filament_minimal_purge_on_wipe_tower", base_ptr, this->filament_minimal_purge_on_wipe_tower);
        cache.opt_add("filament_cooling_before_tower", base_ptr, this->filament_cooling_before_tower);
        cache.opt_add("filament_tower_interface_pre_extrusion_dist", base_ptr, this->filament_tower_interface_pre_extrusion_dist);
        cache.opt_add("filament_tower_interface_pre_extrusion_length", base_ptr, this->filament_tower_interface_pre_extrusion_length);
        cache.opt_add("filament_tower_ironing_area", base_ptr, this->filament_tower_ironing_area);
        cache.opt_add("filament_tower_interface_purge_volume", base_ptr, this->filament_tower_interface_purge_volume);
        cache.opt_add("filament_tower_interface_print_temp", base_ptr, this->filament_tower_interface_print_temp);
        cache.opt_add("filament_cooling_final_speed", base_ptr, this->filament_cooling_final_speed);
        cache.opt_add("filament_ramming_parameters", base_ptr, this->filament_ramming_parameters);
        cache.opt_add("filament_multitool_ramming", base_ptr, this->filament_multitool_ramming);
        cache.opt_add("filament_multitool_ramming_volume", base_ptr, this->filament_multitool_ramming_volume);
        cache.opt_add("filament_multitool_ramming_flow", base_ptr, this->filament_multitool_ramming_flow);
        cache.opt_add("filament_stamping_loading_speed", base_ptr, this->filament_stamping_loading_speed);
        cache.opt_add("filament_stamping_distance", base_ptr, this->filament_stamping_distance);
        cache.opt_add("wipe_tower_type", base_ptr, this->wipe_tower_type);
        cache.opt_add("purge_in_prime_tower", base_ptr, this->purge_in_prime_tower);
        cache.opt_add("enable_filament_ramming", base_ptr, this->enable_filament_ramming);
        cache.opt_add("tool_change_on_wipe_tower", base_ptr, this->tool_change_on_wipe_tower);
        cache.opt_add("support_multi_bed_types", base_ptr, this->support_multi_bed_types);
        cache.opt_add("use_3mf", base_ptr, this->use_3mf);
        cache.opt_add("small_area_infill_flow_compensation_model", base_ptr, this->small_area_infill_flow_compensation_model);
        cache.opt_add("has_scarf_joint_seam", base_ptr, this->has_scarf_joint_seam);
    }
};

// This object is mapped to Perl as Slic3r::Config::Print.
class PrintConfig : public MachineEnvelopeConfig, public GCodeConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(PrintConfig)
public:
    PrintConfig() : MachineEnvelopeConfig(0), GCodeConfig(0) { assert(s_cache_PrintConfig.initialized()); *this = s_cache_PrintConfig.defaults(); }

    ConfigOptionInts additional_cooling_fan_speed;
    ConfigOptionInts close_additional_fan_first_x_layers;
    ConfigOptionInts additional_fan_full_speed_layer;
    ConfigOptionFloats first_x_layer_fan_speed;
    ConfigOptionBool reduce_crossing_wall;
    ConfigOptionFloatOrPercent max_travel_detour_distance;
    ConfigOptionPoints printable_area;
    ConfigOptionPointsGroups extruder_printable_area;
    ConfigOptionBool support_parallel_printheads;
    ConfigOptionInt parallel_printheads_count;
    ConfigOptionStrings parallel_printheads_bed_exclude_areas;
    ConfigOptionPoints bed_exclude_area;
    ConfigOptionPoints head_wrap_detect_zone;
    ConfigOptionString bed_custom_texture;
    ConfigOptionString bed_custom_model;
    ConfigOptionEnum<BedType> curr_bed_type;
    ConfigOptionInts cool_plate_temp;
    ConfigOptionInts textured_cool_plate_temp;
    ConfigOptionInts supertack_plate_temp;
    ConfigOptionInts eng_plate_temp;
    ConfigOptionInts hot_plate_temp;
    ConfigOptionInts textured_plate_temp;
    ConfigOptionInts supertack_plate_temp_initial_layer;
    ConfigOptionInts cool_plate_temp_initial_layer;
    ConfigOptionInts textured_cool_plate_temp_initial_layer;
    ConfigOptionInts eng_plate_temp_initial_layer;
    ConfigOptionInts hot_plate_temp_initial_layer;
    ConfigOptionInts textured_plate_temp_initial_layer;
    ConfigOptionBools enable_overhang_bridge_fan;
    ConfigOptionInts overhang_fan_speed;
    ConfigOptionEnumsGeneric overhang_fan_threshold;
    ConfigOptionEnum<PrintSequence> print_sequence;
    ConfigOptionEnum<PrintOrder> print_order;
    ConfigOptionInts first_layer_print_sequence;
    ConfigOptionInts other_layers_print_sequence;
    ConfigOptionInt other_layers_print_sequence_nums;
    ConfigOptionBools slow_down_for_layer_cooling;
    ConfigOptionInts close_fan_the_first_x_layers;
    ConfigOptionEnum<DraftShield> draft_shield;
    ConfigOptionFloat extruder_clearance_height_to_rod;
    ConfigOptionFloat extruder_clearance_height_to_lid;
    ConfigOptionFloat extruder_clearance_radius;
    ConfigOptionFloat nozzle_height;
    ConfigOptionStrings extruder_colour;
    ConfigOptionPoints extruder_offset;
    ConfigOptionBools reduce_fan_stop_start_freq;
    ConfigOptionBools dont_slow_down_outer_wall;
    ConfigOptionFloats fan_cooling_layer_time;
    ConfigOptionBools activate_air_filtration;
    ConfigOptionBools activate_air_filtration_during_print;
    ConfigOptionBools activate_air_filtration_on_completion;
    ConfigOptionInts during_print_exhaust_fan_speed;
    ConfigOptionInts complete_print_exhaust_fan_speed;
    ConfigOptionFloatOrPercent initial_layer_line_width;
    ConfigOptionFloat initial_layer_print_height;
    ConfigOptionFloat initial_layer_speed;
    ConfigOptionFloat initial_layer_infill_speed;
    ConfigOptionInts nozzle_temperature_initial_layer;
    ConfigOptionInts full_fan_speed_layer;
    ConfigOptionFloats fan_max_speed;
    ConfigOptionFloats max_layer_height;
    ConfigOptionFloats fan_min_speed;
    ConfigOptionFloats min_layer_height;
    ConfigOptionFloat printable_height;
    ConfigOptionFloatsNullable extruder_printable_height;
    ConfigOptionPoint best_object_pos;
    ConfigOptionFloats slow_down_min_speed;
    ConfigOptionFloats nozzle_diameter;
    ConfigOptionBool reduce_infill_retraction;
    ConfigOptionBool ooze_prevention;
    ConfigOptionString filename_format;
    ConfigOptionStrings post_process;
    ConfigOptionString printer_model;
    ConfigOptionFloat resolution;
    ConfigOptionFloats retraction_minimum_travel;
    ConfigOptionBools retract_when_changing_layer;
    ConfigOptionFloat skirt_distance;
    ConfigOptionInt skirt_height;
    ConfigOptionInt skirt_loops;
    ConfigOptionEnum<SkirtType> skirt_type;
    ConfigOptionFloat skirt_speed;
    ConfigOptionBool single_loop_draft_shield;
    ConfigOptionFloat min_skirt_length;
    ConfigOptionFloats slow_down_layer_time;
    ConfigOptionBool spiral_mode;
    ConfigOptionBool spiral_mode_smooth;
    ConfigOptionFloatOrPercent spiral_mode_max_xy_smoothing;
    ConfigOptionFloat spiral_finishing_flow_ratio;
    ConfigOptionFloat spiral_starting_flow_ratio;
    ConfigOptionInt standby_temperature_delta;
    ConfigOptionFloat preheat_time;
    ConfigOptionInt preheat_steps;
    ConfigOptionInts nozzle_temperature;
    ConfigOptionBools wipe;
    ConfigOptionInts nozzle_temperature_range_low;
    ConfigOptionInts nozzle_temperature_range_high;
    ConfigOptionFloats wipe_distance;
    ConfigOptionBool fiber_enabled;
    ConfigOptionBool fiber_shared_nozzle;
    ConfigOptionFloat plastic_nozzle_diameter;
    ConfigOptionFloat composite_nozzle_diameter;
    ConfigOptionFloat fiber_plastic_extruder_offset_x;
    ConfigOptionFloat fiber_plastic_extruder_offset_y;
    ConfigOptionFloat fiber_plastic_extruder_offset_z;
    ConfigOptionFloat fiber_composite_extruder_offset_x;
    ConfigOptionFloat fiber_composite_extruder_offset_y;
    ConfigOptionFloat fiber_composite_extruder_offset_z;
    ConfigOptionFloat fiber_plastic_extruder_heatup_speed;
    ConfigOptionFloat fiber_composite_extruder_heatup_speed;
    ConfigOptionBool fiber_plastic_extruder_has_fan;
    ConfigOptionBool fiber_composite_extruder_has_fan;
    ConfigOptionInt fiber_plastic_extruder_fan_index;
    ConfigOptionInt fiber_composite_extruder_fan_index;
    ConfigOptionFloat fiber_bed_heatup_speed;
    ConfigOptionFloat fiber_chamber_heatup_speed;
    ConfigOptionInt fiber_motion_blocks_buffer_size;
    ConfigOptionFloat fiber_cut_distance;
    ConfigOptionFloat fiber_restart_length;
    ConfigOptionString fiber_cut_gcode;
    ConfigOptionFloat fiber_nozzle_contact_radius;
    ConfigOptionFloat fiber_nozzle_contact_radius_extended;
    ConfigOptionString fiber_toolchange_gcode_before;
    ConfigOptionString fiber_toolchange_gcode_after;
    ConfigOptionString fiber_slot_roles;
    ConfigOptionString continuous_fiber_name;
    ConfigOptionString continuous_fiber_type;
    ConfigOptionString continuous_fiber_material_kind;
    ConfigOptionString continuous_fiber_source_material_id;
    ConfigOptionFloat continuous_fiber_diameter;
    ConfigOptionFloat continuous_fiber_linear_density;
    ConfigOptionInt fiber_postprocessor_type;
    ConfigOptionString fiber_machine_contract_payload;
    ConfigOptionBool enable_prime_tower;
    ConfigOptionBool prime_tower_enable_framework;
    ConfigOptionFloats wipe_tower_x;
    ConfigOptionFloats wipe_tower_y;
    ConfigOptionFloat prime_tower_width;
    ConfigOptionFloat wipe_tower_per_color_wipe;
    ConfigOptionFloat wipe_tower_rotation_angle;
    ConfigOptionFloat prime_tower_brim_width;
    ConfigOptionPercent prime_tower_infill_gap;
    ConfigOptionBool prime_tower_skip_points;
    ConfigOptionBool prime_tower_flat_ironing;
    ConfigOptionBool enable_tower_interface_features;
    ConfigOptionBool enable_tower_interface_cooldown_during_tower;
    ConfigOptionFloat wipe_tower_bridging;
    ConfigOptionPercent wipe_tower_extra_flow;
    ConfigOptionFloats flush_volumes_matrix;
    ConfigOptionFloats flush_volumes_vector;
    ConfigOptionFloat wipe_tower_cone_angle;
    ConfigOptionPercent wipe_tower_extra_spacing;
    ConfigOptionFloat wipe_tower_max_purge_speed;
    ConfigOptionEnum<WipeTowerWallType> wipe_tower_wall_type;
    ConfigOptionFloat wipe_tower_extra_rib_length;
    ConfigOptionFloat wipe_tower_rib_width;
    ConfigOptionBool wipe_tower_fillet_wall;
    ConfigOptionInt wipe_tower_filament;
    ConfigOptionFloats wiping_volumes_extruders;
    ConfigOptionInts idle_temperature;
    ConfigOptionFloat prime_volume;
    ConfigOptionFloats flush_multiplier;
    ConfigOptionFloat z_offset;
    ConfigOptionFloats filament_colour_new;
    ConfigOptionFloatsNullable nozzle_volume;
    ConfigOptionPoints start_end_points;
    ConfigOptionEnum<TimelapseType> timelapse_type;
    ConfigOptionString thumbnails;
    ConfigOptionBool combine_brims;
    ConfigOptionPercents filament_shrink;
    ConfigOptionPercents filament_shrinkage_compensation_z;
    ConfigOptionBool gcode_label_objects;
    ConfigOptionBool exclude_object;
    ConfigOptionFloats grab_length;
    ConfigOptionBool gcode_comments;
    ConfigOptionInt slow_down_layers;
    ConfigOptionInts support_material_interface_fan_speed;
    ConfigOptionInts internal_bridge_fan_speed;
    ConfigOptionInts ironing_fan_speed;
    ConfigOptionStrings filament_notes;
    ConfigOptionString notes;
    ConfigOptionString printer_notes;
    ConfigOptionBools activate_chamber_temp_control;
    ConfigOptionInts chamber_temperature;
    ConfigOptionInts chamber_minimal_temperature;
    ConfigOptionFloat preferred_orientation;
    ConfigOptionPoint bed_mesh_min;
    ConfigOptionPoint bed_mesh_max;
    ConfigOptionPoint bed_mesh_probe_distance;
    ConfigOptionFloat adaptive_bed_mesh_margin;

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const MachineEnvelopeConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const GCodeConfig*>(this)->hash());
        boost::hash_combine(seed, additional_cooling_fan_speed.hash());
        boost::hash_combine(seed, close_additional_fan_first_x_layers.hash());
        boost::hash_combine(seed, additional_fan_full_speed_layer.hash());
        boost::hash_combine(seed, first_x_layer_fan_speed.hash());
        boost::hash_combine(seed, reduce_crossing_wall.hash());
        boost::hash_combine(seed, max_travel_detour_distance.hash());
        boost::hash_combine(seed, printable_area.hash());
        boost::hash_combine(seed, extruder_printable_area.hash());
        boost::hash_combine(seed, support_parallel_printheads.hash());
        boost::hash_combine(seed, parallel_printheads_count.hash());
        boost::hash_combine(seed, parallel_printheads_bed_exclude_areas.hash());
        boost::hash_combine(seed, bed_exclude_area.hash());
        boost::hash_combine(seed, head_wrap_detect_zone.hash());
        boost::hash_combine(seed, bed_custom_texture.hash());
        boost::hash_combine(seed, bed_custom_model.hash());
        boost::hash_combine(seed, curr_bed_type.hash());
        boost::hash_combine(seed, cool_plate_temp.hash());
        boost::hash_combine(seed, textured_cool_plate_temp.hash());
        boost::hash_combine(seed, supertack_plate_temp.hash());
        boost::hash_combine(seed, eng_plate_temp.hash());
        boost::hash_combine(seed, hot_plate_temp.hash());
        boost::hash_combine(seed, textured_plate_temp.hash());
        boost::hash_combine(seed, supertack_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, cool_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, textured_cool_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, eng_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, hot_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, textured_plate_temp_initial_layer.hash());
        boost::hash_combine(seed, enable_overhang_bridge_fan.hash());
        boost::hash_combine(seed, overhang_fan_speed.hash());
        boost::hash_combine(seed, overhang_fan_threshold.hash());
        boost::hash_combine(seed, print_sequence.hash());
        boost::hash_combine(seed, print_order.hash());
        boost::hash_combine(seed, first_layer_print_sequence.hash());
        boost::hash_combine(seed, other_layers_print_sequence.hash());
        boost::hash_combine(seed, other_layers_print_sequence_nums.hash());
        boost::hash_combine(seed, slow_down_for_layer_cooling.hash());
        boost::hash_combine(seed, close_fan_the_first_x_layers.hash());
        boost::hash_combine(seed, draft_shield.hash());
        boost::hash_combine(seed, extruder_clearance_height_to_rod.hash());
        boost::hash_combine(seed, extruder_clearance_height_to_lid.hash());
        boost::hash_combine(seed, extruder_clearance_radius.hash());
        boost::hash_combine(seed, nozzle_height.hash());
        boost::hash_combine(seed, extruder_colour.hash());
        boost::hash_combine(seed, extruder_offset.hash());
        boost::hash_combine(seed, reduce_fan_stop_start_freq.hash());
        boost::hash_combine(seed, dont_slow_down_outer_wall.hash());
        boost::hash_combine(seed, fan_cooling_layer_time.hash());
        boost::hash_combine(seed, activate_air_filtration.hash());
        boost::hash_combine(seed, activate_air_filtration_during_print.hash());
        boost::hash_combine(seed, activate_air_filtration_on_completion.hash());
        boost::hash_combine(seed, during_print_exhaust_fan_speed.hash());
        boost::hash_combine(seed, complete_print_exhaust_fan_speed.hash());
        boost::hash_combine(seed, initial_layer_line_width.hash());
        boost::hash_combine(seed, initial_layer_print_height.hash());
        boost::hash_combine(seed, initial_layer_speed.hash());
        boost::hash_combine(seed, initial_layer_infill_speed.hash());
        boost::hash_combine(seed, nozzle_temperature_initial_layer.hash());
        boost::hash_combine(seed, full_fan_speed_layer.hash());
        boost::hash_combine(seed, fan_max_speed.hash());
        boost::hash_combine(seed, max_layer_height.hash());
        boost::hash_combine(seed, fan_min_speed.hash());
        boost::hash_combine(seed, min_layer_height.hash());
        boost::hash_combine(seed, printable_height.hash());
        boost::hash_combine(seed, extruder_printable_height.hash());
        boost::hash_combine(seed, best_object_pos.hash());
        boost::hash_combine(seed, slow_down_min_speed.hash());
        boost::hash_combine(seed, nozzle_diameter.hash());
        boost::hash_combine(seed, reduce_infill_retraction.hash());
        boost::hash_combine(seed, ooze_prevention.hash());
        boost::hash_combine(seed, filename_format.hash());
        boost::hash_combine(seed, post_process.hash());
        boost::hash_combine(seed, printer_model.hash());
        boost::hash_combine(seed, resolution.hash());
        boost::hash_combine(seed, retraction_minimum_travel.hash());
        boost::hash_combine(seed, retract_when_changing_layer.hash());
        boost::hash_combine(seed, skirt_distance.hash());
        boost::hash_combine(seed, skirt_height.hash());
        boost::hash_combine(seed, skirt_loops.hash());
        boost::hash_combine(seed, skirt_type.hash());
        boost::hash_combine(seed, skirt_speed.hash());
        boost::hash_combine(seed, single_loop_draft_shield.hash());
        boost::hash_combine(seed, min_skirt_length.hash());
        boost::hash_combine(seed, slow_down_layer_time.hash());
        boost::hash_combine(seed, spiral_mode.hash());
        boost::hash_combine(seed, spiral_mode_smooth.hash());
        boost::hash_combine(seed, spiral_mode_max_xy_smoothing.hash());
        boost::hash_combine(seed, spiral_finishing_flow_ratio.hash());
        boost::hash_combine(seed, spiral_starting_flow_ratio.hash());
        boost::hash_combine(seed, standby_temperature_delta.hash());
        boost::hash_combine(seed, preheat_time.hash());
        boost::hash_combine(seed, preheat_steps.hash());
        boost::hash_combine(seed, nozzle_temperature.hash());
        boost::hash_combine(seed, wipe.hash());
        boost::hash_combine(seed, nozzle_temperature_range_low.hash());
        boost::hash_combine(seed, nozzle_temperature_range_high.hash());
        boost::hash_combine(seed, wipe_distance.hash());
        boost::hash_combine(seed, fiber_enabled.hash());
        boost::hash_combine(seed, fiber_shared_nozzle.hash());
        boost::hash_combine(seed, plastic_nozzle_diameter.hash());
        boost::hash_combine(seed, composite_nozzle_diameter.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_offset_x.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_offset_y.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_offset_z.hash());
        boost::hash_combine(seed, fiber_composite_extruder_offset_x.hash());
        boost::hash_combine(seed, fiber_composite_extruder_offset_y.hash());
        boost::hash_combine(seed, fiber_composite_extruder_offset_z.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_heatup_speed.hash());
        boost::hash_combine(seed, fiber_composite_extruder_heatup_speed.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_has_fan.hash());
        boost::hash_combine(seed, fiber_composite_extruder_has_fan.hash());
        boost::hash_combine(seed, fiber_plastic_extruder_fan_index.hash());
        boost::hash_combine(seed, fiber_composite_extruder_fan_index.hash());
        boost::hash_combine(seed, fiber_bed_heatup_speed.hash());
        boost::hash_combine(seed, fiber_chamber_heatup_speed.hash());
        boost::hash_combine(seed, fiber_motion_blocks_buffer_size.hash());
        boost::hash_combine(seed, fiber_cut_distance.hash());
        boost::hash_combine(seed, fiber_restart_length.hash());
        boost::hash_combine(seed, fiber_cut_gcode.hash());
        boost::hash_combine(seed, fiber_nozzle_contact_radius.hash());
        boost::hash_combine(seed, fiber_nozzle_contact_radius_extended.hash());
        boost::hash_combine(seed, fiber_toolchange_gcode_before.hash());
        boost::hash_combine(seed, fiber_toolchange_gcode_after.hash());
        boost::hash_combine(seed, fiber_slot_roles.hash());
        boost::hash_combine(seed, continuous_fiber_name.hash());
        boost::hash_combine(seed, continuous_fiber_type.hash());
        boost::hash_combine(seed, continuous_fiber_material_kind.hash());
        boost::hash_combine(seed, continuous_fiber_source_material_id.hash());
        boost::hash_combine(seed, continuous_fiber_diameter.hash());
        boost::hash_combine(seed, continuous_fiber_linear_density.hash());
        boost::hash_combine(seed, fiber_postprocessor_type.hash());
        boost::hash_combine(seed, fiber_machine_contract_payload.hash());
        boost::hash_combine(seed, enable_prime_tower.hash());
        boost::hash_combine(seed, prime_tower_enable_framework.hash());
        boost::hash_combine(seed, wipe_tower_x.hash());
        boost::hash_combine(seed, wipe_tower_y.hash());
        boost::hash_combine(seed, prime_tower_width.hash());
        boost::hash_combine(seed, wipe_tower_per_color_wipe.hash());
        boost::hash_combine(seed, wipe_tower_rotation_angle.hash());
        boost::hash_combine(seed, prime_tower_brim_width.hash());
        boost::hash_combine(seed, prime_tower_infill_gap.hash());
        boost::hash_combine(seed, prime_tower_skip_points.hash());
        boost::hash_combine(seed, prime_tower_flat_ironing.hash());
        boost::hash_combine(seed, enable_tower_interface_features.hash());
        boost::hash_combine(seed, enable_tower_interface_cooldown_during_tower.hash());
        boost::hash_combine(seed, wipe_tower_bridging.hash());
        boost::hash_combine(seed, wipe_tower_extra_flow.hash());
        boost::hash_combine(seed, flush_volumes_matrix.hash());
        boost::hash_combine(seed, flush_volumes_vector.hash());
        boost::hash_combine(seed, wipe_tower_cone_angle.hash());
        boost::hash_combine(seed, wipe_tower_extra_spacing.hash());
        boost::hash_combine(seed, wipe_tower_max_purge_speed.hash());
        boost::hash_combine(seed, wipe_tower_wall_type.hash());
        boost::hash_combine(seed, wipe_tower_extra_rib_length.hash());
        boost::hash_combine(seed, wipe_tower_rib_width.hash());
        boost::hash_combine(seed, wipe_tower_fillet_wall.hash());
        boost::hash_combine(seed, wipe_tower_filament.hash());
        boost::hash_combine(seed, wiping_volumes_extruders.hash());
        boost::hash_combine(seed, idle_temperature.hash());
        boost::hash_combine(seed, prime_volume.hash());
        boost::hash_combine(seed, flush_multiplier.hash());
        boost::hash_combine(seed, z_offset.hash());
        boost::hash_combine(seed, filament_colour_new.hash());
        boost::hash_combine(seed, nozzle_volume.hash());
        boost::hash_combine(seed, start_end_points.hash());
        boost::hash_combine(seed, timelapse_type.hash());
        boost::hash_combine(seed, thumbnails.hash());
        boost::hash_combine(seed, combine_brims.hash());
        boost::hash_combine(seed, filament_shrink.hash());
        boost::hash_combine(seed, filament_shrinkage_compensation_z.hash());
        boost::hash_combine(seed, gcode_label_objects.hash());
        boost::hash_combine(seed, exclude_object.hash());
        boost::hash_combine(seed, grab_length.hash());
        boost::hash_combine(seed, gcode_comments.hash());
        boost::hash_combine(seed, slow_down_layers.hash());
        boost::hash_combine(seed, support_material_interface_fan_speed.hash());
        boost::hash_combine(seed, internal_bridge_fan_speed.hash());
        boost::hash_combine(seed, ironing_fan_speed.hash());
        boost::hash_combine(seed, filament_notes.hash());
        boost::hash_combine(seed, notes.hash());
        boost::hash_combine(seed, printer_notes.hash());
        boost::hash_combine(seed, activate_chamber_temp_control.hash());
        boost::hash_combine(seed, chamber_temperature.hash());
        boost::hash_combine(seed, chamber_minimal_temperature.hash());
        boost::hash_combine(seed, preferred_orientation.hash());
        boost::hash_combine(seed, bed_mesh_min.hash());
        boost::hash_combine(seed, bed_mesh_max.hash());
        boost::hash_combine(seed, bed_mesh_probe_distance.hash());
        boost::hash_combine(seed, adaptive_bed_mesh_margin.hash());
        return seed;
    }

    bool operator==(const PrintConfig &rhs) const throw()
    {
        if (!(*static_cast<const MachineEnvelopeConfig*>(this) == static_cast<const MachineEnvelopeConfig&>(rhs)))
            return false;
        if (!(*static_cast<const GCodeConfig*>(this) == static_cast<const GCodeConfig&>(rhs)))
            return false;
        if (!(additional_cooling_fan_speed == rhs.additional_cooling_fan_speed))
            return false;
        if (!(close_additional_fan_first_x_layers == rhs.close_additional_fan_first_x_layers))
            return false;
        if (!(additional_fan_full_speed_layer == rhs.additional_fan_full_speed_layer))
            return false;
        if (!(first_x_layer_fan_speed == rhs.first_x_layer_fan_speed))
            return false;
        if (!(reduce_crossing_wall == rhs.reduce_crossing_wall))
            return false;
        if (!(max_travel_detour_distance == rhs.max_travel_detour_distance))
            return false;
        if (!(printable_area == rhs.printable_area))
            return false;
        if (!(extruder_printable_area == rhs.extruder_printable_area))
            return false;
        if (!(support_parallel_printheads == rhs.support_parallel_printheads))
            return false;
        if (!(parallel_printheads_count == rhs.parallel_printheads_count))
            return false;
        if (!(parallel_printheads_bed_exclude_areas == rhs.parallel_printheads_bed_exclude_areas))
            return false;
        if (!(bed_exclude_area == rhs.bed_exclude_area))
            return false;
        if (!(head_wrap_detect_zone == rhs.head_wrap_detect_zone))
            return false;
        if (!(bed_custom_texture == rhs.bed_custom_texture))
            return false;
        if (!(bed_custom_model == rhs.bed_custom_model))
            return false;
        if (!(curr_bed_type == rhs.curr_bed_type))
            return false;
        if (!(cool_plate_temp == rhs.cool_plate_temp))
            return false;
        if (!(textured_cool_plate_temp == rhs.textured_cool_plate_temp))
            return false;
        if (!(supertack_plate_temp == rhs.supertack_plate_temp))
            return false;
        if (!(eng_plate_temp == rhs.eng_plate_temp))
            return false;
        if (!(hot_plate_temp == rhs.hot_plate_temp))
            return false;
        if (!(textured_plate_temp == rhs.textured_plate_temp))
            return false;
        if (!(supertack_plate_temp_initial_layer == rhs.supertack_plate_temp_initial_layer))
            return false;
        if (!(cool_plate_temp_initial_layer == rhs.cool_plate_temp_initial_layer))
            return false;
        if (!(textured_cool_plate_temp_initial_layer == rhs.textured_cool_plate_temp_initial_layer))
            return false;
        if (!(eng_plate_temp_initial_layer == rhs.eng_plate_temp_initial_layer))
            return false;
        if (!(hot_plate_temp_initial_layer == rhs.hot_plate_temp_initial_layer))
            return false;
        if (!(textured_plate_temp_initial_layer == rhs.textured_plate_temp_initial_layer))
            return false;
        if (!(enable_overhang_bridge_fan == rhs.enable_overhang_bridge_fan))
            return false;
        if (!(overhang_fan_speed == rhs.overhang_fan_speed))
            return false;
        if (!(overhang_fan_threshold == rhs.overhang_fan_threshold))
            return false;
        if (!(print_sequence == rhs.print_sequence))
            return false;
        if (!(print_order == rhs.print_order))
            return false;
        if (!(first_layer_print_sequence == rhs.first_layer_print_sequence))
            return false;
        if (!(other_layers_print_sequence == rhs.other_layers_print_sequence))
            return false;
        if (!(other_layers_print_sequence_nums == rhs.other_layers_print_sequence_nums))
            return false;
        if (!(slow_down_for_layer_cooling == rhs.slow_down_for_layer_cooling))
            return false;
        if (!(close_fan_the_first_x_layers == rhs.close_fan_the_first_x_layers))
            return false;
        if (!(draft_shield == rhs.draft_shield))
            return false;
        if (!(extruder_clearance_height_to_rod == rhs.extruder_clearance_height_to_rod))
            return false;
        if (!(extruder_clearance_height_to_lid == rhs.extruder_clearance_height_to_lid))
            return false;
        if (!(extruder_clearance_radius == rhs.extruder_clearance_radius))
            return false;
        if (!(nozzle_height == rhs.nozzle_height))
            return false;
        if (!(extruder_colour == rhs.extruder_colour))
            return false;
        if (!(extruder_offset == rhs.extruder_offset))
            return false;
        if (!(reduce_fan_stop_start_freq == rhs.reduce_fan_stop_start_freq))
            return false;
        if (!(dont_slow_down_outer_wall == rhs.dont_slow_down_outer_wall))
            return false;
        if (!(fan_cooling_layer_time == rhs.fan_cooling_layer_time))
            return false;
        if (!(activate_air_filtration == rhs.activate_air_filtration))
            return false;
        if (!(activate_air_filtration_during_print == rhs.activate_air_filtration_during_print))
            return false;
        if (!(activate_air_filtration_on_completion == rhs.activate_air_filtration_on_completion))
            return false;
        if (!(during_print_exhaust_fan_speed == rhs.during_print_exhaust_fan_speed))
            return false;
        if (!(complete_print_exhaust_fan_speed == rhs.complete_print_exhaust_fan_speed))
            return false;
        if (!(initial_layer_line_width == rhs.initial_layer_line_width))
            return false;
        if (!(initial_layer_print_height == rhs.initial_layer_print_height))
            return false;
        if (!(initial_layer_speed == rhs.initial_layer_speed))
            return false;
        if (!(initial_layer_infill_speed == rhs.initial_layer_infill_speed))
            return false;
        if (!(nozzle_temperature_initial_layer == rhs.nozzle_temperature_initial_layer))
            return false;
        if (!(full_fan_speed_layer == rhs.full_fan_speed_layer))
            return false;
        if (!(fan_max_speed == rhs.fan_max_speed))
            return false;
        if (!(max_layer_height == rhs.max_layer_height))
            return false;
        if (!(fan_min_speed == rhs.fan_min_speed))
            return false;
        if (!(min_layer_height == rhs.min_layer_height))
            return false;
        if (!(printable_height == rhs.printable_height))
            return false;
        if (!(extruder_printable_height == rhs.extruder_printable_height))
            return false;
        if (!(best_object_pos == rhs.best_object_pos))
            return false;
        if (!(slow_down_min_speed == rhs.slow_down_min_speed))
            return false;
        if (!(nozzle_diameter == rhs.nozzle_diameter))
            return false;
        if (!(reduce_infill_retraction == rhs.reduce_infill_retraction))
            return false;
        if (!(ooze_prevention == rhs.ooze_prevention))
            return false;
        if (!(filename_format == rhs.filename_format))
            return false;
        if (!(post_process == rhs.post_process))
            return false;
        if (!(printer_model == rhs.printer_model))
            return false;
        if (!(resolution == rhs.resolution))
            return false;
        if (!(retraction_minimum_travel == rhs.retraction_minimum_travel))
            return false;
        if (!(retract_when_changing_layer == rhs.retract_when_changing_layer))
            return false;
        if (!(skirt_distance == rhs.skirt_distance))
            return false;
        if (!(skirt_height == rhs.skirt_height))
            return false;
        if (!(skirt_loops == rhs.skirt_loops))
            return false;
        if (!(skirt_type == rhs.skirt_type))
            return false;
        if (!(skirt_speed == rhs.skirt_speed))
            return false;
        if (!(single_loop_draft_shield == rhs.single_loop_draft_shield))
            return false;
        if (!(min_skirt_length == rhs.min_skirt_length))
            return false;
        if (!(slow_down_layer_time == rhs.slow_down_layer_time))
            return false;
        if (!(spiral_mode == rhs.spiral_mode))
            return false;
        if (!(spiral_mode_smooth == rhs.spiral_mode_smooth))
            return false;
        if (!(spiral_mode_max_xy_smoothing == rhs.spiral_mode_max_xy_smoothing))
            return false;
        if (!(spiral_finishing_flow_ratio == rhs.spiral_finishing_flow_ratio))
            return false;
        if (!(spiral_starting_flow_ratio == rhs.spiral_starting_flow_ratio))
            return false;
        if (!(standby_temperature_delta == rhs.standby_temperature_delta))
            return false;
        if (!(preheat_time == rhs.preheat_time))
            return false;
        if (!(preheat_steps == rhs.preheat_steps))
            return false;
        if (!(nozzle_temperature == rhs.nozzle_temperature))
            return false;
        if (!(wipe == rhs.wipe))
            return false;
        if (!(nozzle_temperature_range_low == rhs.nozzle_temperature_range_low))
            return false;
        if (!(nozzle_temperature_range_high == rhs.nozzle_temperature_range_high))
            return false;
        if (!(wipe_distance == rhs.wipe_distance))
            return false;
        if (!(fiber_enabled == rhs.fiber_enabled))
            return false;
        if (!(fiber_shared_nozzle == rhs.fiber_shared_nozzle))
            return false;
        if (!(plastic_nozzle_diameter == rhs.plastic_nozzle_diameter))
            return false;
        if (!(composite_nozzle_diameter == rhs.composite_nozzle_diameter))
            return false;
        if (!(fiber_plastic_extruder_offset_x == rhs.fiber_plastic_extruder_offset_x))
            return false;
        if (!(fiber_plastic_extruder_offset_y == rhs.fiber_plastic_extruder_offset_y))
            return false;
        if (!(fiber_plastic_extruder_offset_z == rhs.fiber_plastic_extruder_offset_z))
            return false;
        if (!(fiber_composite_extruder_offset_x == rhs.fiber_composite_extruder_offset_x))
            return false;
        if (!(fiber_composite_extruder_offset_y == rhs.fiber_composite_extruder_offset_y))
            return false;
        if (!(fiber_composite_extruder_offset_z == rhs.fiber_composite_extruder_offset_z))
            return false;
        if (!(fiber_plastic_extruder_heatup_speed == rhs.fiber_plastic_extruder_heatup_speed))
            return false;
        if (!(fiber_composite_extruder_heatup_speed == rhs.fiber_composite_extruder_heatup_speed))
            return false;
        if (!(fiber_plastic_extruder_has_fan == rhs.fiber_plastic_extruder_has_fan))
            return false;
        if (!(fiber_composite_extruder_has_fan == rhs.fiber_composite_extruder_has_fan))
            return false;
        if (!(fiber_plastic_extruder_fan_index == rhs.fiber_plastic_extruder_fan_index))
            return false;
        if (!(fiber_composite_extruder_fan_index == rhs.fiber_composite_extruder_fan_index))
            return false;
        if (!(fiber_bed_heatup_speed == rhs.fiber_bed_heatup_speed))
            return false;
        if (!(fiber_chamber_heatup_speed == rhs.fiber_chamber_heatup_speed))
            return false;
        if (!(fiber_motion_blocks_buffer_size == rhs.fiber_motion_blocks_buffer_size))
            return false;
        if (!(fiber_cut_distance == rhs.fiber_cut_distance))
            return false;
        if (!(fiber_restart_length == rhs.fiber_restart_length))
            return false;
        if (!(fiber_cut_gcode == rhs.fiber_cut_gcode))
            return false;
        if (!(fiber_nozzle_contact_radius == rhs.fiber_nozzle_contact_radius))
            return false;
        if (!(fiber_nozzle_contact_radius_extended == rhs.fiber_nozzle_contact_radius_extended))
            return false;
        if (!(fiber_toolchange_gcode_before == rhs.fiber_toolchange_gcode_before))
            return false;
        if (!(fiber_toolchange_gcode_after == rhs.fiber_toolchange_gcode_after))
            return false;
        if (!(fiber_slot_roles == rhs.fiber_slot_roles))
            return false;
        if (!(continuous_fiber_name == rhs.continuous_fiber_name))
            return false;
        if (!(continuous_fiber_type == rhs.continuous_fiber_type))
            return false;
        if (!(continuous_fiber_material_kind == rhs.continuous_fiber_material_kind))
            return false;
        if (!(continuous_fiber_source_material_id == rhs.continuous_fiber_source_material_id))
            return false;
        if (!(continuous_fiber_diameter == rhs.continuous_fiber_diameter))
            return false;
        if (!(continuous_fiber_linear_density == rhs.continuous_fiber_linear_density))
            return false;
        if (!(fiber_postprocessor_type == rhs.fiber_postprocessor_type))
            return false;
        if (!(fiber_machine_contract_payload == rhs.fiber_machine_contract_payload))
            return false;
        if (!(enable_prime_tower == rhs.enable_prime_tower))
            return false;
        if (!(prime_tower_enable_framework == rhs.prime_tower_enable_framework))
            return false;
        if (!(wipe_tower_x == rhs.wipe_tower_x))
            return false;
        if (!(wipe_tower_y == rhs.wipe_tower_y))
            return false;
        if (!(prime_tower_width == rhs.prime_tower_width))
            return false;
        if (!(wipe_tower_per_color_wipe == rhs.wipe_tower_per_color_wipe))
            return false;
        if (!(wipe_tower_rotation_angle == rhs.wipe_tower_rotation_angle))
            return false;
        if (!(prime_tower_brim_width == rhs.prime_tower_brim_width))
            return false;
        if (!(prime_tower_infill_gap == rhs.prime_tower_infill_gap))
            return false;
        if (!(prime_tower_skip_points == rhs.prime_tower_skip_points))
            return false;
        if (!(prime_tower_flat_ironing == rhs.prime_tower_flat_ironing))
            return false;
        if (!(enable_tower_interface_features == rhs.enable_tower_interface_features))
            return false;
        if (!(enable_tower_interface_cooldown_during_tower == rhs.enable_tower_interface_cooldown_during_tower))
            return false;
        if (!(wipe_tower_bridging == rhs.wipe_tower_bridging))
            return false;
        if (!(wipe_tower_extra_flow == rhs.wipe_tower_extra_flow))
            return false;
        if (!(flush_volumes_matrix == rhs.flush_volumes_matrix))
            return false;
        if (!(flush_volumes_vector == rhs.flush_volumes_vector))
            return false;
        if (!(wipe_tower_cone_angle == rhs.wipe_tower_cone_angle))
            return false;
        if (!(wipe_tower_extra_spacing == rhs.wipe_tower_extra_spacing))
            return false;
        if (!(wipe_tower_max_purge_speed == rhs.wipe_tower_max_purge_speed))
            return false;
        if (!(wipe_tower_wall_type == rhs.wipe_tower_wall_type))
            return false;
        if (!(wipe_tower_extra_rib_length == rhs.wipe_tower_extra_rib_length))
            return false;
        if (!(wipe_tower_rib_width == rhs.wipe_tower_rib_width))
            return false;
        if (!(wipe_tower_fillet_wall == rhs.wipe_tower_fillet_wall))
            return false;
        if (!(wipe_tower_filament == rhs.wipe_tower_filament))
            return false;
        if (!(wiping_volumes_extruders == rhs.wiping_volumes_extruders))
            return false;
        if (!(idle_temperature == rhs.idle_temperature))
            return false;
        if (!(prime_volume == rhs.prime_volume))
            return false;
        if (!(flush_multiplier == rhs.flush_multiplier))
            return false;
        if (!(z_offset == rhs.z_offset))
            return false;
        if (!(filament_colour_new == rhs.filament_colour_new))
            return false;
        if (!(nozzle_volume == rhs.nozzle_volume))
            return false;
        if (!(start_end_points == rhs.start_end_points))
            return false;
        if (!(timelapse_type == rhs.timelapse_type))
            return false;
        if (!(thumbnails == rhs.thumbnails))
            return false;
        if (!(combine_brims == rhs.combine_brims))
            return false;
        if (!(filament_shrink == rhs.filament_shrink))
            return false;
        if (!(filament_shrinkage_compensation_z == rhs.filament_shrinkage_compensation_z))
            return false;
        if (!(gcode_label_objects == rhs.gcode_label_objects))
            return false;
        if (!(exclude_object == rhs.exclude_object))
            return false;
        if (!(grab_length == rhs.grab_length))
            return false;
        if (!(gcode_comments == rhs.gcode_comments))
            return false;
        if (!(slow_down_layers == rhs.slow_down_layers))
            return false;
        if (!(support_material_interface_fan_speed == rhs.support_material_interface_fan_speed))
            return false;
        if (!(internal_bridge_fan_speed == rhs.internal_bridge_fan_speed))
            return false;
        if (!(ironing_fan_speed == rhs.ironing_fan_speed))
            return false;
        if (!(filament_notes == rhs.filament_notes))
            return false;
        if (!(notes == rhs.notes))
            return false;
        if (!(printer_notes == rhs.printer_notes))
            return false;
        if (!(activate_chamber_temp_control == rhs.activate_chamber_temp_control))
            return false;
        if (!(chamber_temperature == rhs.chamber_temperature))
            return false;
        if (!(chamber_minimal_temperature == rhs.chamber_minimal_temperature))
            return false;
        if (!(preferred_orientation == rhs.preferred_orientation))
            return false;
        if (!(bed_mesh_min == rhs.bed_mesh_min))
            return false;
        if (!(bed_mesh_max == rhs.bed_mesh_max))
            return false;
        if (!(bed_mesh_probe_distance == rhs.bed_mesh_probe_distance))
            return false;
        if (!(adaptive_bed_mesh_margin == rhs.adaptive_bed_mesh_margin))
            return false;
        return true;
    }

    bool operator!=(const PrintConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    PrintConfig(int) : MachineEnvelopeConfig(1), GCodeConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->MachineEnvelopeConfig::initialize(cache, base_ptr);
        this->GCodeConfig::initialize(cache, base_ptr);
        cache.opt_add("additional_cooling_fan_speed", base_ptr, this->additional_cooling_fan_speed);
        cache.opt_add("close_additional_fan_first_x_layers", base_ptr, this->close_additional_fan_first_x_layers);
        cache.opt_add("additional_fan_full_speed_layer", base_ptr, this->additional_fan_full_speed_layer);
        cache.opt_add("first_x_layer_fan_speed", base_ptr, this->first_x_layer_fan_speed);
        cache.opt_add("reduce_crossing_wall", base_ptr, this->reduce_crossing_wall);
        cache.opt_add("max_travel_detour_distance", base_ptr, this->max_travel_detour_distance);
        cache.opt_add("printable_area", base_ptr, this->printable_area);
        cache.opt_add("extruder_printable_area", base_ptr, this->extruder_printable_area);
        cache.opt_add("support_parallel_printheads", base_ptr, this->support_parallel_printheads);
        cache.opt_add("parallel_printheads_count", base_ptr, this->parallel_printheads_count);
        cache.opt_add("parallel_printheads_bed_exclude_areas", base_ptr, this->parallel_printheads_bed_exclude_areas);
        cache.opt_add("bed_exclude_area", base_ptr, this->bed_exclude_area);
        cache.opt_add("head_wrap_detect_zone", base_ptr, this->head_wrap_detect_zone);
        cache.opt_add("bed_custom_texture", base_ptr, this->bed_custom_texture);
        cache.opt_add("bed_custom_model", base_ptr, this->bed_custom_model);
        cache.opt_add("curr_bed_type", base_ptr, this->curr_bed_type);
        cache.opt_add("cool_plate_temp", base_ptr, this->cool_plate_temp);
        cache.opt_add("textured_cool_plate_temp", base_ptr, this->textured_cool_plate_temp);
        cache.opt_add("supertack_plate_temp", base_ptr, this->supertack_plate_temp);
        cache.opt_add("eng_plate_temp", base_ptr, this->eng_plate_temp);
        cache.opt_add("hot_plate_temp", base_ptr, this->hot_plate_temp);
        cache.opt_add("textured_plate_temp", base_ptr, this->textured_plate_temp);
        cache.opt_add("supertack_plate_temp_initial_layer", base_ptr, this->supertack_plate_temp_initial_layer);
        cache.opt_add("cool_plate_temp_initial_layer", base_ptr, this->cool_plate_temp_initial_layer);
        cache.opt_add("textured_cool_plate_temp_initial_layer", base_ptr, this->textured_cool_plate_temp_initial_layer);
        cache.opt_add("eng_plate_temp_initial_layer", base_ptr, this->eng_plate_temp_initial_layer);
        cache.opt_add("hot_plate_temp_initial_layer", base_ptr, this->hot_plate_temp_initial_layer);
        cache.opt_add("textured_plate_temp_initial_layer", base_ptr, this->textured_plate_temp_initial_layer);
        cache.opt_add("enable_overhang_bridge_fan", base_ptr, this->enable_overhang_bridge_fan);
        cache.opt_add("overhang_fan_speed", base_ptr, this->overhang_fan_speed);
        cache.opt_add("overhang_fan_threshold", base_ptr, this->overhang_fan_threshold);
        cache.opt_add("print_sequence", base_ptr, this->print_sequence);
        cache.opt_add("print_order", base_ptr, this->print_order);
        cache.opt_add("first_layer_print_sequence", base_ptr, this->first_layer_print_sequence);
        cache.opt_add("other_layers_print_sequence", base_ptr, this->other_layers_print_sequence);
        cache.opt_add("other_layers_print_sequence_nums", base_ptr, this->other_layers_print_sequence_nums);
        cache.opt_add("slow_down_for_layer_cooling", base_ptr, this->slow_down_for_layer_cooling);
        cache.opt_add("close_fan_the_first_x_layers", base_ptr, this->close_fan_the_first_x_layers);
        cache.opt_add("draft_shield", base_ptr, this->draft_shield);
        cache.opt_add("extruder_clearance_height_to_rod", base_ptr, this->extruder_clearance_height_to_rod);
        cache.opt_add("extruder_clearance_height_to_lid", base_ptr, this->extruder_clearance_height_to_lid);
        cache.opt_add("extruder_clearance_radius", base_ptr, this->extruder_clearance_radius);
        cache.opt_add("nozzle_height", base_ptr, this->nozzle_height);
        cache.opt_add("extruder_colour", base_ptr, this->extruder_colour);
        cache.opt_add("extruder_offset", base_ptr, this->extruder_offset);
        cache.opt_add("reduce_fan_stop_start_freq", base_ptr, this->reduce_fan_stop_start_freq);
        cache.opt_add("dont_slow_down_outer_wall", base_ptr, this->dont_slow_down_outer_wall);
        cache.opt_add("fan_cooling_layer_time", base_ptr, this->fan_cooling_layer_time);
        cache.opt_add("activate_air_filtration", base_ptr, this->activate_air_filtration);
        cache.opt_add("activate_air_filtration_during_print", base_ptr, this->activate_air_filtration_during_print);
        cache.opt_add("activate_air_filtration_on_completion", base_ptr, this->activate_air_filtration_on_completion);
        cache.opt_add("during_print_exhaust_fan_speed", base_ptr, this->during_print_exhaust_fan_speed);
        cache.opt_add("complete_print_exhaust_fan_speed", base_ptr, this->complete_print_exhaust_fan_speed);
        cache.opt_add("initial_layer_line_width", base_ptr, this->initial_layer_line_width);
        cache.opt_add("initial_layer_print_height", base_ptr, this->initial_layer_print_height);
        cache.opt_add("initial_layer_speed", base_ptr, this->initial_layer_speed);
        cache.opt_add("initial_layer_infill_speed", base_ptr, this->initial_layer_infill_speed);
        cache.opt_add("nozzle_temperature_initial_layer", base_ptr, this->nozzle_temperature_initial_layer);
        cache.opt_add("full_fan_speed_layer", base_ptr, this->full_fan_speed_layer);
        cache.opt_add("fan_max_speed", base_ptr, this->fan_max_speed);
        cache.opt_add("max_layer_height", base_ptr, this->max_layer_height);
        cache.opt_add("fan_min_speed", base_ptr, this->fan_min_speed);
        cache.opt_add("min_layer_height", base_ptr, this->min_layer_height);
        cache.opt_add("printable_height", base_ptr, this->printable_height);
        cache.opt_add("extruder_printable_height", base_ptr, this->extruder_printable_height);
        cache.opt_add("best_object_pos", base_ptr, this->best_object_pos);
        cache.opt_add("slow_down_min_speed", base_ptr, this->slow_down_min_speed);
        cache.opt_add("nozzle_diameter", base_ptr, this->nozzle_diameter);
        cache.opt_add("reduce_infill_retraction", base_ptr, this->reduce_infill_retraction);
        cache.opt_add("ooze_prevention", base_ptr, this->ooze_prevention);
        cache.opt_add("filename_format", base_ptr, this->filename_format);
        cache.opt_add("post_process", base_ptr, this->post_process);
        cache.opt_add("printer_model", base_ptr, this->printer_model);
        cache.opt_add("resolution", base_ptr, this->resolution);
        cache.opt_add("retraction_minimum_travel", base_ptr, this->retraction_minimum_travel);
        cache.opt_add("retract_when_changing_layer", base_ptr, this->retract_when_changing_layer);
        cache.opt_add("skirt_distance", base_ptr, this->skirt_distance);
        cache.opt_add("skirt_height", base_ptr, this->skirt_height);
        cache.opt_add("skirt_loops", base_ptr, this->skirt_loops);
        cache.opt_add("skirt_type", base_ptr, this->skirt_type);
        cache.opt_add("skirt_speed", base_ptr, this->skirt_speed);
        cache.opt_add("single_loop_draft_shield", base_ptr, this->single_loop_draft_shield);
        cache.opt_add("min_skirt_length", base_ptr, this->min_skirt_length);
        cache.opt_add("slow_down_layer_time", base_ptr, this->slow_down_layer_time);
        cache.opt_add("spiral_mode", base_ptr, this->spiral_mode);
        cache.opt_add("spiral_mode_smooth", base_ptr, this->spiral_mode_smooth);
        cache.opt_add("spiral_mode_max_xy_smoothing", base_ptr, this->spiral_mode_max_xy_smoothing);
        cache.opt_add("spiral_finishing_flow_ratio", base_ptr, this->spiral_finishing_flow_ratio);
        cache.opt_add("spiral_starting_flow_ratio", base_ptr, this->spiral_starting_flow_ratio);
        cache.opt_add("standby_temperature_delta", base_ptr, this->standby_temperature_delta);
        cache.opt_add("preheat_time", base_ptr, this->preheat_time);
        cache.opt_add("preheat_steps", base_ptr, this->preheat_steps);
        cache.opt_add("nozzle_temperature", base_ptr, this->nozzle_temperature);
        cache.opt_add("wipe", base_ptr, this->wipe);
        cache.opt_add("nozzle_temperature_range_low", base_ptr, this->nozzle_temperature_range_low);
        cache.opt_add("nozzle_temperature_range_high", base_ptr, this->nozzle_temperature_range_high);
        cache.opt_add("wipe_distance", base_ptr, this->wipe_distance);
        cache.opt_add("fiber_enabled", base_ptr, this->fiber_enabled);
        cache.opt_add("fiber_shared_nozzle", base_ptr, this->fiber_shared_nozzle);
        cache.opt_add("plastic_nozzle_diameter", base_ptr, this->plastic_nozzle_diameter);
        cache.opt_add("composite_nozzle_diameter", base_ptr, this->composite_nozzle_diameter);
        cache.opt_add("fiber_plastic_extruder_offset_x", base_ptr, this->fiber_plastic_extruder_offset_x);
        cache.opt_add("fiber_plastic_extruder_offset_y", base_ptr, this->fiber_plastic_extruder_offset_y);
        cache.opt_add("fiber_plastic_extruder_offset_z", base_ptr, this->fiber_plastic_extruder_offset_z);
        cache.opt_add("fiber_composite_extruder_offset_x", base_ptr, this->fiber_composite_extruder_offset_x);
        cache.opt_add("fiber_composite_extruder_offset_y", base_ptr, this->fiber_composite_extruder_offset_y);
        cache.opt_add("fiber_composite_extruder_offset_z", base_ptr, this->fiber_composite_extruder_offset_z);
        cache.opt_add("fiber_plastic_extruder_heatup_speed", base_ptr, this->fiber_plastic_extruder_heatup_speed);
        cache.opt_add("fiber_composite_extruder_heatup_speed", base_ptr, this->fiber_composite_extruder_heatup_speed);
        cache.opt_add("fiber_plastic_extruder_has_fan", base_ptr, this->fiber_plastic_extruder_has_fan);
        cache.opt_add("fiber_composite_extruder_has_fan", base_ptr, this->fiber_composite_extruder_has_fan);
        cache.opt_add("fiber_plastic_extruder_fan_index", base_ptr, this->fiber_plastic_extruder_fan_index);
        cache.opt_add("fiber_composite_extruder_fan_index", base_ptr, this->fiber_composite_extruder_fan_index);
        cache.opt_add("fiber_bed_heatup_speed", base_ptr, this->fiber_bed_heatup_speed);
        cache.opt_add("fiber_chamber_heatup_speed", base_ptr, this->fiber_chamber_heatup_speed);
        cache.opt_add("fiber_motion_blocks_buffer_size", base_ptr, this->fiber_motion_blocks_buffer_size);
        cache.opt_add("fiber_cut_distance", base_ptr, this->fiber_cut_distance);
        cache.opt_add("fiber_restart_length", base_ptr, this->fiber_restart_length);
        cache.opt_add("fiber_cut_gcode", base_ptr, this->fiber_cut_gcode);
        cache.opt_add("fiber_nozzle_contact_radius", base_ptr, this->fiber_nozzle_contact_radius);
        cache.opt_add("fiber_nozzle_contact_radius_extended", base_ptr, this->fiber_nozzle_contact_radius_extended);
        cache.opt_add("fiber_toolchange_gcode_before", base_ptr, this->fiber_toolchange_gcode_before);
        cache.opt_add("fiber_toolchange_gcode_after", base_ptr, this->fiber_toolchange_gcode_after);
        cache.opt_add("fiber_slot_roles", base_ptr, this->fiber_slot_roles);
        cache.opt_add("continuous_fiber_name", base_ptr, this->continuous_fiber_name);
        cache.opt_add("continuous_fiber_type", base_ptr, this->continuous_fiber_type);
        cache.opt_add("continuous_fiber_material_kind", base_ptr, this->continuous_fiber_material_kind);
        cache.opt_add("continuous_fiber_source_material_id", base_ptr, this->continuous_fiber_source_material_id);
        cache.opt_add("continuous_fiber_diameter", base_ptr, this->continuous_fiber_diameter);
        cache.opt_add("continuous_fiber_linear_density", base_ptr, this->continuous_fiber_linear_density);
        cache.opt_add("fiber_postprocessor_type", base_ptr, this->fiber_postprocessor_type);
        cache.opt_add("fiber_machine_contract_payload", base_ptr, this->fiber_machine_contract_payload);
        cache.opt_add("enable_prime_tower", base_ptr, this->enable_prime_tower);
        cache.opt_add("prime_tower_enable_framework", base_ptr, this->prime_tower_enable_framework);
        cache.opt_add("wipe_tower_x", base_ptr, this->wipe_tower_x);
        cache.opt_add("wipe_tower_y", base_ptr, this->wipe_tower_y);
        cache.opt_add("prime_tower_width", base_ptr, this->prime_tower_width);
        cache.opt_add("wipe_tower_per_color_wipe", base_ptr, this->wipe_tower_per_color_wipe);
        cache.opt_add("wipe_tower_rotation_angle", base_ptr, this->wipe_tower_rotation_angle);
        cache.opt_add("prime_tower_brim_width", base_ptr, this->prime_tower_brim_width);
        cache.opt_add("prime_tower_infill_gap", base_ptr, this->prime_tower_infill_gap);
        cache.opt_add("prime_tower_skip_points", base_ptr, this->prime_tower_skip_points);
        cache.opt_add("prime_tower_flat_ironing", base_ptr, this->prime_tower_flat_ironing);
        cache.opt_add("enable_tower_interface_features", base_ptr, this->enable_tower_interface_features);
        cache.opt_add("enable_tower_interface_cooldown_during_tower", base_ptr, this->enable_tower_interface_cooldown_during_tower);
        cache.opt_add("wipe_tower_bridging", base_ptr, this->wipe_tower_bridging);
        cache.opt_add("wipe_tower_extra_flow", base_ptr, this->wipe_tower_extra_flow);
        cache.opt_add("flush_volumes_matrix", base_ptr, this->flush_volumes_matrix);
        cache.opt_add("flush_volumes_vector", base_ptr, this->flush_volumes_vector);
        cache.opt_add("wipe_tower_cone_angle", base_ptr, this->wipe_tower_cone_angle);
        cache.opt_add("wipe_tower_extra_spacing", base_ptr, this->wipe_tower_extra_spacing);
        cache.opt_add("wipe_tower_max_purge_speed", base_ptr, this->wipe_tower_max_purge_speed);
        cache.opt_add("wipe_tower_wall_type", base_ptr, this->wipe_tower_wall_type);
        cache.opt_add("wipe_tower_extra_rib_length", base_ptr, this->wipe_tower_extra_rib_length);
        cache.opt_add("wipe_tower_rib_width", base_ptr, this->wipe_tower_rib_width);
        cache.opt_add("wipe_tower_fillet_wall", base_ptr, this->wipe_tower_fillet_wall);
        cache.opt_add("wipe_tower_filament", base_ptr, this->wipe_tower_filament);
        cache.opt_add("wiping_volumes_extruders", base_ptr, this->wiping_volumes_extruders);
        cache.opt_add("idle_temperature", base_ptr, this->idle_temperature);
        cache.opt_add("prime_volume", base_ptr, this->prime_volume);
        cache.opt_add("flush_multiplier", base_ptr, this->flush_multiplier);
        cache.opt_add("z_offset", base_ptr, this->z_offset);
        cache.opt_add("filament_colour_new", base_ptr, this->filament_colour_new);
        cache.opt_add("nozzle_volume", base_ptr, this->nozzle_volume);
        cache.opt_add("start_end_points", base_ptr, this->start_end_points);
        cache.opt_add("timelapse_type", base_ptr, this->timelapse_type);
        cache.opt_add("thumbnails", base_ptr, this->thumbnails);
        cache.opt_add("combine_brims", base_ptr, this->combine_brims);
        cache.opt_add("filament_shrink", base_ptr, this->filament_shrink);
        cache.opt_add("filament_shrinkage_compensation_z", base_ptr, this->filament_shrinkage_compensation_z);
        cache.opt_add("gcode_label_objects", base_ptr, this->gcode_label_objects);
        cache.opt_add("exclude_object", base_ptr, this->exclude_object);
        cache.opt_add("grab_length", base_ptr, this->grab_length);
        cache.opt_add("gcode_comments", base_ptr, this->gcode_comments);
        cache.opt_add("slow_down_layers", base_ptr, this->slow_down_layers);
        cache.opt_add("support_material_interface_fan_speed", base_ptr, this->support_material_interface_fan_speed);
        cache.opt_add("internal_bridge_fan_speed", base_ptr, this->internal_bridge_fan_speed);
        cache.opt_add("ironing_fan_speed", base_ptr, this->ironing_fan_speed);
        cache.opt_add("filament_notes", base_ptr, this->filament_notes);
        cache.opt_add("notes", base_ptr, this->notes);
        cache.opt_add("printer_notes", base_ptr, this->printer_notes);
        cache.opt_add("activate_chamber_temp_control", base_ptr, this->activate_chamber_temp_control);
        cache.opt_add("chamber_temperature", base_ptr, this->chamber_temperature);
        cache.opt_add("chamber_minimal_temperature", base_ptr, this->chamber_minimal_temperature);
        cache.opt_add("preferred_orientation", base_ptr, this->preferred_orientation);
        cache.opt_add("bed_mesh_min", base_ptr, this->bed_mesh_min);
        cache.opt_add("bed_mesh_max", base_ptr, this->bed_mesh_max);
        cache.opt_add("bed_mesh_probe_distance", base_ptr, this->bed_mesh_probe_distance);
        cache.opt_add("adaptive_bed_mesh_margin", base_ptr, this->adaptive_bed_mesh_margin);
    }
};

// This object is mapped to Perl as Slic3r::Config::Full.
class FullPrintConfig : public PrintObjectConfig, public PrintRegionConfig, public FiberReinforcementConfig, public PrintConfig {
    STATIC_PRINT_CONFIG_CACHE_DERIVED(FullPrintConfig)
public:
    FullPrintConfig() : PrintObjectConfig(0), PrintRegionConfig(0), FiberReinforcementConfig(0), PrintConfig(0) { assert(s_cache_FullPrintConfig.initialized()); *this = s_cache_FullPrintConfig.defaults(); }

    size_t hash() const throw()
    {
        size_t seed = 0;
        boost::hash_combine(seed, static_cast<const PrintObjectConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const PrintRegionConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const FiberReinforcementConfig*>(this)->hash());
        boost::hash_combine(seed, static_cast<const PrintConfig*>(this)->hash());
        return seed;
    }

    bool operator==(const FullPrintConfig &rhs) const throw()
    {
        if (!(*static_cast<const PrintObjectConfig*>(this) == static_cast<const PrintObjectConfig&>(rhs)))
            return false;
        if (!(*static_cast<const PrintRegionConfig*>(this) == static_cast<const PrintRegionConfig&>(rhs)))
            return false;
        if (!(*static_cast<const FiberReinforcementConfig*>(this) == static_cast<const FiberReinforcementConfig&>(rhs)))
            return false;
        if (!(*static_cast<const PrintConfig*>(this) == static_cast<const PrintConfig&>(rhs)))
            return false;
        return true;
    }

    bool operator!=(const FullPrintConfig &rhs) const throw() { return !(*this == rhs); }

protected:
    FullPrintConfig(int) : PrintObjectConfig(1), PrintRegionConfig(1), FiberReinforcementConfig(1), PrintConfig(1) {}

    void initialize(StaticCacheBase &cache, const char *base_ptr)
    {
        this->PrintObjectConfig::initialize(cache, base_ptr);
        this->PrintRegionConfig::initialize(cache, base_ptr);
        this->FiberReinforcementConfig::initialize(cache, base_ptr);
        this->PrintConfig::initialize(cache, base_ptr);
    }
};

inline const StaticPrintConfig& static_print_config_ref(const PrintRegionConfig &config)
{
    return static_cast<const StaticPrintConfig&>(static_cast<const PrintRegionCoreConfig&>(config));
}

inline const StaticPrintConfig& static_print_config_ref(const PrintConfig &config)
{
    return static_cast<const StaticPrintConfig&>(static_cast<const MachineEnvelopeConfig&>(config));
}

inline const StaticPrintConfig& static_print_config_ref(const FullPrintConfig &config)
{
    return static_cast<const StaticPrintConfig&>(static_cast<const PrintObjectConfig&>(config));
}

// Validate the FullPrintConfig. Returns an empty string on success, otherwise an error message is returned.
std::map<std::string, std::string> validate(const FullPrintConfig &config, bool under_cli = false);

PRINT_CONFIG_CLASS_DEFINE(
    SLAPrintConfig,
    ((ConfigOptionString,     filename_format))
)

PRINT_CONFIG_CLASS_DEFINE(
    SLAPrintObjectConfig,

    ((ConfigOptionFloat, layer_height))

    //Number of the layers needed for the exposure time fade [3;20]
    ((ConfigOptionInt,  faded_layers))/*= 10*/

    ((ConfigOptionFloat, slice_closing_radius))

    // Enabling or disabling support creation
    ((ConfigOptionBool,  supports_enable))

    // Diameter in mm of the pointing side of the head.
    ((ConfigOptionFloat, support_head_front_diameter))/*= 0.2*/

    // How much the pinhead has to penetrate the model surface
    ((ConfigOptionFloat, support_head_penetration))/*= 0.2*/

    // Width in mm from the back sphere center to the front sphere center.
    ((ConfigOptionFloat, support_head_width))/*= 1.0*/

    // Radius in mm of the support pillars.
    ((ConfigOptionFloat, support_pillar_diameter))/*= 0.8*/

    // The percentage of smaller pillars compared to the normal pillar diameter
    // which are used in problematic areas where a normal pilla cannot fit.
    ((ConfigOptionPercent, support_small_pillar_diameter_percent))

    // How much bridge (supporting another pinhead) can be placed on a pillar.
    ((ConfigOptionInt,   support_max_bridges_on_pillar))

    // How the pillars are bridged together
    ((ConfigOptionEnum<SLAPillarConnectionMode>, support_pillar_connection_mode))

    // Generate only ground facing supports
    ((ConfigOptionBool, support_buildplate_only))

    // TODO: unimplemented at the moment. This coefficient will have an impact
    // when bridges and pillars are merged. The resulting pillar should be a bit
    // thicker than the ones merging into it. How much thicker? I don't know
    // but it will be derived from this value.
    ((ConfigOptionFloat, support_pillar_widening_factor))

    // Radius in mm of the pillar base.
    ((ConfigOptionFloat, support_base_diameter))/*= 2.0*/

    // The height of the pillar base cone in mm.
    ((ConfigOptionFloat, support_base_height))/*= 1.0*/

    // The minimum distance of the pillar base from the model in mm.
    ((ConfigOptionFloat, support_base_safety_distance)) /*= 1.0*/

    // The default angle for connecting support sticks and junctions.
    ((ConfigOptionFloat, support_critical_angle))/*= 45*/

    // The max length of a bridge in mm
    ((ConfigOptionFloat, support_max_bridge_length))/*= 15.0*/

    // The max distance of two pillars to get cross linked.
    ((ConfigOptionFloat, support_max_pillar_link_distance))

    // The elevation in Z direction upwards. This is the space between the pad
    // and the model object's bounding box bottom. Units in mm.
    ((ConfigOptionFloat, support_object_elevation))/*= 5.0*/

    /////// Following options influence automatic support points placement:
    ((ConfigOptionInt, support_points_density_relative))
    ((ConfigOptionFloat, support_points_minimal_distance))

    // Now for the base pool (pad) /////////////////////////////////////////////

    // Enabling or disabling support creation
    ((ConfigOptionBool,  pad_enable))

    // The thickness of the pad walls
    ((ConfigOptionFloat, pad_wall_thickness))/*= 2*/

    // The height of the pad from the bottom to the top not considering the pit
    ((ConfigOptionFloat, pad_wall_height))/*= 5*/

    // How far should the pad extend around the contained geometry
    ((ConfigOptionFloat, pad_brim_size))

    // The greatest distance where two individual pads are merged into one. The
    // distance is measured roughly from the centroids of the pads.
    ((ConfigOptionFloat, pad_max_merge_distance))/*= 50*/

    // The smoothing radius of the pad edges
    // ((ConfigOptionFloat, pad_edge_radius))/*= 1*/;

    // The slope of the pad wall...
    ((ConfigOptionFloat, pad_wall_slope))

    // /////////////////////////////////////////////////////////////////////////
    // Zero elevation mode parameters:
    //    - The object pad will be derived from the model geometry.
    //    - There will be a gap between the object pad and the generated pad
    //      according to the support_base_safety_distance parameter.
    //    - The two pads will be connected with tiny connector sticks
    // /////////////////////////////////////////////////////////////////////////

    // Disable the elevation (ignore its value) and use the zero elevation mode
    ((ConfigOptionBool, pad_around_object))

    ((ConfigOptionBool, pad_around_object_everywhere))

    // This is the gap between the object bottom and the generated pad
    ((ConfigOptionFloat, pad_object_gap))

    // How far to place the connector sticks on the object pad perimeter
    ((ConfigOptionFloat, pad_object_connector_stride))

    // The width of the connectors sticks
    ((ConfigOptionFloat, pad_object_connector_width))

    // How much should the tiny connectors penetrate into the model body
    ((ConfigOptionFloat, pad_object_connector_penetration))

    // /////////////////////////////////////////////////////////////////////////
    // Model hollowing parameters:
    //   - Models can be hollowed out as part of the SLA print process
    //   - Thickness of the hollowed model walls can be adjusted
    //   -
    //   - Additional holes will be drilled into the hollow model to allow for
    //   - resin removal.
    // /////////////////////////////////////////////////////////////////////////

    ((ConfigOptionBool, hollowing_enable))

    // The minimum thickness of the model walls to maintain. Note that the
    // resulting walls may be thicker due to smoothing out fine cavities where
    // resin could stuck.
    ((ConfigOptionFloat, hollowing_min_thickness))

    // Indirectly controls the voxel size (resolution) used by openvdb
    ((ConfigOptionFloat, hollowing_quality))

    // Indirectly controls the minimum size of created cavities.
    ((ConfigOptionFloat, hollowing_closing_distance))
)

enum SLAMaterialSpeed { slamsSlow, slamsFast };

PRINT_CONFIG_CLASS_DEFINE(
    SLAMaterialConfig,

    ((ConfigOptionFloat,                       initial_layer_height))
    ((ConfigOptionFloat,                       bottle_cost))
    ((ConfigOptionFloat,                       bottle_volume))
    ((ConfigOptionFloat,                       bottle_weight))
    ((ConfigOptionFloat,                       material_density))
    ((ConfigOptionFloat,                       exposure_time))
    ((ConfigOptionFloat,                       initial_exposure_time))
    ((ConfigOptionFloats,                      material_correction))
    ((ConfigOptionFloat,                       material_correction_x))
    ((ConfigOptionFloat,                       material_correction_y))
    ((ConfigOptionFloat,                       material_correction_z))
    ((ConfigOptionEnum<SLAMaterialSpeed>,      material_print_speed))
)

PRINT_CONFIG_CLASS_DEFINE(
    SLAPrinterConfig,

    ((ConfigOptionEnum<PrinterTechnology>,    printer_technology))
    ((ConfigOptionPoints,                     printable_area))
    ((ConfigOptionFloat,                      printable_height))
    ((ConfigOptionFloat,                      display_width))
    ((ConfigOptionFloat,                      display_height))
    ((ConfigOptionInt,                        display_pixels_x))
    ((ConfigOptionInt,                        display_pixels_y))
    ((ConfigOptionEnum<SLADisplayOrientation>,display_orientation))
    ((ConfigOptionBool,                       display_mirror_x))
    ((ConfigOptionBool,                       display_mirror_y))
    ((ConfigOptionFloats,                     relative_correction))
    ((ConfigOptionFloat,                      relative_correction_x))
    ((ConfigOptionFloat,                      relative_correction_y))
    ((ConfigOptionFloat,                      relative_correction_z))
    ((ConfigOptionFloat,                      absolute_correction))
    ((ConfigOptionFloat,                      elefant_foot_compensation))
    ((ConfigOptionFloat,                      elefant_foot_min_width))
    ((ConfigOptionFloat,                      gamma_correction))
    ((ConfigOptionFloat,                      fast_tilt_time))
    ((ConfigOptionFloat,                      slow_tilt_time))
    ((ConfigOptionFloat,                      area_fill))
    ((ConfigOptionFloat,                      min_exposure_time))
    ((ConfigOptionFloat,                      max_exposure_time))
    ((ConfigOptionFloat,                      min_initial_exposure_time))
    ((ConfigOptionFloat,                      max_initial_exposure_time))
)

PRINT_CONFIG_CLASS_DERIVED_DEFINE0(
    SLAFullPrintConfig,
    (SLAPrinterConfig, SLAPrintConfig, SLAPrintObjectConfig, SLAMaterialConfig)
)

inline const StaticPrintConfig& static_print_config_ref(const SLAFullPrintConfig &config)
{
    return static_cast<const StaticPrintConfig&>(static_cast<const SLAPrinterConfig&>(config));
}

#undef STATIC_PRINT_CONFIG_CACHE
#undef STATIC_PRINT_CONFIG_CACHE_BASE
#undef STATIC_PRINT_CONFIG_CACHE_DERIVED
#undef PRINT_CONFIG_CLASS_ELEMENT_DEFINITION
#undef PRINT_CONFIG_CLASS_ELEMENT_EQUAL
#undef PRINT_CONFIG_CLASS_ELEMENT_LOWER
#undef PRINT_CONFIG_CLASS_ELEMENT_HASH
#undef PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION
#undef PRINT_CONFIG_CLASS_ELEMENT_INITIALIZATION2
#undef PRINT_CONFIG_CLASS_DEFINE
#undef PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST
#undef PRINT_CONFIG_CLASS_DERIVED_CLASS_LIST_ITEM
#undef PRINT_CONFIG_CLASS_DERIVED_DEFINE
#undef PRINT_CONFIG_CLASS_DERIVED_DEFINE0
#undef PRINT_CONFIG_CLASS_DERIVED_DEFINE1
#undef PRINT_CONFIG_CLASS_DERIVED_HASH
#undef PRINT_CONFIG_CLASS_DERIVED_EQUAL
#undef PRINT_CONFIG_CLASS_DERIVED_INITCACHE_ITEM
#undef PRINT_CONFIG_CLASS_DERIVED_INITCACHE
#undef PRINT_CONFIG_CLASS_DERIVED_INITIALIZER
#undef PRINT_CONFIG_CLASS_DERIVED_INITIALIZER_ITEM

class CLIActionsConfigDef : public ConfigDef
{
public:
    CLIActionsConfigDef();
};

class CLITransformConfigDef : public ConfigDef
{
public:
    CLITransformConfigDef();
};

class CLIMiscConfigDef : public ConfigDef
{
public:
    CLIMiscConfigDef();
};

typedef std::string t_custom_gcode_key;
// This map containes list of specific placeholders for each custom G-code, if any exist
const std::map<t_custom_gcode_key, t_config_option_keys>& custom_gcode_specific_placeholders();

// Next classes define placeholders used by GUI::EditGCodeDialog.

class ReadOnlySlicingStatesConfigDef : public ConfigDef
{
public:
    ReadOnlySlicingStatesConfigDef();
};

class ReadWriteSlicingStatesConfigDef : public ConfigDef
{
public:
    ReadWriteSlicingStatesConfigDef();
};

class OtherSlicingStatesConfigDef : public ConfigDef
{
public:
    OtherSlicingStatesConfigDef();
};

class PrintStatisticsConfigDef : public ConfigDef
{
public:
    PrintStatisticsConfigDef();
};

class ObjectsInfoConfigDef : public ConfigDef
{
public:
    ObjectsInfoConfigDef();
};

class DimensionsConfigDef : public ConfigDef
{
public:
    DimensionsConfigDef();
};

class TemperaturesConfigDef : public ConfigDef
{
public:
    TemperaturesConfigDef();
};

class TimestampsConfigDef : public ConfigDef
{
public:
    TimestampsConfigDef();
};

class OtherPresetsConfigDef : public ConfigDef
{
public:
    OtherPresetsConfigDef();
};

// This classes defines all custom G-code specific placeholders.
class CustomGcodeSpecificConfigDef : public ConfigDef
{
public:
    CustomGcodeSpecificConfigDef();
};
extern const CustomGcodeSpecificConfigDef    custom_gcode_specific_config_def;

// This class defines the command line options representing actions.
extern const CLIActionsConfigDef    cli_actions_config_def;

// This class defines the command line options representing transforms.
extern const CLITransformConfigDef  cli_transform_config_def;

// This class defines all command line options that are not actions or transforms.
extern const CLIMiscConfigDef       cli_misc_config_def;

class DynamicPrintAndCLIConfig : public DynamicPrintConfig
{
public:
    DynamicPrintAndCLIConfig() {}
    DynamicPrintAndCLIConfig(const DynamicPrintAndCLIConfig &other) : DynamicPrintConfig(other) {}

    // Overrides ConfigBase::def(). Static configuration definition. Any value stored into this ConfigBase shall have its definition here.
    const ConfigDef*        def() const override { return &s_def; }

    // Verify whether the opt_key has not been obsoleted or renamed.
    // Both opt_key and value may be modified by handle_legacy().
    // If the opt_key is no more valid in this version of Slic3r, opt_key is cleared by handle_legacy().
    // handle_legacy() is called internally by set_deserialize().
    void                    handle_legacy(t_config_option_key &opt_key, std::string &value) const override;

private:
    class PrintAndCLIConfigDef : public ConfigDef
    {
    public:
        PrintAndCLIConfigDef() {
            this->options.insert(print_config_def.options.begin(), print_config_def.options.end());
            this->options.insert(cli_actions_config_def.options.begin(), cli_actions_config_def.options.end());
            this->options.insert(cli_transform_config_def.options.begin(), cli_transform_config_def.options.end());
            this->options.insert(cli_misc_config_def.options.begin(), cli_misc_config_def.options.end());
            for (const auto &kvp : this->options)
                this->by_serialization_key_ordinal[kvp.second.serialization_key_ordinal] = &kvp.second;
        }
        // Do not release the default values, they are handled by print_config_def & cli_actions_config_def / cli_transform_config_def / cli_misc_config_def.
        ~PrintAndCLIConfigDef() { this->options.clear(); }
    };
    static PrintAndCLIConfigDef s_def;
};

bool is_XL_printer(const DynamicPrintConfig &cfg);
bool is_XL_printer(const PrintConfig &cfg);

Polygon get_shared_poly(const std::vector<Pointfs>& extruder_polys);
Points get_bed_shape(const DynamicPrintConfig &cfg, bool use_share = true);
Points get_bed_shape(const PrintConfig &cfg, bool use_share = false);
Points get_bed_shape(const SLAPrinterConfig &cfg);
Slic3r::Polygons get_bed_excluded_area(const PrintConfig& cfg);
Slic3r::Polygon get_bed_shape_with_excluded_area(const PrintConfig& cfg, bool use_share = false);
bool has_skirt(const DynamicPrintConfig& cfg);
float get_real_skirt_dist(const DynamicPrintConfig& cfg);

// ModelConfig is a wrapper around DynamicPrintConfig with an addition of a timestamp.
// Each change of ModelConfig is tracked by assigning a new timestamp from a global counter.
// The counter is used for faster synchronization of the background slicing thread
// with the front end by skipping synchronization of equal config dictionaries.
// The global counter is also used for avoiding unnecessary serialization of config
// dictionaries when taking an Undo snapshot.
//
// The global counter is NOT thread safe, therefore it is recommended to use ModelConfig from
// the main thread only.
//
// As there is a global counter and it is being increased with each change to any ModelConfig,
// if two ModelConfig dictionaries differ, they should differ with their timestamp as well.
// Therefore copying the ModelConfig including its timestamp is safe as there is no harm
// in having multiple ModelConfig with equal timestamps as long as their dictionaries are equal.
//
// The timestamp is used by the Undo/Redo stack. As zero timestamp means invalid timestamp
// to the Undo/Redo stack (zero timestamp means the Undo/Redo stack needs to serialize and
// compare serialized data for differences), zero timestamp shall never be used.
// Timestamp==1 shall only be used for empty dictionaries.
class ModelConfig
{
public:
    // Following method clears the config and increases its timestamp, so the deleted
    // state is considered changed from perspective of the undo/redo stack.
    void         reset() { m_data.clear(); touch(); }

    void         assign_config(const ModelConfig &rhs) {
        if (m_timestamp != rhs.m_timestamp) {
            m_data      = rhs.m_data;
            m_timestamp = rhs.m_timestamp;
        }
    }
    void         assign_config(ModelConfig &&rhs) {
        if (m_timestamp != rhs.m_timestamp) {
            m_data      = std::move(rhs.m_data);
            m_timestamp = rhs.m_timestamp;
            rhs.reset();
        }
    }

    // Modification of the ModelConfig is not thread safe due to the global timestamp counter!
    // Don't call modification methods from the back-end!
    // Assign methods don't assign if src==dst to not having to bump the timestamp in case they are equal.
    void         assign_config(const DynamicPrintConfig &rhs)  { if (m_data != rhs) { m_data = rhs; this->touch(); } }
    void         assign_config(DynamicPrintConfig &&rhs)       { if (m_data != rhs) { m_data = std::move(rhs); this->touch(); } }
    void         apply(const ModelConfig &other, bool ignore_nonexistent = false) { this->apply(other.get(), ignore_nonexistent); }
    void         apply(const ConfigBase &other, bool ignore_nonexistent = false) { m_data.apply_only(other, other.keys(), ignore_nonexistent); this->touch(); }
    void         apply_only(const ModelConfig &other, const t_config_option_keys &keys, bool ignore_nonexistent = false) { this->apply_only(other.get(), keys, ignore_nonexistent); }
    void         apply_only(const ConfigBase &other, const t_config_option_keys &keys, bool ignore_nonexistent = false) { m_data.apply_only(other, keys, ignore_nonexistent); this->touch(); }
    bool         set_key_value(const std::string &opt_key, ConfigOption *opt) { bool out = m_data.set_key_value(opt_key, opt); this->touch(); return out; }
    template<typename T>
    void         set(const std::string &opt_key, T value) { m_data.set(opt_key, value, true); this->touch(); }
    void         set_deserialize(const t_config_option_key &opt_key, const std::string &str, ConfigSubstitutionContext &substitution_context, bool append = false)
        { m_data.set_deserialize(opt_key, str, substitution_context, append); this->touch(); }
    bool         erase(const t_config_option_key &opt_key) { bool out = m_data.erase(opt_key); if (out) this->touch(); return out; }

    // Getters are thread safe.
    // The following implicit conversion breaks the Cereal serialization.
//    operator const DynamicPrintConfig&() const throw() { return this->get(); }
    const DynamicPrintConfig&   get() const throw() { return m_data; }
    bool                        empty() const throw() { return m_data.empty(); }
    size_t                      size() const throw() { return m_data.size(); }
    auto                        cbegin() const { return m_data.cbegin(); }
    auto                        cend() const { return m_data.cend(); }
    t_config_option_keys        keys() const { return m_data.keys(); }
    bool                        has(const t_config_option_key &opt_key) const { return m_data.has(opt_key); }
    const ConfigOption*         option(const t_config_option_key &opt_key) const { return m_data.option(opt_key); }
    int                         opt_int(const t_config_option_key &opt_key) const { return m_data.opt_int(opt_key); }
    int                         extruder() const { return opt_int("extruder"); }
    double opt_float(const t_config_option_key &opt_key) const {
      return m_data.opt_float(opt_key);
    }
    double get_abs_value(const t_config_option_key &opt_key) const {
      return m_data.get_abs_value(opt_key);
    }
    std::string                 opt_serialize(const t_config_option_key &opt_key) const { return m_data.opt_serialize(opt_key); }

    // Return an optional timestamp of this object.
    // If the timestamp returned is non-zero, then the serialization framework will
    // only save this object on the Undo/Redo stack if the timestamp is different
    // from the timestmap of the object at the top of the Undo / Redo stack.
    virtual uint64_t    timestamp() const throw() { return m_timestamp; }
    bool                timestamp_matches(const ModelConfig &rhs) const throw() { return m_timestamp == rhs.m_timestamp; }
    // Not thread safe! Should not be called from other than the main thread!
    void                touch() { m_timestamp = ++ s_last_timestamp; }

private:
    friend class cereal::access;
    template<class Archive> void serialize(Archive& ar) { ar(m_timestamp); ar(m_data); }

    uint64_t                    m_timestamp { 1 };
    DynamicPrintConfig          m_data;

    static uint64_t             s_last_timestamp;
};

// const std::vector<double> &fv_matrix:  origin matrix from json
// size_t extruder_id: -1 means single-nozzle for old file, 0 means the 1st extruder, 1 means the 2nd extruder
template<class T>
static std::vector<T> get_flush_volumes_matrix(const std::vector<T> &fv_matrix, size_t extruder_id = -1, size_t nozzle_nums = 1)
{
    if (extruder_id != -1 && nozzle_nums != 1) {
        return std::vector<T>(fv_matrix.begin() + size_t(fv_matrix.size() / nozzle_nums * extruder_id + EPSILON),
                                   fv_matrix.begin() + size_t(fv_matrix.size() / nozzle_nums * (extruder_id + 1) + EPSILON));
    }
    return fv_matrix;
}

// std::vector<double> &out_matrix:
// const std::vector<double> &fv_matrix: the matrix of one nozzle
// size_t extruder_id: -1 means single-nozzle for old file, 0 means the 1st extruder, 1 means the 2nd extruder
template<class T>
static void set_flush_volumes_matrix(std::vector<T> &out_matrix, const std::vector<T> &fv_matrix, size_t extruder_id = -1, size_t nozzle_nums = 1)
{
    bool is_multi_extruder = false;
    if (extruder_id != -1 && nozzle_nums != 1) {
        std::copy(fv_matrix.begin(), fv_matrix.end(), out_matrix.begin() + size_t(out_matrix.size() / nozzle_nums * extruder_id + EPSILON));
    }
    else {
        out_matrix = std::vector<T>(fv_matrix.begin(), fv_matrix.end());
    }
}

size_t get_extruder_index(const GCodeConfig& config, unsigned int filament_id);

} // namespace Slic3r

// Serialization through the Cereal library
namespace cereal {
    // Let cereal know that there are load / save non-member functions declared for DynamicPrintConfig, ignore serialize / load / save from parent class DynamicConfig.
    template <class Archive> struct specialize<Archive, Slic3r::DynamicPrintConfig, cereal::specialization::non_member_load_save> {};

    template<class Archive> void load(Archive& archive, Slic3r::DynamicPrintConfig &config)
    {
        size_t cnt;
        archive(cnt);
        config.clear();
        for (size_t i = 0; i < cnt; ++ i) {
            size_t serialization_key_ordinal;
            archive(serialization_key_ordinal);
            assert(serialization_key_ordinal > 0);
            auto it = Slic3r::print_config_def.by_serialization_key_ordinal.find(serialization_key_ordinal);
            assert(it != Slic3r::print_config_def.by_serialization_key_ordinal.end());
            config.set_key_value(it->second->opt_key, it->second->load_option_from_archive(archive));
        }
    }

    template<class Archive> void save(Archive& archive, const Slic3r::DynamicPrintConfig &config)
    {
        size_t cnt = config.size();
        archive(cnt);
        for (auto it = config.cbegin(); it != config.cend(); ++it) {
            const Slic3r::ConfigOptionDef* optdef = Slic3r::print_config_def.get(it->first);
            assert(optdef != nullptr);
            assert(optdef->serialization_key_ordinal > 0);
            archive(optdef->serialization_key_ordinal);
            optdef->save_option_to_archive(archive, it->second.get());
        }
    }
}

#endif
