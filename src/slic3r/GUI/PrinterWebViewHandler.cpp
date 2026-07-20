#include "PrinterWebViewHandler.hpp"

#include "I18N.hpp"
#include "PrinterWebView.hpp"
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/Widgets/WebView.hpp"
#include "slic3r/Utils/PrintHost.hpp"
#include "libslic3r/Preset.hpp"

#include <nlohmann/json.hpp>
#include <atomic>
#include <boost/filesystem/path.hpp>
#include <thread>
#include <wx/filedlg.h>
#include <wx/string.h>

using json = nlohmann::json;

namespace Slic3r {
namespace GUI {

PrinterWebViewHandler::PrinterWebViewHandler(PrinterWebView& owner)
    : m_owner(owner)
{
}

PrinterWebViewHandler::~PrinterWebViewHandler() = default;

void PrinterWebViewHandler::on_loaded(wxWebViewEvent &evt)
{
}

void PrinterWebViewHandler::on_script_message(wxWebViewEvent &evt)
{
}

PrinterWebView& PrinterWebViewHandler::owner() const
{
    return m_owner;
}

wxWebView* PrinterWebViewHandler::browser() const
{
    return m_owner.m_browser;
}

namespace {

DynamicPrintConfig* get_active_printer_config()
{
    if (wxGetApp().preset_bundle == nullptr)
        return nullptr;

    return &wxGetApp().preset_bundle->printers.get_edited_preset().config;
}

std::string json_string(const json& node, const char* key)
{
    auto it = node.find(key);
    return (it != node.end() && it->is_string()) ? it->get<std::string>() : std::string();
}

std::string dump_json(const json& node)
{
    return node.dump(-1, ' ', false, json::error_handler_t::replace);
}

boost::filesystem::path path_from_utf8(const std::string& utf8_path)
{
#ifdef _WIN32
    const wxString wide_path = wxString::FromUTF8(utf8_path.c_str());
    return boost::filesystem::path(wide_path.ToStdWstring());
#else
    return boost::filesystem::path(utf8_path);
#endif
}

std::string filename_to_utf8(const boost::filesystem::path& path)
{
#ifdef _WIN32
    const wxString wx_filename(path.filename().c_str());
    const wxScopedCharBuffer utf8 = wx_filename.ToUTF8();
    return utf8.data() != nullptr ? std::string(utf8.data()) : std::string();
#else
    return path.filename().string();
#endif
}

class ElegooPrinterWebViewHandler final : public PrinterWebViewHandler {
public:
    explicit ElegooPrinterWebViewHandler(PrinterWebView& owner)
        : PrinterWebViewHandler(owner)
    {
    }

    ~ElegooPrinterWebViewHandler() override
    {
        stop_upload = true;
        if (upload_thread.joinable())
            upload_thread.join();
    }

    void on_script_message(wxWebViewEvent &evt) override
    {
        const wxString message = evt.GetString();
        if (message.empty())
            return;

        json root = json::parse(message.ToUTF8().data(), nullptr, false);
        if (root.is_discarded() || !root.is_object())
            return;

        std::string request_id = json_string(root, "id");
        std::string method     = json_string(root, "method");
        json        params     = root.contains("params") && root["params"].is_object() ? root["params"] : json::object();

        if (method.empty()) {
            method = json_string(root, "command");
            if (params.empty() && root.contains("data") && root["data"].is_object())
                params = root["data"];
        }

        if (method == "open" || method == "common_openurl") {
            const std::string url = json_string(params, "url").empty() ? json_string(root, "url") : json_string(params, "url");
            if (!url.empty())
                wxLaunchDefaultBrowser(url);
            if (!request_id.empty())
                send_ipc_message("response", request_id, method, 0, "success");
            return;
        }

        if (method == "upload_file") {
            handle_upload_request(request_id, method, dump_json(params));
            return;
        }

        if (method == "open_file_dialog") {
            handle_open_file_dialog_request(request_id, method, dump_json(params));
            return;
        }

        if (method == "get_sn") {
            handle_get_sn_request(request_id, method);
            return;
        }
    }

private:
    void send_ipc_message(const char* type, const std::string& request_id, const std::string& method, int code,
                          const std::string& message, const std::string& data_json = "{}")
    {
        if (browser() == nullptr)
            return;

        json body = json::object();
        body["type"] = type;
        if (!request_id.empty())
            body["id"] = request_id;
        if (!method.empty())
            body["method"] = method;

        json data = json::parse(data_json, nullptr, false);
        if (data.is_discarded())
            data = json::object();
        body["data"] = std::move(data);

        if (std::string(type) == "response") {
            body["code"] = code;
            body["message"] = message;
        }

        const wxString payload = wxString::FromUTF8(dump_json(body));
        const wxString script = "if (typeof HandleStudio === 'function') { HandleStudio(" + payload + "); } else { window.postMessage(" + payload + ", '*'); }";
        wxGetApp().CallAfter([this, script]() {
            if (browser() != nullptr)
                WebView::RunScript(browser(), script);
        });
    }

