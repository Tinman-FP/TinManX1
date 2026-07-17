#include "MultiMachineManagerPage.hpp"
#include "GUI_App.hpp"
#include "MainFrame.hpp"

#include "DeviceCore/DevManager.h"
#include "libslic3r/PresetBundle.hpp"
#include "../Utils/NetworkAgentFactory.hpp"
#include "../Utils/Http.hpp"

#include <nlohmann/json.hpp>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/algorithm/string.hpp>
#include <boost/log/trivial.hpp>
#include <algorithm>
#include <cmath>
#include <set>

namespace Slic3r {
namespace GUI {

namespace {

constexpr int MULTI_DEVICE_STATUS_TIMER_ID = wxID_HIGHEST + 613;
constexpr auto MULTI_DEVICE_STATUS_TTL = std::chrono::seconds(20);

struct ProbeTarget
{
    std::string dev_id;
    std::string dev_name;
    std::string dev_ip;
    std::string printer_type;
    std::string access_code;
};

struct ProbeResult
{
    bool online{ false };
    int state_device{ 9 };
    std::string task_name;
    std::string stage_text;
    int task_progress{ -1 };
    int left_time{ -1 };
};

static std::string trim_copy(std::string value)
{
    boost::algorithm::trim(value);
    return value;
}

static std::string strip_trailing_slashes(std::string value)
{
    while (!value.empty() && value.back() == '/')
        value.pop_back();
    return value;
}

static std::string ensure_http_url(std::string value)
{
    value = trim_copy(value);
    if (value.empty())
        return value;
    if (!boost::algorithm::istarts_with(value, "http://") && !boost::algorithm::istarts_with(value, "https://"))
        value = "http://" + value;
    return strip_trailing_slashes(value);
}

static std::string authority_from_url(std::string value)
{
    value = trim_copy(value);
    if (boost::algorithm::istarts_with(value, "http://"))
        value = value.substr(7);
    else if (boost::algorithm::istarts_with(value, "https://"))
        value = value.substr(8);

    const size_t slash = value.find('/');
    if (slash != std::string::npos)
        value = value.substr(0, slash);
    return value;
}

static std::string host_from_address(const std::string& address)
{
    std::string authority = authority_from_url(address);
    if (!authority.empty() && authority.front() == '[') {
        const size_t end = authority.find(']');
        if (end != std::string::npos)
            return authority.substr(1, end - 1);
    }
    const size_t colon = authority.find(':');
    return colon == std::string::npos ? authority : authority.substr(0, colon);
}

static bool address_has_port(const std::string& address)
{
    const std::string authority = authority_from_url(address);
    if (authority.empty())
        return false;
    if (!authority.empty() && authority.front() == '[')
        return authority.find("]:") != std::string::npos;
    return authority.find(':') != std::string::npos;
}

static bool address_matches_machine(const std::string& address, const ProbeTarget& target)
{
    if (address.empty())
        return false;

    const std::string address_authority = authority_from_url(address);
    const std::string address_host = host_from_address(address);
    const std::string ip_authority = authority_from_url(target.dev_ip);
    const std::string id_authority = authority_from_url(target.dev_id);

    return (!target.dev_ip.empty() && (address == target.dev_ip || address_authority == ip_authority || address_host == host_from_address(target.dev_ip))) ||
           (!target.dev_id.empty() && (address == target.dev_id || address_authority == id_authority || address_host == host_from_address(target.dev_id)));
}

static void add_unique(std::vector<std::string>& values, const std::string& value)
{
    const std::string normalized = ensure_http_url(value);
    if (normalized.empty())
        return;
    if (std::find(values.begin(), values.end(), normalized) == values.end())
        values.push_back(normalized);
}

static bool looks_moonrakerish(const ProbeTarget& target)
{
    const std::string key = target.dev_name + " " + target.printer_type + " " + target.dev_id;
    return boost::algorithm::icontains(key, "qidi") ||
           boost::algorithm::icontains(key, "snapmaker") ||
           boost::algorithm::icontains(key, "ratrig") ||
           boost::algorithm::icontains(key, "rat rig") ||
           boost::algorithm::icontains(key, "v-core") ||
           boost::algorithm::icontains(key, "creality") ||
           boost::algorithm::icontains(key, "k2") ||
           boost::algorithm::icontains(key, "sovol") ||
           boost::algorithm::icontains(key, "klipper") ||
           boost::algorithm::icontains(key, "moonraker");
}

static std::vector<std::string> configured_urls_for_target(const ProbeTarget& target)
{
    std::vector<std::string> urls;
    PresetBundle* bundle = wxGetApp().preset_bundle;
    if (!bundle)
        return urls;

    auto add_from_config = [&](const DynamicPrintConfig& cfg) {
        const std::string print_host = cfg.has("print_host") ? cfg.opt_string("print_host") : std::string();
        const std::string print_host_webui = cfg.has("print_host_webui") ? cfg.opt_string("print_host_webui") : std::string();
        if (address_matches_machine(print_host, target)) {
            add_unique(urls, print_host);
            add_unique(urls, print_host_webui);
        } else if (address_matches_machine(print_host_webui, target)) {
            add_unique(urls, print_host_webui);
            add_unique(urls, print_host);
        }
    };

    for (const PhysicalPrinter& printer : bundle->physical_printers)
        add_from_config(printer.config);
    for (const Preset& printer : bundle->printers)
        add_from_config(printer.config);

    return urls;
}

static std::vector<std::string> probe_candidate_base_urls(const ProbeTarget& target)
{
    std::vector<std::string> urls = configured_urls_for_target(target);

    const std::string preferred = target.dev_ip.empty() ? target.dev_id : target.dev_ip;
    add_unique(urls, preferred);

    const std::string host = host_from_address(preferred);
    if (!host.empty() && !address_has_port(preferred) && looks_moonrakerish(target)) {
        add_unique(urls, host + ":7125");
        add_unique(urls, host + ":4408");
    }

    return urls;
}

static std::string join_url(const std::string& base_url, const std::string& path)
{
    if (base_url.empty())
        return path;
    if (path.empty())
        return base_url;

    const bool base_slash = base_url.back() == '/';
    const bool path_slash = path.front() == '/';
    if (base_slash && path_slash)
        return base_url + path.substr(1);
    if (!base_slash && !path_slash)
        return base_url + "/" + path;
    return base_url + path;
}

static bool fetch_json(const std::string& url, const std::string& api_key, nlohmann::json& out, std::string& error)
{
    std::string response_body;
    bool success = false;
    std::string http_error;

    auto http = Http::get(url);
    if (!api_key.empty())
        http.header("X-Api-Key", api_key);

    http.timeout_connect(2)
        .timeout_max(4)
        .on_complete([&](std::string body, unsigned status) {
            if (status >= 200 && status < 300) {
                response_body = std::move(body);
                success = true;
            } else {
                http_error = "HTTP " + std::to_string(status);
            }
        })
        .on_error([&](std::string body, std::string err, unsigned status) {
            (void) body;
            http_error = err.empty() ? "HTTP request failed" : err;
            if (status > 0)
                http_error += " (HTTP " + std::to_string(status) + ")";
        })
        .perform_sync();

    if (!success) {
        error = http_error.empty() ? "Connection failed" : http_error;
        return false;
    }

    out = nlohmann::json::parse(response_body, nullptr, false, true);
    if (out.is_discarded()) {
        error = "Invalid JSON response";
        return false;
    }
    return true;
}

static bool fetch_reachable(const std::string& url, const std::string& api_key, std::string& error)
{
    bool success = false;
    std::string http_error;

    auto http = Http::get(url);
    if (!api_key.empty())
        http.header("X-Api-Key", api_key);

    http.timeout_connect(2)
        .timeout_max(4)
        .size_limit(65536)
        .on_complete([&](std::string body, unsigned status) {
            (void) body;
            if (status >= 200 && status < 400) {
                success = true;
            } else {
                http_error = "HTTP " + std::to_string(status);
            }
        })
        .on_error([&](std::string body, std::string err, unsigned status) {
            (void) body;
            http_error = err.empty() ? "HTTP request failed" : err;
            if (status > 0)
                http_error += " (HTTP " + std::to_string(status) + ")";
        })
        .perform_sync();

    if (!success)
        error = http_error.empty() ? "Connection failed" : http_error;
    return success;
}

static int multi_device_state_from_moonraker_state(std::string state)
{
    boost::algorithm::to_lower(state);
    if (state == "printing")
        return 3;
    if (state == "paused")
        return 4;
    if (state == "complete")
        return 1;
    if (state == "error" || state == "cancelled")
        return 2;
    if (state == "standby" || state == "ready")
        return 0;
    return 8;
}

static std::string stage_text_from_state(int state_device)
{
    switch (state_device) {
    case 0: return "Idle";
    case 1: return "Printing Finish";
    case 2: return "Printing Failed";
    case 3: return "Printing";
    case 4: return "Printing Pause";
    case 5: return "Prepare";
    case 6: return "Slicing";
    case 8: return "Online";
    case 9: return "Offline";
    default: return "Syncing";
    }
}

static int json_int(const nlohmann::json& obj, const char* key, int fallback = 0)
{
    auto it = obj.find(key);
    if (it == obj.end())
        return fallback;
    if (it->is_number_integer() || it->is_number_unsigned())
        return it->get<int>();
    if (it->is_number_float())
        return static_cast<int>(std::round(it->get<double>()));
    return fallback;
}

static double json_double(const nlohmann::json& obj, const char* key, double fallback = 0.0)
{
    auto it = obj.find(key);
    if (it == obj.end() || !it->is_number())
        return fallback;
    return it->get<double>();
}

static std::string json_string(const nlohmann::json& obj, const char* key)
{
    auto it = obj.find(key);
    if (it == obj.end() || !it->is_string())
        return {};
    return it->get<std::string>();
}

static bool parse_moonraker_status(const nlohmann::json& root, ProbeResult& result)
{
    if (!root.contains("result") || !root["result"].contains("status"))
        return false;

    const auto& status = root["result"]["status"];
    if (!status.is_object())
        return false;

    const auto print_stats_it = status.find("print_stats");
    if (print_stats_it == status.end() || !print_stats_it->is_object())
        return false;

    const auto& print_stats = *print_stats_it;
    result.online = true;
    result.state_device = multi_device_state_from_moonraker_state(json_string(print_stats, "state"));
    result.task_name = json_string(print_stats, "filename");
    result.stage_text = stage_text_from_state(result.state_device);

    double progress = -1.0;
    if (auto it = status.find("virtual_sdcard"); it != status.end() && it->is_object())
        progress = json_double(*it, "progress", -1.0);
    if (progress < 0.0) {
        if (auto it = status.find("display_status"); it != status.end() && it->is_object())
            progress = json_double(*it, "progress", -1.0);
    }
    if (progress >= 0.0) {
        if (progress <= 1.0)
            progress *= 100.0;
        result.task_progress = std::clamp(static_cast<int>(std::round(progress)), 0, 100);
    }

    const double print_duration = json_double(print_stats, "print_duration", 0.0);
    if (result.task_progress > 0 && result.task_progress < 100 && print_duration > 0.0) {
        result.left_time = static_cast<int>(std::round(print_duration * (100.0 - result.task_progress) / result.task_progress));
    }

    if (result.task_name.empty() && result.state_device > 2 && result.state_device < 7)
        result.task_name = "Active print";

    return true;
}

static ProbeResult probe_target_status(const ProbeTarget& target)
{
    ProbeResult result;
    const auto urls = probe_candidate_base_urls(target);
    if (urls.empty()) {
        result.online = false;
        result.state_device = 9;
        result.stage_text = "Offline";
        return result;
    }

    for (const std::string& base_url : urls) {
        std::string error;
        nlohmann::json status_json;
        if (fetch_json(join_url(base_url, "/printer/objects/query?print_stats&virtual_sdcard&display_status&extruder&heater_bed&toolhead&webhooks"),
                       target.access_code, status_json, error) &&
            parse_moonraker_status(status_json, result)) {
            BOOST_LOG_TRIVIAL(info) << "MultiDeviceStatus: " << target.dev_name << " live status from " << base_url;
            return result;
        }

        nlohmann::json info_json;
        if (fetch_json(join_url(base_url, "/server/info"), target.access_code, info_json, error)) {
            result.online = true;
            result.state_device = 8;
            result.stage_text = "Online";
            BOOST_LOG_TRIVIAL(info) << "MultiDeviceStatus: " << target.dev_name << " reachable via " << base_url;
            return result;
        }

        // Non-Moonraker firmwares often serve only a web UI. Prove reachability,
        // but do not invent print progress when the status API is not available.
        if (fetch_reachable(base_url, target.access_code, error)) {
            result.online = true;
            result.state_device = 8;
            result.stage_text = "Online";
            BOOST_LOG_TRIVIAL(info) << "MultiDeviceStatus: " << target.dev_name << " generic HTTP reachable via " << base_url;
            return result;
        }

        BOOST_LOG_TRIVIAL(debug) << "MultiDeviceStatus: probe failed for " << target.dev_name
                                 << " at " << base_url << ": " << error;
    }

    result.online = false;
    result.state_device = 9;
    result.stage_text = "Offline";
    return result;
}

} // namespace

static bool is_bambu_multi_device_machine(const MachineObject* obj)
{
    if (obj == nullptr)
        return false;

    return obj->is_series_x() || obj->is_series_p() || obj->is_series_n() || obj->is_series_o() ||
           obj->printer_type == "O1D" || boost::algorithm::istarts_with(obj->printer_type, "BL-");
}

static bool should_subscribe_multi_device_machine(const MachineObject* obj)
{
    auto* agent = wxGetApp().getAgent();
    if (!agent || !agent->get_printer_agent())
        return false;

    const std::string current_agent = agent->get_printer_agent()->get_agent_info().id;
    if (current_agent == BBL_PRINTER_AGENT_ID)
        return is_bambu_multi_device_machine(obj);

    return false;
}

MultiMachineItem::MultiMachineItem(wxWindow* parent, MachineObject* obj)
    : DeviceItem(parent, obj)
{
    SetBackgroundColour(*wxWHITE);
    SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    SetMaxSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));

