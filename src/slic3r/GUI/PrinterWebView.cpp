#include "PrinterWebView.hpp"

#include "I18N.hpp"
#include "DeviceManager.hpp"
#include "MediaPlayCtrl.h"
#include "PrinterWebViewHandler.hpp"
#include "slic3r/GUI/PrinterWebView.hpp"
#include "slic3r/GUI/Widgets/Button.hpp"
#include "slic3r/GUI/wxExtensions.hpp"
#include "slic3r/GUI/wxMediaCtrl2.h"
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/MainFrame.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r_version.h"

#include <boost/algorithm/string.hpp>
#include <boost/asio.hpp>
#include <boost/filesystem/path.hpp>
#include <algorithm>
#include <chrono>
#include <mutex>
#include <thread>
#include <vector>
#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/string.h>
#include <wx/textdlg.h>
#include <wx/toolbar.h>
#include <wx/uri.h>

#include <slic3r/GUI/Widgets/WebView.hpp>
#include <wx/webview.h>

#ifdef __linux__
#include <webkit2/webkit2.h>
#endif

namespace Slic3r {
namespace GUI {

namespace {

bool active_printer_is_prusa()
{
    if (wxGetApp().preset_bundle == nullptr)
        return false;

    const Preset& preset = wxGetApp().preset_bundle->printers.get_edited_preset();
    std::string identity = preset.name;
    for (const char* key : {"printer_model", "printer_settings_id", "printer_vendor"}) {
        if (preset.config.has(key))
            identity += " " + preset.config.opt_string(key);
    }
    return boost::algorithm::icontains(identity, "prusa");
}

std::string host_from_printer_url(std::string url)
{
    boost::algorithm::trim(url);
    const size_t scheme = url.find("://");
    if (scheme != std::string::npos)
        url.erase(0, scheme + 3);
    const size_t slash = url.find('/');
    if (slash != std::string::npos)
        url.resize(slash);
    const size_t at = url.rfind('@');
    if (at != std::string::npos)
        url.erase(0, at + 1);
    if (!url.empty() && url.front() == '[') {
        const size_t end = url.find(']');
        return end == std::string::npos ? std::string() : url.substr(1, end - 1);
    }
    const size_t port = url.find(':');
    return port == std::string::npos ? url : url.substr(0, port);
}

std::string normalize_prusa_camera_url(std::string url)
{
    boost::algorithm::trim(url);
    if (url.empty())
        return {};
    if (!boost::algorithm::istarts_with(url, "rtsp://") &&
        !boost::algorithm::istarts_with(url, "rtsps://"))
        url = "rtsp://" + url;

    const size_t authority = url.find("://") + 3;
    if (url.find('/', authority) == std::string::npos)
        url += "/live";
    return url;
}

std::vector<std::string> discover_rtsp_hosts(const std::string& printer_host)
{
    boost::system::error_code ec;
    const auto printer_address = boost::asio::ip::address_v4::from_string(printer_host, ec);
    if (ec)
        return {};

    boost::asio::io_context io;
    std::mutex results_mutex;
    std::vector<std::string> results;
    const auto network = printer_address.to_ulong() & 0xffffff00UL;

    for (unsigned int suffix = 1; suffix < 255; ++suffix) {
        const auto address = boost::asio::ip::address_v4(network | suffix);
        auto socket = std::make_shared<boost::asio::ip::tcp::socket>(io);
        auto timer  = std::make_shared<boost::asio::steady_timer>(io);
        timer->expires_after(std::chrono::milliseconds(1200));
        timer->async_wait([socket](const boost::system::error_code& timer_error) {
            if (!timer_error) {
                boost::system::error_code ignored;
                socket->cancel(ignored);
            }
        });
        socket->async_connect(boost::asio::ip::tcp::endpoint(address, 554),
            [socket, timer, address, &results, &results_mutex](const boost::system::error_code& connect_error) {
                boost::system::error_code ignored;
                timer->cancel(ignored);
                socket->close(ignored);
                if (!connect_error) {
                    std::lock_guard<std::mutex> lock(results_mutex);
                    results.push_back(address.to_string());
                }
            });
    }

    io.run();
    std::sort(results.begin(), results.end());
    return results;
}

} // namespace

#ifdef __linux__
// Workaround for #7210: WebKitGTK crashes on vue-resize's hidden <object> probe used by
// older Fluidd/Mainsail pages. Swap that <object> for a <div> shim at appendChild time
// and bridge resize events through a fake contentDocument.defaultView so vue-resize keeps
// working. Workaround proposed by @VittC.
static void inject_vue_resize_workaround(wxWebView *webView)
{
    webView->AddUserScript(
        "(function() {"
        "  'use strict';"
        "  function isVueResizeObject(el) {"
        "    return el && el.tagName === 'OBJECT'"
        "        && el.type === 'text/html'"
        "        && el.getAttribute('aria-hidden') === 'true'"
        "        && el.getAttribute('tabindex') === '-1';"
        "  }"
        "  function isResizeObserverParent(p) {"
        "    return p && p.classList && p.classList.contains('resize-observer');"
        "  }"
        "  function makeShim(orig, parentForRO) {"
        "    var shim = document.createElement('div');"
        "    shim.setAttribute('aria-hidden', 'true');"
        "    shim.setAttribute('tabindex', '-1');"
        "    shim.style.display = 'none';"
        "    var fakeWin = document.createElement('div');"
        "    var ro = null;"
        "    var origRemoveEL = fakeWin.removeEventListener.bind(fakeWin);"
        "    fakeWin.removeEventListener = function(type, fn, opts) {"
        "      origRemoveEL(type, fn, opts);"
        "      if (type === 'resize' && ro) { ro.disconnect(); ro = null; }"
        "    };"
        "    Object.defineProperty(shim, 'contentDocument', {"
        "      configurable: true,"
        "      get: function() { return { defaultView: fakeWin }; }"
        "    });"
        "    Object.defineProperty(shim, 'contentWindow', {"
        "      configurable: true,"
        "      get: function() { return fakeWin; }"
        "    });"
        "    if (typeof orig.onload === 'function') { shim.onload = orig.onload; }"
        "    queueMicrotask(function() {"
        "      if (parentForRO && typeof ResizeObserver !== 'undefined') {"
        "        ro = new ResizeObserver(function() {"
        "          fakeWin.dispatchEvent(new Event('resize'));"
        "        });"
        "        ro.observe(parentForRO);"
        "      }"
        "      if (typeof shim.onload === 'function') {"
        "        try { shim.onload(new Event('load')); } catch (e) {}"
        "      }"
        "      shim.dispatchEvent(new Event('load'));"
        "    });"
        "    return shim;"
        "  }"
        "  var origAppend = Node.prototype.appendChild;"
        "  Node.prototype.appendChild = function(child) {"
        "    if (isResizeObserverParent(this) && isVueResizeObject(child)) {"
        "      return origAppend.call(this, makeShim(child, this));"
        "    }"
        "    return origAppend.call(this, child);"
        "  };"
        "  var origInsertBefore = Node.prototype.insertBefore;"
        "  Node.prototype.insertBefore = function(child, ref) {"
        "    if (isResizeObserverParent(this) && isVueResizeObject(child)) {"
        "      return origInsertBefore.call(this, makeShim(child, this), ref);"
        "    }"
        "    return origInsertBefore.call(this, child, ref);"
        "  };"
        "  console.log('[vr-fix] vue-resize WebKitGTK patch active');"
        "})();",
        wxWEBVIEW_INJECT_AT_DOCUMENT_START
    );
}
#endif

PrinterWebView::PrinterWebView(wxWindow *parent)
        : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize)
    , m_browser(nullptr)
    , m_prusa_camera_panel(nullptr)
    , m_prusa_camera_media(nullptr)
    , m_prusa_camera_player(nullptr)
    , m_prusa_camera_refresh(nullptr)
    , m_prusa_camera_settings(nullptr)
    , m_zoomFactor(100)
    , m_apikey()
    , m_apikey_sent(false)
    , m_url_deferred()
    , m_handler(std::make_unique<PrinterWebViewHandler>(*this))
    , m_prusa_camera_token(std::make_shared<int>(0))
    , m_prusa_camera_generation(0)
 {

    wxBoxSizer* topsizer = new wxBoxSizer(wxVERTICAL);

    m_prusa_camera_panel = new wxPanel(this);
    m_prusa_camera_panel->SetBackgroundColour(*wxBLACK);
    wxBoxSizer* camera_sizer = new wxBoxSizer(wxVERTICAL);
    wxPanel* camera_header = new wxPanel(m_prusa_camera_panel);
    camera_header->SetBackgroundColour(*wxWHITE);
    wxBoxSizer* camera_header_sizer = new wxBoxSizer(wxHORIZONTAL);
    wxStaticText* camera_title = new wxStaticText(camera_header, wxID_ANY, _L("CORE One L Camera"));
    camera_title->SetFont(wxGetApp().bold_font());
    m_prusa_camera_refresh = new Button(camera_header, "", "refresh", wxBORDER_NONE, 16);
    m_prusa_camera_refresh->SetToolTip(_L("Find camera"));
    m_prusa_camera_settings = new Button(camera_header, "", "settings", wxBORDER_NONE, 16);
    m_prusa_camera_settings->SetToolTip(_L("Camera address"));
    camera_header_sizer->Add(camera_title, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(12));
    camera_header_sizer->AddStretchSpacer();
    camera_header_sizer->Add(m_prusa_camera_refresh, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(4));
    camera_header_sizer->Add(m_prusa_camera_settings, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(8));
    camera_header->SetSizer(camera_header_sizer);

    m_prusa_camera_media = new wxMediaCtrl2(m_prusa_camera_panel);
    m_prusa_camera_media->SetMinSize(wxSize(-1, FromDIP(260)));
    m_prusa_camera_player = new MediaPlayCtrl(m_prusa_camera_panel, m_prusa_camera_media,
                                               wxDefaultPosition, wxSize(-1, FromDIP(40)));
    camera_sizer->Add(camera_header, 0, wxEXPAND);
    camera_sizer->Add(m_prusa_camera_media, 1, wxEXPAND);
    camera_sizer->Add(m_prusa_camera_player, 0, wxEXPAND);
    m_prusa_camera_panel->SetSizer(camera_sizer);
    m_prusa_camera_panel->Hide();

    m_prusa_camera_refresh->Bind(wxEVT_COMMAND_BUTTON_CLICKED, [this](wxCommandEvent&) {
        start_prusa_camera_discovery();
    });
    m_prusa_camera_settings->Bind(wxEVT_COMMAND_BUTTON_CLICKED, [this](wxCommandEvent&) {
        prompt_for_prusa_camera_url();
    });

      // Create the webview
    m_browser = WebView::CreateWebView(this, "");
    if (m_browser == nullptr) {
        wxLogError("Could not init m_browser");
        return;
    }

#ifdef __linux__
    inject_vue_resize_workaround(m_browser);

    auto cookiesPath = boost::filesystem::path(data_dir() + "/cache/cookies.db");
    auto wv = static_cast<WebKitWebView*>(m_browser->GetNativeBackend());
    auto wv_ctx = webkit_web_view_get_context(wv);
    auto cookieManager = webkit_web_context_get_cookie_manager(wv_ctx);
    webkit_cookie_manager_set_persistent_storage(cookieManager, cookiesPath.c_str(), WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE);
#endif

    m_browser->Bind(wxEVT_WEBVIEW_ERROR, &PrinterWebView::OnError, this);
    m_browser->Bind(wxEVT_WEBVIEW_LOADED, &PrinterWebView::OnLoaded, this);
    m_browser->Bind(wxEVT_WEBVIEW_NEWWINDOW, &PrinterWebView::OnNewWindow, this);
    m_browser->Bind(wxEVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, &PrinterWebView::OnScriptMessage, this);

    SetSizer(topsizer);

    topsizer->Add(m_prusa_camera_panel, 0, wxEXPAND);
    topsizer->Add(m_browser, wxSizerFlags().Expand().Proportion(1));

    update_mode();

    // Log backend information
    /* m_browser->GetUserAgent() may lead crash
    if (wxGetApp().get_mode() == comDevelop) {
        wxLogMessage(wxWebView::GetBackendVersionInfo().ToString());
        wxLogMessage("Backend: %s Version: %s", m_browser->GetClassInfo()->GetClassName(),
            wxWebView::GetBackendVersionInfo().ToString());
        wxLogMessage("User Agent: %s", m_browser->GetUserAgent());
    }
    */

    //Connect the idle events
    Bind(wxEVT_CLOSE_WINDOW, &PrinterWebView::OnClose, this);

 }

PrinterWebView::~PrinterWebView()
{
    BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << " Start";
    SetEvtHandlerEnabled(false);
    m_prusa_camera_token.reset();
    m_handler.reset();

    // Destroy the webview
    if(m_browser){
        m_browser->Destroy();
        m_browser = nullptr;
    }


    BOOST_LOG_TRIVIAL(info) << __FUNCTION__ << " End";
}

void PrinterWebView::load_url(wxString& url, wxString apikey)
{
//    this->Show();
//    this->Raise();
    if (m_browser == nullptr)
        return;
    m_apikey = apikey;
    m_apikey_sent = false;
    m_handler = create_printer_webview_handler(*this);
    m_url_deferred = url;
    update_prusa_camera(url);

    if (this->IsShown()) {
        m_browser->LoadURL(url);
        m_url_deferred.clear();
    }
    //m_browser->SetFocus();
    UpdateState();
}

void PrinterWebView::update_prusa_camera(const wxString& printer_url)
{
    const bool is_prusa = active_printer_is_prusa();
    m_prusa_camera_panel->Show(is_prusa);
    if (!is_prusa) {
        ++m_prusa_camera_generation;
        m_prusa_camera_player->SetDirectStreamURL({}, {}, {});
        Layout();
        return;
    }

    m_prusa_printer_host = host_from_printer_url(into_u8(printer_url));
    const std::string saved_url = wxGetApp().app_config->get("prusa_camera", m_prusa_printer_host);
    if (!saved_url.empty())
        set_prusa_camera_url(saved_url, false);
    else
        start_prusa_camera_discovery();
    Layout();
}

void PrinterWebView::set_prusa_camera_url(const std::string& camera_url, bool persist)
{
    const std::string normalized = normalize_prusa_camera_url(camera_url);
    m_prusa_camera_url = normalized;
    if (persist && !m_prusa_printer_host.empty()) {
        wxGetApp().app_config->set("prusa_camera", m_prusa_printer_host, normalized);
        wxGetApp().app_config->save();
    }

    const std::string identity = "prusa-camera:" + m_prusa_printer_host;
    m_prusa_camera_player->SetDirectStreamURL(normalized, identity,
        normalized.empty() ? _L("Enable Local RTSP in Prusa App, then refresh.") : wxString());
}

void PrinterWebView::start_prusa_camera_discovery()
{
    if (m_prusa_printer_host.empty()) {
        set_prusa_camera_url({}, false);
        return;
    }

    const std::uint64_t generation = ++m_prusa_camera_generation;
    const std::string printer_host = m_prusa_printer_host;
    const std::weak_ptr<int> token = m_prusa_camera_token;
    m_prusa_camera_player->SetDirectStreamURL({}, "prusa-camera:" + printer_host,
                                               _L("Searching for Buddy3D camera..."));

    std::thread([this, token, generation, printer_host] {
        const std::vector<std::string> hosts = discover_rtsp_hosts(printer_host);
        if (token.expired())
            return;
        wxGetApp().CallAfter([this, token, generation, hosts] {
            if (token.expired() || generation != m_prusa_camera_generation)
                return;
            if (hosts.size() == 1) {
                set_prusa_camera_url("rtsp://" + hosts.front() + "/live", true);
            } else if (hosts.empty()) {
                m_prusa_camera_player->SetDirectStreamURL({}, "prusa-camera:" + m_prusa_printer_host,
                    _L("Buddy3D stream not found. Enable Local RTSP in Prusa App, then refresh."));
            } else {
                m_prusa_camera_player->SetDirectStreamURL({}, "prusa-camera:" + m_prusa_printer_host,
                    _L("Multiple camera streams found. Set the Buddy3D camera address."));
            }
        });
    }).detach();
}

void PrinterWebView::prompt_for_prusa_camera_url()
{
    wxTextEntryDialog dialog(this,
        _L("Enter the Buddy3D Local RTSP address or camera IP address."),
        _L("CORE One L Camera"), from_u8(m_prusa_camera_url));
    if (dialog.ShowModal() != wxID_OK)
        return;

    const std::string normalized = normalize_prusa_camera_url(into_u8(dialog.GetValue()));
    if (!normalized.empty() && !boost::algorithm::istarts_with(normalized, "rtsp://") &&
        !boost::algorithm::istarts_with(normalized, "rtsps://")) {
        wxMessageBox(_L("Enter an RTSP address or camera IP address."), _L("CORE One L Camera"),
                     wxOK | wxICON_WARNING, this);
        return;
    }
    ++m_prusa_camera_generation;
    set_prusa_camera_url(normalized, true);
}

bool PrinterWebView::Show(bool show)
{
    if (show && !m_url_deferred.empty()) {
        wxString url = m_url_deferred;
        m_url_deferred.clear();
        m_browser->LoadURL(url);
    }
    return wxPanel::Show(show);
}

void PrinterWebView::reload()
{
    m_browser->Reload();
}

void PrinterWebView::update_mode()
{
    m_browser->EnableAccessToDevTools(wxGetApp().app_config->get_bool("developer_mode"));
}

/**
 * Method that retrieves the current state from the web control and updates the
 * GUI the reflect this current state.
 */
void PrinterWebView::UpdateState() {
  // SetTitle(m_browser->GetCurrentTitle());

}

void PrinterWebView::OnClose(wxCloseEvent& evt)
{
    this->Hide();
}

void PrinterWebView::SendAPIKey()
{
    if (m_apikey_sent || m_apikey.IsEmpty())
        return;
    m_apikey_sent   = true;
    wxString script = wxString::Format(R"(
    // Check if window.fetch exists before overriding
    if (window.fetch) {
        const originalFetch = window.fetch;
        window.fetch = function(input, init = {}) {
            init.headers = init.headers || {};
            init.headers['X-API-Key'] = '%s';
            return originalFetch(input, init);
        };
    }
)",
                                       m_apikey);
    m_browser->RemoveAllUserScripts();
    
