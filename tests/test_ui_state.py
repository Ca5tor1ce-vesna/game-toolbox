"""应用状态文件的持久化、顺序保护和损坏保护。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_toolbox import config
from core import ui_state


class TestUIState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gt-ui-state-")
        self.path = Path(self.tmp.name)
        self.patch = patch.object(config, "USERDATA_DIR", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def entry(self, time, value=None):
        return {"version": 1, "updatedAt": time, "value": value or {"data": {"characterId": "1503"}}}

    def test_roundtrip_is_file_backed_and_scoped(self):
        a, b = "honkai-star-rail/speed-plan", "honkai-star-rail/aha-speed"
        ui_state.save({"key": a, "entry": self.entry(100)})
        ui_state.save({"key": b, "entry": self.entry(101, {"data": {"maxAV": 400}})})
        raw = json.loads((self.path / "ui-state.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["entries"][a], self.entry(100))
        self.assertEqual(raw["entries"][b]["value"]["data"]["maxAV"], 400)
        self.assertEqual(ui_state.read()["entries"], raw["entries"])
        self.assertTrue(ui_state.read()["storageId"])

    def test_late_request_cannot_overwrite_newer_edit(self):
        ui_state.save({"key": "shell", "entry": self.entry(200)})
        result = ui_state.save({"key": "shell", "entry": self.entry(100, {"old": True})})
        self.assertFalse(result["saved"])
        self.assertEqual(ui_state.load()["entries"]["shell"], self.entry(200))

    def test_invalid_parameters_do_not_write(self):
        for payload in ({"key": "../bad", "entry": self.entry(100)},
                        {"key": "shell", "entry": self.entry(float("nan"))},
                        {"key": "shell", "entry": {"version": 1, "updatedAt": 1, "value": []}},
                        {"key": "shell", "entry": self.entry(1, {"value": float("inf")})},
                        {"key": "shell", "entry": self.entry(1, {"blob": "x" * (513 * 1024)})}):
            with self.assertRaises(ValueError):
                ui_state.save(payload)
        self.assertFalse((self.path / "ui-state.json").exists())

    def test_corrupt_json_is_quarantined(self):
        (self.path / "ui-state.json").write_bytes(b"{broken")
        self.assertEqual(ui_state.load()["entries"], {})
        backup = list(self.path.glob("ui-state.corrupt-*.json"))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_bytes(), b"{broken")

    def test_future_version_is_preserved(self):
        original = '{"version": 2, "entries": {}}'
        (self.path / "ui-state.json").write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "版本"):
            ui_state.save({"key": "shell", "entry": self.entry(1)})
        self.assertEqual((self.path / "ui-state.json").read_text(encoding="utf-8"), original)

    def test_http_route_checks_origin_and_local_client(self):
        from core import server
        handler = server.make_handler(server.ToolboxState.__new__(server.ToolboxState))
        probe = handler.__new__(handler)
        probe.path = "/api/ui-state"
        probe.headers = {"Host": "127.0.0.1:8961", "Origin": "https://other.example"}
        probe.client_address = ("127.0.0.1", 1234)
        responses = []
        probe._json = lambda body, status=200: responses.append((status, body))
        probe._read_json_body = lambda: {"key": "shell", "entry": self.entry(1)}
        probe.do_POST()
        self.assertEqual(responses[-1][0], 403)
        probe.headers = {"Host": "127.0.0.1:8961"}
        probe.client_address = ("192.168.1.2", 1234)
        probe.do_POST()
        self.assertEqual(responses[-1][0], 403)
        probe._api_get("/api/ui-state")
        self.assertEqual(responses[-1][0], 403)
        self.assertFalse((self.path / "ui-state.json").exists())
        probe.client_address = ("127.0.0.1", 1234)
        probe.do_POST()
        self.assertEqual(responses[-1][0], 200)
        probe._api_get("/api/ui-state")
        self.assertEqual(responses[-1][1]["entries"]["shell"], self.entry(1))
