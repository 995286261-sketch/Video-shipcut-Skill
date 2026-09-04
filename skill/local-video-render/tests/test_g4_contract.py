import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
PREPARE=ROOT/"skill"/"local-video-render"/"scripts"/"g4_prepare.py"
VALIDATE=ROOT/"skill"/"local-video-render"/"scripts"/"g4_validate.py"
HANDOFF=ROOT/"skill"/"local-video-render"/"scripts"/"g4_build_handoff.py"

class G4ContractTest(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)
    def run_cli(self, script, *args, code=0):
        result=subprocess.run([sys.executable,str(script),*map(str,args)],capture_output=True,text=True,encoding="utf-8",errors="replace")
        self.assertEqual(result.returncode,code,result.stdout+result.stderr); return json.loads(result.stdout)
    def test_prepare_preserves_all_approved_segments_and_provenance(self):
        pack=self.root/"pack"; (pack/"raw").mkdir(parents=True); media=pack/"raw"/"a.mp4"; media.write_bytes(b"fixture")
        import hashlib; digest=hashlib.sha256(b"fixture").hexdigest().upper()
        (pack/"material-pack.json").write_text(json.dumps({"sourceAssets":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest}]}))
        visual={"status":"verified","frameManifestRef":"frames.json","frameRefs":["start.jpg","middle.jpg","end.jpg"],"observedVisuals":"已查看起点、中点、终点帧，主体清晰可见。"}
        plan={"schemaVersion":"0.1","projectId":"p","status":"approved_for_g4","sourceAudioPolicy":"exclude","targetProfile":{"targetDurationSec":3},"segments":[{"segmentId":"one","assetId":"a","startMs":0,"endMs":1000,"mappingMode":"one_to_one","visualVerification":visual},{"segmentId":"two","assetId":"a","startMs":1000,"endMs":3000,"mappingMode":"one_to_one","visualVerification":visual}],"editPlan":{"timeline":[{"segmentId":"one"},{"segmentId":"two"}]}}
        evidence={"projectId":"p","sourceEvidence":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest,"sourceProbe":{"durationMs":3000}}]}
        plan_path=self.root/"plan.json"; evidence_path=self.root/"evidence.json"; plan_path.write_text(json.dumps(plan)); evidence_path.write_text(json.dumps(evidence)); output=self.root/"out"
        value=self.run_cli(PREPARE,"--plan",plan_path,"--evidence",evidence_path,"--source-pack",pack,"--output-dir",output)
        self.assertEqual(2,value["segments"]); manifest=output/"G4-可编辑工程-v0.2.json"; checked=self.run_cli(VALIDATE,"--manifest",manifest)
        self.assertEqual("valid",checked["status"])

    def test_prepare_rejects_guessed_timecode_without_visual_verification(self):
        pack=self.root/"pack"; (pack/"raw").mkdir(parents=True); media=pack/"raw"/"a.mp4"; media.write_bytes(b"fixture")
        import hashlib; digest=hashlib.sha256(b"fixture").hexdigest().upper()
        (pack/"material-pack.json").write_text(json.dumps({"sourceAssets":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest}]}))
        plan={"projectId":"p","status":"approved_for_g4","sourceAudioPolicy":"exclude","segments":[{"segmentId":"one","assetId":"a","startMs":0,"endMs":1000}],"editPlan":{"timeline":[{"segmentId":"one"}]}}
        evidence={"projectId":"p","sourceEvidence":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest,"sourceProbe":{"durationMs":3000}}]}
        p=self.root/"plan.json"; e=self.root/"evidence.json"; p.write_text(json.dumps(plan)); e.write_text(json.dumps(evidence))
        value=self.run_cli(PREPARE,"--plan",p,"--evidence",e,"--source-pack",pack,"--output-dir",self.root/"out",code=2)
        self.assertIn("refuses guessed timecodes",value["error"])
    def test_prepare_rejects_nonapproved_plan(self):
        plan={"projectId":"p","status":"review_required"}; p=self.root/"p.json"; e=self.root/"e.json"; p.write_text(json.dumps(plan)); e.write_text(json.dumps({"projectId":"p"}))
        value=self.run_cli(PREPARE,"--plan",p,"--evidence",e,"--source-pack",self.root,"--output-dir",self.root/"o",code=2)
        self.assertEqual("invalid",value["status"])

    def test_prepare_rejects_output_that_exceeds_approved_source_range(self):
        pack=self.root/"pack"; (pack/"raw").mkdir(parents=True); media=pack/"raw"/"a.mp4"; media.write_bytes(b"fixture")
        import hashlib; digest=hashlib.sha256(b"fixture").hexdigest().upper()
        (pack/"material-pack.json").write_text(json.dumps({"sourceAssets":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest}]}))
        visual={"status":"verified","frameManifestRef":"frames.json","frameRefs":["start.jpg","middle.jpg","end.jpg"],"observedVisuals":"主体清晰可见。"}
        plan={"projectId":"p","status":"approved_for_g4","sourceAudioPolicy":"exclude","segments":[{"segmentId":"one","assetId":"a","startMs":0,"endMs":1000,"visualVerification":visual}],"editPlan":{"timeline":[{"segmentId":"one","timelineStartMs":0,"timelineEndMs":1200}]}}
        evidence={"projectId":"p","sourceEvidence":[{"assetId":"a","relativePath":"raw/a.mp4","sha256":digest,"sourceProbe":{"durationMs":3000}}]}
        p=self.root/"p.json"; e=self.root/"e.json"; p.write_text(json.dumps(plan)); e.write_text(json.dumps(evidence))
        value=self.run_cli(PREPARE,"--plan",p,"--evidence",e,"--source-pack",pack,"--output-dir",self.root/"out",code=2)
        self.assertIn("exceeds approved source range",value["error"])

    def test_validator_rejects_flattened_preview_in_handoff(self):
        manifest={"schemaVersion":"0.2","status":"prepared_for_render","segmentCount":1,"timelineDurationMs":1000,"segments":[{"order":1,"timeline":{"startMs":0,"endMs":1000},"source":{"relativePath":"raw/a.mp4","sha256":"a","startMs":0,"endMs":1000},"output":{"filename":"seg-001.mp4","audio":"excluded"}}]}
        mp=self.root/"manifest.json"; mp.write_text(json.dumps(manifest)); handoff=self.root/"handoff"; handoff.mkdir()
        for name in ("README.md","subtitles-draft.srt","approved-script.txt"): (handoff/name).write_text("x")
        (handoff/"asset-manifest.json").write_text(json.dumps({"assets":[{"filename":"seg-001.mp4"},{"filename":"G4-粗剪-v0.2.mp4"}]}))
        value=self.run_cli(VALIDATE,"--manifest",mp,"--handoff-dir",handoff,code=2)
        self.assertEqual("invalid",value["status"])

if __name__=="__main__": unittest.main()
