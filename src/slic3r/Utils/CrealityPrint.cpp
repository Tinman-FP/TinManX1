#include "CrealityPrint.hpp"

#include <algorithm>
#include <chrono>
#include <map>
#include <regex>
#include <sstream>
#include <exception>
#include <thread>
#include <boost/format.hpp>
#include <boost/foreach.hpp>
#include <boost/log/trivial.hpp>
#include <boost/property_tree/ptree.hpp>
#include <boost/property_tree/json_parser.hpp>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/asio.hpp>
#include <boost/algorithm/string/split.hpp>
#include <boost/algorithm/string/trim.hpp>
#include <boost/nowide/convert.hpp>

#include <curl/curl.h>
#include <wx/progdlg.h>

#include "slic3r/GUI/GUI.hpp"
#include "slic3r/GUI/I18N.hpp"
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/format.hpp"
#include "Http.hpp"
#include "libslic3r/AppConfig.hpp"
#include "Bonjour.hpp"
#include "slic3r/GUI/BonjourDialog.hpp"

#include <boost/beast/core.hpp>
#include <boost/beast/websocket.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <cstdlib>
#include <iostream>
#include <string>

#include <fstream>
#include <nlohmann/json.hpp>
using json = nlohmann::json;
using std::to_string;

namespace beast = boost::beast;
namespace http = beast::http;
namespace websocket = beast::websocket;
namespace net = boost::asio;
using tcp = boost::asio::ip::tcp;

namespace fs = boost::filesystem;
namespace pt = boost::property_tree;

