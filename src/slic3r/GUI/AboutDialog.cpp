#include "AboutDialog.hpp"
#include "I18N.hpp"
#include "TinManBuildInfo.hpp"

#include "libslic3r/Utils.hpp"
#include "libslic3r/Color.hpp"
#include "GUI.hpp"
#include "GUI_App.hpp"
#include "MainFrame.hpp"
#include "format.hpp"
#include "Widgets/Button.hpp"

#include <wx/clipbrd.h>

namespace Slic3r {
namespace GUI {

AboutDialogLogo::AboutDialogLogo(wxWindow* parent)
    : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxDefaultSize)
{
    this->SetBackgroundColour(*wxWHITE);
    this->logo = ScalableBitmap(this, Slic3r::var("TinManX1_192px.png"), wxBITMAP_TYPE_PNG);
    this->SetMinSize(this->logo.GetBmpSize());

    this->Bind(wxEVT_PAINT, &AboutDialogLogo::onRepaint, this);
}

void AboutDialogLogo::onRepaint(wxEvent &event)
{
    wxPaintDC dc(this);
    dc.SetBackgroundMode(wxTRANSPARENT);

    wxSize size = this->GetSize();
    int logo_w = this->logo.GetBmpWidth();
    int logo_h = this->logo.GetBmpHeight();
    dc.DrawBitmap(this->logo.bmp(), (size.GetWidth() - logo_w)/2, (size.GetHeight() - logo_h)/2, true);

    event.Skip();
}


// -----------------------------------------
// CopyrightsDialog
// -----------------------------------------
CopyrightsDialog::CopyrightsDialog()
    : DPIDialog(static_cast<wxWindow*>(wxGetApp().mainframe), wxID_ANY, from_u8((boost::format("%1% - %2%")
        % (wxGetApp().is_editor() ? SLIC3R_APP_FULL_NAME : GCODEVIEWER_APP_NAME)
        % _utf8(L("Credits and Licenses"))).str()),
        wxDefaultPosition, wxDefaultSize, wxDEFAULT_DIALOG_STYLE | wxRESIZE_BORDER)
{
    this->SetFont(wxGetApp().normal_font());
	this->SetBackgroundColour(*wxWHITE);

    wxStaticLine *staticline1 = new wxStaticLine( this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxLI_HORIZONTAL );

	auto sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add( staticline1, 0, wxEXPAND | wxALL, 5 );

    fill_entries();

    m_html = new wxHtmlWindow(this, wxID_ANY, wxDefaultPosition,
                              wxSize(40 * em_unit(), 20 * em_unit()), wxHW_SCROLLBAR_AUTO);
    m_html->SetMinSize(wxSize(FromDIP(620), FromDIP(440)));
    m_html->SetBackgroundColour(*wxWHITE);
    wxFont font = get_default_font(this);
    const int fs = font.GetPointSize();
    const int fs2 = static_cast<int>(1.2f*fs);
    int size[] = { fs, fs, fs, fs, fs2, fs2, fs2 };

    m_html->SetFonts(font.GetFaceName(), font.GetFaceName(), size);
    m_html->SetBorders(2);
    m_html->SetPage(get_html_text());

    sizer->Add(m_html, 1, wxEXPAND | wxALL, 15);
    m_html->Bind(wxEVT_HTML_LINK_CLICKED, &CopyrightsDialog::onLinkClicked, this);

    SetSizer(sizer);
    sizer->SetSizeHints(this);
    CenterOnParent();
    wxGetApp().UpdateDlgDarkUI(this);
}

void CopyrightsDialog::fill_entries()
{
    m_entries = {
        { "Admesh",                                         "",      "https://admesh.readthedocs.io/" },
        { "Anti-Grain Geometry",                            "",      "http://antigrain.com" },
        { "ankerl::unordered_dense",                        "",      "https://github.com/martinus/unordered_dense" },
        { "ArcWelderLib",                                   "",      "https://plugins.octoprint.org/plugins/arc_welder" },
        { "Boost",                                          "",      "http://www.boost.org" },
        { "Cereal",                                         "",      "http://uscilab.github.io/cereal" },
        { "CGAL",                                           "",      "https://www.cgal.org" },
        { "Clipper",                                        "",      "http://www.angusj.co" },
        { "Clipper2",                                       "",      "https://github.com/AngusJohnson/Clipper2" },
        { "libcurl",                                        "",      "https://curl.se/libcurl" },
        { "Draco",                                          "",      "https://google.github.io/draco/" },
        { "Earcut",                                         "",      "https://github.com/mapbox/earcut.hpp" },
        { "Eigen3",                                         "",      "http://eigen.tuxfamily.org" },
        { "Expat",                                          "",      "http://www.libexpat.org" },
        { "fast_float",                                     "",      "https://github.com/fastfloat/fast_float" },
        { "FFmpeg (macOS camera bridge)",                    "",      "https://ffmpeg.org/" },
        { "FreeType",                                       "",      "https://freetype.org/" },
        { "GLAD (Multi-Language GL Loader-Generator)",       "",      "https://github.com/Dav1dde/glad" },
        { "GLFW",                                           "",      "https://www.glfw.org" },
        { "GLU tessellator",                                "",      "https://gitlab.freedesktop.org/mesa/glu" },
        { "GNU gettext",                                    "",      "https://www.gnu.org/software/gettext" },
        { "HIDAPI",                                         "",      "https://github.com/libusb/hidapi" },
        { "ImGUI",                                          "",      "https://github.com/ocornut/imgui" },
        { "ImGuizmo",                                       "",      "https://github.com/CedricGuillemet/ImGuizmo" },
        { "Libigl",                                         "",      "https://libigl.github.io" },
        { "libnest2d",                                      "",      "https://github.com/tamasmeszaros/libnest2d" },
        { "libnoise",                                       "",      "https://github.com/SoftFever/Orca-deps-libnoise" },
        { "libjpeg-turbo",                                  "",      "https://libjpeg-turbo.org/" },
        { "libpng",                                         "",      "https://www.libpng.org/pub/png/libpng.html" },
        { "lib_fts",                                        "",      "https://www.forrestthewoods.com" },
        { "Mesa 3D",                                        "",      "https://mesa3d.org" },
        { "MCUT",                                           "",      "https://github.com/cutdigital/mcut" },
        { "MD4C",                                           "",      "https://github.com/mity/md4c" },
        { "mdns",                                           "",      "https://github.com/mjansson/mdns" },
        { "miniLZO",                                        "",      "https://www.oberhumer.com/opensource/lzo/" },
        { "Miniz",                                          "",      "https://github.com/richgel999/miniz" },
        { "Nanosvg",                                        "",      "https://github.com/memononen/nanosvg" },
        { "nlohmann/json",                                  "",      "https://json.nlohmann.me" },
        { "Qhull",                                          "",      "http://qhull.org" },
        { "Open Cascade",                                   "",      "https://www.opencascade.com" },
        { "OpenCV",                                         "",      "https://opencv.org/" },
        { "OpenGL",                                         "",      "https://www.opengl.org" },
        { "OpenSSL",                                        "",      "https://openssl-library.org/" },
        { "PoEdit",                                         "",      "https://poedit.net" },
        { "PrusaSlicer",                                    "",      "https://www.prusa3d.com" },
        { "QOI",                                            "",      "https://qoiformat.org/" },
        { "Real-Time DXT1/DXT5 C compression library",      "",      "https://github.com/Cyan4973/RygsDXTc" },
        { "SemVer",                                         "",      "https://semver.org" },
        { "Shinyprofiler",                                  "",      "https://code.google.com/p/shinyprofiler" },
        { "Shapely (optional Arc Overhang tooling)",         "",      "https://github.com/shapely/shapely" },
        { "SuperSlicer",                                    "",      "https://github.com/supermerill/SuperSlicer" },
        { "TBB",                                            "",      "https://www.intel.cn/content/www/cn/zh/developer/tools/oneapi/onetbb.html" },
        { "wxWidgets",                                      "",      "https://www.wxwidgets.org" },
        { "zlib",                                           "",      "http://zlib.net" },

    };
}

wxString CopyrightsDialog::get_html_text()
{
    wxColour bgr_clr = wxGetApp().get_window_default_clr();//wxSystemSettings::GetColour(wxSYS_COLOUR_WINDOW);

    const auto text_clr = wxGetApp().get_label_clr_default();// wxSystemSettings::GetColour(wxSYS_COLOUR_WINDOWTEXT);
    const auto text_clr_str = encode_color(ColorRGB(text_clr.Red(), text_clr.Green(), text_clr.Blue()));
    const auto bgr_clr_str = encode_color(ColorRGB(bgr_clr.Red(), bgr_clr.Green(), bgr_clr.Blue()));

    wxString text = wxString::Format(
        "<html>"
            "<body bgcolor= %s link= %s>"
            "<font color=%s>"
                "<font size=\"5\">%s</font><br/>"
                "<font size=\"5\">%s</font>"
                "<a href=\"%s\">%s.</a><br/>"
                "<font size=\"5\">%s.</font><br/>"
                "<br /><br />"
                "<font size=\"3\">",
         bgr_clr_str, text_clr_str, text_clr_str,
        _L("License"),
        _L("TinManX1 is based on Orca Slicer and is licensed under "),
        "https://www.gnu.org/licenses/agpl-3.0.html",_L("GNU Affero General Public License, version 3"),
        _L("Upstream copyrights and third-party license notices are retained"));

    const auto append_credits = [&text](const wxString& heading, const std::vector<Entry>& entries) {
        text += "<h3>" + heading + "</h3>";
        for (const auto& entry : entries) {
            text += wxString::Format("<p><b>%s</b><br/>%s<br/><a href=\"%s\">%s</a></p>",
                from_u8(entry.lib_name), from_u8(entry.copyright), from_u8(entry.link), _L("Source and details"));
        }
    };

    append_credits(_L("TinManX1 Contributors"), {
        { "William Tinney / Tinman-FP", "Project stewardship, requirements, printer testing, validation feedback, and release direction.", "https://github.com/Tinman-FP/TinManX1" },
        { "OpenAI Codex", "AI-assisted engineering, implementation, review, regression tests, documentation, and packaging under project direction.", "https://openai.com/codex/" },
    });
    append_credits(_L("Upstream Slicer Projects"), {
        { "OrcaSlicer / SoftFever and contributors", "Primary application and slicing baseline: OrcaSlicer 2.4.2.", "https://github.com/OrcaSlicer/OrcaSlicer" },
        { "Bambu Studio / Bambu Lab and contributors", "Upstream application lineage and printer integration work.", "https://github.com/bambulab/BambuStudio" },
        { "PrusaSlicer / Prusa Research and contributors", "Upstream slicing lineage; selected profile-reliability improvements inspired by PrusaSlicer 3.0.0-alpha11. Not a full PrusaSlicer 3 rebase.", "https://github.com/prusa3d/PrusaSlicer" },
        { "Slic3r / Alessandro Ranellucci and the RepRap community", "Original slicer foundation and community contributions.", "https://github.com/slic3r/Slic3r" },
        { "SuperSlicer / supermerill and contributors", "Community slicing enhancements inherited through the upstream family.", "https://github.com/supermerill/SuperSlicer" },
        { "Cura / UltiMaker and contributors", "Algorithm contributions acknowledged by the OrcaSlicer upstream project.", "https://github.com/Ultimaker/Cura" },
    });
    append_credits(_L("Feature Sources and Research"), {
        { "Wave Overhangs / Dennis Klappe and contributors", "OrcaSlicer integration; the current port follows upstream v0.4.0.", "https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs" },
        { "Janis A. Andersons, Salome Sanchez, and Tom Vaneker", "Wave-inspired overhang research; Janis A. Andersons also authored the wavefront generator used by the implementation.", "https://doi.org/10.1016/j.addlet.2026.100392" },
        { "Steven McCulloch / layershift3d", "Arc Overhang concept and PrusaSlicer Wave Overhangs lineage.", "https://github.com/stmcculloch" },
        { "Nicolai Wachenschwan", "PrusaSlicer Arc Overhang integration.", "https://github.com/nicolai-wachenschwan/arc-overhang-prusaslicer-integration" },
        { "Kelsch", "OrcaSlicer Arc Overhang integration; its GPL-3.0 notices remain with the bundled adapter sources.", "https://github.com/Kelsch/arc-overhang-orcaslicer-integration" },
        { "Rieks Kaiser / LaSO", "Laterally supported overhang research reference.", "https://github.com/riekskaiser/wave_LaSO" },
        { "Klipper contributors", "Printer-control and calibration compatibility references.", "https://www.klipper3d.org/" },
        { "Moonraker / Arksine and contributors", "HTTP and WebSocket API reference for supported printer integrations.", "https://github.com/Arksine/moonraker" },
        { "CNC Kitchen / Stefan Hermann and ModBot", "Material, flow, pressure-advance, and calibration research references.", "https://github.com/Tinman-FP/TinManX1/blob/agent/snapmaker-live-filament-sync/ATTRIBUTION.md" },
        { "Anonoei / Klipper Auto Speed", "Missed-step search research reference; no Auto Speed source code is vendored.", "https://github.com/Anonoei/klipper_auto_speed" },
        { "Andrew Ellis and Frix-x / Shake&amp;Tune", "Motion-limit validation and vibration-analysis references; no Shake&amp;Tune source code is vendored.", "https://github.com/Tinman-FP/TinManX1/blob/agent/snapmaker-live-filament-sync/ATTRIBUTION.md" },
        { "MechaniCalc, Autodesk, SOLIDWORKS, and additive-manufacturing researchers", "Strength Lens mechanics and visualization references. Strength Lens is advisory, not certified FEA.", "https://github.com/Tinman-FP/TinManX1/blob/agent/snapmaker-live-filament-sync/SoftFever_doc/orcaslicer_codex_feature_attribution.md" },
        { "Rocket / FibreSeek", "Interoperability research only. No proprietary source code, assets, or endorsement is claimed.", "https://github.com/Tinman-FP/TinManX1/blob/agent/snapmaker-live-filament-sync/NOTICE.md" },
    });
    text += "<p><a href=\"https://github.com/Tinman-FP/TinManX1/blob/agent/snapmaker-live-filament-sync/ATTRIBUTION.md\">"
            "Full attribution and source ledgers</a></p>";
    text += "<h3>" + _L("Libraries") + "</h3><p>" +
        _L("This software uses open source components whose copyright and other proprietary rights belong to their respective owners") + "</p>";

    for (auto& entry : m_entries) {
        text += format_wxstr(
                    "%s<br/>"
                    , entry.lib_name);

         text += wxString::Format(
                    "<a href=\"%s\">%s</a><br/><br/>"
                    , entry.link, entry.link);
    }

    text += wxString(
                "</font>"
            "</font>"
            "</body>"
        "</html>");

    return text;
}

void CopyrightsDialog::on_dpi_changed(const wxRect &suggested_rect)
{
    const wxFont& font = GetFont();
    const int fs = font.GetPointSize();
    const int fs2 = static_cast<int>(1.2f*fs);
    int font_size[] = { fs, fs, fs, fs, fs2, fs2, fs2 };

    m_html->SetFonts(font.GetFaceName(), font.GetFaceName(), font_size);

    const int& em = em_unit();

    msw_buttons_rescale(this, em, { wxID_CLOSE });

    const wxSize size(FromDIP(620), FromDIP(440));

    m_html->SetMinSize(size);
    m_html->Refresh();

    SetMinSize(size);
    Fit();

    Refresh();
}

void CopyrightsDialog::onLinkClicked(wxHtmlLinkEvent &event)
{
    wxGetApp().open_browser_with_warning_dialog(event.GetLinkInfo().GetHref());
    event.Skip(false);
}

void CopyrightsDialog::onCloseDialog(wxEvent &)
{
     this->EndModal(wxID_CLOSE);
}

AboutDialog::AboutDialog()
    : DPIDialog(static_cast<wxWindow *>(wxGetApp().mainframe),wxID_ANY,from_u8((boost::format(_utf8(L("About %s"))) % (wxGetApp().is_editor() ? SLIC3R_APP_FULL_NAME : GCODEVIEWER_APP_NAME)).str()),wxDefaultPosition,
        wxDefaultSize, /*wxCAPTION*/wxDEFAULT_DIALOG_STYLE)
{
    SetFont(wxGetApp().normal_font());
	SetBackgroundColour(*wxWHITE);

    wxBoxSizer *ver_sizer = new wxBoxSizer(wxVERTICAL);
    auto main_sizer = new wxBoxSizer(wxVERTICAL);
    auto header = new wxBoxSizer(wxHORIZONTAL);
    auto identity = new wxBoxSizer(wxVERTICAL);

    // NanoSVG does not render SVG text. Keep the product name and build identity native.
    m_logo_bitmap = ScalableBitmap(this, "TinManX1_192px", 96);
    m_logo = new wxStaticBitmap(this, wxID_ANY, m_logo_bitmap.bmp());
    header->Add(m_logo, 0, wxRIGHT | wxALIGN_CENTER_VERTICAL, FromDIP(20));
    auto name = new wxStaticText(this, wxID_ANY, "TinManX1");
    name->SetFont(GetFont().Scaled(1.85f).Bold());
    identity->Add(name, 0, wxBOTTOM, FromDIP(8));
    const wxString revision = wxString::FromUTF8(TINMANX1_REVISION) + "\n" +
                              wxString::Format("Build %s", std::string(GIT_COMMIT_HASH));
    auto version = new wxStaticText(this, wxID_ANY, revision);
    version->SetFont(Label::Body_12);
    identity->Add(version, 0, wxBOTTOM, FromDIP(8));
    auto upstream = new wxStaticText(this, wxID_ANY,
        _L("Based on OrcaSlicer") + " " + wxString::FromUTF8(SoftFever_VERSION));
    upstream->SetFont(Label::Body_12);
    identity->Add(upstream);
    header->Add(identity, 1, wxALIGN_CENTER_VERTICAL);
    main_sizer->Add(header, 0, wxALL | wxEXPAND, FromDIP(20));
    main_sizer->Add(new wxStaticLine(this), 0, wxLEFT | wxRIGHT | wxEXPAND, FromDIP(20));
    main_sizer->Add(ver_sizer, 0, wxEXPAND);

    wxBoxSizer *text_sizer_horiz = new wxBoxSizer(wxHORIZONTAL);
    wxBoxSizer *text_sizer = new wxBoxSizer(wxVERTICAL);
    text_sizer_horiz->Add( 0, 0, 0, wxLEFT, FromDIP(20));

    std::vector<wxString> text_list;
    text_list.push_back(_L("An independent slicer maintained by William Tinney / Tinman-FP, with OpenAI Codex engineering assistance and community contributions."));
    text_list.push_back(_L("Built on OrcaSlicer by SoftFever and contributors, with foundations and contributions from Bambu Studio, PrusaSlicer, Slic3r, SuperSlicer, and Cura."));
    text_list.push_back(_L("Includes selected improvements inspired by PrusaSlicer 3.0.0-alpha11: profile ownership, derived-state handling, and layer-height inheritance. This is not a full PrusaSlicer 3 rebase."));
    text_list.push_back(_L("Feature authors, research references, and third-party libraries are acknowledged in Credits and Licenses. TinManX1 is not affiliated with or endorsed by the upstream projects or printer manufacturers."));

    text_sizer->Add( 0, 0, 0, wxTOP, FromDIP(16));
    bool is_zh = wxGetApp().app_config->get("language") == "zh_CN";
    for (int i = 0; i < text_list.size(); i++)
    {
        auto staticText = new wxStaticText( this, wxID_ANY, wxEmptyString,wxDefaultPosition,wxSize(FromDIP(520), -1), wxALIGN_LEFT );
        staticText->SetForegroundColour(wxColour(107, 107, 107));
        staticText->SetBackgroundColour(*wxWHITE);
        staticText->SetMinSize(wxSize(FromDIP(520), -1));
        staticText->SetFont(Label::Body_12);
        if (is_zh) {
            wxString find_txt = "";
            wxString count_txt = "";
            for (auto  o = 0; o < text_list[i].length(); o++) {
                auto size = staticText->GetTextExtent(count_txt);
                if (size.x < FromDIP(506)) {
                    find_txt += text_list[i][o];
                    count_txt += text_list[i][o];
                } else {
                    find_txt += "\n";
                    find_txt += text_list[i][o];
                    count_txt = text_list[i][o];
                }
            }
            staticText->SetLabel(find_txt);
        } else {
            staticText->SetLabel(text_list[i]);
            staticText->Wrap(FromDIP(520));
        }

        text_sizer->Add( staticText, 0, wxUP | wxDOWN, FromDIP(3));
    }

    text_sizer_horiz->Add(text_sizer, 1, wxRIGHT, FromDIP(20));
    ver_sizer->Add(text_sizer_horiz, 0, wxALL,0);
    ver_sizer->Add( 0, 0, 0, wxTOP, FromDIP(20));

    wxBoxSizer *copyright_ver_sizer = new wxBoxSizer(wxVERTICAL);
    wxBoxSizer *copyright_hor_sizer = new wxBoxSizer(wxHORIZONTAL);

    copyright_hor_sizer->Add(copyright_ver_sizer, 0, wxLEFT, FromDIP(20));

    wxStaticText *html_text = new wxStaticText(this, wxID_ANY, "AGPL-3.0-or-later. Upstream notices retained.", wxDefaultPosition, wxDefaultSize);
    html_text->SetFont(Label::Body_12);
    html_text->Wrap(FromDIP(300));
    html_text->SetForegroundColour(wxColour(107, 107, 107));

    copyright_ver_sizer->Add(html_text, 0, wxALL , 0);

    m_html = new wxHtmlWindow(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxHW_SCROLLBAR_NEVER /*NEVER*/);
      {
          wxFont font = get_default_font(this);
          const int fs = font.GetPointSize()-1;
          int size[] = {fs,fs,fs,fs,fs,fs,fs};
          m_html->SetFonts(font.GetFaceName(), font.GetFaceName(), size);
          m_html->SetMinSize(wxSize(FromDIP(-1), FromDIP(16)));
          m_html->SetBorders(2);
          const auto text = from_u8(
              (boost::format(
              "<html>"
              "<body>"
              "<p style=\"text-align:left\"><a style=\"color:#009789\" href=\"https://github.com/Tinman-FP/TinManX1\">TinManX1 on GitHub</a></p>"
              "</body>"
              "</html>")
            ).str());
          m_html->SetPage(text);
          copyright_ver_sizer->Add(m_html, 0, wxEXPAND, 0);
          m_html->Bind(wxEVT_HTML_LINK_CLICKED, &AboutDialog::onLinkClicked, this);
      }
    Button* button_portions = new Button(this, _L("Credits and Licenses"));
    m_copy_rights_btn_id = button_portions->GetId();
    button_portions->SetStyle(ButtonStyle::Regular, ButtonType::Window);

    wxBoxSizer *copyright_button_ver = new wxBoxSizer(wxVERTICAL);
    copyright_button_ver->Add( 0, 0, 0, wxTOP, FromDIP(10));
    copyright_button_ver->Add(button_portions, 0, wxALL,0);

    copyright_hor_sizer->AddStretchSpacer();
    copyright_hor_sizer->Add(copyright_button_ver, 0, wxRIGHT, FromDIP(20));

    ver_sizer->Add(copyright_hor_sizer, 0, wxEXPAND ,0);
    ver_sizer->Add( 0, 0, 0, wxTOP, FromDIP(20));
    button_portions->Bind(wxEVT_BUTTON, &AboutDialog::onCopyrightBtn, this);

    wxGetApp().UpdateDlgDarkUI(this);
	SetSizer(main_sizer);
    Layout();
    Fit();
    CenterOnParent();
}

void AboutDialog::on_dpi_changed(const wxRect &suggested_rect)
{
    m_logo_bitmap.msw_rescale();
    m_logo->SetBitmap(m_logo_bitmap.bmp());

    const wxFont& font = GetFont();
    const int fs = font.GetPointSize() - 1;
    int font_size[] = { fs, fs, fs, fs, fs, fs, fs };
    m_html->SetFonts(font.GetFaceName(), font.GetFaceName(), font_size);

    const int& em = em_unit();

    msw_buttons_rescale(this, em, { wxID_CLOSE, m_copy_rights_btn_id });

    m_html->SetMinSize(wxSize(-1, FromDIP(16)));
    m_html->Refresh();

    Fit();
    Refresh();
}

void AboutDialog::onLinkClicked(wxHtmlLinkEvent &event)
{
    wxGetApp().open_browser_with_warning_dialog(event.GetLinkInfo().GetHref());
    event.Skip(false);
}

void AboutDialog::onCloseDialog(wxEvent &)
{
    this->EndModal(wxID_CLOSE);
}

void AboutDialog::onCopyrightBtn(wxEvent &)
{
    CopyrightsDialog dlg;
    dlg.ShowModal();
}

void AboutDialog::onCopyToClipboard(wxEvent&)
{
    wxTheClipboard->Open();
    wxTheClipboard->SetData(new wxTextDataObject(_L("Version") + " " + GUI_App::format_display_version()));
    wxTheClipboard->Close();
}

} // namespace GUI
} // namespace Slic3r
