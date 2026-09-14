#include "PrinterWebViewHandler.hpp"

#include "I18N.hpp"
#include "PrinterWebView.hpp"
#include "DeviceManager.hpp"
#include "DeviceCore/DevManager.h"
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/Widgets/WebView.hpp"
#include "slic3r/Utils/NetworkAgentFactory.hpp"
#include "slic3r/Utils/PrintHost.hpp"
#include "libslic3r/Preset.hpp"

#include <nlohmann/json.hpp>
#include <atomic>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/filesystem/path.hpp>
#include <string>
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

std::string config_string(const DynamicPrintConfig& cfg, const std::string& key)
{
    return cfg.has(key) ? cfg.opt_string(key) : std::string();
}

static std::string authority_from_url(std::string url)
{
    if (url.empty())
        return url;

    const size_t scheme = url.find("://");
    if (scheme != std::string::npos)
        url = url.substr(scheme + 3);

    const size_t slash = url.find('/');
    if (slash != std::string::npos)
        url = url.substr(0, slash);

    return url;
}

static std::string host_from_url(const std::string& url)
{
    std::string authority = authority_from_url(url);
    if (!authority.empty() && authority.front() == '[') {
        const size_t end = authority.find(']');
        if (end != std::string::npos)
            return authority.substr(1, end - 1);
    }

    const size_t port = authority.find(':');
    return port == std::string::npos ? authority : authority.substr(0, port);
}

bool address_matches_machine(const std::string& address, const MachineObject* obj)
{
    if (address.empty() || obj == nullptr)
        return false;

    const std::string dev_ip = obj->get_dev_ip();
    const std::string dev_id = obj->get_dev_id();
    if (address == dev_ip || address == dev_id)
        return true;

    const std::string address_authority = authority_from_url(address);
    const std::string address_host      = host_from_url(address);
    const std::string dev_ip_authority  = authority_from_url(dev_ip);
    const std::string dev_id_authority  = authority_from_url(dev_id);

    return (!dev_ip.empty() && (address_authority == dev_ip_authority || address_host == host_from_url(dev_ip))) ||
           (!dev_id.empty() && (address_authority == dev_id_authority || address_host == host_from_url(dev_id)));
}

bool config_matches_machine(const DynamicPrintConfig& cfg, const MachineObject* obj)
{
    return address_matches_machine(config_string(cfg, "print_host"), obj) ||
           address_matches_machine(config_string(cfg, "print_host_webui"), obj);
}

std::string configured_agent_for_machine(const MachineObject* obj)
{
    if (obj == nullptr || wxGetApp().preset_bundle == nullptr)
        return {};

    for (const PhysicalPrinter& printer : wxGetApp().preset_bundle->physical_printers) {
        if (config_matches_machine(printer.config, obj) && printer.config.has("printer_agent")) {
            const std::string agent_id = printer.config.opt_string("printer_agent");
            if (!agent_id.empty())
                return agent_id;
        }
    }

    for (const Preset& printer : wxGetApp().preset_bundle->printers) {
        if (config_matches_machine(printer.config, obj) && printer.config.has("printer_agent")) {
            const std::string agent_id = printer.config.opt_string("printer_agent");
            if (!agent_id.empty())
                return agent_id;
        }
    }

    return {};
}

std::string infer_agent_from_text(const std::string& key)
{
    if (boost::algorithm::icontains(key, "qidi"))
        return "qidi";
    if (boost::algorithm::icontains(key, "snapmaker"))
        return "snapmaker";
    if (boost::algorithm::icontains(key, "creality") || boost::algorithm::icontains(key, "k2"))
        return "crealityprint";
    if (boost::algorithm::icontains(key, "prusa"))
        return "prusalink";
    if (boost::algorithm::icontains(key, "v-core") || boost::algorithm::icontains(key, "ratrig") ||
        boost::algorithm::icontains(key, "sovol"))
        return "moonraker";

    return {};
}

std::string selected_machine_agent_id()
{
    DeviceManager* device_manager = wxGetApp().getDeviceManager();
    MachineObject* obj            = device_manager ? device_manager->get_selected_machine() : nullptr;
    if (obj == nullptr)
        return {};

    std::string agent_id = configured_agent_for_machine(obj);
    if (!agent_id.empty())
        return agent_id;

    return infer_agent_from_text(obj->printer_type + " " + obj->get_dev_name() + " " +
                                 obj->get_dev_id() + " " + obj->get_dev_ip());
}