    void handle_upload_request(const std::string& request_id, const std::string& method, const std::string& params_json)
    {
        if (upload_in_progress.exchange(true)) {
            send_ipc_message("response", request_id, method, 1, "Upload already in progress");
            return;
        }

        if (upload_thread.joinable())
            upload_thread.join();

        json params = json::parse(params_json, nullptr, false);
        if (params.is_discarded())
            params = json::object();

        std::string file_path = json_string(params, "filePath");
        std::string file_name = json_string(params, "fileName");

        if (file_path.empty()) {
            upload_in_progress = false;
            send_ipc_message("response", request_id, method, 1, "Missing filePath");
            return;
        }

        // HTML IPC passes UTF-8 strings; decode explicitly to avoid Windows codepage issues.
        boost::filesystem::path source_path = path_from_utf8(file_path);
        if (file_name.empty())
            file_name = filename_to_utf8(source_path);

        DynamicPrintConfig* config = get_active_printer_config();
        std::unique_ptr<PrintHost> print_host(config == nullptr ? nullptr : PrintHost::get_print_host(config));
        if (print_host == nullptr) {
            upload_in_progress = false;
            send_ipc_message("response", request_id, method, 1, "Could not get a valid Printer Host reference");
            return;
        }

        stop_upload = false;
        upload_thread = std::thread([this, request_id, method, file_path, file_name, source_path, print_host = std::move(print_host)]() mutable {
            std::string error_message;

            PrintHostUpload upload_data;
            upload_data.use_3mf      = false;
            upload_data.post_action  = PrintHostPostUploadAction::None;
            upload_data.source_path  = source_path;
            upload_data.upload_path  = path_from_utf8(file_name);

            const bool success = print_host->upload(
                std::move(upload_data),
                [this, request_id](Http::Progress progress, bool& cancel) {
                    cancel = stop_upload.load();
                    json data = {
                        {"uploadedBytes", static_cast<uint64_t>(progress.ulnow)},
                        {"totalBytes", static_cast<uint64_t>(progress.ultotal)}
                    };
                    send_ipc_message("event", request_id, "upload_progress", 0, "", dump_json(data));
                },
                [&error_message](wxString error) {
                    error_message = error.ToUTF8().data();
                },
                [this, request_id](wxString tag, wxString status) {
                    json data = {
                        {"tag", tag.ToUTF8().data()},
                        {"status", status.ToUTF8().data()}
                    };
                    send_ipc_message("event", request_id, "upload_info", 0, "", dump_json(data));
                });

            upload_in_progress = false;

            if (success) {
                json data = {
                    {"success", true},
                    {"filePath", file_path},
                    {"fileName", file_name}
                };
                send_ipc_message("response", request_id, method, 0, "success", dump_json(data));
            } else {
                if (error_message.empty())
                    error_message = "Upload failed";
                send_ipc_message("response", request_id, method, 1, error_message);
            }
        });
    }

    void handle_open_file_dialog_request(const std::string& request_id, const std::string& method, const std::string& params_json)
    {
        json params = json::parse(params_json, nullptr, false);
        if (params.is_discarded())
            params = json::object();

        const std::string filter = json_string(params, "filter").empty() ? "All files (*.*)|*.*" : json_string(params, "filter");

        wxWindow* parent = owner().GetParent();
        if (parent == nullptr)
            parent = wxGetApp().GetTopWindow();

        wxFileDialog open_file_dialog(parent, _L("Open File"), "", "", wxString::FromUTF8(filter), wxFD_OPEN | wxFD_FILE_MUST_EXIST);

        json data = json::object();
        data["files"] = json::array();
        if (open_file_dialog.ShowModal() != wxID_CANCEL)
            data["files"].push_back(open_file_dialog.GetPath().ToUTF8().data());

        send_ipc_message("response", request_id, method, 0, "success", dump_json(data));
    }

