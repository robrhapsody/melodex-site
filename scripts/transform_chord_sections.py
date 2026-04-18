from __future__ import annotations

import argparse
import csv
import importlib.util
from pathlib import Path


SECTION_COLUMNS = ("intro", "verse", "chorus", "bridge", "outro")
OUTPUT_COLUMNS = [
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "chords",
    "intro",
    "verse",
    "chorus",
    "bridge",
    "outro",
    "detected_key",
    "intro_nashville",
    "verse_nashville",
    "chorus_nashville",
    "bridge_nashville",
    "outro_nashville",
    "spotify_song_id",
    "spotify_artist_id",
]


def load_build_module(project_root: Path):
    path = project_root / "scripts" / "build_melodex_phase1_db.py"
    spec = importlib.util.spec_from_file_location("build_melodex_phase1_db", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Transform merged Spotify chord rows into structured section columns.")
    parser.add_argument(
        "--input",
        default=str(project_root / "data" / "processed" / "merged_spotify_chords_slim.csv"),
        help="Input slim CSV.",
    )
    parser.add_argument(
        "--output",
        default=str(project_root / "data" / "processed" / "merged_spotify_chords_structured.csv"),
        help="Output structured CSV.",
    )
    args = parser.parse_args()

    bm = load_build_module(project_root)

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as src, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        rows_written = 0
        rows_parsed = 0

        for row in reader:
            raw_chords = row.get("chords", "") or ""
            parsed_sections = bm.parse_all_sections(raw_chords)
            normalized_full = bm.clean_chord_sequence(raw_chords)

            output_row = {column: "" for column in OUTPUT_COLUMNS}
            for column in ("artist_name", "track_name", "year", "main_genre", "spotify_song_id", "spotify_artist_id"):
                output_row[column] = row.get(column, "") or ""

            section_entries = []
            for entry in parsed_sections:
                section_type = entry.get("section_type_estimated")
                if section_type in SECTION_COLUMNS and not output_row[section_type]:
                    output_row[section_type] = entry.get("normalized_chords", "") or ""
                if section_type in SECTION_COLUMNS:
                    section_entries.append(entry)

            detected_key = None
            if section_entries:
                key_sequences = bm.select_key_detection_sequences(section_entries, normalized_full)
                chord_objects = bm.chord_objects_from_sequences(key_sequences)
                detected_key = bm.detect_key(chord_objects) if chord_objects else None

            if detected_key:
                output_row["detected_key"] = detected_key["raw_name"]
                for section in SECTION_COLUMNS:
                    output_row[f"{section}_nashville"] = bm.convert_to_nashville_sequence(
                        output_row[section],
                        detected_key["raw_tonic"],
                    )

            output_row["chords"] = "" if section_entries else raw_chords

            writer.writerow(output_row)
            rows_written += 1
            if section_entries:
                rows_parsed += 1

    print(f"Structured file written to: {output_path}")
    print(f"Rows written: {rows_written}")
    print(f"Rows parsed into sections: {rows_parsed}")


if __name__ == "__main__":
    main()