namespace Slic3r {

CrealityPrint::CrealityPrint(DynamicPrintConfig* config) : 
    m_host(get_device_api_url(config->opt_string("print_host"))),
    m_web_ui(config->opt_string("print_host_webui")),
    m_cafile(config->opt_string("printhost_cafile")),
    m_port(config->opt_string("printhost_port")),
    m_apikey(config->opt_string("printhost_apikey")),
    m_ssl_revoke_best_effort(config->opt_bool("printhost_ssl_ignore_revoke"))
{}

const char* CrealityPrint::get_name() const { return "Creality Print"; }

std::string CrealityPrint::get_device_api_url(std::string url)
{
    boost::trim(url);
    const std::string host = Http::get_host_from_url(url);
    return host.empty() ? std::string() : "http://" + host;
}

std::string CrealityPrint::get_device_webui_url(std::string url)
{
    boost::trim(url);
    if (url.empty())
        return url;

    if (!boost::algorithm::istarts_with(url, "http://") &&
        !boost::algorithm::istarts_with(url, "https://"))
        url = "http://" + url;

    const size_t scheme_end      = url.find("://");
    const size_t authority_begin = scheme_end == std::string::npos ? 0 : scheme_end + 3;
    const size_t authority_end   = url.find_first_of("/?#", authority_begin);
    const size_t end             = authority_end == std::string::npos ? url.size() : authority_end;
    const std::string authority  = url.substr(authority_begin, end - authority_begin);

    // A path indicates an intentional proxy URL. Only supply the K-series
    // reverse-proxy port for a bare printer host that has no explicit port.
    const bool has_path_separator = authority_end != std::string::npos && url[authority_end] == '/';
    const bool has_custom_path = has_path_separator && authority_end + 1 < url.size()
        && url[authority_end + 1] != '?' && url[authority_end + 1] != '#';
    bool has_port = false;
    if (!authority.empty() && authority.front() == '[') {
        const size_t bracket = authority.find(']');
        has_port = bracket != std::string::npos && bracket + 1 < authority.size() && authority[bracket + 1] == ':';
    } else {
        has_port = authority.rfind(':') != std::string::npos;
    }

    if (!has_custom_path && !has_port)
        url.insert(end, ":4408");
    if (!has_path_separator) {
        const size_t query_or_fragment = url.find_first_of("?#", authority_begin);
        url.insert(query_or_fragment == std::string::npos ? url.size() : query_or_fragment, "/");
    }
    return url;
}

std::string CrealityPrint::get_host() const {
    return m_host;
}
void  CrealityPrint::set_auth(Http& http) const
{
    http.header("Authorization", "Bearer " + m_apikey);
    if (!m_cafile.empty()) {
        http.ca_file(m_cafile);
    }
}

wxString CrealityPrint::get_test_ok_msg() const { return _(L("Connected to CrealityPrint successfully!")); }

wxString CrealityPrint::get_test_failed_msg(wxString& msg) const
{
    return GUI::format_wxstr("%s: %s", _L("Could not connect to CrealityPrint"), msg.Truncate(256));
}

bool CrealityPrint::test(wxString& msg) const
{ 
    bool res = true;
    const char* name = get_name();
    auto url = make_url("info");

    BOOST_LOG_TRIVIAL(info) << boost::format("%1%: Get version at: %2%") % name % url;
    // Here we do not have to add custom "Host" header - the url contains host filled by user and libCurl will set the header by itself.
    auto http = Http::get(std::move(url));
    set_auth(http);
    http.timeout_max(5)
        .on_error([&](std::string body, std::string error, unsigned status) {
            BOOST_LOG_TRIVIAL(error) << boost::format("%1%: Error getting version: %2%, HTTP %3%, body: `%4%`") % name % error % status %
                                            body;
            res = false;
            msg = format_error(body, error, status);
        })
        .on_complete([&, this](std::string body, unsigned) {
            BOOST_LOG_TRIVIAL(debug) << boost::format("%1%: Got version: %2%") % name % body;
            try {
                auto info = json::parse(body);
                if (info.contains("model")) {
                    m_model = info["model"].get<std::string>();
                    BOOST_LOG_TRIVIAL(info) << boost::format("%1%: Detected model: %2%") % name % m_model;
                }
            } catch (const json::exception& e) {
                BOOST_LOG_TRIVIAL(warning) << boost::format("%1%: Failed to parse /info response: %2%") % name % e.what();
            }
        })
#ifdef WIN32
        .ssl_revoke_best_effort(m_ssl_revoke_best_effort)
        .on_ip_resolve([&](std::string address) {
            // Workaround for Windows 10/11 mDNS resolve issue, where two mDNS resolves in succession fail.
            // Remember resolved address to be reused at successive REST API call.
            msg = GUI::from_u8(address);
        })
#endif // WIN32
        .perform_sync();

    return res;
}

PrintHostPostUploadActions CrealityPrint::get_post_upload_actions() const {
    return PrintHostPostUploadAction::StartPrint; 
}

bool CrealityPrint::upload(PrintHostUpload upload_data, ProgressFn prorgess_fn, ErrorFn error_fn, InfoFn info_fn) const
{   
    const char* name = get_name();
    const auto upload_filename = upload_data.upload_path.filename();
    const auto upload_parent_path = upload_data.upload_path.parent_path();
    wxString test_msg;
    if (!test(test_msg)) {
        error_fn(std::move(test_msg));
        return false;
    }

    bool res = true;
    const auto safe_upload_filename = safe_filename(upload_filename.string());
    // Only encode the URL path segment; keep the multipart filename and start-print path as the stored filename.
    auto url = make_url("upload/" + Http::url_encode(safe_upload_filename));

    auto  http = Http::post(url); // std::move(url));
    set_auth(http);
    if (!supports_multi_color_print())
        http.form_add("path", upload_parent_path.string());
    http.form_add_file("file", upload_data.source_path.string(), safe_upload_filename)

        .on_complete([&](std::string body, unsigned status) {
            BOOST_LOG_TRIVIAL(debug) << boost::format("%1%: File uploaded: HTTP %2%: %3%") % name % status % body;

            if (upload_data.post_action == PrintHostPostUploadAction::StartPrint) {
                wxString errormsg;
                if (!start_print(errormsg, safe_upload_filename, upload_data.extended_info)) {
                    error_fn(std::move(errormsg));
                    res = false;
                }
            }
        })
        .on_error([&](std::string body, std::string error, unsigned status) {
            BOOST_LOG_TRIVIAL(error) << boost::format("%1%: Error uploading file to %2%: %3%, HTTP %4%, body: `%5%`") % name % url % error %
                                            status % body;
            error_fn(format_error(body, error, status));
            res = false;
        })
        .on_progress([&](Http::Progress progress, bool& cancel) {
            prorgess_fn(std::move(progress), cancel);
            if (cancel) {
                // Upload was canceled
                BOOST_LOG_TRIVIAL(info) << name << ": Upload canceled";
                res = false;
            }
        })
#ifdef WIN32
        .ssl_revoke_best_effort(m_ssl_revoke_best_effort)
#endif
        .perform_sync();
    return res;
}

std::string CrealityPrint::make_url(const std::string &path) const
{
    if (m_host.find("http://") == 0 || m_host.find("https://") == 0) {
        if (m_host.back() == '/') {
            return (boost::format("%1%%2%") % m_host % path).str();
        } else {
            return (boost::format("%1%/%2%") % m_host % path).str();
        }
    } else {
        return (boost::format("http://%1%/%2%") % m_host % path).str();
    }
}

std::string CrealityPrint::safe_filename(const std::string &filename) const
{
    std::string safe_filename = filename;
    std::replace(safe_filename.begin(), safe_filename.end(), ' ', '_');

    return safe_filename;
}

static void ws_connect(net::io_context& ioc, websocket::stream<beast::tcp_stream>& ws,
                       const std::string& host_url, const std::string& port)
{
    std::string host = Http::get_host_from_url(host_url);

    tcp::resolver resolver{ioc};
    beast::get_lowest_layer(ws).expires_after(std::chrono::seconds(5));
    auto const results = resolver.resolve(host, port);
    beast::get_lowest_layer(ws).connect(results);
    host += ':' + std::to_string(beast::get_lowest_layer(ws).socket().remote_endpoint().port());

    ws.set_option(websocket::stream_base::decorator(
        [](websocket::request_type& req) {
            req.set(http::field::user_agent,
                std::string(BOOST_BEAST_VERSION_STRING) + " websocket-client-coro");
        }));
    ws.handshake(host, "/");

#ifdef _WIN32
    DWORD recv_timeout = 3000;
#else
    struct timeval recv_timeout = {3, 0};
#endif
    setsockopt(beast::get_lowest_layer(ws).socket().native_handle(),
               SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&recv_timeout), sizeof(recv_timeout));
}