    void handle_get_sn_request(const std::string& request_id, const std::string& method)
    {
        // Panel always calls get_sn with a 10s IPC timeout. Answer immediately from
        // dev_sn / cache — do not spawn a thread or perform HTTP (panel uses URL sn on miss).
        std::string sn;
        if (DynamicPrintConfig* config = get_active_printer_config()) {
            const std::unique_ptr<PrintHost> host(PrintHost::get_print_host(config));
            if (host)
                sn = host->get_sn();
        }
        json data = { { "sn", sn } };
        send_ipc_message("response", request_id, method, 0, "success", dump_json(data));
    }

    std::atomic<bool> upload_in_progress { false };
    std::atomic<bool> stop_upload { false };
    std::thread       upload_thread;
};

class QidiBoxPrinterWebViewHandler final : public PrinterWebViewHandler {
public:
    explicit QidiBoxPrinterWebViewHandler(PrinterWebView& owner)
        : PrinterWebViewHandler(owner)
    {
    }

    void on_loaded(wxWebViewEvent& evt) override
    {
        if (browser() == nullptr || evt.GetURL().IsEmpty())
            return;

        WebView::RunScript(browser(), wxString::FromUTF8(qidi_box_injection_script()));
    }

private:
    static const char* qidi_box_injection_script()
    {
        return R"JS(
(function () {
  'use strict';
  if (window.__tinmanQidiBoxPanelActive) {
    if (typeof window.__tinmanQidiBoxPanelRefresh === 'function') {
      window.__tinmanQidiBoxPanelRefresh();
    }
    return;
  }

  const query =
    '/printer/objects/query?' +
    'box_extras&save_variables=variables&print_stats&extruder&' +
    'filament_switch_sensor%20fila&filament_motion_sensor%20box_motion_sensor&hall_filament_width_sensor&' +
    'heater_generic%20heater_box1&temperature_sensor%20heater_temp_a_box1&temperature_sensor%20heater_temp_b_box1&' +
    'aht20_f%20heater_box1&' +
    'box_stepper%20slot0=runout_button&box_stepper%20slot1=runout_button&' +
    'box_stepper%20slot2=runout_button&box_stepper%20slot3=runout_button';

  const state = {
    selected: 0,
    dict: null,
    macros: new Set(),
    timer: null,
    busy: false
  };

  async function getJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(path + ' returned HTTP ' + response.status);
    }
    return response.json();
  }

  async function getText(path) {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(path + ' returned HTTP ' + response.status);
    }
    return response.text();
  }

  function parseQidiDictionary(text) {
    const dict = { colors: {}, filaments: {} };
    let section = '';
    let currentFila = null;

    text.split(/\r?\n/).forEach((raw) => {
      const line = raw.trim();
      if (!line || line.startsWith('#') || line.startsWith(';')) return;
      const sectionMatch = line.match(/^\[(.+)\]$/);
      if (sectionMatch) {
        section = sectionMatch[1].trim();
        const filaMatch = section.match(/^fila(\d+)$/i);
        currentFila = filaMatch ? Number(filaMatch[1]) : null;
        if (currentFila !== null && !dict.filaments[currentFila]) {
          dict.filaments[currentFila] = {};
        }
        return;
      }

      const eq = line.indexOf('=');
      if (eq < 0) return;
      const key = line.slice(0, eq).trim();
      const value = line.slice(eq + 1).trim();

      if (section === 'colordict') {
        const idx = Number(key);
        if (Number.isFinite(idx) && value) {
          dict.colors[idx] = normalizeColor(value);
        }
      } else if (currentFila !== null) {
        dict.filaments[currentFila][key] = value;
      }
    });

    return dict;
  }

  function normalizeColor(value) {
    let color = String(value || '').trim();
    if (!color) return '#b7bdc6';
    if (!color.startsWith('#')) color = '#' + color;
    if (/^#[0-9a-fA-F]{8}$/.test(color)) color = '#' + color.slice(1, 7);
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) return '#b7bdc6';
    return color;
  }