    Bind(wxEVT_PAINT, &MultiMachineItem::paintEvent, this);
    Bind(wxEVT_ENTER_WINDOW, &MultiMachineItem::OnEnterWindow, this);
    Bind(wxEVT_LEAVE_WINDOW, &MultiMachineItem::OnLeaveWindow, this);
    Bind(wxEVT_LEFT_DOWN, &MultiMachineItem::OnLeftDown, this);
    Bind(wxEVT_MOTION, &MultiMachineItem::OnMove, this);
    Bind(EVT_MULTI_DEVICE_VIEW, [obj](auto& e) {
        auto* mainframe = wxGetApp().mainframe;
        mainframe->jump_to_monitor(obj->get_dev_id());
    });
    wxGetApp().UpdateDarkUIWin(this);
}

void MultiMachineItem::OnEnterWindow(wxMouseEvent& evt)
{
    m_hover = true;
    Refresh();
}

void MultiMachineItem::OnLeaveWindow(wxMouseEvent& evt)
{
    m_hover = false;
    Refresh();
}

void MultiMachineItem::OnLeftDown(wxMouseEvent& evt)
{
    int left = FromDIP(DEVICE_LEFT_PADDING_LEFT +
        DEVICE_LEFT_DEV_NAME +
        DEVICE_LEFT_PRO_NAME +
        DEVICE_LEFT_PRO_INFO);
    auto mouse_pos = ClientToScreen(evt.GetPosition());
    auto item = this->ClientToScreen(wxPoint(0, 0));

    if (mouse_pos.x > (item.x + left) &&
        mouse_pos.x < (item.x + left + FromDIP(90)) &&
        mouse_pos.y > item.y &&
        mouse_pos.y < (item.y + DEVICE_ITEM_MAX_HEIGHT)) {
        post_event(wxCommandEvent(EVT_MULTI_DEVICE_VIEW));
    }
}