static std::string ws_send_and_read(websocket::stream<beast::tcp_stream>& ws, const json& cmd, const std::string& expected_key, int max_reads = 20)
{
    ws.write(net::buffer(to_string(cmd)));

    for (int i = 0; i < max_reads; i++) {
        beast::flat_buffer buf;
        beast::error_code ec;
        ws.read(buf, ec);
        if (ec == net::error::would_block)
            break;
        if (ec)
            throw beast::system_error{ec};
        std::string msg = beast::buffers_to_string(buf.data());
        if (msg.find(expected_key) != std::string::npos)
            return msg;
    }
    BOOST_LOG_TRIVIAL(warning) << "CrealityPrint: No '" << expected_key << "' response after " << max_reads << " messages";
    return {};
}

void CrealityPrint::query_model() const
{
    if (!m_model.empty())
        return;

    wxString msg;
    test(msg);
}

bool CrealityPrint::supports_multi_color_print() const
{
    query_model();
    // K2-platform printers with CFS support
    return m_model == "F008"    // K2 Plus
        || m_model == "F012"    // K2 Pro
        || m_model == "F021"    // K2
        || m_model == "F022";   // SPARKX i7
}

std::string CrealityPrint::model_name() const
{
    static const std::map<std::string, std::string> names = {
        {"F008", "K2 Plus"},
        {"F012", "K2 Pro"},
        {"F021", "K2"},
        {"F022", "SPARKX i7"},
    };
    query_model();
    if (m_model.empty())
        return "unreachable";
    auto it = names.find(m_model);
    return it != names.end() ? it->second : "unknown (" + m_model + ")";
}

std::string CrealityPrint::query_boxes_info() const
{
    try {
        net::io_context ioc;
        websocket::stream<beast::tcp_stream> ws{ioc};
        ws_connect(ioc, ws, m_host, "9999");

        json boxs_query = {{"method", "get"}, {"params", {{"boxsInfo", 1}}}};
        std::string result = ws_send_and_read(ws, boxs_query, "boxsInfo");
        ws.close(websocket::close_code::normal);
        return result;
    } catch (std::exception const& e) {
        BOOST_LOG_TRIVIAL(error) << "CrealityPrint: Failed to query boxsInfo: " << e.what();
        return {};
    }
}

bool CrealityPrint::validate_cfs_file_info_response(const std::string& response,
                                                    const std::string& filename,
                                                    std::string& error)
{
    error.clear();
    try {
        const json payload = json::parse(response);
        if (!payload.contains("retGcodeFileInfo2") || !payload["retGcodeFileInfo2"].is_array()) {
            error = "The K2 did not return its G-code metadata index.";
            return false;
        }

        const json* file_info = nullptr;
        for (const auto& item : payload["retGcodeFileInfo2"]) {
            if (item.value("name", std::string()) == filename) {
                file_info = &item;
                break;
            }
        }
        if (file_info == nullptr) {
            error = "The K2 did not index the uploaded G-code file.";
            return false;
        }
        if (!file_info->value("validation_completed", false)) {
            error = "The K2 has not finished validating the uploaded G-code file.";
            return false;
        }
        if (file_info->value("material", std::string()).empty() ||
            file_info->value("materialColors", std::string()).empty() ||
            file_info->value("materialIds", std::string()).empty() ||
            file_info->value("printer_model", std::string()).empty()) {
            error = "The K2 could not read the filament metadata required for CFS printing.";
            return false;
        }

        const std::string match = file_info->value("match", std::string());
        static const std::regex confirmed_mapping(R"(T[0-9]+[A-Z]=T[0-9]+[A-Z])");
        if (!std::regex_search(match, confirmed_mapping)) {
            error = "The K2 did not confirm a usable CFS filament mapping.";
            return false;
        }
        return true;
    } catch (const json::exception& e) {
        error = std::string("The K2 returned invalid G-code metadata: ") + e.what();
        return false;
    }
}