  function materialFor(id) {
    const rec = state.dict && state.dict.filaments ? state.dict.filaments[id] : null;
    if (!rec) return { name: id > 0 ? 'Fila ' + id : 'Empty', min: 0, max: 0 };
    return {
      name: rec.filament || rec.type || ('Fila ' + id),
      min: Number(rec.min_temp || 0),
      max: Number(rec.max_temp || 0),
      boxMax: Number(rec.box_max_temp || 0)
    };
  }

  function loadTemp(material, fallback) {
    if (material.min > 0 && material.max > material.min) {
      return Math.round((material.min + material.max) / 2);
    }
    return Math.round(Number(fallback || 250));
  }

  function slotColor(index, vars) {
    const colorIdx = Number(vars['color_slot' + index] || 0);
    return normalizeColor(state.dict && state.dict.colors ? state.dict.colors[colorIdx] : '');
  }

  function slotNameFor(index, vars) {
    return String(vars['value_t' + index] || ('slot' + index));
  }

  function hasMacro(name) {
    return state.macros.has('gcode_macro ' + name);
  }

  function macroObjects(objects) {
    state.macros = new Set(Array.isArray(objects) ? objects.filter((name) => name.startsWith('gcode_macro ')) : []);
  }

  function fluiddThemeClass() {
    const app = document.querySelector('.v-application.theme--light, .v-application.theme--dark') ||
      document.querySelector('.theme--light, .theme--dark');
    return app && app.classList.contains('theme--light') ? 'theme--light' : 'theme--dark';
  }

  function normalText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function findFluiddCardByTitle(matches) {
    const cards = Array.from(document.querySelectorAll('.v-card.collapsable-card, .v-card'));
    return cards.find((card) => {
      if (card.id === 'tinman-qidi-box-panel' || card.closest('#tinman-qidi-box-panel')) return false;
      const heading = card.querySelector('.v-card__title, .card-heading');
      const title = normalText(heading ? heading.textContent : card.textContent);
      return matches.some((match) => title.includes(match));
    }) || null;
  }

  function placePanel(panel) {
    if (!panel) return false;

    panel.className = 'tinman-qidi-box-card v-card v-sheet collapsable-card mb-2 mb-sm-4 ' + fluiddThemeClass();

    const consoleCard = findFluiddCardByTitle(['console']);
    if (consoleCard && consoleCard.parentNode) {
      panel.classList.remove('tq-floating-fallback');
      consoleCard.parentNode.insertBefore(panel, consoleCard);
      return true;
    }

    const temperatureCard = findFluiddCardByTitle(['temperature', 'temperatures']);
    if (temperatureCard && temperatureCard.parentNode) {
      panel.classList.remove('tq-floating-fallback');
      temperatureCard.parentNode.insertBefore(panel, temperatureCard.nextSibling);
      return true;
    }

    panel.classList.add('tq-floating-fallback');
    if (!document.body.contains(panel)) {
      document.body.appendChild(panel);
    }
    return false;
  }

