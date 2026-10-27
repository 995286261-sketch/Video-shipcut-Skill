"""v1.34.0 能力预检申报（用户令 2026-10-22：硬闸+如实披露豁免，禁软提醒）。
盘点聚合 + state 入册两侧的合同测试。全部进程内调用（无 shell、无外部命令拼接）。"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
TOKEN_VARS = ("MUSIC_EXPERT_FREESOUND_TOKEN", "P0C_FREESOUND_TOKEN")


def load_script(relative_path):
    # 专员脚本按"同目录兄弟导入"形制编写（直接跑脚本时 sys.path 含脚本目录），
    # 进程内加载需临时把该目录补进 sys.path。
    module_name = relative_path.replace("/", "_").replace(".py", "")
    script_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script_path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(script_path.parent))
    return module


AUDIT = load_script("skill/p0-c-pipeline/scripts/capability_audit.py")
PS = load_script("skill/p0-c-pipeline/scripts/pipeline_state.py")


def call(module, argv):
    """调 CLI 的进程内等价：返回 (exit_code, parsed_json_or_None)。"""
    buffer = io.StringIO()
    argv_list = [str(item) for item in argv]
    code = 0
    with contextlib.redirect_stdout(buffer):
        try:
            if module is PS:
                args = PS.parser().parse_args(argv_list)
                args.func(args)
            else:
                with mock.patch.object(sys, "argv", ["capability_audit.py"] + argv_list):
                    code = module.main() or 0
        except SystemExit as exit_info:
            code = exit_info.code if isinstance(exit_info.code, int) else 1
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else None


class CapabilityAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # v1.35.0 工作台选址硬闸：以 env 注入登记根，项目按正形 <根>/工作台/<pid>/ 落位（init 走进程内调用）。
        self.home = Path(self.temp.name).resolve()
        os.environ["P0C_WORKSPACE_HOME"] = str(self.home)
        self.addCleanup(os.environ.pop, "P0C_WORKSPACE_HOME", None)
        self.project = self.home / "工作台" / "demo-proj"
        self.project.mkdir(parents=True)

    def audit(self, extra_args=()):
        argv = ["--project", str(self.project)]
        argv.extend(str(item) for item in extra_args)
        return call(AUDIT, argv)

    # ---- 盘点聚合侧

    def test_uninvolved_items_are_not_probed(self):
        code, out = self.audit()
        self.assertEqual(code, 0)
        report = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
        statuses = {item["status"] for item in report["items"]}
        self.assertIn("not_applicable", statuses)
        for item in report["items"]:
            if item["status"] == "not_applicable":
                self.assertFalse(item["evidence"].get("probed"), item["id"] + " 未涉却声称探过")
        self.assertEqual(report["summary"]["ready"] + report["summary"]["missing"]
                         + report["summary"]["notApplicable"], len(report["items"]))

    def test_versioned_increment_never_overwrites(self):
        _, first = self.audit()
        _, second = self.audit()
        self.assertNotEqual(first["file"], second["file"])
        self.assertTrue(Path(first["file"]).is_file() and Path(second["file"]).is_file())

    def test_absent_token_is_declared_missing(self):
        frozen = {name: "" for name in TOKEN_VARS}
        with mock.patch.dict(os.environ, frozen, clear=False):
            for name in TOKEN_VARS:
                os.environ.pop(name, None)
            code, out = self.audit(["--profile", "bgm"])
        self.assertEqual(code, 0)  # 申报非预授权：有缺口仍出盘点、仍开工
        self.assertIn("bgm-search", out["summary"]["missingIds"])
        report = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
        item = next(i for i in report["items"] if i["id"] == "bgm-search")
        self.assertIn("freesound.org/apiv2/apply", item["remedy"])

    def test_token_presence_never_echoes_value(self):
        canary = "CANARY-must-never-surface-0123456789"
        with mock.patch.dict(os.environ, {"MUSIC_EXPERT_FREESOUND_TOKEN": canary}):
            code, out = self.audit(["--profile", "bgm"])
        self.assertEqual(code, 0)
        report_text = Path(out["file"]).read_text(encoding="utf-8")
        self.assertNotIn(canary, report_text)  # 泄露三次的老病：值永不落盘、永不回显
        by_id = {i["id"]: i for i in json.loads(report_text)["items"]}
        self.assertEqual(by_id["bgm-search"]["status"], "ready")

    def test_bad_profile_and_missing_project_blocked(self):
        code, out = self.audit(["--profile", "bogus"])
        self.assertEqual(code, 2)
        self.assertEqual(out["status"], "blocked")
        code, out = call(AUDIT, ["--project", str(self.project / "nope")])
        self.assertEqual(code, 2)

    def test_labels_are_plain_language(self):
        _, out = self.audit(["--profile", "bgm,narration,subtitles,transitions"])
        report = json.loads(Path(out["file"]).read_text(encoding="utf-8"))
        for item in report["items"]:
            self.assertTrue(item["labelPlain"])
            self.assertNotIn("capability_missing", item["labelPlain"])

    # ---- state 入册侧

    def init_state(self):
        pack = self.project / "material-pack.json"
        pack.write_text(json.dumps({"packStatus": "complete"}), encoding="utf-8")
        state = self.project / "pipeline-state.json"
        code, out = call(PS, ["init", "--project-id", "demo-proj", "--source-pack", str(pack),
                              "--state", str(state), "--authorization", "internal_test",
                              "--distribution", "internal_test"])
        self.assertEqual(code, 0, out)
        return state

    def audit_file(self):
        _, out = self.audit(["--profile", "bgm"])
        return Path(out["file"])

    def test_record_block_and_status_surfacing(self):
        state = self.init_state()
        audit_file = self.audit_file()
        code, out = call(PS, ["capability-audit", "--state", str(state), "--audit-file", str(audit_file)])
        self.assertEqual(code, 0, out)
        self.assertEqual(out["capabilityAudit"]["sha256"], out["capabilityAudit"]["sha256"].upper())
        _, status = call(PS, ["status", "--state", str(state)])
        self.assertIsNotNone(status["capabilityAudit"])
        self.assertEqual(status["capabilityAudit"]["file"], str(audit_file))

    def test_rerecord_moves_old_block_to_history(self):
        state = self.init_state()
        audit_file = self.audit_file()
        call(PS, ["capability-audit", "--state", str(state), "--audit-file", str(audit_file)])
        code, out = call(PS, ["capability-audit", "--state", str(state), "--audit-file", str(audit_file)])
        self.assertEqual(code, 0, out)
        recorded = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(len(recorded["capabilityAuditHistory"]), 1)  # 永不覆盖留痕（㉘形制）

    def test_hand_made_audit_rejected(self):
        state = self.init_state()
        fake = self.project / "手补盘点.json"
        fake.write_text(json.dumps({"kind": "capability-audit-ish", "schemaVersion": "0.1"}), encoding="utf-8")
        code, out = call(PS, ["capability-audit", "--state", str(state), "--audit-file", str(fake)])
        self.assertEqual(code, 2)
        self.assertEqual(out["status"], "blocked")

    def test_half_shape_block_refused_at_validate(self):
        # v0.13.1 教训的常驻化：申报形状歪（半块）不当 legacy 放过
        state = self.init_state()
        recorded = json.loads(state.read_text(encoding="utf-8"))
        recorded["capabilityAudit"] = {"file": "x.json"}  # 缺 sha256/probedAt/summary
        state.write_text(json.dumps(recorded, ensure_ascii=False), encoding="utf-8")
        code, out = call(PS, ["status", "--state", str(state)])
        self.assertEqual(code, 2)
        self.assertIn("capabilityAudit", json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
