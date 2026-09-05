#pragma once

#include <map>
#include <cstddef>
#include <string>
#include <vector>

namespace Slic3r {

class ConfigBase;
class ConfigOption;
class Preset;
class PresetCollection;

enum class ConfigOriginKind {
    Defaults, SystemPreset, UserPreset, ImportedPreset, ProjectPreset,
    UnsavedEdit, Project, ToolVariant, Generated, HardwareContract, Normalization
};

struct ConfigValueOrigin {
    ConfigOriginKind kind = ConfigOriginKind::Defaults;
    std::string preset;
    std::string parent;
    size_t material = 0; // One-based logical slot; zero means not material-specific.
    bool projected = false;
    std::string input_value;
    std::string saved_value;
};

struct ConfigResolutionStep {
    std::string value;
    std::vector<ConfigValueOrigin> origins;
};

// Optional observer of the actual full-config merge. It never loads presets,
// reads project files, or changes an input config. Histories describe resolved
// preset ownership, not which ancestor originally declared an equal value.
class ConfigResolutionTrace {
public:
    using History = std::vector<ConfigResolutionStep>;
    using Settings = std::map<std::string, History>;

    const Settings &settings() const { return m_settings; }
    const std::vector<std::string> &warnings() const { return m_warnings; }
    void clear();
    void warn(std::string warning);

    void record(const std::string &key, const ConfigOption &option,
                std::vector<ConfigValueOrigin> origins);
    void applied(const ConfigBase &config, ConfigValueOrigin origin);
    void applied_preset(const ConfigBase &config, const Preset &preset,
                        const PresetCollection &collection, size_t material = 0,
                        bool projected = false);
    void checkpoint(const ConfigBase &config, ConfigValueOrigin origin);

    static ConfigValueOrigin preset_origin(const std::string &key, const Preset &preset,
                                          const PresetCollection &collection,
                                          size_t material = 0, bool projected = false);
    static bool reportable(const std::string &key);

private:
    Settings m_settings;
    std::vector<std::string> m_warnings;
};

} // namespace Slic3r