  function ensureShell() {
    if (!document.getElementById('tinman-qidi-box-style')) {
      const style = document.createElement('style');
      style.id = 'tinman-qidi-box-style';
      style.textContent = `
      #tinman-qidi-box-panel { width: 100%; overflow: hidden; font: inherit; }
      #tinman-qidi-box-panel.tq-floating-fallback {
        position: fixed; right: 18px; top: 74px; width: min(430px, calc(100vw - 36px));
        z-index: 2147483000; margin: 0;
      }
      #tinman-qidi-box-panel * { box-sizing: border-box; }
      #tinman-qidi-box-panel .tq-head { position: relative; z-index: 4; min-height: 36px; padding-top: 0; padding-bottom: 0; }
      #tinman-qidi-box-panel .tq-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
      .tq-dot { width: 8px; height: 8px; border-radius: 50%; background: #7a8492; }
      .tq-dot.ready { background: #15b886; }
      .tq-dot.warn { background: #e0a329; }
      .tq-icon-btn {
        width: 28px; height: 28px; border: 0; border-radius: 50%; color: currentColor;
        background: transparent; cursor: pointer; opacity: .72; font: inherit;
      }
      .tq-icon-btn:hover { opacity: 1; background: rgba(127,127,127,.16); }
      .tq-body { padding: 16px; }
      .tq-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
      .tq-metric { min-width: 0; padding: 7px 8px; background: #171d27; border: 1px solid rgba(255,255,255,.08); border-radius: 6px; }
      .tq-metric span { display: block; color: #99a4b2; font-size: 11px; }
      .tq-metric b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
      .tq-diagram { position: relative; min-height: 182px; padding: 12px 8px 8px; background: #0c0f14; border: 1px solid rgba(255,255,255,.08); border-radius: 7px; overflow: hidden; }
      .tq-diagram-row { display: grid; grid-template-columns: 1fr 88px; gap: 12px; align-items: center; }
      .tq-box { position: relative; height: 122px; border: 2px solid rgba(255,255,255,.17); border-radius: 5px; background: linear-gradient(135deg, rgba(255,255,255,.06), rgba(255,255,255,.015)); padding: 14px 11px 8px; }
      .tq-box-label { position: absolute; left: 11px; bottom: 8px; color: #cbd5e1; font-weight: 700; }
      .tq-slots { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; align-items: start; }
      .tq-slot { min-width: 0; cursor: pointer; text-align: center; color: #d9e2ec; border: 1px solid transparent; border-radius: 7px; padding: 3px 3px 24px; position: relative; }
      .tq-slot:hover { border-color: rgba(99,179,237,.38); background: rgba(99,179,237,.08); }
      .tq-slot.selected { border-color: #63b3ed; background: rgba(99,179,237,.12); }
      .tq-slot.active::after { content: ""; position: absolute; left: 50%; bottom: 10px; width: 9px; height: 9px; border-radius: 50%; background: #55a7ff; transform: translateX(-50%); box-shadow: 0 0 0 4px rgba(85,167,255,.16); }
      .tq-spool { width: 44px; height: 66px; margin: 0 auto 5px; border-radius: 50% / 18%; background: var(--slot-color); border-left: 8px solid #bdc3cb; border-right: 8px solid #d9dde3; box-shadow: inset 0 0 0 1px rgba(0,0,0,.18); }
      .tq-spool.empty { background: #303946; border-color: #566173; opacity: .55; }
      .tq-slot-name { font-weight: 700; font-size: 12px; }
      .tq-material { color: #aeb8c5; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .tq-ext { text-align: center; color: #d9e2ec; }
      .tq-ext .tq-spool { width: 48px; height: 72px; }
      .tq-hotend { position: absolute; left: 51%; right: 86px; bottom: 32px; height: 3px; background: #55a7ff; opacity: .75; }
      .tq-hotend::after { content: ""; position: absolute; right: -20px; top: -15px; width: 20px; height: 32px; border-radius: 3px; background: linear-gradient(#d9dde3, #8e99a8); box-shadow: inset 0 -9px 0 rgba(0,0,0,.18); }
      .tq-controls { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; }
      .tq-btn { min-height: 32px; border: 1px solid rgba(255,255,255,.14); border-radius: 6px; color: #edf2f7; background: #18202b; cursor: pointer; }
      .tq-btn:hover:not(:disabled) { background: #243044; border-color: rgba(99,179,237,.6); }
      .tq-btn.primary { background: #176b87; border-color: #2494b7; }
      .tq-btn.danger { background: #43212a; border-color: #8a4050; }
      .tq-btn:disabled { cursor: default; opacity: .42; }
      .tq-selected { margin-top: 10px; min-height: 18px; color: #b7c0ce; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .tq-status { margin-top: 8px; min-height: 17px; color: #8fb9d8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      @media only screen and (min-width: 600px) {
        #tinman-qidi-box-panel .tq-head { min-height: 42px; }
      }
      @media (max-width: 700px) {
        #tinman-qidi-box-panel.tq-floating-fallback { left: 10px; right: 10px; top: 58px; width: auto; }
        .tq-metrics { grid-template-columns: repeat(2, 1fr); }
      }
    `;
      document.head.appendChild(style);
    }

    const existing = document.getElementById('tinman-qidi-box-panel');
    if (existing) {
      placePanel(existing);
      return;
    }

    const panel = document.createElement('section');
    panel.id = 'tinman-qidi-box-panel';
    panel.innerHTML = `
      <div class="tq-head v-card__title collapsable-card-title card-heading">
        <div class="row flex-nowrap no-gutters">
          <div class="col align-self-center tq-title">
            <span class="tq-dot"></span>
            <span class="font-weight-light">Qidi Box</span>
          </div>
          <div class="col col-auto align-self-center">
            <button class="tq-icon-btn" type="button" data-tq-action="close" title="Hide Qidi Box panel">x</button>
          </div>
        </div>
      </div>
      <div class="tq-body v-card__text overflow-hidden" id="card-content">
        <div class="tq-metrics">
          <div class="tq-metric"><span>Box Temp</span><b data-tq="box-temp">--</b></div>
          <div class="tq-metric"><span>Humidity</span><b data-tq="humidity">--</b></div>
          <div class="tq-metric"><span>Hotend</span><b data-tq="hotend">--</b></div>
          <div class="tq-metric"><span>Path</span><b data-tq="path">--</b></div>
        </div>
        <div class="tq-diagram">
          <div class="tq-diagram-row">
            <div class="tq-box">
              <div class="tq-slots" data-tq="slots"></div>
              <div class="tq-box-label">BOX-1</div>
            </div>
            <div class="tq-ext" data-tq="ext"></div>
          </div>
          <div class="tq-hotend"></div>
        </div>
        <div class="tq-selected" data-tq="selected"></div>
        <div class="tq-controls">
          <button class="tq-btn primary" type="button" data-tq-action="load">Load</button>
          <button class="tq-btn" type="button" data-tq-action="unload">Unload</button>
          <button class="tq-btn danger" type="button" data-tq-action="eject">Eject</button>
          <button class="tq-btn" type="button" data-tq-action="refresh">Re-read</button>
        </div>
        <div class="tq-status" data-tq="status"></div>
      </div>
    `;
    placePanel(panel);

    panel.addEventListener('click', (event) => {
      const button = event.target.closest('[data-tq-action]');
      if (!button) return;
      const action = button.getAttribute('data-tq-action');
      if (action === 'close') {
        panel.remove();
        window.__tinmanQidiBoxPanelActive = false;
        if (state.timer) clearInterval(state.timer);
      } else if (action === 'refresh') {
        refresh(true);
      } else {
        runAction(action);
      }
    });
  }