std::string config_agent_id(const DynamicPrintConfig& cfg)
{
    const std::string explicit_agent = config_string(cfg, "printer_agent");
    if (!explicit_agent.empty())
        return explicit_agent;

    return infer_agent_from_text(config_string(cfg, "printer_model") + " " +
                                 config_string(cfg, "printer_settings_id") + " " +
                                 config_string(cfg, "print_host") + " " +
                                 config_string(cfg, "print_host_webui"));
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

class CrealityPrinterWebViewHandler final : public PrinterWebViewHandler {
public:
    explicit CrealityPrinterWebViewHandler(PrinterWebView& owner)
        : PrinterWebViewHandler(owner)
    {
    }

    void on_loaded(wxWebViewEvent& evt) override
    {
        if (browser() == nullptr || evt.GetURL().IsEmpty())
            return;

        WebView::RunScript(browser(), wxString::FromUTF8(camera_injection_script()));
    }

private:
    static const char* camera_injection_script()
    {
        static const std::string script = std::string(R"JS(
(function () {
  'use strict';

  const panelId = 'tinman-creality-camera-panel';
  const stateKey = '__tinmanCrealityCameraState';
  const probeDelayMs = 3000;
  const reconnectDelayMs = 5000;
  const connectTimeoutMs = 20000;

  if (window[stateKey]) {
    window[stateKey].probeCamera();
    return;
  }

  const state = {
    cameraAvailable: false,
    connecting: false,
    connectStartedAt: 0,
    probeInFlight: false,
    probeTimer: 0,
    reconnectTimer: 0,
    attempt: 0,
    peerConnection: null,
    controlSocket: null,
    observer: null,
    monitorTimer: 0,
    probeCamera: null,
    connectCamera: null
  };
  window[stateKey] = state;

  function normalText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function fluiddThemeClass() {
    const app = document.querySelector('.v-application.theme--light, .v-application.theme--dark') ||
      document.querySelector('.theme--light, .theme--dark');
    return app && app.classList.contains('theme--light') ? 'theme--light' : 'theme--dark';
  }

  function findFluiddCardByTitle(matches) {
    const cards = Array.from(document.querySelectorAll('.v-card.collapsable-card, .v-card'));
    return cards.find((card) => {
      if (card.id === panelId || card.closest('#' + panelId)) return false;
      const heading = card.querySelector('.v-card__title, .card-heading');
      const title = normalText(heading ? heading.textContent : '');
      return matches.some((match) => title === match || title.startsWith(match + ' '));
    }) || null;
  }

  function hideLegacyCameraCards() {
    const cards = Array.from(document.querySelectorAll('.v-card.collapsable-card, .v-card'));
    for (const card of cards) {
      if (card.id === panelId || card.closest('#' + panelId)) continue;
      const heading = card.querySelector('.v-card__title, .card-heading');
      const title = normalText(heading ? heading.textContent : '');
      if (title === 'camera' || title === 'cameras' || title.startsWith('camera ')) {
        card.setAttribute('data-tinman-legacy-camera', 'hidden');
        card.style.setProperty('display', 'none', 'important');
      }
    }
  }

  function placePanel(panel) {
    if (!panel) return false;

    panel.className = 'v-card v-sheet collapsable-card mb-2 mb-sm-4 ' + fluiddThemeClass();
    const toolheadCard = findFluiddCardByTitle(['tool', 'toolhead']);
    if (toolheadCard && toolheadCard.parentNode) {
      panel.classList.remove('tk2-floating-fallback');
      if (toolheadCard.previousElementSibling !== panel)
        toolheadCard.parentNode.insertBefore(panel, toolheadCard);
      return true;
    }

    const statusCard = findFluiddCardByTitle(['status', 'printer']);
    if (statusCard && statusCard.parentNode) {
      panel.classList.remove('tk2-floating-fallback');
      if (statusCard.nextElementSibling !== panel)
        statusCard.parentNode.insertBefore(panel, statusCard.nextSibling);
      return true;
    }

    panel.classList.add('tk2-floating-fallback');
    if (!document.body.contains(panel)) document.body.appendChild(panel);
    return false;
  }

  function ensureStyle() {
    if (document.getElementById('tinman-creality-camera-style')) return;
    const style = document.createElement('style');
    style.id = 'tinman-creality-camera-style';
    style.textContent = `
      #${panelId} { width: 100%; overflow: hidden; }
      #${panelId}.tk2-floating-fallback {
        position: fixed; right: 18px; top: 74px; width: min(520px, calc(100vw - 36px));
        z-index: 2147483000; margin: 0;
      }
      #${panelId} .tk2-head { min-height: 42px; padding-top: 0; padding-bottom: 0; }
      #${panelId} .tk2-title { display: flex; align-items: center; gap: 9px; min-width: 0; }
      #${panelId} .tk2-camera-icon {
        width: 18px; height: 13px; border: 2px solid currentColor; border-radius: 2px;
        position: relative; display: inline-block; opacity: .8;
      }
      #${panelId} .tk2-camera-icon::after {
        content: ''; position: absolute; right: -7px; top: 2px; width: 6px; height: 7px;
        background: currentColor; clip-path: polygon(0 20%, 100% 0, 100% 100%, 0 80%);
      }
      #${panelId} .tk2-actions { display: flex; gap: 6px; align-items: center; }
      #${panelId} .tk2-btn {
        min-height: 30px; padding: 0 10px; border: 1px solid rgba(255,255,255,.15);
        border-radius: 5px; color: currentColor; background: rgba(127,127,127,.10);
        cursor: pointer; font: inherit; font-size: 12px;
      }
      #${panelId} .tk2-btn:hover { background: rgba(127,127,127,.22); }
      #${panelId} .tk2-body {
        position: relative; padding: 0; background: #1e1e20; aspect-ratio: 16 / 9;
      }
      #${panelId} .tk2-video {
        display: block; width: 100%; height: 100%; object-fit: contain; background: #1e1e20;
      }
      #${panelId} .tk2-status {
        position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
        color: rgba(255,255,255,.78); background: #1e1e20; font-size: 13px;
      }
      #${panelId} .tk2-status[hidden] { display: none; }
      @media (max-width: 700px) {
        #${panelId}.tk2-floating-fallback { left: 10px; right: 10px; top: 58px; width: auto; }
      }
    `;
    document.head.appendChild(style);
  }

  function panelVideo() {
    return document.querySelector('#' + panelId + ' .tk2-video');
  }

  function cameraIsLive() {
    const video = panelVideo();
    return Boolean(video && video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0);
  }

  function setCameraStatus(message) {
    const status = document.querySelector('#' + panelId + ' .tk2-status');
    if (!status) return;
    status.textContent = message || '';
    status.hidden = !message;
  }

  function closeCameraConnections() {
    state.attempt++;
    state.connecting = false;

    const peer = state.peerConnection;
    state.peerConnection = null;
    if (peer) peer.close();

    const socket = state.controlSocket;
    state.controlSocket = null;
    if (socket) socket.close();

    const video = panelVideo();
    if (video) video.srcObject = null;
  }

  function scheduleReconnect() {
    if (state.reconnectTimer || document.hidden || !state.cameraAvailable) return;
    state.reconnectTimer = window.setTimeout(() => {
      state.reconnectTimer = 0;
      if (!cameraIsLive()) state.connectCamera(true);
    }, reconnectDelayMs);
  }

  function waitForIce(peer, timeoutMs = 8000) {
    if (peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve) => {
      const timeout = window.setTimeout(resolve, timeoutMs);
      peer.addEventListener('icegatheringstatechange', () => {
        if (peer.iceGatheringState === 'complete') {
          window.clearTimeout(timeout);
          resolve();
        }
      });
    });
  }

  function getPrinterSession(currentAttempt, timeoutMs = 7000) {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket('ws://' + location.hostname + ':9999');
      const session = { features: [], token: '' };
      let settled = false;
      state.controlSocket = socket;

      const fail = (message) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        socket.close();
        reject(new Error(message));
      };

      const timeout = window.setTimeout(() => fail('Camera token timed out.'), timeoutMs);
      socket.addEventListener('open', () => {
        if (currentAttempt !== state.attempt) return fail('Camera connection cancelled.');
        socket.send(JSON.stringify({ method: 'get', params: { getToken: 1 } }));
      });
      socket.addEventListener('message', (event) => {
        if (event.data === 'ok' || currentAttempt !== state.attempt) return;
        try {
          const message = JSON.parse(event.data);
          if (Array.isArray(message.features)) session.features = message.features;
          if (message.videoToken && !settled) {
            settled = true;
            window.clearTimeout(timeout);
            session.token = String(message.videoToken).trim();
            resolve(session);
          }
        } catch (_) {}
      });
      socket.addEventListener('error', () => fail('Camera control channel unavailable.'));
      socket.addEventListener('close', () => {
        if (!settled) fail('Camera control channel closed.');
      });
    });
  }

  // Match Creality Print's H.264-only offer. Current K2 firmware rejects the
  // browser's full codec list even when a valid H.264 payload is present.
  function filterCrealitySdp(sdp) {
    try {
      const lines = sdp.split('\r\n');
      const prefix = [];
      const suffix = [];
      const codecGroups = [];

      for (let index = 0; index < lines.length; index++) {
        const line = lines[index];
        if (line.includes('a=rtpmap:')) {
          const group = [];
          for (;;) {
            group.push(lines[index]);
            if (index + 1 === lines.length || lines[index + 1].includes('a=rtpmap:')) {
              codecGroups.push(group);
              break;
            }
            index++;
          }
        }
        if (codecGroups.length === 0) prefix.push(line);
      }

      const remove = [];
      for (let index = 0; index < codecGroups.length; index++) {
        if (index === codecGroups.length - 1) continue;
        let discard = true;
        for (const line of codecGroups[index]) {
          if (line.includes('a=rtpmap:')) {
            const payload = parseInt(line.split(' ')[0].split(':')[1], 10);
            if (payload < 96 || payload > 127) break;
          }
          if (/H264/i.test(line)) {
            discard = false;
            break;
          }
        }
        if (discard) remove.push(index);
      }
      for (let index = remove.length - 1; index >= 0; index--)
        codecGroups.splice(remove[index], 1);

      if (codecGroups.length) {
        const last = codecGroups[codecGroups.length - 1];
        const payload = parseInt(last[0].split(' ')[0].split(':')[1], 10);
        const codecLines = [];
        for (const line of last) {
          if (line.includes(':' + payload + ' ')) codecLines.push(line);
          else suffix.push(line);
        }
        const valid = codecLines.some((line) => /H264/i.test(line)) && payload >= 96 && payload <= 127;
        if (valid) codecGroups[codecGroups.length - 1] = codecLines;
        else codecGroups.splice(codecGroups.length - 1, 1);
      }

      return codecGroups.length ? [...prefix, ...codecGroups[0], ...suffix].join('\r\n') : sdp;
    } catch (_) {
      return sdp;
    }
  }
)JS") + R"JS(

  function makeCandidatesNumeric(sdp) {
    return sdp.split('\r\n').map((line) => {
      if (!line.startsWith('a=candidate:')) return line;
      const fields = line.split(' ');
      if (fields[4] && fields[4].endsWith('.local')) fields[4] = '192.0.2.1';
      return fields.join(' ');
    }).join('\r\n');
  }

  // Token flow and SDP compatibility are based on Creality Print 7.2 behavior.
  // Credit: GecKoTDF's GPL-3.0 Creality-K2-Camera-Fix documented the current
  // firmware protocol after Creality retired the legacy unauthenticated player.
  state.connectCamera = async function (force = false) {
    if (!state.cameraAvailable || document.hidden || state.connecting || (!force && cameraIsLive())) return;

    if (state.reconnectTimer) {
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = 0;
    }
    closeCameraConnections();
    const currentAttempt = state.attempt;
    state.connecting = true;
    state.connectStartedAt = Date.now();
    setCameraStatus('Connecting camera...');

    try {
      // The K2 camera service briefly retains the previous WebRTC session.
      // Give it a bounded teardown window before requesting a replacement token.
      await new Promise((resolve) => window.setTimeout(resolve, 300));
      if (currentAttempt !== state.attempt) return;

      const session = await getPrinterSession(currentAttempt);
      if (currentAttempt !== state.attempt) return;

      const encryptedProtocol = session.features.includes('videoInfo.videoEncryption');
      const peer = new RTCPeerConnection({ iceServers: [] });
      state.peerConnection = peer;

      peer.addEventListener('connectionstatechange', () => {
        if (peer !== state.peerConnection) return;
        if (peer.connectionState === 'failed' || peer.connectionState === 'disconnected')
          scheduleReconnect();
      });
      peer.addEventListener('track', (event) => {
        if (peer !== state.peerConnection || event.track.kind !== 'video') return;
        const video = panelVideo();
        if (!video) return;
        video.srcObject = event.streams[0] || new MediaStream([event.track]);
        video.play().catch(() => scheduleReconnect());
      });

      const transceiver = peer.addTransceiver('video', { direction: 'sendrecv' });
      const capabilities = RTCRtpReceiver.getCapabilities && RTCRtpReceiver.getCapabilities('video');
      const h264 = capabilities ? capabilities.codecs.filter((codec) => codec.mimeType.toLowerCase() === 'video/h264') : [];
      if (h264.length && typeof transceiver.setCodecPreferences === 'function')
        transceiver.setCodecPreferences(h264);

      await peer.setLocalDescription(await peer.createOffer());
      await waitForIce(peer);
      if (currentAttempt !== state.attempt) return;

      const request = {
        type: 'offer',
        sdp: filterCrealitySdp(makeCandidatesNumeric(peer.localDescription.sdp))
      };
      if (encryptedProtocol) request.token = session.token;

      const signalUrl = encryptedProtocol
        ? 'http://' + location.hostname + '/call/webrtc_local'
        : 'http://' + location.hostname + ':8000/call/webrtc_local';
      const response = await fetch(signalUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'plain/text' },
        body: btoa(JSON.stringify(request))
      });
      const responseText = (await response.text()).trim();
      if (!response.ok || !responseText || responseText === '{}')
        throw new Error('Camera signaling failed.');

      const answer = JSON.parse(atob(responseText));
      await peer.setRemoteDescription(new RTCSessionDescription(answer));
      setCameraStatus('Waiting for video...');
    } catch (_) {
      if (currentAttempt === state.attempt) {
        state.connecting = false;
        setCameraStatus('Camera reconnecting...');
        scheduleReconnect();
      }
    }
  };

  function monitorCamera() {
    if (!state.cameraAvailable || document.hidden) return;
    ensurePanel();
    if (cameraIsLive()) {
      if (state.reconnectTimer) {
        window.clearTimeout(state.reconnectTimer);
        state.reconnectTimer = 0;
      }
      setCameraStatus('');
      return;
    }

    const connectionAge = Date.now() - state.connectStartedAt;
    if (state.connecting && connectionAge > connectTimeoutMs) {
      state.connecting = false;
      closeCameraConnections();
      setCameraStatus('Camera reconnecting...');
      scheduleReconnect();
    } else if (!state.connecting && connectionAge > connectTimeoutMs) {
      scheduleReconnect();
    }
  }

  function ensurePanel() {
    hideLegacyCameraCards();
    ensureStyle();
    let panel = document.getElementById(panelId);
    if (!panel) {
      panel = document.createElement('section');
      panel.id = panelId;
      panel.innerHTML = `
        <div class="tk2-head v-card__title collapsable-card-title card-heading">
          <div class="row flex-nowrap no-gutters">
            <div class="col align-self-center tk2-title">
              <span class="tk2-camera-icon" aria-hidden="true"></span>
              <span class="font-weight-light">Camera</span>
            </div>
            <div class="col col-auto align-self-center tk2-actions">
              <button class="tk2-btn" type="button" data-tk2-action="refresh">Refresh</button>
              <button class="tk2-btn" type="button" data-tk2-action="fullscreen">Full screen</button>
            </div>
          </div>
        </div>
        <div class="tk2-body v-card__text overflow-hidden">
          <video class="tk2-video" aria-label="K2 Plus camera" autoplay muted playsinline></video>
          <div class="tk2-status">Connecting camera...</div>
        </div>
      `;
      panel.querySelector('.tk2-video').addEventListener('playing', () => {
        if (!cameraIsLive()) return;
        state.connecting = false;
        if (state.reconnectTimer) {
          window.clearTimeout(state.reconnectTimer);
          state.reconnectTimer = 0;
        }
        setCameraStatus('');
      });
      panel.addEventListener('click', (event) => {
        const button = event.target.closest('[data-tk2-action]');
        if (!button) return;
        const action = button.getAttribute('data-tk2-action');
        if (action === 'refresh') {
          state.connectCamera(true);
        } else if (action === 'fullscreen') {
          const video = panelVideo();
          if (video && video.requestFullscreen) video.requestFullscreen();
        }
      });
    }
    placePanel(panel);
    if (state.cameraAvailable && !state.connecting && !cameraIsLive() && !state.reconnectTimer)
      state.connectCamera();
  }

  function startCameraUi() {
    state.cameraAvailable = true;
    ensurePanel();

    if (!state.observer) {
      let scheduled = false;
      state.observer = new MutationObserver(() => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
          scheduled = false;
          ensurePanel();
        });
      });
      state.observer.observe(document.body, { childList: true, subtree: true });
    }

    if (!state.monitorTimer)
      state.monitorTimer = window.setInterval(monitorCamera, 3000);

    state.connectCamera();
  }

  function scheduleProbe() {
    if (state.probeTimer || state.cameraAvailable) return;
    state.probeTimer = window.setTimeout(() => {
      state.probeTimer = 0;
      state.probeCamera();
    }, probeDelayMs);
  }

  async function cameraEndpointAvailable() {
    try {
      const infoResponse = await fetch('http://' + location.hostname + '/info?tinman=' + Date.now(), { cache: 'no-store' });
      if (infoResponse.ok) {
        const info = await infoResponse.json();
        if (Number(info.videoPort) > 0) return true;
      }
    } catch (_) {}

    try {
      const response = await fetch('/camera.html?tinman_probe=' + Date.now(), { cache: 'no-store' });
      if (!response.ok) return false;
      const html = await response.text();
      return html.includes('RTCPeerConnection') && html.includes('webrtc_local');
    } catch (_) {
      return false;
    }
  }

  state.probeCamera = async function () {
    if (state.cameraAvailable) {
      startCameraUi();
      return;
    }
    if (state.probeInFlight) return;

    state.probeInFlight = true;
    const available = await cameraEndpointAvailable();
    state.probeInFlight = false;
    if (available) startCameraUi();
    else scheduleProbe();
  };

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && state.cameraAvailable && !cameraIsLive()) state.connectCamera(true);
  });

  state.probeCamera();
})();
)JS";
        return script.c_str();
    }
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
        static const std::string script =
