#include <catch2/catch_all.hpp>

#include <boost/filesystem.hpp>
#include <boost/nowide/fstream.hpp>

#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PrinterConnectionUpdate.hpp"
#include "libslic3r/Utils.hpp"

using namespace Slic3r;

namespace {
namespace fs = boost::filesystem;

struct ConnectionFixture {
    fs::path root = fs::temp_directory_path() / fs::unique_path("tinman-connection-%%%%-%%%%");
    PresetBundle bundle;

    ConnectionFixture()
    {
        fs::create_directories(root / "physical_printer");
        auto config = bundle.printers.default_preset().config;
        config.option<ConfigOptionString>("inherits", true)->value.clear();
        bundle.printers.load_preset("", "Machine A", config, true);
        bundle.printers.load_preset("", "Machine B", config, false);
        PresetsConfigSubstitutions substitutions;
        bundle.physical_printers.load_printers(root.string(), "physical_printer", substitutions,
                                               ForwardCompatibilitySubstitutionRule::Disable);
    }

    ~ConnectionFixture()
    {
        boost::system::error_code error;
        fs::remove_all(root, error);
    }

    DynamicPrintConfig config(const std::string &host = "192.0.2.10") const
    {
        auto result = bundle.physical_printers.default_config();
        result.option<ConfigOptionStrings>("preset_names")->values = {"Machine A"};
        result.opt_string("print_host") = host;
        result.opt_string("printhost_apikey") = "fixture-key-not-a-real-credential";
        return result;
    }

    std::string file(const std::string &name) const
    {
        return bundle.physical_printers.path_from_name(name);
    }

    void add(const std::string &name)
    {
        bundle.physical_printers.load_printer(file(name), name, config(), true, true);
    }
};

std::string read_bytes(const std::string &file)
{
    boost::nowide::ifstream input(file, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(input), {});
}
} // namespace

TEST_CASE("Failed connection overwrite retains the stored printer and draft", "[Preset][ConnectionRecovery][TinMan]")
{
    ConnectionFixture fixture;
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    const auto previous = printers.get_selected_printer();
    const auto old_bytes = read_bytes(fixture.file("Workshop"));
    PhysicalPrinter candidate = previous;
    candidate.config.opt_string("print_host") = std::string(1, char(0xff));
    candidate.add_preset("Machine B");
    const auto pending_config = candidate.config;

    REQUIRE_THROWS(printers.save_printer(candidate));
    CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine A");
    CHECK(printers.get_selected_printer().config == previous.config);
    CHECK(printers.get_selected_printer().preset_names == previous.preset_names);
    CHECK(candidate.config == pending_config);
    CHECK(candidate.preset_names == std::set<std::string>{"Machine A", "Machine B"});
    CHECK(read_bytes(fixture.file("Workshop")) == old_bytes);
}

TEST_CASE("Import with connection persistence stages new and replacement records", "[Preset][ConnectionRecovery][TinMan]")
{
    const bool overwrite = GENERATE(false, true);
    ConnectionFixture fixture;
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    const auto previous = printers.get_selected_printer();
    const auto size = printers().size();
    const auto bad_path = (fixture.root / "missing-directory" / "Printer.json").string();

    REQUIRE_THROWS(printers.load_printer(bad_path, overwrite ? "Workshop" : "New connection",
                                        fixture.config("192.0.2.20"), true, true));
    CHECK(printers().size() == size);
    CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine A");
    REQUIRE(printers.find_printer("Workshop") != nullptr);
    CHECK(printers.find_printer("Workshop")->config == previous.config);
    CHECK(printers.find_printer("Workshop")->file == previous.file);
    CHECK(printers.find_printer("New connection") == nullptr);
}

TEST_CASE("Malformed physical printer files are retained but never published", "[Preset][ConnectionRecovery][TinMan]")
{
    const std::string bad_json = GENERATE(std::string("{ broken"), std::string("[]"),
        std::string("{\"version\":\"invalid\",\"print_host\":\"192.0.2.20\"}"));
    ConnectionFixture fixture;
    fixture.add("Workshop");
    write_file_with_replace(fixture.file("Broken"), bad_json);
    auto &printers = fixture.bundle.physical_printers;
    const auto previous = printers.get_selected_printer();
    PresetsConfigSubstitutions substitutions;

    CHECK_THROWS(printers.load_printers(fixture.root.string(), "physical_printer", substitutions,
                                       ForwardCompatibilitySubstitutionRule::Disable));
    CHECK(printers.find_printer("Broken") == nullptr);
    CHECK(read_bytes(fixture.file("Broken")) == bad_json);
    CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine A");
    CHECK(printers.get_selected_printer().config == previous.config);
}