  function setStatus(message, tone) {
    const panel = document.getElementById('tinman-qidi-box-panel');
    const text = panel && panel.querySelector('[data-tq="status"]');
    const dot = panel && panel.querySelector('.tq-dot');
    if (text) text.textContent = message || '';
    if (dot) {
      dot.className = 'tq-dot' + (tone ? ' ' + tone : '');
    }
  }

  function render(data) {
    const panel = document.getElementById('tinman-qidi-box-panel');
    if (!panel) return;

    const status = data.result && data.result.status ? data.result.status : {};
    const vars = status.save_variables && status.save_variables.variables ? status.save_variables.variables : {};
    const printState = String(status.print_stats && status.print_stats.state || 'standby').toLowerCase();
    const busyPrint = printState === 'printing';
    const boxExtras = status.box_extras || {};
    const eState = Number(boxExtras.e_endstop_state || 0);
    const bState = Number(boxExtras.b_endstop_state || 0);
    const fila = !!(status['filament_switch_sensor fila'] && status['filament_switch_sensor fila'].filament_detected);
    const motion = !!(status['filament_motion_sensor box_motion_sensor'] && status['filament_motion_sensor box_motion_sensor'].filament_detected);
    const hall = Number(status.hall_filament_width_sensor && status.hall_filament_width_sensor.Diameter || 0);
    const syncSlot = String(vars.slot_sync || 'slot-1');
    const lastLoadSlot = String(vars.last_load_slot || 'slot-1');
    const pathOccupied = eState === 1 || fila || hall > 0.5;
    const activeSlot = syncSlot !== 'slot-1' ? syncSlot : (pathOccupied && lastLoadSlot !== 'slot-1' ? lastLoadSlot : 'slot-1');
    const loaded = activeSlot !== 'slot-1' && pathOccupied;
    const fallbackTemp = Number(vars.print_temp || 250);

    const temp = status['heater_generic heater_box1'] && Number(status['heater_generic heater_box1'].temperature);
    const humidity = status['aht20_f heater_box1'] && Number(status['aht20_f heater_box1'].humidity);
    const hotendTemp = status.extruder && Number(status.extruder.temperature);
    const hotendTarget = status.extruder && Number(status.extruder.target);

    panel.querySelector('[data-tq="box-temp"]').textContent = Number.isFinite(temp) ? temp.toFixed(1) + ' C' : '--';
    panel.querySelector('[data-tq="humidity"]').textContent = Number.isFinite(humidity) ? humidity.toFixed(0) + '%' : '--';
    panel.querySelector('[data-tq="hotend"]').textContent =
      Number.isFinite(hotendTemp) ? hotendTemp.toFixed(0) + ' / ' + Number(hotendTarget || 0).toFixed(0) + ' C' : '--';
    panel.querySelector('[data-tq="path"]').textContent =
      loaded ? activeSlot.replace('slot', 'T') + ' loaded' : (pathOccupied ? 'Path occupied' : (bState ? 'Parked' : (motion ? 'At feeder' : 'Clear')));

    const slotsEl = panel.querySelector('[data-tq="slots"]');
    slotsEl.innerHTML = '';

    const slots = [0, 1, 2, 3].map((idx) => {
      const slotName = slotNameFor(idx, vars);
      const runoutObject = status['box_stepper slot' + idx];
      const runoutButton = runoutObject && runoutObject.runout_button;
      const slotVariable = Number(vars[slotName] || vars['slot' + idx] || 0);
      const hasFilament = runoutButton !== undefined && runoutButton !== null ? Number(runoutButton) === 0 : slotVariable !== 0;
      const materialId = Number(vars['filament_' + slotName] || vars['filament_slot' + idx] || 0);
      const material = materialFor(materialId);
      const isActive = loaded && slotName === activeSlot;
      return { idx, slotName, hasFilament, materialId, material, color: slotColor(idx, vars), isActive };
    });

    if (!slots[state.selected] || !slots[state.selected].hasFilament) {
      const activeIdx = slots.findIndex((slot) => slot.isActive);
      const firstPresent = slots.findIndex((slot) => slot.hasFilament);
      state.selected = activeIdx >= 0 ? activeIdx : Math.max(0, firstPresent);
    }

    slots.forEach((slot) => {
      const slotEl = document.createElement('button');
      slotEl.type = 'button';
      slotEl.className = 'tq-slot' +
        (slot.idx === state.selected ? ' selected' : '') +
        (slot.isActive ? ' active' : '');
      slotEl.style.setProperty('--slot-color', slot.color);
      slotEl.title = slot.hasFilament ? ('T' + slot.idx + ' ' + slot.material.name) : ('T' + slot.idx + ' empty');
      slotEl.innerHTML = `
        <div class="tq-spool ${slot.hasFilament ? '' : 'empty'}"></div>
        <div class="tq-slot-name">T${slot.idx}</div>
        <div class="tq-material">${escapeHtml(slot.hasFilament ? slot.material.name : 'Empty')}</div>
      `;
      slotEl.addEventListener('click', () => {
        state.selected = slot.idx;
        render(data);
      });
      slotsEl.appendChild(slotEl);
    });

    const extMaterialId = Number(vars.filament_slot16 || 0);
    const extMaterial = materialFor(extMaterialId);
    const extColor = normalizeColor(state.dict && state.dict.colors ? state.dict.colors[Number(vars.color_slot16 || 0)] : '');
    const extEl = panel.querySelector('[data-tq="ext"]');
    extEl.style.setProperty('--slot-color', extColor);
    extEl.innerHTML = `
      <div class="tq-spool ${extMaterialId ? '' : 'empty'}"></div>
      <div class="tq-slot-name">Ext</div>
      <div class="tq-material">${escapeHtml(extMaterialId ? extMaterial.name : 'Empty')}</div>
    `;

    const selected = slots[state.selected] || slots[0];
    const selectedTemp = selected ? loadTemp(selected.material, fallbackTemp) : Math.round(fallbackTemp);
    panel.querySelector('[data-tq="selected"]').textContent =
      selected ? `Selected T${selected.idx}: ${selected.hasFilament ? selected.material.name : 'empty'} / ${selectedTemp} C` : '';

    const loadBtn = panel.querySelector('[data-tq-action="load"]');
    const unloadBtn = panel.querySelector('[data-tq-action="unload"]');
    const ejectBtn = panel.querySelector('[data-tq-action="eject"]');
    loadBtn.disabled = state.busy || busyPrint || !selected || !selected.hasFilament;
    unloadBtn.disabled = state.busy || busyPrint || !selected || !selected.isActive || !hasMacro('TINMAN_QIDI_BOX_UNLOAD');
    ejectBtn.disabled = state.busy || busyPrint || !selected || !selected.hasFilament || selected.isActive || !hasMacro('TINMAN_QIDI_BOX_EJECT');

    loadBtn.title = busyPrint ? 'Disabled while printing' : 'Load selected Qidi Box slot';
    unloadBtn.title = selected && selected.isActive ? 'Unload selected slot from the hotend path' : 'Unload is available for the loaded slot';
    ejectBtn.title = selected && selected.isActive ? 'Unload before ejecting' : 'Eject selected slot from the box path';

    window.__tinmanQidiBoxLastSlots = slots;
    window.__tinmanQidiBoxFallbackTemp = fallbackTemp;
    setStatus(busyPrint ? 'Print in progress: box motion controls disabled.' : 'Ready', busyPrint ? 'warn' : 'ready');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function refresh(force) {
    try {
      if (force) setStatus('Refreshing...', 'warn');
      const data = await getJson(query);
      if (!data.result || !data.result.status || !data.result.status.box_extras) {
        return false;
      }
      if (!state.dict) {
        try {
          state.dict = parseQidiDictionary(await getText('/server/files/config/officiall_filas_list.cfg'));
        } catch (error) {
          state.dict = { colors: {}, filaments: {} };
        }
      }
      try {
        const objects = await getJson('/printer/objects/list');
        macroObjects(objects.result && objects.result.objects);
      } catch (error) {}
      ensureShell();
      render(data);
      return true;
    } catch (error) {
      setStatus(error.message || 'Qidi Box refresh failed.', 'warn');
      return false;
    }
  }

  async function runGcode(script, label) {
    if (!script || state.busy) return;
    state.busy = true;
    setStatus(label + '...', 'warn');
    try {
      const response = await fetch('/printer/gcode/script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script })
      });
      if (!response.ok) throw new Error(label + ' returned HTTP ' + response.status);
      setStatus(label + ' command sent.', 'ready');
      setTimeout(() => refresh(true), 1200);
    } catch (error) {
      setStatus(error.message || (label + ' failed.'), 'warn');
    } finally {
      state.busy = false;
      setTimeout(() => refresh(false), 2500);
    }
  }

