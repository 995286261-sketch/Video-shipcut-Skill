"""v1.34.0 G4 能力预检硬闸（用户令 2026-10-22：申报类=硬闸+如实披露豁免，禁软提醒）。
进程内测闸函数与路由函数，不触发真实装配。"""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load_script(relative_path):
    script_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location("g4a_under_test", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(script_path.parent))
    return module


G4 = load_script("skill/local-video-render/scripts/g4_assemble.py")


def iso(offset_minutes=0):
    moment = datetime.now(timezone.utc).astimezone() + timedelta(minutes=offset_minutes)
    return moment.isoformat(timespec="seconds")


class CapabilityAuditGateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audit = Path(self.temp.name) / "能力盘点-v0.1.json"
        self.audit.write_text(json.dumps({"kind": "capability-audit"}), encoding="utf-8")
        self.sha = G4.sha256(self.audit)

    def state(self, probed, approved, missing=None, sha=None):
        return {"nodes": {"G3": {"approval": {"approvedAt": approved} if approved else None}},
                "capabilityAudit": {"file": str(self.audit), "sha256": sha or self.sha,
                                    "probedAt": probed, "summary": {"ready": 7},
                                    "missing": missing or []}}

    def test_fresh_audit_binds(self):
        block = G4.capability_audit_gate(self.state(iso(10), iso(0)))
        self.assertEqual(block["status"], "bound")
        self.assertEqual(block["sha256"], self.sha)

    def test_stale_audit_strikes(self):
        with self.assertRaises(ValueError) as caught:
            G4.capability_audit_gate(self.state(iso(-30), iso(0)))
        self.assertIn("旧于最近一次 G3 批准", str(caught.exception))
        self.assertIn("capability-audit-waiver", str(caught.exception))  # 罢工必须点名出路

    def test_tampered_or_replaced_artifact_strikes(self):
        with self.assertRaises(ValueError):
            G4.capability_audit_gate(self.state(iso(0), "", sha="0" * 64))
        moved = self.state(iso(0), "")
        moved["capabilityAudit"]["file"] = str(Path(self.temp.name) / "不在盘上.json")
        with self.assertRaises(ValueError):
            G4.capability_audit_gate(moved)

    def test_z_suffix_timestamps_parse(self):
        # 老 state 实盘形制（banshee G3 approvedAt 带 Z）+ 新盘点带 +08:00：混排必须可比
        block = G4.capability_audit_gate(self.state(iso(0), "2026-10-09T10:50:15Z"))
        self.assertEqual(block["status"], "bound")
        stale = self.state("2026-10-09T08:00:00Z", "2026-10-09T10:50:15Z")
        with self.assertRaises(ValueError):
            G4.capability_audit_gate(stale)

    def test_garbage_timestamp_strikes(self):
        with self.assertRaises(ValueError) as caught:
            G4.capability_audit_gate(self.state("昨天", ""))
        self.assertIn("无法解析", str(caught.exception))

    def test_missing_block_is_disclosed_legacy_not_silent(self):
        block = G4.capability_audit_gate({"nodes": {}})
        self.assertEqual(block["status"], "legacy-unaudited")
        self.assertTrue(block["disclosure"])

    def test_missing_gaps_surface_in_block(self):
        block = G4.capability_audit_gate(self.state(iso(0), "", missing=[{"id": "listen"}]))
        self.assertEqual(block["status"], "bound")
        self.assertIn("摊上", block["disclosure"])


class ResolveCapabilityBlockTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / "pipeline-state.json"

    def state(self, audit_block=None):
        payload = {"nodes": {"G3": {"approval": None}}}
        if audit_block is not None:
            payload["capabilityAudit"] = audit_block
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        return self.state_path

    def test_waiver_needs_nonempty_text(self):
        with self.assertRaises(ValueError):
            G4.resolve_capability_block(None, "   ")
        block = G4.resolve_capability_block(None, "我知道盘点过期，照常渲染")
        self.assertEqual(block["status"], "waived")
        self.assertEqual(block["reason"], "我知道盘点过期，照常渲染")

    def test_double_flag_is_mutually_exclusive(self):
        path = self.state({"file": "x.json", "sha256": "0" * 64, "probedAt": iso(0),
                           "summary": {}, "missing": []})
        with self.assertRaises(ValueError) as caught:
            G4.resolve_capability_block(path, "既持证又豁免")
        self.assertIn("互斥", str(caught.exception))

    def test_no_state_channel_is_disclosed_legacy(self):
        block = G4.resolve_capability_block(None, None)
        self.assertEqual(block["status"], "legacy-unwired")
        self.assertTrue(block["disclosure"])

    def test_state_without_block_routes_to_gate(self):
        path = self.state()
        block = G4.resolve_capability_block(path, None)
        self.assertEqual(block["status"], "legacy-unaudited")


if __name__ == "__main__":
    unittest.main()