void MultiMachineItem::OnMove(wxMouseEvent& evt)
{
    int left = FromDIP(DEVICE_LEFT_PADDING_LEFT +
        DEVICE_LEFT_DEV_NAME +
        DEVICE_LEFT_PRO_NAME +
        DEVICE_LEFT_PRO_INFO);

    auto mouse_pos = ClientToScreen(evt.GetPosition());
    auto item = this->ClientToScreen(wxPoint(0, 0));

    if (mouse_pos.x > (item.x + left) &&
        mouse_pos.x < (item.x + left + FromDIP(90)) &&
        mouse_pos.y > item.y &&
        mouse_pos.y < (item.y + DEVICE_ITEM_MAX_HEIGHT)) {
        SetCursor(wxCURSOR_HAND);
    }
    else {
        SetCursor(wxCURSOR_ARROW);
    }
}

void MultiMachineItem::paintEvent(wxPaintEvent& evt)
{
    wxPaintDC dc(this);
    render(dc);
}

void MultiMachineItem::render(wxDC& dc)
{
#ifdef __WXMSW__
    wxSize     size = GetSize();
    wxMemoryDC memdc;
    wxBitmap   bmp(size.x, size.y);
    memdc.SelectObject(bmp);
    memdc.Blit({ 0, 0 }, size, &dc, { 0, 0 });

    {
        wxGCDC dc2(memdc);
        doRender(dc2);
    }

    memdc.SelectObject(wxNullBitmap);
    dc.DrawBitmap(bmp, 0, 0);
#else
    doRender(dc);
#endif
}

void MultiMachineItem::DrawTextWithEllipsis(wxDC& dc, const wxString& text, int maxWidth, int left, int top) {
    wxSize size = GetSize();
    wxFont font = dc.GetFont();

    wxSize textSize = dc.GetTextExtent(text);
    dc.SetTextForeground(StateColor::darkModeColorFor(wxColour(50, 58, 61)));
    int textWidth = textSize.GetWidth();

    if (textWidth > maxWidth) {
        wxString truncatedText = text;
        int ellipsisWidth = dc.GetTextExtent("...").GetWidth();
        int numChars = text.length();

        for (int i = numChars - 1; i >= 0; --i) {
            truncatedText = text.substr(0, i) + "...";
            int truncatedWidth = dc.GetTextExtent(truncatedText).GetWidth();

            if (truncatedWidth <= maxWidth - ellipsisWidth) {
                break;
            }
        }

        if (top == 0) {
            dc.DrawText(truncatedText, left, (size.y - textSize.y) / 2);
        }
        else {
            dc.DrawText(truncatedText, left, (size.y - textSize.y) / 2 - top);
        }

    }
    else {
        if (top == 0) {
            dc.DrawText(text, left, (size.y - textSize.y) / 2);
        }
        else {
            dc.DrawText(text, left, (size.y - textSize.y) / 2 - top);
        }
    }
}

