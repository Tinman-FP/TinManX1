#ifndef slic3r_TinManMachineProfileContract_hpp_
#define slic3r_TinManMachineProfileContract_hpp_

#include <string>

namespace Slic3r {

class AppConfig;
class DynamicPrintConfig;

// Non-curated machines are unaffected. Curated machines expose only the four
// generated "TinMan Codex" nozzle profiles plus declared mixed-tool profiles,
// regardless of local/cloud copies.
bool tinmanx_machine_preset_allowed(const std::string &preset_name, const std::string &machine_hint = {});

// True only for a canonical TinMan machine/nozzle preset or a declared mixed-
// tool preset. Runtime connection values on these presets are maintained
// separately from the printable profile and must not make it appear modified.
bool tinmanx_managed_machine_preset(const std::string &preset_name, const std::string &machine_hint = {});
bool tinmanx_runtime_connection_option(const std::string &option_name);

// Return the printer-agent implementation required by a curated machine.
// An empty value means the profile's configured agent should be used.
std::string tinmanx_expected_printer_agent(const std::string &preset_name,
                                           const std::string &machine_hint = {});

// Repair routing values that are intrinsic to the physical machine rather
// than user-editable connection credentials (for example K2 CFS support).
bool tinmanx_enforce_machine_connection_contract(const std::string &preset_name,
                                                  DynamicPrintConfig &printer_config);

// Apply the fixed nozzle-flow hardware declared by a canonical TinMan machine
// to the project configuration. Returns true when the preset is managed and
// the contract was applied, even if the project was already correct.
bool tinmanx_apply_nozzle_volume_contract(const std::string &preset_name,
                                          const DynamicPrintConfig &printer_config,
                                          DynamicPrintConfig &project_config);

// Return the selector-facing TinMan profile for a curated machine/nozzle.
// An empty result means the machine is outside the curated catalog or the
// nozzle is not one of the four supported variants.
std::string tinmanx_canonical_machine_preset_name(const std::string &preset_name,
                                                  const std::string &machine_hint = {},
                                                  const std::string &nozzle_variant = {});

// Curated machines use only processes that explicitly name the selected
// canonical machine. This prevents inherited vendor conditions from leaking
// stock process profiles back into the TinMan selector.
bool tinmanx_process_preset_allowed(const std::string &preset_name, const std::string &active_printer_name);

// Keep startup and cloud-restored model selections on the same declared
// machine/nozzle catalog used by the generated resources.
void tinmanx_apply_machine_catalog(AppConfig &config);

// Keep local print-host credentials outside generated machine presets. The
// overlay is keyed by physical machine family, so every supported nozzle uses
// the same connection without creating a visible "Copy" preset.
bool tinmanx_remember_machine_connection(AppConfig &app_config,
                                         const std::string &preset_name,
                                         const DynamicPrintConfig &printer_config,
                                         bool overwrite_existing = true);
bool tinmanx_restore_machine_connection(const AppConfig &app_config,
                                        const std::string &preset_name,
                                        DynamicPrintConfig &printer_config);

} // namespace Slic3r

#endif // slic3r_TinManMachineProfileContract_hpp_
