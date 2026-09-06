#ifndef slic3r_PrinterWebView_hpp_
#define slic3r_PrinterWebView_hpp_


#include "wx/artprov.h"
#include "wx/cmdline.h"
#include "wx/notifmsg.h"
#include "wx/settings.h"
#include <wx/webview.h>
#include <wx/string.h>

#if wxUSE_WEBVIEW_EDGE
#include "wx/msw/webview_edge.h"
#endif

#include "wx/webviewarchivehandler.h"
#include "wx/webviewfshandler.h"
#include "wx/numdlg.h"
#include "wx/infobar.h"
#include "wx/filesys.h"
#include "wx/fs_arc.h"
#include "wx/fs_mem.h"
#include "wx/stdpaths.h"
#include <wx/panel.h>
#include <wx/tbarbase.h>
#include "wx/textctrl.h"
#include <wx/timer.h>
#include <cstdint>
#include <memory>
#include <string>

class Button;
class wxMediaCtrl2;

namespace Slic3r {
namespace GUI {

class PrinterWebViewHandler;
class MediaPlayCtrl;


class PrinterWebView : public wxPanel {
public:
    PrinterWebView(wxWindow *parent);
    virtual ~PrinterWebView();

    void load_url(wxString& url, wxString apikey = "");
    void UpdateState();
    void OnClose(wxCloseEvent& evt);
    void OnError(wxWebViewEvent& evt);
    void OnNavigating(wxWebViewEvent& evt);
    void OnLoaded(wxWebViewEvent& evt);
    void OnNewWindow(wxWebViewEvent& evt);
    void OnScriptMessage(wxWebViewEvent& evt);
    void reload();
    void update_mode();

    bool Show(bool show = true) override;

private:
    friend class PrinterWebViewHandler;

    void SendAPIKey();
    void update_prusa_camera(const wxString& printer_url);
    void start_prusa_camera_discovery();
    void set_prusa_camera_url(const std::string& camera_url, bool persist);
    void prompt_for_prusa_camera_url();

    wxWebView* m_browser;
    wxPanel* m_prusa_camera_panel;
    wxMediaCtrl2* m_prusa_camera_media;
    MediaPlayCtrl* m_prusa_camera_player;
    ::Button* m_prusa_camera_refresh;
    ::Button* m_prusa_camera_settings;
    long m_zoomFactor;
    wxString m_apikey;
    bool m_apikey_sent;
    wxString m_url_deferred;
    std::string m_requested_endpoint;
    std::unique_ptr<PrinterWebViewHandler> m_handler;
    std::shared_ptr<int> m_prusa_camera_token;
    std::string m_prusa_printer_host;
    std::string m_prusa_camera_url;
    std::uint64_t m_prusa_camera_generation;

    // DECLARE_EVENT_TABLE()
};

} // GUI
} // Slic3r

#endif /* slic3r_Tab_hpp_ */