R"JS(
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

    // Mainsail owns its dashboard card grid through Vue. Adding a foreign child
    // to that managed tree causes Vue to remount the dashboard on subsequent
    // status renders, which tears down and recreates every Moonraker WebSocket.
    // Keep the Tinman panel at body level so its polling and controls cannot
    // invalidate Mainsail's virtual DOM.
    panel.className = 'tinman-qidi-box-card v-card v-sheet collapsable-card mb-2 mb-sm-4 tq-floating-fallback ' + fluiddThemeClass();
    if (panel.parentNode !== document.body)
      document.body.appendChild(panel);
    return false;
  }
)JS"
R"JS(

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
)JS"
R"JS(

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
)JS"
R"JS(

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
        return script.c_str();
    }
};

} // namespace

std::unique_ptr<PrinterWebViewHandler> create_printer_webview_handler(PrinterWebView& owner)
{
    const std::string selected_agent_id = selected_machine_agent_id();
    if (!selected_agent_id.empty()) {
        if (selected_agent_id == "qidi")
            return std::make_unique<QidiBoxPrinterWebViewHandler>(owner);
        if (selected_agent_id == "crealityprint")
            return std::make_unique<CrealityPrinterWebViewHandler>(owner);

        return std::make_unique<PrinterWebViewHandler>(owner);
    }

    auto     cfg = get_active_printer_config();
    if (cfg != nullptr) {
        const auto* host_type_opt = cfg->option<ConfigOptionEnum<PrintHostType>>("host_type");
        if (host_type_opt != nullptr && host_type_opt->value == PrintHostType::htElegooLink)
            return std::make_unique<ElegooPrinterWebViewHandler>(owner);

        if (config_agent_id(*cfg) == "qidi")
            return std::make_unique<QidiBoxPrinterWebViewHandler>(owner);
        if (config_agent_id(*cfg) == "crealityprint")
            return std::make_unique<CrealityPrinterWebViewHandler>(owner);
    }

    return std::make_unique<PrinterWebViewHandler>(owner);
}

} // GUI
} // Slic3r