void MultiMachineItem::doRender(wxDC& dc)
{
    wxSize size = GetSize();
    dc.SetPen(wxPen(*wxBLACK));

    int left = FromDIP(DEVICE_LEFT_PADDING_LEFT);

    if (obj_) {
        //dev name
        wxString dev_name = wxString::FromUTF8(obj_->get_dev_name());
        const bool show_offline = state_has_live_status ? state_device == 9 : !state_online;
        if (show_offline) {
            dev_name = dev_name + "(" + _L("Offline") + ")";
        }
        dc.SetFont(Label::Body_13);
        DrawTextWithEllipsis(dc, dev_name, FromDIP(DEVICE_LEFT_DEV_NAME), left);
        left += FromDIP(DEVICE_LEFT_DEV_NAME);

        //project name
        wxString project_name = _L("No task");
        if (!state_task_name.empty() && state_device > 2 && state_device < 7) {
            project_name = wxString::Format("%s", GUI::from_u8(state_task_name));
        }
        dc.SetFont(Label::Body_13);
        DrawTextWithEllipsis(dc, project_name, FromDIP(DEVICE_LEFT_PRO_NAME), left);
        left += FromDIP(DEVICE_LEFT_PRO_NAME);

        //state
        dc.SetFont(Label::Body_13);
        if (state_device == 0) {
            dc.SetTextForeground(*wxBLACK);
            DrawTextWithEllipsis(dc, get_state_device(), FromDIP(DEVICE_LEFT_PRO_INFO), left);
        }
        else if (state_device == 1) {
            dc.SetTextForeground(wxColour(0,174,66));
            DrawTextWithEllipsis(dc, get_state_device(), FromDIP(DEVICE_LEFT_PRO_INFO), left);
        }
        else if (state_device == 2)
        {
            dc.SetTextForeground(wxColour(208,27,27));
            DrawTextWithEllipsis(dc, get_state_device(), FromDIP(DEVICE_LEFT_PRO_INFO), left);
        }
        else if (state_device > 2 && state_device < 7) {
            dc.SetFont(Label::Body_12);
            dc.SetTextForeground(wxColour(0, 150, 136));
            if (state_task_progress >= 0) {
                //wxString layer_info = wxString::Format(_L("Layer: %d/%d"), obj_->curr_layer, obj_->total_layers);
                wxString progress_info = wxString::Format("%d", state_task_progress);
                wxString left_time = wxString::Format("%s", get_left_time(state_left_time));

                DrawTextWithEllipsis(dc, progress_info + "%  |  " + left_time, FromDIP(DEVICE_LEFT_PRO_INFO), left, FromDIP(10));


                dc.SetPen(wxPen(wxColour(233,233,233)));
                dc.SetBrush(wxBrush(wxColour(233,233,233)));
                dc.DrawRoundedRectangle(left, FromDIP(30), FromDIP(DEVICE_LEFT_PRO_INFO), FromDIP(10), 2);

                dc.SetPen(wxPen(wxColour(0, 150, 136)));
                dc.SetBrush(wxBrush(wxColour(0, 150, 136)));
                dc.DrawRoundedRectangle(left, FromDIP(30), FromDIP(DEVICE_LEFT_PRO_INFO) * (static_cast<float>(state_task_progress) / 100.0f), FromDIP(10), 2);
            }
            else {
                DrawTextWithEllipsis(dc, state_stage_text.empty() ? get_state_device() : GUI::from_u8(state_stage_text), FromDIP(DEVICE_LEFT_PRO_INFO), left);
            }

        }
        else {
            dc.SetTextForeground(*wxBLACK);
            DrawTextWithEllipsis(dc, get_state_device(), FromDIP(DEVICE_LEFT_PRO_INFO), left);
        }

        left += FromDIP(DEVICE_LEFT_PRO_INFO);

        //button
        dc.SetPen(wxPen(wxColour(38, 46, 48)));
        dc.SetBrush(wxBrush(wxColour(*wxWHITE)));
        dc.DrawRoundedRectangle(left, (size.y - FromDIP(38)) / 2, FromDIP(90), FromDIP(38), 6);
        dc.SetFont(Label::Body_14);
        dc.SetTextForeground(*wxBLACK);
        dc.DrawText(_L("View"),left + FromDIP(90) / 2 - dc.GetTextExtent(_L("View")).x / 2, (size.y -dc.GetTextExtent(_L("View")).y) / 2);

    }

    if (m_hover) {
        dc.SetPen(wxPen(wxColour(0, 150, 136)));
        dc.SetBrush(*wxTRANSPARENT_BRUSH);
        dc.DrawRoundedRectangle(0, 0, size.x, size.y, 3);
    }
}

void MultiMachineItem::post_event(wxCommandEvent&& event)
{
    event.SetEventObject(this);
    event.SetString(obj_->get_dev_id());
    event.SetInt(state_selected);
    wxPostEvent(this, event);
}

void MultiMachineItem::DoSetSize(int x, int y, int width, int height, int sizeFlags /*= wxSIZE_AUTO*/)
{
    wxWindow::DoSetSize(x, y, width, height, sizeFlags);
}

wxString MultiMachineItem::get_left_time(int mc_left_time)
{
    // update gcode progress
    std::string left_time;
    wxString    left_time_text = _L("N/A");

    try {
        left_time = get_bbl_monitor_time_dhm(mc_left_time);
    }
    catch (...) {
        ;
    }

    if (!left_time.empty()) left_time_text = wxString::Format("-%s", left_time);
    return left_time_text;
}


