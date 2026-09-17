"""Issue ㉛ regression: drawtext must never start on a font whose glyphs are missing.

Fonts are synthetic byte fixtures (a cmap table is all the parser reads), so the
test runs identically on macOS and Windows clients without system fonts."""
import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "skill" / "local-video-render" / "scripts" / "g4_assemble.py"
spec = importlib.util.spec_from_file_location("g4_assemble", MODULE_PATH)
g4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g4)


def cmap_format4(segments):
    """segments: list of (start, end, delta); a 0xFFFF sentinel segment is appended."""
    items = list(segments) + [(0xFFFF, 0xFFFF, 1)]
    count = len(items)
    ends = b"".join(struct.pack(">H", end) for _, end, _ in items)
    starts = b"".join(struct.pack(">H", start) for start, _, _ in items)
    deltas = b"".join(struct.pack(">H", delta & 0xFFFF) for _, _, delta in items)
    roffs = b"\x00\x00" * count
    body = ends + b"\x00\x00" + starts + deltas + roffs
    header = struct.pack(">HHHHHHH", 4, 16 + len(body), 0, count * 2, 0, 0, 0)
    return header + body


def cmap_format12(groups):
    """groups: list of (start, end, gid)."""
    body = b"".join(struct.pack(">III", *group) for group in groups)
    return struct.pack(">HHIII", 12, 0, 16 + len(body), 0, len(groups)) + body


def face_bytes(subtables, base=0):
    """subtables: list of (platform, encoding, bytes); `base` is the face's position
    in the final file because TrueType table offsets are absolute (issue ㉛ fixtures)."""
    directory_size = 4 + 8 * len(subtables)
    offsets, data, cursor = [], [], directory_size
    for platform, encoding, blob in subtables:
        offsets.append(struct.pack(">HHI", platform, encoding, cursor))
        blob = blob + b"\x00" * (4 - len(blob) % 4) if len(blob) % 4 else blob
        data.append(blob)
        cursor += len(blob)
    cmap = struct.pack(">HH", 0, len(subtables)) + b"".join(offsets) + b"".join(data)
    # sfnt header is 12 bytes (uint32 version + 4×uint16); one 16-byte table record follows.
    table_record = b"cmap" + struct.pack(">III", 0, base + 12 + 16, len(cmap))
    return struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0) + table_record + cmap


def ttc_bytes(subtable_faces):
    header_size = 12 + 4 * len(subtable_faces)
    offsets, data, cursor = [], [], header_size
    for subtables in subtable_faces:
        face = face_bytes(subtables, base=cursor)
        face = face + b"\x00" * (4 - len(face) % 4) if len(face) % 4 else face
        offsets.append(struct.pack(">I", cursor))
        data.append(face)
        cursor += len(face)
    return b"ttcf" + struct.pack(">II", 0x00010000, len(subtable_faces)) + b"".join(offsets) + b"".join(data)


class GlyphCoverageTest(unittest.TestCase):
    def setUp(self):
        # 中 U+4E2D, 战 U+6218 via a format-4 BMP face; 𠀀 U+20000 via format-12.
        self.solo = face_bytes([(3, 1, cmap_format4([(0x4E2D, 0x4E2D, 1), (0x6218, 0x6218, 3)]))])
        self.plane2 = face_bytes([(0, 4, cmap_format12([(0x20000, 0x20000, 5)]))])

    def check(self, blob, text, tmpdir):
        font = Path(tmpdir) / "font.bin"
        font.write_bytes(blob)
        return g4.require_glyph_coverage(font, text, "fixture")

    def test_covered_text_passes_and_whitespace_is_free(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.check(self.solo, "中 战　", tmp))

    def test_missing_glyph_blocks_before_ffmpeg(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                self.check(self.solo, "中文", tmp)
            self.assertIn("no glyphs", str(caught.exception))
            self.assertIn("文", str(caught.exception))

    def test_format12_covers_astral_planes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.check(self.plane2, "𠀀", tmp))
            with self.assertRaises(ValueError):
                self.check(self.plane2, "中", tmp)

    def test_ttc_first_face_gap_blocks_even_if_a_later_face_covers(self):
        # The live-test failure mode: PingFang.ttc face 0 lacks the simplified
        # glyphs, a later face has them; drawtext renders face 0 and shows tofu.
        import tempfile
        blob = ttc_bytes([
            [(3, 1, cmap_format4([(0x4E2D, 0x4E2D, 1)]))],
            [(3, 1, cmap_format4([(0x6218, 0x6218, 3)]))],
        ])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                self.check(blob, "中战", tmp)
            self.assertIn("TTC", str(caught.exception))
            self.assertIn("战", str(caught.exception))
            self.assertIsNone(self.check(blob, "中", tmp))

    def test_unparseable_font_refuses_instead_of_risking_silent_tofu(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError) as caught:
                self.check(b"not a font at all", "中", tmp)
            self.assertIn("cannot be checked", str(caught.exception))

    def test_every_drawtext_entry_point_is_guarded(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for site in ('require_glyph_coverage(font, title, f"chapter card {index}")',
                     'require_glyph_coverage(font, title, "title bar")',
                     'require_glyph_coverage(font, title, "cover title")'):
            self.assertIn(site, source)


if __name__ == "__main__":
    unittest.main()
