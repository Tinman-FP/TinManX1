#!/usr/bin/env python3
"""Guard GUI handoff boundaries that cannot be exercised by headless wx tests.

These source contracts supplement native agent tests and live GUI acceptance;
they do not simulate the proprietary Bambu networking plug-in.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def section(path, start, end):
    source = (ROOT / path).read_text(encoding="utf-8")
    return source.split(start, 1)[1].split(end, 1)[0]


class PrinterHandoffContract(unittest.TestCase):
    def test_button_teardown_releases_capture_and_capture_loss_cancels_click(self):
        destructor = section("src/slic3r/GUI/Widgets/Button.cpp", "Button::~Button()", "void Button::mouseDown(")
        self.assertIn("if (HasCapture())", destructor)
        self.assertIn("ReleaseMouse()", destructor)
        lost = section("src/slic3r/GUI/Widgets/Button.cpp", "void Button::mouseCaptureLost(", "void Button::keyDownUp(")
        self.assertIn("pressedDown = false", lost)
        self.assertNotIn("mouseReleased(", lost)
        self.assertNotIn("sendButtonEvent(", lost)

    def test_lan_success_is_validated_after_queueing_before_sending(self):
        body = section("src/slic3r/GUI/GUI_App.cpp",
                       "m_agent->set_on_local_connect_fn(\n            [this](int state, std::string dev_id, std::string msg)",
                       "auto message_arrive_fn =")
        self.assertLess(body.index("lan_connection_generation(dev_id)"), body.index("CallAfter("))
        self.assertIn("[this, state, dev_id, msg, generation]", body)
        self.assertLess(body.index("is_current_lan_connection(dev_id, generation)"),
                        body.index("obj->command_request_push_all(true)"))

    def test_rendering_filament_inventory_does_not_switch_or_connect_agents(self):
        body = section("src/slic3r/GUI/Plater.cpp",
                       "Sidebar::build_filament_ams_list(MachineObject* obj)",
                       "int Sidebar::get_sidebar_pos_right_x()")
        for call in ("sidebar_ensure_printer_agent_for_machine(", "connect_printer(",
                     "fetch_filament_info(", "set_printer_agent("):
            self.assertNotIn(call, body)

    def test_selection_is_committed_before_observers_read_it(self):
        body = section("src/slic3r/GUI/DeviceCore/DevManager.cpp",
                       "bool DeviceManager::set_selected_machine(std::string dev_id)",
                       "MachineObject* DeviceManager::get_selected_machine()")
        self.assertLess(body.index("selected_machine = dev_id;"),
                        body.index("OnSelectedMachineChanged("))

    def test_only_explicit_sync_pulls_inventory(self):
        body = section("src/slic3r/GUI/Plater.cpp",
                       "void Sidebar::sync_ams_list(bool is_from_big_sync_btn)",
                       "auto & list =")
        self.assertIn("sidebar_refresh_filament_info(obj)", body)
        self.assertLess(body.index("sidebar_refresh_filament_info(obj)"),
                        body.index("load_ams_list(obj)"))


if __name__ == "__main__":
    unittest.main()