MultiMachineManagerPage::MultiMachineManagerPage(wxWindow* parent)
    : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxTAB_TRAVERSAL)
{
#ifdef __WINDOWS__
    SetDoubleBuffered(true);
#endif //__WINDOWS__
    SetBackgroundColour(wxColour(0xEEEEEE));
    m_main_panel = new wxPanel(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxTAB_TRAVERSAL);
    m_main_panel->SetBackgroundColour(*wxWHITE);
    m_main_sizer = new wxBoxSizer(wxVERTICAL);

    StateColor head_bg(
        std::pair<wxColour, int>(TABLE_HEAD_PRESSED_COLOUR, StateColor::Pressed),
        std::pair<wxColour, int>(TABLE_HEAR_NORMAL_COLOUR, StateColor::Normal)
    );

    //edit prints
    auto sizer_button_printer = new wxBoxSizer(wxHORIZONTAL);
    sizer_button_printer->SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_button_edit = new Button(m_main_panel, _L("Edit Printers"));
    m_button_edit->SetStyle(ButtonStyle::Confirm, ButtonType::Window);

    m_button_edit->Bind(wxEVT_BUTTON, [this](wxCommandEvent& evt) {
        MultiMachinePickPage dlg;
        dlg.ShowModal();
        refresh_user_device();
        evt.Skip();
    });

    sizer_button_printer->Add( 0, 0, 1, wxEXPAND, 5 );
    sizer_button_printer->Add(m_button_edit, 0, wxALIGN_CENTER, 0);

    m_table_head_panel = new wxPanel(m_main_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize);
    m_table_head_panel->SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_table_head_panel->SetMaxSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_table_head_panel->SetBackgroundColour(TABLE_HEAR_NORMAL_COLOUR);
    m_table_head_sizer = new wxBoxSizer(wxHORIZONTAL);

    m_printer_name = new Button(m_table_head_panel, _L("Device Name"), "toolbar_double_directional_arrow", wxNO_BORDER, ICON_SINGLE_SIZE);
    m_printer_name->SetBackgroundColor(head_bg);
    m_printer_name->SetFont(TABLE_HEAD_FONT);
    m_printer_name->SetCornerRadius(0);
    m_printer_name->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_printer_name->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_printer_name->SetCenter(false);
    m_printer_name->Bind(wxEVT_ENTER_WINDOW, [&](wxMouseEvent& evt) {
        SetCursor(wxCURSOR_HAND);
        });
    m_printer_name->Bind(wxEVT_LEAVE_WINDOW, [&](wxMouseEvent& evt) {
        SetCursor(wxCURSOR_ARROW);
        });
    m_printer_name->Bind(wxEVT_LEFT_DOWN, [this](wxMouseEvent& evt) {
        device_dev_name_big = !device_dev_name_big;
        auto sortcb = [this](ObjState s1, ObjState s2) {
            return device_dev_name_big ? s1.state_dev_name > s2.state_dev_name : s1.state_dev_name < s2.state_dev_name;
        };
        this->m_sort.set_role(sortcb, SortItem::SR_MACHINE_NAME, device_dev_name_big);
        this->refresh_user_device();
    });


    m_task_name = new Button(m_table_head_panel, _L("Task Name"), "", wxNO_BORDER, ICON_SINGLE_SIZE);
    m_task_name->SetBackgroundColor(TABLE_HEAR_NORMAL_COLOUR);
    m_task_name->SetFont(TABLE_HEAD_FONT);
    m_task_name->SetCornerRadius(0);
    m_task_name->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_task_name->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_task_name->SetCenter(false);



    m_status = new Button(m_table_head_panel, _L("Device Status"), "toolbar_double_directional_arrow", wxNO_BORDER, ICON_SINGLE_SIZE);
    m_status->SetBackgroundColor(head_bg);
    m_status->SetFont(TABLE_HEAD_FONT);
    m_status->SetCornerRadius(0);
    m_status->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_PRO_INFO), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_status->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_PRO_INFO), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_status->SetCenter(false);
    m_status->Bind(wxEVT_ENTER_WINDOW, [&](wxMouseEvent& evt) {
        SetCursor(wxCURSOR_HAND);
        });
    m_status->Bind(wxEVT_LEAVE_WINDOW, [&](wxMouseEvent& evt) {
        SetCursor(wxCURSOR_ARROW);
        });
    m_status->Bind(wxEVT_LEFT_DOWN, [this](wxMouseEvent& evt) {
        device_state_big = !device_state_big;
        auto sortcb = [this](ObjState s1, ObjState s2) {
            return device_state_big ? s1.state_device > s2.state_device : s1.state_device < s2.state_device;
            };
        this->m_sort.set_role(sortcb, SortItem::SortRule::SR_MACHINE_STATE, device_state_big);
        this->refresh_user_device();
    });


    m_action = new Button(m_table_head_panel, _L("Actions"), "", wxNO_BORDER, ICON_SINGLE_SIZE, false);
    m_action->SetBackgroundColor(TABLE_HEAR_NORMAL_COLOUR);
    m_action->SetFont(TABLE_HEAD_FONT);
    m_action->SetCornerRadius(0);
    m_action->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_PRO_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_action->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_PRO_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_action->SetCenter(false);


    m_table_head_sizer->AddSpacer(FromDIP(DEVICE_LEFT_PADDING_LEFT));
    m_table_head_sizer->Add(m_printer_name, 0, wxALIGN_CENTER_VERTICAL, 0);
    m_table_head_sizer->Add(m_task_name, 0, wxALIGN_CENTER_VERTICAL, 0);
    m_table_head_sizer->Add(m_status, 0, wxALIGN_CENTER_VERTICAL, 0);
    m_table_head_sizer->Add(m_action, 0, wxLEFT, 0);

    m_table_head_panel->SetSizer(m_table_head_sizer);
    m_table_head_panel->Layout();

    m_tip_text = new wxStaticText(m_main_panel, wxID_ANY, wxEmptyString, wxDefaultPosition, wxDefaultSize, wxALIGN_CENTER);
    m_tip_text->SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_tip_text->SetMaxSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_tip_text->SetLabel(_L("Please select the devices you would like to manage here (up to 6 devices)"));
    m_tip_text->SetForegroundColour(wxColour(50, 58, 61));
    m_tip_text->SetFont(::Label::Head_20);
    m_tip_text->Wrap(-1);

    m_button_add = new Button(m_main_panel, _L("Add"));
    m_button_add->SetStyle(ButtonStyle::Confirm, ButtonType::Window);

    m_button_add->Bind(wxEVT_BUTTON, [this](wxCommandEvent& evt) {
        MultiMachinePickPage dlg;
        dlg.ShowModal();
        refresh_user_device();
        evt.Skip();
    });

    m_machine_list = new wxScrolledWindow(m_main_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize);
    m_machine_list->SetBackgroundColour(*wxWHITE);
    m_machine_list->SetScrollRate(0, 5);
    m_machine_list->SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), 10 * FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_machine_list->SetMaxSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), 10 * FromDIP(DEVICE_ITEM_MAX_HEIGHT)));

    m_sizer_machine_list = new wxBoxSizer(wxVERTICAL);
    m_machine_list->SetSizer(m_sizer_machine_list);
    m_machine_list->Layout();

    // add flipping page
    StateColor ctrl_bg(
        std::pair<wxColour, int>(CTRL_BUTTON_PRESSEN_COLOUR, StateColor::Pressed),
        std::pair<wxColour, int>(CTRL_BUTTON_NORMAL_COLOUR, StateColor::Normal)
    );

    m_flipping_panel = new wxPanel(m_main_panel, wxID_ANY, wxDefaultPosition, wxDefaultSize);
    m_flipping_panel->SetMinSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_flipping_panel->SetMaxSize(wxSize(FromDIP(DEVICE_ITEM_MAX_WIDTH), -1));
    m_flipping_panel->SetBackgroundColour(*wxWHITE);

    m_flipping_page_sizer = new wxBoxSizer(wxHORIZONTAL);
    m_page_sizer = new wxBoxSizer(wxVERTICAL);
    btn_last_page = new Button(m_flipping_panel, "", "go_last_plate", 0, FromDIP(20));
    btn_last_page->SetMinSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_last_page->SetMaxSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_last_page->SetBackgroundColor(head_bg);
    btn_last_page->Bind(wxEVT_LEFT_DOWN, [&](wxMouseEvent& evt) {
        evt.Skip();
        if (m_current_page == 0)
            return;
        btn_last_page->Enable(false);
        btn_next_page->Enable(false);
        start_timer();
        m_current_page--;
        if (m_current_page < 0)
            m_current_page = 0;
        refresh_user_device();
        update_page_number();
    });
    st_page_number = new wxStaticText(m_flipping_panel, wxID_ANY, wxEmptyString, wxDefaultPosition, wxDefaultSize);
    btn_next_page = new Button(m_flipping_panel, "", "go_next_plate", 0, FromDIP(20));
    btn_next_page->SetMinSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_next_page->SetMaxSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_next_page->SetBackgroundColor(head_bg);
    btn_next_page->Bind(wxEVT_LEFT_DOWN, [&](wxMouseEvent& evt) {
        evt.Skip();
        if (m_current_page == m_total_page - 1)
            return;
        btn_last_page->Enable(false);
        btn_next_page->Enable(false);
        start_timer();
        m_current_page++;
        if (m_current_page > m_total_page - 1)
            m_current_page = m_total_page - 1;
        refresh_user_device();
        update_page_number();
    });

    m_page_num_input = new ::TextInput(m_flipping_panel, wxEmptyString, wxEmptyString, wxEmptyString, wxDefaultPosition, wxSize(FromDIP(50), -1), wxTE_PROCESS_ENTER);
    StateColor input_bg(std::pair<wxColour, int>(wxColour("#F0F0F1"), StateColor::Disabled), std::pair<wxColour, int>(*wxWHITE, StateColor::Enabled));
    m_page_num_input->SetBackgroundColor(input_bg);
    m_page_num_input->GetTextCtrl()->SetValue("1");
    wxTextValidator validator(wxFILTER_DIGITS);
    m_page_num_input->GetTextCtrl()->SetValidator(validator);
    m_page_num_input->GetTextCtrl()->Bind(wxEVT_TEXT_ENTER, [&](wxCommandEvent& e) {
        page_num_enter_evt();
    });

    m_page_num_enter = new Button(m_flipping_panel, _("Go"));
    m_page_num_enter->SetMinSize(wxSize(FromDIP(25), FromDIP(25)));
    m_page_num_enter->SetMaxSize(wxSize(FromDIP(25), FromDIP(25)));
    m_page_num_enter->SetBackgroundColor(ctrl_bg);
    m_page_num_enter->SetCornerRadius(FromDIP(5));
    m_page_num_enter->Bind(wxEVT_COMMAND_BUTTON_CLICKED, [&](auto& evt) {
        page_num_enter_evt();
    });

    m_flipping_page_sizer->Add(0, 0, 1, wxEXPAND, 0);
    m_flipping_page_sizer->Add(btn_last_page, 0, wxALIGN_CENTER, 0);
    m_flipping_page_sizer->Add(st_page_number, 0, wxLEFT | wxALIGN_CENTER_VERTICAL, FromDIP(5));
    m_flipping_page_sizer->Add(btn_next_page, 0, wxLEFT | wxALIGN_CENTER_VERTICAL, FromDIP(5));
    m_flipping_page_sizer->Add(m_page_num_input, 0, wxLEFT | wxALIGN_CENTER_VERTICAL, FromDIP(20));
    m_flipping_page_sizer->Add(m_page_num_enter, 0, wxLEFT | wxALIGN_CENTER_VERTICAL, FromDIP(5));
    m_page_sizer->Add(m_flipping_page_sizer, 0, wxALIGN_CENTER_HORIZONTAL, FromDIP(5));
    m_flipping_panel->SetSizer(m_page_sizer);
    m_flipping_panel->Layout();

    m_main_sizer->AddSpacer(FromDIP(16));
    m_main_sizer->Add(sizer_button_printer, 0, wxALIGN_CENTER_HORIZONTAL, 0);
     m_main_sizer->AddSpacer(FromDIP(5));
    m_main_sizer->Add(m_table_head_panel, 0, wxALIGN_CENTER_HORIZONTAL, 0);
    m_main_sizer->Add(m_tip_text, 0, wxALIGN_CENTER_HORIZONTAL | wxTOP, FromDIP(50));
    m_main_sizer->Add(m_button_add, 0, wxALIGN_CENTER_HORIZONTAL | wxTOP, FromDIP(16));
    m_main_sizer->Add(m_machine_list, 0, wxALIGN_CENTER_HORIZONTAL, 0);
    m_main_sizer->Add(m_flipping_panel, 0, wxALIGN_CENTER_HORIZONTAL, 0);
    m_main_panel->SetSizer(m_main_sizer);
    m_main_panel->Layout();
    page_sizer = new wxBoxSizer(wxVERTICAL);
    page_sizer->Add(m_main_panel, 1, wxALL | wxEXPAND, FromDIP(10)); // ORCA match margin with other tabs

    SetSizer(page_sizer);
    Layout();
    Fit();

    m_status_timer = new wxTimer(this, MULTI_DEVICE_STATUS_TIMER_ID);
    Bind(wxEVT_TIMER, &MultiMachineManagerPage::on_timer, this);
}

