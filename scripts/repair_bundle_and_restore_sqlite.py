from __future__ import annotations

import argparse
import csv
import importlib.util
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path


TABLE_IMPORT_ORDER = [
    "songs",
    "song_audio_features",
    "song_catalog_memberships",
    "song_sources",
    "song_versions",
    "section_occurrences",
]


def load_build_module(project_root: Path):
    path = project_root / "scripts" / "build_melodex_phase1_db.py"
    spec = importlib.util.spec_from_file_location("build_melodex_phase1_db", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return headers, rows


def write_csv_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def normalize_row_value(value: str | None) -> str:
    return "" if value is None else str(value)


def repair_bundle(project_root: Path, input_bundle: Path, output_bundle: Path) -> dict[str, int]:
    bm = load_build_module(project_root)

    output_bundle.mkdir(parents=True, exist_ok=True)
    for table_name in ("songs", "song_audio_features", "song_catalog_memberships", "song_sources"):
        shutil.copyfile(input_bundle / f"{table_name}.csv", output_bundle / f"{table_name}.csv")

    version_headers, version_rows = read_csv_rows(input_bundle / "song_versions.csv")
    section_headers, section_rows = read_csv_rows(input_bundle / "section_occurrences.csv")

    sections_by_version: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in section_rows:
        sections_by_version[normalize_row_value(row.get("song_version_id"))].append(row)

    changed_versions = 0
    changed_sections = 0

    for version_row in version_rows:
        version_id = normalize_row_value(version_row.get("id"))
        section_rows_for_version = sections_by_version.get(version_id, [])

        raw_full = normalize_row_value(version_row.get("raw_chords_full"))
        normalized_full = bm.clean_chord_sequence(raw_full) if raw_full else ""

        section_entries: list[dict] = []
        for section_row in section_rows_for_version:
            raw_chords = normalize_row_value(section_row.get("raw_chords"))
            if raw_chords:
                normalized_section = bm.clean_chord_sequence(raw_chords)
            else:
                normalized_section = bm.normalize_whitespace(section_row.get("normalized_chords"))

            section_entries.append(
                {
                    "name_raw": normalize_row_value(section_row.get("name_raw")),
                    "base_name": bm.ORDINAL_SUFFIX_PATTERN.sub("", normalize_row_value(section_row.get("name_raw")).lower()),
                    "section_type_estimated": normalize_row_value(section_row.get("section_type_estimated")),
                    "normalized_chords": normalized_section,
                }
            )

        key_sequences = bm.select_key_detection_sequences(section_entries, normalized_full)
        chord_objects = bm.chord_objects_from_sequences(key_sequences)
        detected_key = bm.detect_key(chord_objects) if chord_objects else None

        original_display_key = normalize_row_value(version_row.get("display_key"))
        original_normalized_full = normalize_row_value(version_row.get("normalized_chords_full"))

        if normalized_full:
            version_row["normalized_chords_full"] = normalized_full

        if detected_key:
            version_row["display_key"] = detected_key["display_key"]
            version_row["detected_key_raw"] = detected_key["raw_name"]
            version_row["detected_key_relative_major"] = detected_key["relative_major_name"]

        if (
            normalize_row_value(version_row.get("display_key")) != original_display_key
            or normalize_row_value(version_row.get("normalized_chords_full")) != original_normalized_full
        ):
            changed_versions += 1

        for section_row, section_entry in zip(section_rows_for_version, section_entries):
            raw_chords = normalize_row_value(section_row.get("raw_chords"))
            if raw_chords:
                original_normalized = normalize_row_value(section_row.get("normalized_chords"))
                original_nashville = normalize_row_value(section_row.get("nashville"))
                original_relative = normalize_row_value(section_row.get("nashville_relative_major"))

                normalized_section = section_entry["normalized_chords"]
                section_row["normalized_chords"] = normalized_section
                section_row["length_chords"] = str(len(normalized_section.split())) if normalized_section else ""

                if detected_key:
                    section_row["nashville"] = bm.convert_to_nashville_sequence(
                        normalized_section,
                        detected_key["raw_tonic"],
                    )
                    section_row["nashville_relative_major"] = bm.convert_to_nashville_sequence(
                        normalized_section,
                        detected_key["relative_major_tonic"],
                    )

                if (
                    normalize_row_value(section_row.get("normalized_chords")) != original_normalized
                    or normalize_row_value(section_row.get("nashville")) != original_nashville
                    or normalize_row_value(section_row.get("nashville_relative_major")) != original_relative
                ):
                    changed_sections += 1

    write_csv_rows(output_bundle / "song_versions.csv", version_headers, version_rows)
    write_csv_rows(output_bundle / "section_occurrences.csv", section_headers, section_rows)

    readme_path = input_bundle / "README_IMPORT_ORDER.md"
    if readme_path.exists():
        shutil.copyfile(readme_path, output_bundle / "README_IMPORT_ORDER.md")

    return {
        "versions_changed": changed_versions,
        "sections_changed": changed_sections,
        "versions_total": len(version_rows),
        "sections_total": len(section_rows),
    }


def restore_sqlite_from_bundle(schema_path: Path, bundle_dir: Path, output_db: Path) -> None:
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()

    connection = sqlite3.connect(output_db)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys = OFF")

        for table_name in TABLE_IMPORT_ORDER:
            csv_path = bundle_dir / f"{table_name}.csv"
            headers, rows = read_csv_rows(csv_path)
            if not headers:
                continue

            placeholders = ", ".join("?" for _ in headers)
            column_list = ", ".join(headers)
            insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"

            batch = []
            for row in rows:
                batch.append(tuple(None if row.get(header, "") == "" else row.get(header, "") for header in headers))
                if len(batch) >= 1000:
                    connection.executemany(insert_sql, batch)
                    batch.clear()

            if batch:
                connection.executemany(insert_sql, batch)

        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
    finally:
        connection.close()


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Repair chord normalization/key detection in the Supabase bundle and restore SQLite.")
    parser.add_argument(
        "--input-bundle",
        default=str(project_root / "data" / "processed" / "supabase_import_bundle"),
        help="Existing Supabase import bundle directory.",
    )
    parser.add_argument(
        "--output-bundle",
        default=str(project_root / "data" / "processed" / "supabase_import_bundle_repaired"),
        help="Directory to write the repaired bundle.",
    )
    parser.add_argument(
        "--schema",
        default=str(project_root / "docs" / "melodex-schema.sql"),
        help="SQLite schema path.",
    )
    parser.add_argument(
        "--output-db",
        default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"),
        help="Path to restore the repaired SQLite database.",
    )
    args = parser.parse_args()

    stats = repair_bundle(
        project_root=project_root,
        input_bundle=Path(args.input_bundle),
        output_bundle=Path(args.output_bundle),
    )
    restore_sqlite_from_bundle(
        schema_path=Path(args.schema),
        bundle_dir=Path(args.output_bundle),
        output_db=Path(args.output_db),
    )

    print(f"Repaired bundle written to: {args.output_bundle}")
    print(f"SQLite restored to: {args.output_db}")
    print(f"Song versions changed: {stats['versions_changed']} / {stats['versions_total']}")
    print(f"Section rows changed: {stats['sections_changed']} / {stats['sections_total']}")


if __name__ == "__main__":
    main()