TEST_CASE("Connection save and rename round-trip credentials and nozzle associations", "[Preset][ConnectionRecovery][TinMan]")
{
    const bool rename = GENERATE(false, true);
    ConnectionFixture fixture;
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    PhysicalPrinter candidate = printers.get_selected_printer();
    candidate.config.opt_string("print_host") = "192.0.2.20";
    candidate.add_preset("Machine B");
    if (rename)
        candidate.name = "Renamed Workshop";
    const auto pending_config = candidate.config;
    REQUIRE_NOTHROW(printers.save_printer(candidate, rename ? "Workshop" : ""));
    CHECK(candidate.config == pending_config);
    CHECK(printers().size() == 1);
    CHECK(printers.get_selected_printer_name() == candidate.name);
    CHECK(printers.get_selected_printer_preset_name() == "Machine A");
    CHECK(printers.get_selected_printer().config.opt_string("print_host") == "192.0.2.20");
    CHECK(printers.get_selected_printer().config.opt_string("printhost_apikey") == "fixture-key-not-a-real-credential");
    CHECK(printers.get_selected_printer().preset_names == std::set<std::string>{"Machine A", "Machine B"});
    CHECK(fs::is_regular_file(fixture.file(candidate.name)));
    if (rename)
        CHECK_FALSE(fs::exists(fixture.file("Workshop")));

    PhysicalPrinterCollection reloaded(PhysicalPrinter::printer_options(), &fixture.bundle);
    PresetsConfigSubstitutions substitutions;
    REQUIRE_NOTHROW(reloaded.load_printers(fixture.root.string(), "physical_printer", substitutions,
                                          ForwardCompatibilitySubstitutionRule::Disable));
    REQUIRE(reloaded.find_printer(candidate.name) != nullptr);
    CHECK(reloaded.find_printer(candidate.name)->config == printers.get_selected_printer().config);
    reloaded.select_printer(candidate.name, "Machine B");
    CHECK(reloaded.has_selection());
    CHECK(reloaded.get_selected_printer_preset_name() == "Machine B");
}

TEST_CASE("Failed connection rename preserves the original file and identity", "[Preset][ConnectionRecovery][TinMan]")
{
    const bool collision = GENERATE(false, true);
    ConnectionFixture fixture;
    if (collision)
        fixture.add("Occupied");
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    const auto previous = printers.get_selected_printer();
    const auto old_bytes = read_bytes(fixture.file("Workshop"));
    const auto other_bytes = read_bytes(fixture.file("Occupied"));
    PhysicalPrinter candidate = previous;
    candidate.name = collision ? "Occupied" : "Renamed";
    if (!collision)
        candidate.config.opt_string("print_host") = std::string(1, char(0xff));
    const auto pending_config = candidate.config;
    REQUIRE_THROWS(printers.save_printer(candidate, "Workshop"));
    CHECK(candidate.config == pending_config);
    CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine A");
    CHECK(printers.get_selected_printer().config == previous.config);
    CHECK(printers.get_selected_printer().file == previous.file);
    CHECK(read_bytes(fixture.file("Workshop")) == old_bytes);
    CHECK(read_bytes(fixture.file("Occupied")) == other_bytes);
    CHECK(printers.find_printer("Renamed") == nullptr);
    CHECK_FALSE(fs::exists(fixture.file("Renamed")));
}

TEST_CASE("Deferred connection actions preserve existing associations until applied", "[Preset][ConnectionRecovery][TinMan]")
{
    using Action = PendingPhysicalPrinterUpdate::Action;
    const auto action = GENERATE(Action::None, Action::Switch, Action::Replace, Action::Add);
    ConnectionFixture fixture;
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    const auto before = read_bytes(fixture.file("Workshop"));
    PendingPhysicalPrinterUpdate request{action, "Workshop", "Machine A", "Machine B"};
    CHECK(read_bytes(fixture.file("Workshop")) == before);
    CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine A");
    REQUIRE_NOTHROW(request.apply(fixture.bundle));
    const PhysicalPrinter *saved = printers.find_printer("Workshop");
    REQUIRE(saved != nullptr);
    CHECK(saved->config.opt_string("printhost_apikey") == "fixture-key-not-a-real-credential");
    if (action == Action::None || action == Action::Switch) {
        CHECK(read_bytes(fixture.file("Workshop")) == before);
        CHECK(saved->preset_names == std::set<std::string>{"Machine A"});
        CHECK(printers.has_selection() == (action == Action::None));
    } else {
        CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine B");
        CHECK(saved->preset_names.count("Machine B") == 1);
        CHECK(saved->preset_names.count("Machine A") == (action == Action::Add ? 1 : 0));
        CHECK(saved->config.option<ConfigOptionStrings>("preset_names")->values.size() == saved->preset_names.size());
    }
}

TEST_CASE("Deferred connection updates reject stale choices and preserve failed changes", "[Preset][ConnectionRecovery][TinMan]")
{
    const int failure = GENERATE(0, 1, 2);
    ConnectionFixture fixture;
    fixture.add("Other workshop");
    fixture.add("Workshop");
    auto &printers = fixture.bundle.physical_printers;
    PendingPhysicalPrinterUpdate request{PendingPhysicalPrinterUpdate::Action::Replace, "Workshop", "Machine A", "Machine B"};
    if (failure == 0)
        request.new_preset_name = "Missing Machine";
    else if (failure == 1)
        printers.select_printer("Other workshop", "Machine A");
    else {
        fs::rename(fixture.file("Workshop"), fixture.root / "original.json");
        fs::create_directory(fixture.file("Workshop"));
    }
    const auto before = printers.get_selected_printer();
    const auto full_name = printers.get_selected_full_printer_name();
    REQUIRE_THROWS(request.apply(fixture.bundle));
    CHECK(printers.get_selected_full_printer_name() == full_name);
    CHECK(printers.get_selected_printer().config == before.config);
    CHECK(printers.get_selected_printer().preset_names == before.preset_names);
    if (failure == 2) {
        fs::remove(fixture.file("Workshop"));
        fs::rename(fixture.root / "original.json", fixture.file("Workshop"));
        REQUIRE_NOTHROW(request.apply(fixture.bundle));
        CHECK(printers.get_selected_full_printer_name() == "Workshop * Machine B");
    }
}