MultiMachineManagerPage::~MultiMachineManagerPage()
{
    if (m_status_timer) {
        m_status_timer->Stop();
        delete m_status_timer;
        m_status_timer = nullptr;
    }
    if (m_flipping_timer) {
        m_flipping_timer->Stop();
        delete m_flipping_timer;
        m_flipping_timer = nullptr;
    }
    stop_status_worker();
}

void MultiMachineManagerPage::update_page()
{
    for (int i = 0; i < m_device_items.size(); i++) {
        m_device_items[i]->sync_state();
        apply_cached_live_status(m_device_items[i]);
        m_device_items[i]->Refresh();
    }
}

void MultiMachineManagerPage::refresh_user_device(bool clear)
{
    m_sizer_machine_list->Clear(true);
    m_device_items.clear();

    if(clear) return;

    Slic3r::DeviceManager* dev = Slic3r::GUI::wxGetApp().getDeviceManager();
    if (!dev) return;

    auto all_machine = dev->get_my_machine_list();
    auto user_machine = std::map<std::string, MachineObject*>();

    //selected machine
    for (int i = 0; i < PICK_DEVICE_MAX; i++) {
        auto dev_id = wxGetApp().app_config->get("multi_devices", std::to_string(i));

        if (all_machine.count(dev_id) > 0) {
            user_machine[dev_id] = all_machine[dev_id];
        }
    }


    m_total_count = user_machine.size();

    m_state_objs.clear();
    for (auto it = user_machine.begin(); it != user_machine.end(); ++it) {
        sync_state(it->second);
    }

    //sort
    if (m_sort.rule != SortItem::SortRule::SR_None) {
        std::sort(m_state_objs.begin(), m_state_objs.end(), m_sort.get_machine_call_back());
    }

    double result = static_cast<double>(user_machine.size()) / m_count_page_item;
    m_total_page = std::ceil(result);

    std::vector<ObjState> sort_devices = extractRange(m_state_objs, m_current_page * m_count_page_item, (m_current_page + 1) * m_count_page_item - 1 );
    std::vector<std::string> subscribe_list;

    std::vector<MachineObject*> visible_machines;
    for (auto i = 0; i < sort_devices.size(); ++i) {
        auto dev_id = sort_devices[i].dev_id;

        auto machine = user_machine[dev_id];

        MultiMachineItem* di = new MultiMachineItem(m_machine_list, machine);
        apply_cached_live_status(di);
        m_device_items.push_back(di);
        m_sizer_machine_list->Add(m_device_items[i], 0, wxALL | wxEXPAND, 0);
        visible_machines.push_back(machine);

        if (should_subscribe_multi_device_machine(machine))
            subscribe_list.push_back(dev_id);
    }

    dev->subscribe_device_list(subscribe_list);
    request_status_refresh(visible_machines);

    m_tip_text->Show(m_device_items.empty());
    m_button_add->Show(m_device_items.empty());

    update_page_number();
    m_flipping_panel->Show(m_total_page > 1);
    m_sizer_machine_list->Layout();
    Layout();
}

