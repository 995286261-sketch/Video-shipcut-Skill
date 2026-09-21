import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skill" / "video-edit-plan" / "scripts" / "validate_g3_semantic_beats.py"

CLAIM_TYPES = {"object", "appearance", "state_change", "weapon", "action", "character_reaction", "abstract_conclusion", "editorial_hold"}


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_g3_semantic_beats", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ValidateG3SemanticBeatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def base_payload(self) -> dict:
        return {
            "schemaVersion": "0.1",
            "node": "G3",
            "status": "draft",
            "projectId": "demo-001",
            "narrationDraft": "G2-口播-v0.1.md",
            "narrationDecisionRef": "decision.json",
            "timingBasis": "approved-narration",
            "beats": [
                {
                    "beatId": "B01",
                    "outputStartMs": 0,
                    "outputEndMs": 4000,
                    "narrationText": "开场白",
                    "claim": {"type": "object", "minimumVisibleEvidence": ["机体入画"]},
                    "allowedVisualAlternatives": ["全景", "半身"],
                },
                {
                    "beatId": "B02",
                    "outputStartMs": 4000,
                    "outputEndMs": 8000,
                    "narrationText": "武器特写",
                    "claim": {"type": "weapon", "minimumVisibleEvidence": ["武器轮廓"]},
                    "allowedVisualAlternatives": [],
                },
            ],
        }

    def call(self, payload_path: Path):
        stdout = io.StringIO()
        argv_backup = sys.argv
        sys.argv = ["validate_g3_semantic_beats.py", "--beats", str(payload_path)]
        try:
            with contextlib.redirect_stdout(stdout):
                code = self.validator.main()
        finally:
            sys.argv = argv_backup
        return code, json.loads(stdout.getvalue())

    def write_json(self, name: str, payload: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def assert_valid(self, payload: dict) -> dict:
        path = self.write_json("beats.json", payload)
        code, report = self.call(path)
        self.assertEqual(code, 0)
        return report

    def assert_invalid(self, payload: dict, needle: str) -> None:
        path = self.write_json("beats.json", payload)
        with self.assertRaises(ValueError) as caught:
            self.call(path)
        self.assertIn(needle, str(caught.exception))

    def test_accepts_two_beat_contract_and_reports_counts(self):
        report = self.assert_valid(self.base_payload())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["beats"], 2)
        self.assertEqual(report["timingBasis"], "approved-narration")

    def test_touching_beats_are_allowed_but_overlap_fails(self):
        self.assertEqual(self.assert_valid(self.base_payload())["status"], "completed")
        overlap = self.base_payload()
        overlap["beats"][1]["outputStartMs"] = 3999
        self.assert_invalid(overlap, "overlaps the preceding beat")

    def test_alternatives_may_be_omitted_but_not_wrongly_typed(self):
        without_key = self.base_payload()
        without_key["beats"][0].pop("allowedVisualAlternatives")
        self.assert_valid(without_key)
        bad_item = self.base_payload()
        bad_item["beats"][0]["allowedVisualAlternatives"] = ["全景", 42]
        self.assert_invalid(bad_item, "allowedVisualAlternatives must be a string list")

    def test_empty_beats_list_fails(self):
        empty = self.base_payload()
        empty["beats"] = []
        self.assert_invalid(empty, "non-empty beats list")

    def test_duplicate_beat_id_fails(self):
        duplicate = self.base_payload()
        duplicate["beats"][1]["beatId"] = "B01"
        self.assert_invalid(duplicate, "unique")

    def test_negative_start_or_backwards_range_fails(self):
        negative = self.base_payload()
        negative["beats"][0]["outputStartMs"] = -1
        self.assert_invalid(negative, "invalid output time range")
        backwards = self.base_payload()
        backwards["beats"][0]["outputEndMs"] = 0
        self.assert_invalid(backwards, "invalid output time range")

    def test_blank_narration_fails(self):
        blank = self.base_payload()
        blank["beats"][1]["narrationText"] = "  "
        self.assert_invalid(blank, "requires narrationText")

    def test_all_eight_claim_types_are_accepted(self):
        for claim_type in sorted(CLAIM_TYPES):
            payload = self.base_payload()
            payload["beats"][0]["claim"]["type"] = claim_type
            self.assert_valid(payload)

    def test_invalid_claim_type_fails(self):
        bad = self.base_payload()
        bad["beats"][0]["claim"]["type"] = "vibes"
        self.assert_invalid(bad, "valid claim type")

    def test_missing_or_blank_visible_evidence_fails(self):
        missing = self.base_payload()
        missing["beats"][0]["claim"].pop("minimumVisibleEvidence")
        self.assert_invalid(missing, "minimumVisibleEvidence")
        blank_item = self.base_payload()
        blank_item["beats"][0]["claim"]["minimumVisibleEvidence"] = ["机体入画", "   "]
        self.assert_invalid(blank_item, "minimumVisibleEvidence")

    def test_non_object_beat_entry_fails(self):
        bad = self.base_payload()
        bad["beats"][1] = "B02"
        self.assert_invalid(bad, "must be an object")

    def test_missing_required_envelope_field_fails(self):
        for field in ("projectId", "narrationDraft", "narrationDecisionRef", "timingBasis"):
            missing = self.base_payload()
            missing.pop(field)
            self.assert_invalid(missing, f"requires {field}")

    def test_status_outside_allowed_set_fails(self):
        bad = self.base_payload()
        bad["status"] = "approved_and_locked"
        self.assert_invalid(bad, "status must be draft")

    def test_envelope_version_or_node_mismatch_fails(self):
        bad_version = self.base_payload()
        bad_version["schemaVersion"] = "0.2"
        self.assert_invalid(bad_version, "G3 schemaVersion 0.1")
        bad_node = self.base_payload()
        bad_node["node"] = "G4"
        self.assert_invalid(bad_node, "G3 schemaVersion 0.1")

    def test_reads_utf8_bom_artifact(self):
        path = self.root / "beats-bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(self.base_payload(), ensure_ascii=False).encode("utf-8"))
        code, report = self.call(path)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "completed")


if __name__ == "__main__":
    unittest.main()
