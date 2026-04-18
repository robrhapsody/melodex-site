from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bm = load_module("build_melodex_phase1_db", "scripts/build_melodex_phase1_db.py")
iw = load_module("import_worship_csv_and_merge", "scripts/import_worship_csv_and_merge.py")
io = load_module("import_opensong_and_compare", "scripts/import_opensong_and_compare.py")


BUILD_MY_LIFE_PAT_BARRETT = (
    "<verse_1> G C G/B C G C G C "
    "<verse_2> G C G/B C G C G/B C "
    "<chorus_1> Amin7 G/D Emin C Amin7 G/D Emin "
    "<instrumental_1> C "
    "<verse_3> G C G/B C G C G/B C "
    "<chorus_2> Amin7 G/D Emin C Amin7 G/D Emin C Dsus4 "
    "<bridge_1> C Dsus4 Emin G/B C Dsus4 Emin G/B C Dsus4 Emin G/B C Dsus4 Emin G/B "
    "<chorus_3> C Amin7 G/D Emin C Amin7 G Emin C"
)


class ChordNormalizationTests(unittest.TestCase):
    def test_build_melodex_keeps_sus_roots_intact(self):
        self.assertEqual(bm.normalize_chord_token("Dsus4"), "D")
        self.assertEqual(bm.normalize_chord_token("Csus4/Gs"), "C/G#")
        self.assertEqual(bm.normalize_chord_token("Fsmin7"), "F#m")

    def test_import_merge_keeps_sus_roots_intact(self):
        self.assertEqual(iw.normalize_chord_token("Dsus4"), (2, False))
        self.assertEqual(iw.normalize_chord_token("Fsmin7"), (6, True))

    def test_opensong_compare_keeps_sus_roots_intact(self):
        self.assertEqual(io.chord_token_to_parts("Dsus4"), (2, False))
        self.assertEqual(io.chord_token_to_parts("Asus2"), (9, False))

    def test_build_my_life_detects_g_from_representative_sections(self):
        section_entries = bm.parse_all_sections(BUILD_MY_LIFE_PAT_BARRETT)
        normalized_full = bm.clean_chord_sequence(bm.SECTION_TAG_PATTERN.sub(" ", BUILD_MY_LIFE_PAT_BARRETT))
        key_sequences = bm.select_key_detection_sequences(section_entries, normalized_full)

        self.assertIn("C D Em G/B C D Em G/B C D Em G/B C D Em G/B", key_sequences)

        detected = bm.detect_key(bm.chord_objects_from_sequences(key_sequences))
        self.assertIsNotNone(detected)
        self.assertEqual(detected["display_key"], "G")


if __name__ == "__main__":
    unittest.main()