    // RemoveAllUserScripts causes WebView to forget about our script message handler, 
    // so re-add it here.
    m_browser->RemoveScriptMessageHandler("wx");
    if (m_browser->AddScriptMessageHandler("wx"))
        WebView::MarkScriptMessageHandlerAdded(m_browser);
    else
        wxLogError("Could not add script message handler");

#ifdef __linux__
    // Re-inject the vue-resize/WebKitGTK workaround that RemoveAllUserScripts just cleared.
    inject_vue_resize_workaround(m_browser);
#endif

    m_browser->AddUserScript(script);
    m_browser->Reload();
}

void PrinterWebView::OnError(wxWebViewEvent &evt)
{
    auto e = "unknown error";
    switch (evt.GetInt()) {
      case wxWEBVIEW_NAV_ERR_CONNECTION:
        e = "wxWEBVIEW_NAV_ERR_CONNECTION";
        break;
      case wxWEBVIEW_NAV_ERR_CERTIFICATE:
        e = "wxWEBVIEW_NAV_ERR_CERTIFICATE";
        break;
      case wxWEBVIEW_NAV_ERR_AUTH:
        e = "wxWEBVIEW_NAV_ERR_AUTH";
        break;
      case wxWEBVIEW_NAV_ERR_SECURITY:
        e = "wxWEBVIEW_NAV_ERR_SECURITY";
        break;
      case wxWEBVIEW_NAV_ERR_NOT_FOUND:
        e = "wxWEBVIEW_NAV_ERR_NOT_FOUND";
        break;
      case wxWEBVIEW_NAV_ERR_REQUEST:
        e = "wxWEBVIEW_NAV_ERR_REQUEST";
        break;
      case wxWEBVIEW_NAV_ERR_USER_CANCELLED:
        e = "wxWEBVIEW_NAV_ERR_USER_CANCELLED";
        break;
      case wxWEBVIEW_NAV_ERR_OTHER:
        e = "wxWEBVIEW_NAV_ERR_OTHER";
        break;
      }
    BOOST_LOG_TRIVIAL(info) << __FUNCTION__<< boost::format(": error loading page %1% %2% %3% %4%") %evt.GetURL() %evt.GetTarget() %e %evt.GetString();
}

void PrinterWebView::OnLoaded(wxWebViewEvent& evt)
{
    if (evt.GetURL().IsEmpty())
        return;
    //ORCA: url loaded successfully, safe to clear
    m_url_deferred.clear();
    SendAPIKey();
  
    if (m_handler != nullptr) {
        m_handler->on_loaded(evt);
        return;
    }
}

void PrinterWebView::OnNewWindow(wxWebViewEvent& evt)
{
  const wxString url = evt.GetURL();
  if (!url.empty())
    wxLaunchDefaultBrowser(url);
  evt.Veto();
}

void PrinterWebView::OnScriptMessage(wxWebViewEvent& evt)
{
  if (m_handler != nullptr)
    m_handler->on_script_message(evt);
}


} // GUI
} // Slic3r