std::vector<ObjState> MultiMachineManagerPage::extractRange(const std::vector<ObjState>& source, int start, int end) {
    std::vector<ObjState> result;

    if (start < 0 || start > end || source.size() <= 0) {
        return result;
    }

    if ( end >= source.size() ) {
        end = source.size();
    }

    auto startIter = source.begin() + start;
    auto endIter = source.begin() + end;
    result.assign(startIter, endIter);
    return result;
}

void MultiMachineManagerPage::sync_state(MachineObject* obj_)
{
    ObjState state_obj;

    if (obj_) {
        state_obj.dev_id = obj_->get_dev_id();
        state_obj.state_dev_name = obj_->get_dev_name();
        state_obj.state_device = multi_device_state_from_machine(obj_);
        CachedLiveStatus cached;
        if (!is_bambu_multi_device_machine(obj_) && cached_live_status_for(obj_->get_dev_id(), cached))
            state_obj.state_device = cached.state_device;
    }
    m_state_objs.push_back(state_obj);
}

bool MultiMachineManagerPage::cached_live_status_for(const std::string& dev_id, CachedLiveStatus& out) const
{
    std::lock_guard<std::mutex> lock(m_live_status_mutex);
    auto it = m_live_status_cache.find(dev_id);
    if (it == m_live_status_cache.end())
        return false;

    const auto age = std::chrono::steady_clock::now() - it->second.updated_at;
    if (age > MULTI_DEVICE_STATUS_TTL * 3)
        return false;

    out = it->second;
    return true;
}

bool MultiMachineManagerPage::cached_live_status_is_fresh(const std::string& dev_id) const
{
    std::lock_guard<std::mutex> lock(m_live_status_mutex);
    auto it = m_live_status_cache.find(dev_id);
    if (it == m_live_status_cache.end())
        return false;
    return std::chrono::steady_clock::now() - it->second.updated_at < MULTI_DEVICE_STATUS_TTL;
}

void MultiMachineManagerPage::apply_cached_live_status(DeviceItem* item)
{
    if (!item || !item->get_obj() || is_bambu_multi_device_machine(item->get_obj()))
        return;

    CachedLiveStatus cached;
    if (cached_live_status_for(item->get_obj()->get_dev_id(), cached)) {
        item->apply_live_status(true,
                                cached.online,
                                cached.state_device,
                                cached.task_name,
                                cached.task_progress,
                                cached.left_time,
                                cached.stage_text);
    } else {
        item->apply_live_status(true, false, 7, "", -1, -1, "Syncing");
    }
}

