import importlib.util
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = SKILL_ROOT / "assets" / "asset-library" / "manifest.json"
SPEC = importlib.util.spec_from_file_location("asset_validator", SKILL_ROOT / "scripts" / "validate_asset_library.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AssetLibraryTest(unittest.TestCase):
    def test_empty_library_manifest_is_valid_and_requires_no_unregistered_assets(self) -> None:
        result = MODULE.validate(MANIFEST)
        self.assertEqual("pass", result["status"])
        self.assertEqual(0, result["assetCount"])


if __name__ == "__main__":
    unittest.main()