bool CrealityPrint::start_print(wxString &msg, const std::string &filename, const std::map<std::string, std::string>& extended_info) const
{
    try {
        const std::string gcode_path = "/mnt/UDISK/printer_data/gcodes/" + filename;

        net::io_context ioc;
        websocket::stream<beast::tcp_stream> ws{ioc};
        ws_connect(ioc, ws, m_host, "9999");

        if (supports_multi_color_print()) {
            // Build colorMatch list from the mapping provided by the dialog
            bool use_spool_holder = false;
            json color_list = json::array();
            for (int i = 0; ; i++) {
                auto it = extended_info.find("colorMatch_" + std::to_string(i));
                if (it == extended_info.end())
                    break;
                // Value format: "toolId\ttype\tcolor\tboxId\tmaterialId"
                auto val = it->second;
                std::vector<std::string> parts;
                std::istringstream iss(val);
                std::string part;
                while (std::getline(iss, part, '\t'))
                    parts.push_back(part);
                if (parts.size() >= 5) {
                    int box_id = std::stoi(parts[3]);
                    if (box_id == 0)
                        use_spool_holder = true;
                    color_list.push_back({
                        {"id", parts[0]},
                        {"type", parts[1]},
                        {"color", parts[2]},
                        {"boxId", box_id},
                        {"materialId", std::stoi(parts[4])}
                    });
                }
            }

            int enable_self_test = 0;
            {
                auto it = extended_info.find("enableSelfTest");
                if (it != extended_info.end())
                    enable_self_test = std::stoi(it->second);
            }

            if (use_spool_holder) {
                json cmd = {
                    {"method", "set"},
                    {"params", {
                        {"opGcodeFile", "printprt:" + gcode_path},
                        {"enableSelfTest", enable_self_test}
                    }}
                };
                ws.write(net::buffer(to_string(cmd)));
            } else {
                if (color_list.empty()) {
                    msg = _L("No CFS filament mapping was provided. The printer was not started.");
                    return false;
                }

                json color_match = {
                    {"method", "set"},
                    {"params", {
                        {"colorMatch", {
                            {"path", gcode_path},
                            {"list", color_list}
                        }}
                    }}
                };
                ws.write(net::buffer(to_string(color_match)));

                json metadata_query = {
                    {"method", "get"},
                    {"params", {
                        {"reqGcodeFile", 1},
                        {"reqGcodeList", 1}
                    }}
                };
                std::string validation_error;
                bool metadata_valid = false;
                for (int attempt = 0; attempt < 5 && !metadata_valid; ++attempt) {
                    const std::string metadata_response =
                        ws_send_and_read(ws, metadata_query, "retGcodeFileInfo2", 40);
                    metadata_valid = !metadata_response.empty() &&
                        validate_cfs_file_info_response(metadata_response, filename, validation_error);
                    if (!metadata_valid && attempt < 4)
                        std::this_thread::sleep_for(std::chrono::milliseconds(250));
                }
                if (!metadata_valid) {
                    if (validation_error.empty())
                        validation_error = "The K2 did not confirm the uploaded G-code metadata.";
                    BOOST_LOG_TRIVIAL(error) << "CrealityPrint: Refusing CFS start for " << filename
                                             << ": " << validation_error;
                    msg = wxString::FromUTF8(validation_error) +
                          _L(" Reslice with the current TinManX1 build and verify the filament mapping; the printer was not started.");
                    return false;
                }

                BOOST_LOG_TRIVIAL(info) << "CrealityPrint: K2 validated CFS metadata and mapping for "
                                        << filename << " (" << color_list.size() << " mapping entries)";

                json multi_color_print = {
                    {"method", "set"},
                    {"params", {
                        {"multiColorPrint", {
                            {"gcode", gcode_path},
                            {"enableSelfTest", enable_self_test}
                        }}
                    }}
                };
                ws.write(net::buffer(to_string(multi_color_print)));
            }
        } else {
            json cmd = {
                {"method", "set"},
                {"params", {
                    {"opGcodeFile", "printprt:/usr/data/printer_data/gcodes/" + filename}
                }}
            };
            ws.write(net::buffer(to_string(cmd)));

            // K1-family firmware closes the WebSocket right after accepting the
            // start command, so a blocking read here surfaces a benign
            // "End of file [asio.misc:2]" even though the print already started
            // (the command is delivered by write()). Read best-effort, ignore errors.
            beast::flat_buffer buffer;
            beast::error_code  read_ec;
            ws.read(buffer, read_ec);
        }

        // Same reason: the printer may have already closed the connection. A close
        // error here is not a failure — the start command was sent above.
        beast::error_code close_ec;
        ws.close(websocket::close_code::normal, close_ec);
        return true;
    } catch(std::exception const& e) {
        BOOST_LOG_TRIVIAL(error) << "CrealityPrint: Error starting print: " << e.what();
        msg = wxString::FromUTF8(e.what());
        return false;
    }
}

}