void MultiMachineManagerPage::request_status_refresh(const std::vector<MachineObject*>& machines)
{
    std::vector<ProbeTarget> targets;
    targets.reserve(machines.size());
    std::set<std::string> seen;

    for (MachineObject* machine : machines) {
        if (!machine || is_bambu_multi_device_machine(machine))
            continue;

        const std::string dev_id = machine->get_dev_id();
        if (dev_id.empty() || seen.count(dev_id) != 0 || cached_live_status_is_fresh(dev_id))
            continue;
        seen.insert(dev_id);

        ProbeTarget target;
        target.dev_id = dev_id;
        target.dev_name = machine->get_dev_name();
        target.dev_ip = machine->get_dev_ip();
        target.printer_type = machine->printer_type;
        target.access_code = machine->get_access_code();
        targets.push_back(std::move(target));
    }

    if (targets.empty())
        return;

    if (m_status_worker_running.exchange(true))
        return;

    if (m_status_thread.joinable())
        m_status_thread.join();

    const unsigned long long generation = ++m_status_generation;
    m_status_stop.store(false);

    m_status_thread = std::thread([this, targets = std::move(targets), generation]() {
        std::map<std::string, CachedLiveStatus> updates;

        for (const ProbeTarget& target : targets) {
            if (m_status_stop.load())
                break;

            const ProbeResult result = probe_target_status(target);
            CachedLiveStatus cached;
            cached.online = result.online;
            cached.state_device = result.state_device;
            cached.task_name = result.task_name;
            cached.stage_text = result.stage_text;
            cached.task_progress = result.task_progress;
            cached.left_time = result.left_time;
            cached.updated_at = std::chrono::steady_clock::now();
            updates[target.dev_id] = std::move(cached);
        }

        {
            std::lock_guard<std::mutex> lock(m_live_status_mutex);
            for (auto& [dev_id, status] : updates)
                m_live_status_cache[dev_id] = std::move(status);
        }

        m_status_worker_running.store(false);

        if (!m_status_stop.load() && generation == m_status_generation.load()) {
            wxGetApp().CallAfter([this, generation]() {
                if (!m_status_stop.load() && generation == m_status_generation.load())
                    refresh_user_device();
            });
        }
    });
}

void MultiMachineManagerPage::stop_status_worker()
{
    m_status_stop.store(true);
    ++m_status_generation;
    if (m_status_thread.joinable())
        m_status_thread.join();
    m_status_worker_running.store(false);
}

bool MultiMachineManagerPage::Show(bool show)
{
    if (show) {
        if (m_status_timer && !m_status_timer->IsRunning())
            m_status_timer->Start(15000);
        refresh_user_device();
    }
    else {
        if (m_status_timer)
            m_status_timer->Stop();
        Slic3r::DeviceManager* dev = Slic3r::GUI::wxGetApp().getDeviceManager();
        if (dev) {
            dev->subscribe_device_list(std::vector<std::string>());
        }
    }
    return wxPanel::Show(show);
}

void MultiMachineManagerPage::start_timer()
{
    if (m_flipping_timer) {
        m_flipping_timer->Stop();
    }
    else {
        m_flipping_timer = new wxTimer();
    }

    m_flipping_timer->SetOwner(this);
    m_flipping_timer->Start(1000);
    wxPostEvent(this, wxTimerEvent(*m_flipping_timer));
}

void MultiMachineManagerPage::update_page_number()
{
    double result = static_cast<double>(m_total_count) / m_count_page_item;
    m_total_page = std::ceil(result);

    wxString number = wxString(std::to_string(m_current_page + 1)) + " / " + wxString(std::to_string(m_total_page));
    st_page_number->SetLabel(number);
}

void MultiMachineManagerPage::on_timer(wxTimerEvent& event)
{
    if (m_status_timer && event.GetId() == m_status_timer->GetId()) {
        refresh_user_device();
        return;
    }

    m_flipping_timer->Stop();
    if (btn_last_page)
        btn_last_page->Enable(true);
    if (btn_next_page)
        btn_next_page->Enable(true);
}

void MultiMachineManagerPage::clear_page()
{

}

void MultiMachineManagerPage::page_num_enter_evt()
{
    btn_last_page->Enable(false);
    btn_next_page->Enable(false);
    start_timer();
    auto value = m_page_num_input->GetTextCtrl()->GetValue();
    long page_num = 0;
    if (value.ToLong(&page_num)) {
        if (page_num > m_total_page)
            m_current_page = m_total_page - 1;
        else if (page_num < 1)
            m_current_page = 0;
        else
            m_current_page = page_num - 1;
    }
    refresh_user_device();
    update_page_number();
}

void MultiMachineManagerPage::msw_rescale()
{
    m_printer_name->Rescale();
    m_printer_name->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_printer_name->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_task_name->Rescale();
    m_task_name->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_task_name->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_DEV_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_status->Rescale();
    m_status->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_PRO_INFO), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_status->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_PRO_INFO), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_action->Rescale();
    m_action->SetMinSize(wxSize(FromDIP(DEVICE_LEFT_PRO_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_action->SetMaxSize(wxSize(FromDIP(DEVICE_LEFT_PRO_NAME), FromDIP(DEVICE_ITEM_MAX_HEIGHT)));
    m_button_add->Rescale();
    m_button_add->SetMinSize(wxSize(FromDIP(90), FromDIP(36)));
    m_button_add->SetMaxSize(wxSize(FromDIP(90), FromDIP(36)));

    btn_last_page->Rescale();
    btn_last_page->SetMinSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_last_page->SetMaxSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_next_page->Rescale();
    btn_next_page->SetMinSize(wxSize(FromDIP(20), FromDIP(20)));
    btn_next_page->SetMaxSize(wxSize(FromDIP(20), FromDIP(20)));
    m_page_num_enter->Rescale();
    m_page_num_enter->SetMinSize(wxSize(FromDIP(25), FromDIP(25)));
    m_page_num_enter->SetMaxSize(wxSize(FromDIP(25), FromDIP(25)));

    m_button_edit->Rescale();
    m_button_edit->SetMinSize(wxSize(FromDIP(90), FromDIP(36)));
    m_button_edit->SetMaxSize(wxSize(FromDIP(90), FromDIP(36)));


    for (const auto& item : m_device_items) {
        item->Refresh();
    }

    Fit();
    Layout();
    Refresh();
}

} // namespace GUI
} // namespace Slic3r