  function runAction(action) {
    const slots = window.__tinmanQidiBoxLastSlots || [];
    const selected = slots[state.selected];
    if (!selected) return;
    const temp = loadTemp(selected.material, window.__tinmanQidiBoxFallbackTemp || 250);
    if (action === 'load') {
      runGcode(`LOAD_FILAMENT TOOL=${selected.idx} TEMP=${temp}`, `Load T${selected.idx}`);
    } else if (action === 'unload') {
      runGcode(`TINMAN_QIDI_BOX_UNLOAD TOOL=${selected.idx} TEMP=${temp}`, `Unload T${selected.idx}`);
    } else if (action === 'eject') {
      if (window.confirm(`Eject T${selected.idx} (${selected.material.name}) from the Qidi Box path?`)) {
        runGcode(`TINMAN_QIDI_BOX_EJECT TOOL=${selected.idx}`, `Eject T${selected.idx}`);
      }
    }
  }

  window.__tinmanQidiBoxPanelActive = true;
  window.__tinmanQidiBoxPanelRefresh = () => refresh(true);

  refresh(false).then((hasBox) => {
    if (hasBox) {
      state.timer = setInterval(() => refresh(false), 3000);
    } else {
      window.__tinmanQidiBoxPanelActive = false;
    }
  });
})();
)JS";
    }
};

} // namespace

std::unique_ptr<PrinterWebViewHandler> create_printer_webview_handler(PrinterWebView& owner)
{
    auto     cfg = get_active_printer_config();
    if (cfg != nullptr) {
        const auto* host_type_opt = cfg->option<ConfigOptionEnum<PrintHostType>>("host_type");
        if (host_type_opt != nullptr && host_type_opt->value == PrintHostType::htElegooLink)
            return std::make_unique<ElegooPrinterWebViewHandler>(owner);
    }

    return std::make_unique<QidiBoxPrinterWebViewHandler>(owner);
}

} // GUI
} // Slic3r
