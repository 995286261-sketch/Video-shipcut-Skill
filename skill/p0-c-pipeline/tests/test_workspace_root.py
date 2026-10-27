"""v1.35.0 工作台选址合同（connector workspaceRootRef 语义的本地补齐）。
落点零临场：env>人的选址记录>仓库默认；init 硬闸、无逐字原话拒写、半形记录如实报错。
全部进程内调用；选址文件一律打在临时"仓根"上，绝不落进真仓库。"""
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
ENV_NAME = "P0C_WORKSPACE_HOME"
CHOICE_NAME = "工作台选址.json"


def load_script(relative_path):
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


PS = load_script("skill/p0-c-pipeline/scripts/pipeline_state.py")
# PS 体内 `from project_layout import ...` 走常规导入——取 sys.modules 里被引擎实际使用的那个实例，
# 打桩 REPO_ROOT 才能同时生效于选址读写与 init 闸。
LAYOUT = sys.modules["project_layout"]


def call(argv):
    buffer = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buffer):
        try:
            args = PS.parser().parse_args([str(item) for item in argv])
            args.func(args)
        except SystemExit as exit_info:
            code = exit_info.code if isinstance(exit_info.code, int) else 1
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else None


class WorkspaceRootContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()  # macOS /var→/private/var 软链：两侧同 resolve 才可比
        self.repo = self.base / "repo"
        self.repo.mkdir()
        # 默认干净机器：无 env、无选址记录，仓根打在 tmp。
        self.addCleanup(os.environ.pop, ENV_NAME, None)
        os.environ.pop(ENV_NAME, None)
        self.patch = mock.patch.object(LAYOUT, "REPO_ROOT", self.repo)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def status(self):
        code, out = call(["workspace-root"])
        self.assertEqual(code, 0, out)
        return out

    def make_pack(self):
        pack = self.base / "material-pack.json"
        pack.write_text(json.dumps({"packStatus": "complete"}), encoding="utf-8")
        return pack

    def init(self, state_path):
        return call(["init", "--project-id", state_path.parent.name, "--source-pack", str(self.make_pack()),
                     "--state", str(state_path), "--authorization", "internal_test",
                     "--distribution", "not_for_distribution"])

    # ---- 解析优先级与首次待选 ----

    def test_default_root_asks_once(self):
        out = self.status()
        self.assertEqual(out["source"], "default")
        self.assertEqual(Path(out["root"]), self.repo)
        self.assertTrue(out["needsUserChoice"])

    def test_choice_recorded_and_read_back(self):
        code, out = call(["workspace-root", "--set", str(self.repo), "--user-words", "就放仓库里吧"])
        self.assertEqual(code, 0, out)
        self.assertEqual(out["source"], "choice")
        record = json.loads((self.repo / CHOICE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "workspace-root-choice")
        self.assertEqual(record["userWords"], "就放仓库里吧")  # 逐字，不加工
        status = self.status()
        self.assertEqual(status["source"], "choice")
        self.assertFalse(status["needsUserChoice"])
        self.assertEqual(status["userWords"], "就放仓库里吧")

    def test_env_is_a_human_fact_too(self):
        other = self.base / "bigdisk"
        other.mkdir()
        os.environ[ENV_NAME] = str(other)
        out = self.status()
        self.assertEqual(out["source"], "env")
        self.assertEqual(Path(out["root"]), other)
        self.assertFalse(out["needsUserChoice"])

    # ---- AI 永不代选 / ⑤嵌套语义 / 半形如实 ----

    def test_set_without_verbatim_words_refused(self):
        code, out = call(["workspace-root", "--set", str(self.repo)])
        self.assertEqual(code, 2)
        self.assertIn("逐字", out["error"])
        self.assertFalse((self.repo / CHOICE_NAME).exists())

    def test_root_containing_workbench_refused(self):
        nested = self.repo / "工作台"
        code, out = call(["workspace-root", "--set", str(nested), "--user-words", "放这里"])
        self.assertEqual(code, 2)
        self.assertIn("嵌套", out["error"])

    def test_corrupt_choice_fails_loud(self):
        (self.repo / CHOICE_NAME).write_text(json.dumps(
            {"kind": "workspace-root-choice", "root": str(self.repo)}, ensure_ascii=False), encoding="utf-8")
        code, out = call(["workspace-root"])
        self.assertEqual(code, 2)
        self.assertIn("userWords", out["error"])

    # ---- init 落点硬闸 ----

    def test_init_binds_under_registered_workbench(self):
        state = self.repo / "工作台" / "proj-a" / "pipeline-state.json"
        code, out = self.init(state)
        self.assertEqual(code, 0, out)
        recorded = json.loads(state.read_text(encoding="utf-8"))["workspaceRoot"]
        self.assertEqual(Path(recorded["root"]), self.repo)
        self.assertEqual(recorded["source"], "default")

    def test_init_elsewhere_blocked_and_no_file(self):
        state = self.repo / "随手一起" / "proj-b" / "pipeline-state.json"
        code, out = self.init(state)
        self.assertEqual(code, 2)
        self.assertIn("工作台选址合同", out["error"])
        self.assertIn(str(self.repo), out["error"])  # 点名登记根与出处
        self.assertFalse(state.exists())
        self.assertFalse(state.parent.parent.exists())  # 罢工先于建目录

    def test_choice_moves_the_gate(self):
        other = self.base / "otherdisk"
        other.mkdir()
        code, out = call(["workspace-root", "--set", str(other), "--user-words", "放那块大盘"])
        self.assertEqual(code, 0, out)
        # 原仓库默认位不再被认（越界点名）
        old_state = self.repo / "工作台" / "proj-c" / "pipeline-state.json"
        code, out = self.init(old_state)
        self.assertEqual(code, 2)
        self.assertIn("choice", out["error"])  # 出处如实报
        new_state = other / "工作台" / "proj-c" / "pipeline-state.json"
        code, out = self.init(new_state)
        self.assertEqual(code, 0, out)
        recorded = json.loads(new_state.read_text(encoding="utf-8"))["workspaceRoot"]
        self.assertEqual(recorded["source"], "choice")

    def test_status_surfaces_workspace_root(self):
        state = self.repo / "工作台" / "proj-d" / "pipeline-state.json"
        self.init(state)
        code, out = call(["status", "--state", str(state)])
        self.assertEqual(code, 0, out)
        self.assertEqual(Path(out["workspaceRoot"]["root"]), self.repo)

    def test_choice_file_never_enters_the_repo(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(CHOICE_NAME, text)  # 个人绝对路径永不入库（公开仓红线）


if __name__ == "__main__":
    unittest.main()
