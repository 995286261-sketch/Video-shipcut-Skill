import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILL_ROOT = Path(__file__).resolve().parents[1]
ENGINE = SKILL_ROOT / "scripts" / "local_edit_engine.py"

_python_home = os.environ.get("SHIPCUT_PYTHON_HOME")
if _python_home:
    _p = Path(_python_home)
    PYTHON = _p / ("python.exe" if os.name == "nt" else "bin" / "python") if _p.is_dir() else _p
else:
    PYTHON = Path(sys.executable)


def find_ffmpeg():
    home = os.environ.get("SHIPCUT_FFMPEG_HOME")
    if home:
        for candidate in (
            Path(home) / "ffmpeg.exe",
            Path(home) / "bin" / "ffmpeg.exe",
            Path(home) / "ffmpeg",
            Path(home) / "bin" / "ffmpeg",
        ):
            if candidate.is_file():
                return str(candidate)
    return shutil.which("ffmpeg")


FFMPEG = find_ffmpeg()


class LocalEditCliTest(unittest.TestCase):
    def build_fixture(self, workspace: Path) -> Path:
        raw = workspace / "raw"; raw.mkdir()
        source = raw / "source.mp4"
        subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30", "-t", "8", "-c:v", "libx264", "-an", str(source)], capture_output=True, check=True)
        assets = []
        hints = []
        for index, (start, end) in enumerate(((600, 7200), (400, 4500), (300, 6800)), 1):
            path = raw / f"source-{index}.mp4"; shutil.copyfile(source, path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            asset_id = f"fixture-{index}"
            assets.append({"assetId": asset_id, "sourceKind": "local-file", "sourceValue": str(path), "sha256": digest})
            hints.append({"assetId": asset_id, "startMs": start, "endMs": end, "tags": ["fixture"], "reason": "test fixture"})
        request = {"schemaVersion": "0.1", "requestId": "fixture-request", "projectId": "fixture-project", "operation": "media.edit.plan", "editPrompt": "Use only fixture footage.", "sourceAssets": assets, "targetProfile": {"aspectRatio": "16:9", "targetDurationSec": 18}, "selectionHints": hints}
        path = workspace / "request.json"; path.write_text(json.dumps(request), encoding="utf-8")
        return path

    def run_cli(self, *args: str) -> dict:
        result = subprocess.run(
            [str(PYTHON), str(ENGINE), *args],
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    @unittest.skipIf(FFMPEG is None, "FFmpeg not found: install FFmpeg or set SHIPCUT_FFMPEG_HOME")
    def test_micro_fixture_requires_approval_before_render_and_passes_basic_qa(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            request = self.build_fixture(workspace)
            plan = self.run_cli("plan", "--request", str(request), "--workspace", str(workspace))

            self.assertEqual("review_required", plan["status"])
            self.assertEqual(3, len(plan["segments"]))
            self.assertEqual("pending", plan["editPlan"]["approvalState"])
            self.assertTrue(plan["humanReviewPoints"])
            self.assertTrue(plan["editPlan"]["qualityPolicy"]["onePrimaryVisualPerBeat"])
            self.assertEqual("source_audio_excluded", plan["editPlan"]["qualityPolicy"]["audio"]["mode"])
            self.assertTrue(
                any(point["type"] == "quality_policy_review_required" for point in plan["humanReviewPoints"])
            )

            approved_path = workspace / "approved-plan.json"
            approved = self.run_cli(
                "approve",
                "--plan",
                str(workspace / "plan-result.json"),
                "--reviewer",
                "fixture-reviewer",
                "--output",
                str(approved_path),
            )
            self.assertEqual("approved", approved["editPlan"]["approvalState"])

            render = self.run_cli("render", "--plan", str(approved_path), "--workspace", str(workspace))
            final_artifact = next(item for item in render["artifacts"] if item["type"] == "final_render")
            self.assertTrue((workspace / final_artifact["path"]).is_file())

            qa = self.run_cli("qa", "--plan", str(approved_path), "--artifact", str(workspace / final_artifact["path"]))
            self.assertEqual("pass", qa["qaReport"]["checks"]["decodable"]["status"])
            self.assertEqual("pass", qa["qaReport"]["checks"]["dimensions"]["status"])
            self.assertEqual("pass", qa["qaReport"]["checks"]["duration"]["status"])


if __name__ == "__main__":
    unittest.main()
