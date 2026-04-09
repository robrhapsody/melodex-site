from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


SECTION_TAG_PATTERN = re.compile(r"<([^>]+)>")
ORDINAL_SUFFIX_PATTERN = re.compile(r"_(\d+)$")

NOTE_TO_SEMITONE = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}

SEMITONE_TO_CANONICAL = {
    0: "C",
    1: "C#",
    2: "D",
    3: "Eb",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "Ab",
    9: "A",
    10: "Bb",
    11: "B",
}

SECTION_TYPE_MAP = {
    "intro": "intro",
    "verse": "verse",
    "prechorus": "pre_chorus",
    "pre_chorus": "pre_chorus",
    "pre-chorus": "pre_chorus",
    "chorus": "chorus",
    "refrain": "chorus",
    "hook": "chorus",
    "bridge": "bridge",
    "tag": "tag",
    "interlude": "interlude",
    "instrumental": "instrumental",
    "solo": "solo",
    "outro": "outro",
    "ending": "outro",
}

STANDARD_SECTION_TYPES = {
    "intro",
    "verse",
    "pre_chorus",
    "chorus",
    "bridge",
    "tag",
    "interlude",
    "instrumental",
    "solo",
    "outro",
}

APPROVED_OVERRIDE_STATUSES = {"approved", "apply", "ready", "applied"}
SECTION_OVERRIDE_ACTIONS = {
    "replace_sections",
    "replace_section",
    "update_sections",
    "update_section",
    "apply_overrides",
    "apply_override",
}


def normalize_whitespace(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def clean_string(value: str | None) -> str | None:
    text = normalize_whitespace(value)
    return text or None


def normalize_label(value: str | None) -> str:
    text = normalize_whitespace(value).lower()
    if not text:
        return ""
    return re.sub(r"[\s-]+", "_", text)


def parse_int(value: str | None) -> int | None:
    text = normalize_whitespace(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: str | None) -> float | None:
    text = normalize_whitespace(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_note_name(note: str | None) -> str | None:
    if not note:
        return None
    trimmed = note.strip()
    if not trimmed:
        return None
    root = trimmed[0].upper()
    suffix = trimmed[1:]
    lowered = suffix.lower()
    if lowered in {"s", "#"}:
        return f"{root}#"
    if lowered == "b":
        return f"{root}b"
    return root


def get_note_semitone(note: str | None) -> int | None:
    if not note:
        return None
    return NOTE_TO_SEMITONE.get(note)


def get_canonical_key_name(semitone: int) -> str:
    return SEMITONE_TO_CANONICAL[semitone % 12]


def normalize_chord_token(token: str | None) -> str | None:
    if not token:
        return None

    text = token.strip()
    if not text or re.fullmatch(r"(?i:n\.?c\.?)", text):
        return None

    parts = text.split("/", 1)
    main = parts[0]
    bass = parts[1] if len(parts) > 1 else None

    match = re.match(r"^([A-Ga-g])([#bs]?)(.*)$", main)
    if not match:
        return None

    root = normalize_note_name(f"{match.group(1)}{match.group(2)}")
    tail = (match.group(3) or "").lower()
    is_minor = bool(re.match(r"^m(?!aj)", tail) or "min" in tail)
    normalized = f"{root}m" if is_minor else root

    if bass:
        bass_match = re.match(r"^([A-Ga-g])([#bs]?)", bass)
        if bass_match:
            bass_root = normalize_note_name(f"{bass_match.group(1)}{bass_match.group(2)}")
            if bass_root:
                normalized = f"{normalized}/{bass_root}"

    return normalized


def clean_chord_sequence(chord_text: str | None) -> str:
    if not chord_text:
        return ""

    cleaned: list[str] = []
    for token in re.split(r"\s+", chord_text.strip()):
        normalized = normalize_chord_token(token)
        if normalized:
            cleaned.append(normalized)
    return " ".join(cleaned)


def estimate_section_type(base_name: str) -> str:
    normalized = re.sub(r"[\s-]+", "_", base_name.strip().lower())
    if not normalized:
        return "unknown"
    if normalized in SECTION_TYPE_MAP:
        return SECTION_TYPE_MAP[normalized]
    if normalized.startswith("prechorus"):
        return "pre_chorus"
    return normalized


def parse_all_sections(chord_text: str | None) -> list[dict]:
    if not chord_text:
        return []

    matches = list(SECTION_TAG_PATTERN.finditer(chord_text))
    if not matches:
        return []

    entries: list[dict] = []
    seen_by_base: defaultdict[str, int] = defaultdict(int)
    for index, match in enumerate(matches):
        raw_name = match.group(1).strip().lower()
        base_name = ORDINAL_SUFFIX_PATTERN.sub("", raw_name)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(chord_text)
        raw_section = chord_text[start:end].strip()
        normalized_section = clean_chord_sequence(raw_section)
        if not normalized_section:
            continue

        seen_by_base[base_name] += 1
        ordinal_match = ORDINAL_SUFFIX_PATTERN.search(raw_name)
        ordinal = int(ordinal_match.group(1)) if ordinal_match else seen_by_base[base_name]

        entries.append(
            {
                "name_raw": raw_name,
                "base_name": base_name,
                "section_type_estimated": estimate_section_type(base_name),
                "ordinal": ordinal,
                "position_index": len(entries),
                "raw_chords": raw_section,
                "normalized_chords": normalized_section,
            }
        )

    base_counts = Counter(entry["base_name"] for entry in entries)
    for entry in entries:
        entry["is_repeating"] = 1 if base_counts[entry["base_name"]] > 1 else 0
        entry["length_chords"] = len(entry["normalized_chords"].split())

    return entries


def chord_objects_from_sequences(sequences: Iterable[str]) -> list[dict]:
    chord_objects: list[dict] = []
    for sequence in sequences:
        if not sequence:
            continue
        for token in sequence.split():
            normalized = normalize_chord_token(token)
            if not normalized:
                continue
            parts = normalized.split("/", 1)
            main = parts[0]
            bass = parts[1] if len(parts) > 1 else None
            is_minor = main.endswith("m")
            root = main[:-1] if is_minor else main
            root_semitone = get_note_semitone(root)
            if root_semitone is None:
                continue
            bass_semitone = get_note_semitone(bass) if bass else None
            chord_objects.append(
                {
                    "root_semitone": root_semitone,
                    "is_minor": is_minor,
                    "bass_semitone": bass_semitone,
                }
            )
    return chord_objects


def get_key_score(chords: list[dict], tonic: int, minor_mode: bool) -> float:
    score = 0.0
    if minor_mode:
        diatonic_intervals = {0, 2, 3, 5, 7, 8, 10}
        minor_expected = {0: True, 2: False, 3: False, 5: True, 7: False, 8: False, 10: False}
    else:
        diatonic_intervals = {0, 2, 4, 5, 7, 9, 11}
        minor_expected = {0: False, 2: True, 4: True, 5: False, 7: False, 9: True, 11: False}

    for index, chord in enumerate(chords):
        interval = (chord["root_semitone"] - tonic + 12) % 12
        is_diatonic = interval in diatonic_intervals

        if is_diatonic:
            score += 2.0
            if interval in minor_expected and minor_expected[interval] == chord["is_minor"]:
                score += 1.5
            elif minor_mode and interval == 7 and not chord["is_minor"]:
                score += 1.0
        else:
            score -= 0.75

        if interval == 0:
            score += 3.0
        elif interval == 7:
            score += 1.25
        elif interval == 5:
            score += 0.75

        if index == 0 and interval == 0:
            score += 1.0
        if index == len(chords) - 1 and interval == 0:
            score += 2.0

    return score


def detect_key(chords: list[dict]) -> dict | None:
    if not chords:
        return None

    best_major = None
    best_minor = None
    for tonic in range(12):
        major_score = get_key_score(chords, tonic, False)
        minor_score = get_key_score(chords, tonic, True)

        major_candidate = {"tonic": tonic, "minor_mode": False, "score": major_score}
        minor_candidate = {"tonic": tonic, "minor_mode": True, "score": minor_score}

        if best_major is None or major_score > best_major["score"]:
            best_major = major_candidate
        if best_minor is None or minor_score > best_minor["score"]:
            best_minor = minor_candidate

    assert best_major is not None and best_minor is not None
    selected = best_minor if best_minor["score"] > best_major["score"] + 2.0 else best_major

    raw_key_name = get_canonical_key_name(selected["tonic"])
    raw_display = f"{raw_key_name} minor" if selected["minor_mode"] else raw_key_name
    relative_major_tonic = (selected["tonic"] + 3) % 12 if selected["minor_mode"] else selected["tonic"]
    relative_major_name = get_canonical_key_name(relative_major_tonic)
    display_key = relative_major_name if selected["minor_mode"] else raw_display

    return {
        "raw_name": raw_display,
        "display_key": display_key,
        "relative_major_name": relative_major_name,
        "raw_tonic": selected["tonic"],
        "relative_major_tonic": relative_major_tonic,
        "uses_relative_major_numbers": 1 if selected["minor_mode"] else 0,
    }


def get_nashville_degree(offset: int) -> str:
    mapping = {
        0: "1",
        1: "b2",
        2: "2",
        3: "b3",
        4: "3",
        5: "4",
        6: "#4",
        7: "5",
        8: "b6",
        9: "6",
        10: "b7",
        11: "7",
    }
    return mapping[offset % 12]


def convert_to_nashville_sequence(chord_text: str | None, tonic: int | None) -> str:
    if not chord_text or tonic is None:
        return ""

    numbers: list[str] = []
    for token in chord_text.split():
        normalized = normalize_chord_token(token)
        if not normalized:
            continue

        parts = normalized.split("/", 1)
        main = parts[0]
        bass = parts[1] if len(parts) > 1 else None
        is_minor = main.endswith("m")
        root = main[:-1] if is_minor else main
        root_semitone = get_note_semitone(root)
        if root_semitone is None:
            continue

        degree = get_nashville_degree((root_semitone - tonic + 12) % 12)
        display = f"{degree}m" if is_minor else degree

        if bass:
            bass_semitone = get_note_semitone(bass)
            if bass_semitone is not None:
                bass_degree = get_nashville_degree((bass_semitone - tonic + 12) % 12)
                display = f"{display}/{bass_degree}"

        numbers.append(display)

    return " ".join(numbers)


def row_quality(row: dict) -> tuple:
    normalized_full = clean_chord_sequence(row.get("chords"))
    has_markers = 1 if SECTION_TAG_PATTERN.search(row.get("chords", "") or "") else 0
    populated_fields = sum(1 for value in row.values() if normalize_whitespace(value))
    return (has_markers, len(normalized_full.split()), populated_fields)


def pick_best_row(rows: list[dict]) -> dict:
    return max(rows, key=row_quality)


def pick_field(rows: list[dict], field_name: str) -> str | None:
    for row in sorted(rows, key=row_quality, reverse=True):
        value = clean_string(row.get(field_name))
        if value is not None:
            return value
    return None


def derive_parse_status(section_entries: list[dict], normalized_full: str) -> str:
    if not normalized_full:
        return "no_chords"
    if not section_entries:
        return "unsectioned_full_song"
    has_nonstandard = any(entry["section_type_estimated"] not in STANDARD_SECTION_TYPES for entry in section_entries)
    return "sections_with_nonstandard_labels" if has_nonstandard else "sections_explicit"


def load_catalog_memberships(csv_path: Path, catalog_name: str) -> dict[str, list[dict]]:
    memberships: dict[str, list[dict]] = defaultdict(list)
    if not csv_path.exists():
        return memberships

    seen: set[tuple[str, str, str]] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            spotify_song_id = clean_string(row.get("spotify_song_id"))
            if not spotify_song_id:
                continue
            bucket = clean_string(row.get("christian_bucket"))
            dedupe_key = (spotify_song_id, catalog_name, bucket or "")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            memberships[spotify_song_id].append(
                {
                    "catalog_name": catalog_name,
                    "catalog_bucket": bucket,
                    "source_file": str(csv_path),
                }
            )
    return memberships


def split_multi_value_field(text: str | None) -> list[str]:
    value = text or ""
    if not value.strip():
        return []
    return [part.strip() for part in re.split(r"\s*\|\|\s*|\r?\n+", value) if part.strip()]


def parse_override_changes(text: str | None) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for item in split_multi_value_field(text):
        match = re.match(r"^([^:=]+?)\s*(?:=|:)\s*(.+)$", item)
        if not match:
            continue
        section_name = normalize_label(match.group(1))
        progression = normalize_whitespace(match.group(2))
        if section_name and progression:
            changes.append({"section_name": section_name, "progression": progression})
    return changes


def load_review_queue_overrides(queue_path: Path | None) -> dict[str, list[dict]]:
    overrides: dict[str, list[dict]] = defaultdict(list)
    if not queue_path or not queue_path.exists():
        return overrides

    with queue_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            spotify_song_id = clean_string(row.get("spotify_song_id"))
            if not spotify_song_id:
                continue

            review_status = normalize_label(row.get("review_status"))
            if review_status not in APPROVED_OVERRIDE_STATUSES:
                continue

            action = normalize_label(row.get("override_action"))
            if action and action not in SECTION_OVERRIDE_ACTIONS:
                continue

            changes = parse_override_changes(row.get("override_changes"))
            if not changes:
                continue

            notes = clean_string(row.get("review_notes"))
            source_urls = " || ".join(split_multi_value_field(row.get("source_urls")))
            overrides[spotify_song_id].append(
                {
                    "action": action or "replace_sections",
                    "changes": changes,
                    "review_notes": notes or "",
                    "source_urls": source_urls,
                    "artist_name": clean_string(row.get("artist_name")) or "",
                    "track_name": clean_string(row.get("track_name")) or "",
                }
            )

    return overrides


def build_override_reason(override: dict) -> str:
    parts = ["Review queue override applied."]
    if override.get("review_notes"):
        parts.append(override["review_notes"])
    if override.get("source_urls"):
        parts.append(f"Sources: {override['source_urls']}")
    return " ".join(parts)


def append_version_note(existing_notes: str | None, message: str) -> str:
    if not existing_notes:
        return message
    if message in existing_notes:
        return existing_notes
    return f"{existing_notes} | {message}"


def apply_review_queue_overrides(
    conn: sqlite3.Connection,
    song_id: int,
    song_version_id: int,
    spotify_song_id: str | None,
    queue_overrides: dict[str, list[dict]],
) -> dict[str, int]:
    if not spotify_song_id or spotify_song_id not in queue_overrides:
        return {"rows_changed": 0, "entries_inserted": 0, "override_records_written": 0}

    section_rows = conn.execute(
        """
        SELECT
            id,
            name_raw,
            section_type_estimated,
            ordinal,
            position_index,
            raw_chords,
            normalized_chords,
            nashville,
            nashville_relative_major,
            core_progression,
            confidence,
            is_repeating,
            is_fallback_full_song,
            length_chords
        FROM section_occurrences
        WHERE song_version_id = ?
        ORDER BY position_index, ordinal, id
        """,
        (song_version_id,),
    ).fetchall()

    rows_changed = 0
    entries_inserted = 0
    override_records_written = 0
    next_position_index = (max((int(row["position_index"]) for row in section_rows), default=-1) + 1)

    for override in queue_overrides[spotify_song_id]:
        reason = build_override_reason(override)
        for change in override["changes"]:
            section_name = change["section_name"]
            progression = change["progression"]

            exact_matches = [
                row for row in section_rows
                if normalize_label(row["name_raw"]) == section_name
            ]
            if exact_matches:
                target_rows = exact_matches
                target_section_type = exact_matches[0]["section_type_estimated"] or estimate_section_type(section_name)
            else:
                target_section_type = estimate_section_type(section_name)
                target_rows = [
                    row for row in section_rows
                    if normalize_label(row["section_type_estimated"]) == target_section_type
                ]

            if target_rows:
                for row in target_rows:
                    old_value = clean_string(row["nashville_relative_major"]) or clean_string(row["nashville"]) or ""
                    conn.execute(
                        """
                        UPDATE section_occurrences
                        SET
                            nashville = ?,
                            nashville_relative_major = ?,
                            core_progression = ?,
                            confidence = CASE
                                WHEN confidence IS NULL OR confidence < 0.95 THEN 0.95
                                ELSE confidence
                            END
                        WHERE id = ?
                        """,
                        (progression, progression, progression, row["id"]),
                    )
                    conn.execute(
                        """
                        INSERT INTO manual_overrides (
                            entity_type,
                            entity_id,
                            field_name,
                            old_value,
                            new_value,
                            reason,
                            created_by
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "section_occurrence",
                            row["id"],
                            "nashville_relative_major",
                            old_value,
                            progression,
                            reason,
                            "worship_song_verification_queue",
                        ),
                    )
                    rows_changed += 1
                    override_records_written += 1
            else:
                ordinal = 1
                same_type_ordinals = [
                    int(row["ordinal"])
                    for row in section_rows
                    if normalize_label(row["section_type_estimated"]) == target_section_type and row["ordinal"] is not None
                ]
                if same_type_ordinals:
                    ordinal = max(same_type_ordinals) + 1

                name_raw = section_name if re.search(r"_\d+$", section_name) else f"{target_section_type}_{ordinal}"
                cursor = conn.execute(
                    """
                    INSERT INTO section_occurrences (
                        song_version_id,
                        name_raw,
                        section_type_estimated,
                        ordinal,
                        position_index,
                        raw_chords,
                        normalized_chords,
                        nashville,
                        nashville_relative_major,
                        core_progression,
                        confidence,
                        is_repeating,
                        is_fallback_full_song,
                        length_chords
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        song_version_id,
                        name_raw,
                        target_section_type,
                        ordinal,
                        next_position_index,
                        None,
                        None,
                        progression,
                        progression,
                        progression,
                        0.95,
                        0,
                        0,
                        len(progression.split()),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO manual_overrides (
                        entity_type,
                        entity_id,
                        field_name,
                        old_value,
                        new_value,
                        reason,
                        created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "section_occurrence",
                        cursor.lastrowid,
                        "nashville_relative_major",
                        None,
                        progression,
                        reason,
                        "worship_song_verification_queue",
                    ),
                )
                section_rows = section_rows + [
                    {
                        "id": cursor.lastrowid,
                        "name_raw": name_raw,
                        "section_type_estimated": target_section_type,
                        "ordinal": ordinal,
                        "position_index": next_position_index,
                        "nashville": progression,
                        "nashville_relative_major": progression,
                    }
                ]
                entries_inserted += 1
                override_records_written += 1
                next_position_index += 1

        existing_notes = conn.execute(
            "SELECT notes FROM song_versions WHERE id = ?",
            (song_version_id,),
        ).fetchone()
        updated_notes = append_version_note(
            existing_notes["notes"] if existing_notes else None,
            "Manual review queue overrides applied",
        )
        conn.execute(
            """
            UPDATE song_versions
            SET
                notes = ?,
                section_parse_status = CASE
                    WHEN section_parse_status = 'unsectioned_full_song' THEN 'sections_with_manual_overrides'
                    ELSE section_parse_status
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (updated_notes, song_version_id),
        )

    return {
        "rows_changed": rows_changed,
        "entries_inserted": entries_inserted,
        "override_records_written": override_records_written,
    }


def create_database(conn: sqlite3.Connection, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def build_phase1_database(
    input_path: Path,
    schema_path: Path,
    output_path: Path,
    broad_catalog_path: Path | None = None,
    worship_catalog_path: Path | None = None,
    review_queue_path: Path | None = None,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with input_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    broad_memberships = (
        load_catalog_memberships(broad_catalog_path, "broad_christian_worship") if broad_catalog_path else {}
    )
    worship_memberships = (
        load_catalog_memberships(worship_catalog_path, "worship_strict") if worship_catalog_path else {}
    )
    queue_overrides = load_review_queue_overrides(review_queue_path)

    grouped_rows: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        spotify_song_id = clean_string(row.get("spotify_song_id"))
        row_id = clean_string(row.get("id")) or f"row_{len(grouped_rows) + 1}"
        group_key = spotify_song_id or f"import_row:{row_id}"
        grouped_rows[group_key].append(row)

    conn = sqlite3.connect(output_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    create_database(conn, schema_path)

    songs_written = 0
    versions_written = 0
    explicit_sections_written = 0
    fallback_sections_written = 0
    catalog_memberships_written = 0
    override_rows_changed = 0
    override_entries_inserted = 0
    override_records_written = 0

    for group_key, song_rows in grouped_rows.items():
        best_row = pick_best_row(song_rows)
        best_row_has_markers = any(SECTION_TAG_PATTERN.search(row.get("chords", "") or "") for row in song_rows)
        spotify_song_id = clean_string(best_row.get("spotify_song_id"))

        song_cursor = conn.execute(
            """
            INSERT INTO songs (
                spotify_song_id,
                title,
                artist_name,
                spotify_artist_id,
                release_date,
                year,
                genre,
                main_genre,
                source_genres,
                decade,
                rock_genre,
                country,
                source_status,
                has_complete_structure,
                has_section_markers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_string(best_row.get("spotify_song_id")),
                pick_field(song_rows, "track_name") or "Unknown Title",
                pick_field(song_rows, "artist_name") or "Unknown Artist",
                pick_field(song_rows, "spotify_artist_id"),
                pick_field(song_rows, "release_date"),
                parse_int(pick_field(song_rows, "year")),
                pick_field(song_rows, "genre"),
                pick_field(song_rows, "main_genre"),
                pick_field(song_rows, "genres"),
                pick_field(song_rows, "decade"),
                pick_field(song_rows, "rock_genre"),
                None,
                "imported",
                1 if best_row_has_markers else 0,
                1 if best_row_has_markers else 0,
            ),
        )
        song_id = song_cursor.lastrowid
        songs_written += 1

        memberships_for_song: list[dict] = []
        if spotify_song_id:
            memberships_for_song.extend(broad_memberships.get(spotify_song_id, []))
            memberships_for_song.extend(worship_memberships.get(spotify_song_id, []))

        for membership in memberships_for_song:
            conn.execute(
                """
                INSERT INTO song_catalog_memberships (
                    song_id,
                    catalog_name,
                    catalog_bucket,
                    source_file
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    song_id,
                    membership["catalog_name"],
                    membership["catalog_bucket"],
                    membership["source_file"],
                ),
            )
            catalog_memberships_written += 1

        conn.execute(
            """
            INSERT INTO song_audio_features (
                song_id,
                popularity,
                danceability,
                energy,
                spotify_key,
                loudness,
                spotify_mode,
                speechiness,
                acousticness,
                instrumentalness,
                liveness,
                valence,
                tempo,
                duration_ms,
                time_signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                song_id,
                parse_int(pick_field(song_rows, "popularity")),
                parse_float(pick_field(song_rows, "danceability")),
                parse_float(pick_field(song_rows, "energy")),
                parse_int(pick_field(song_rows, "key")),
                parse_float(pick_field(song_rows, "loudness")),
                parse_int(pick_field(song_rows, "mode")),
                parse_float(pick_field(song_rows, "speechiness")),
                parse_float(pick_field(song_rows, "acousticness")),
                parse_float(pick_field(song_rows, "instrumentalness")),
                parse_float(pick_field(song_rows, "liveness")),
                parse_float(pick_field(song_rows, "valence")),
                parse_float(pick_field(song_rows, "tempo")),
                parse_int(pick_field(song_rows, "duration_ms")),
                parse_int(pick_field(song_rows, "time_signature")),
            ),
        )

        ranked_rows = sorted(song_rows, key=row_quality, reverse=True)
        canonical_version_id: int | None = None
        for version_index, row in enumerate(ranked_rows, start=1):
            raw_chords_full = clean_string(row.get("chords")) or ""
            normalized_full = clean_chord_sequence(raw_chords_full)
            section_entries = parse_all_sections(raw_chords_full)
            chord_objects = chord_objects_from_sequences(
                [entry["normalized_chords"] for entry in section_entries] if section_entries else [normalized_full]
            )
            detected_key = detect_key(chord_objects)
            parse_status = derive_parse_status(section_entries, normalized_full)

            source_cursor = conn.execute(
                """
                INSERT INTO song_sources (
                    song_id,
                    source_type,
                    source_url,
                    external_source_id,
                    license_notes,
                    fetched_at,
                    raw_payload_path,
                    confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    song_id,
                    "merged_csv_import",
                    None,
                    clean_string(row.get("id")),
                    None,
                    None,
                    str(input_path),
                    None,
                ),
            )
            source_id = source_cursor.lastrowid

            version_cursor = conn.execute(
                """
                INSERT INTO song_versions (
                    song_id,
                    source_id,
                    version_label,
                    display_key,
                    detected_key_raw,
                    detected_key_relative_major,
                    normalization_mode,
                    raw_chords_full,
                    normalized_chords_full,
                    section_parse_status,
                    is_active_canonical,
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    song_id,
                    source_id,
                    f"import_row_{clean_string(row.get('id')) or version_index}",
                    detected_key["display_key"] if detected_key else None,
                    detected_key["raw_name"] if detected_key else None,
                    detected_key["relative_major_name"] if detected_key else None,
                    "relative_major_if_minor",
                    raw_chords_full or None,
                    normalized_full or None,
                    parse_status,
                    1 if row is ranked_rows[0] else 0,
                    None,
                ),
            )
            version_id = version_cursor.lastrowid
            versions_written += 1
            if row is ranked_rows[0]:
                canonical_version_id = version_id

            if section_entries:
                for entry in section_entries:
                    conn.execute(
                        """
                        INSERT INTO section_occurrences (
                            song_version_id,
                            name_raw,
                            section_type_estimated,
                            ordinal,
                            position_index,
                            raw_chords,
                            normalized_chords,
                            nashville,
                            nashville_relative_major,
                            core_progression,
                            confidence,
                            is_repeating,
                            is_fallback_full_song,
                            length_chords
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            version_id,
                            entry["name_raw"],
                            entry["section_type_estimated"],
                            entry["ordinal"],
                            entry["position_index"],
                            entry["raw_chords"],
                            entry["normalized_chords"],
                            convert_to_nashville_sequence(
                                entry["normalized_chords"],
                                detected_key["raw_tonic"] if detected_key else None,
                            ),
                            convert_to_nashville_sequence(
                                entry["normalized_chords"],
                                detected_key["relative_major_tonic"] if detected_key else None,
                            ),
                            None,
                            1.0 if entry["section_type_estimated"] in STANDARD_SECTION_TYPES else 0.8,
                            entry["is_repeating"],
                            0,
                            entry["length_chords"],
                        ),
                    )
                    explicit_sections_written += 1
            elif normalized_full:
                conn.execute(
                    """
                    INSERT INTO section_occurrences (
                        song_version_id,
                        name_raw,
                        section_type_estimated,
                        ordinal,
                        position_index,
                        raw_chords,
                        normalized_chords,
                        nashville,
                        nashville_relative_major,
                        core_progression,
                        confidence,
                        is_repeating,
                        is_fallback_full_song,
                        length_chords
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        "full_song_1",
                        "full_song",
                        1,
                        0,
                        raw_chords_full,
                        normalized_full,
                        convert_to_nashville_sequence(
                            normalized_full,
                            detected_key["raw_tonic"] if detected_key else None,
                        ),
                        convert_to_nashville_sequence(
                            normalized_full,
                            detected_key["relative_major_tonic"] if detected_key else None,
                        ),
                        None,
                        0.5,
                        0,
                        1,
                        len(normalized_full.split()),
                    ),
                )
                fallback_sections_written += 1

        override_result = apply_review_queue_overrides(
            conn=conn,
            song_id=song_id,
            song_version_id=canonical_version_id or 0,
            spotify_song_id=spotify_song_id,
            queue_overrides=queue_overrides,
        )
        override_rows_changed += override_result["rows_changed"]
        override_entries_inserted += override_result["entries_inserted"]
        override_records_written += override_result["override_records_written"]

    conn.commit()
    conn.close()

    return {
        "songs": songs_written,
        "versions": versions_written,
        "explicit_sections": explicit_sections_written,
        "fallback_full_song_sections": fallback_sections_written,
        "catalog_memberships": catalog_memberships_written,
        "override_rows_changed": override_rows_changed,
        "override_entries_inserted": override_entries_inserted,
        "override_records_written": override_records_written,
        "database": str(output_path),
    }


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the Phase 1 Melodex SQLite database.")
    parser.add_argument(
        "--input",
        dest="input_path",
        default=str(project_root / "data" / "processed" / "merged_spotify_chords.csv"),
        help="Path to the merged Spotify chords CSV.",
    )
    parser.add_argument(
        "--schema",
        dest="schema_path",
        default=str(project_root / "docs" / "melodex-schema.sql"),
        help="Path to the SQLite schema file.",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"),
        help="Path to the output SQLite database.",
    )
    parser.add_argument(
        "--broad-catalog",
        dest="broad_catalog_path",
        default=str(project_root / "data" / "processed" / "christian_worship_songs_refined.csv"),
        help="Path to the broad Christian/Worship song catalog CSV.",
    )
    parser.add_argument(
        "--worship-catalog",
        dest="worship_catalog_path",
        default=str(project_root / "data" / "processed" / "worship_songs_strict.csv"),
        help="Path to the strict worship song catalog CSV.",
    )
    default_review_queue = project_root / "data" / "review" / "worship_song_verification_queue_v2.csv"
    if not default_review_queue.exists():
        default_review_queue = project_root / "data" / "review" / "worship_song_verification_queue.csv"
    parser.add_argument(
        "--review-queue",
        dest="review_queue_path",
        default=str(default_review_queue),
        help="Path to the worship song verification queue CSV.",
    )
    args = parser.parse_args()

    result = build_phase1_database(
        input_path=Path(args.input_path),
        schema_path=Path(args.schema_path),
        output_path=Path(args.output_path),
        broad_catalog_path=Path(args.broad_catalog_path) if args.broad_catalog_path else None,
        worship_catalog_path=Path(args.worship_catalog_path) if args.worship_catalog_path else None,
        review_queue_path=Path(args.review_queue_path) if args.review_queue_path else None,
    )

    print(f"Melodex Phase 1 database written to: {result['database']}")
    print(f"Songs written: {result['songs']}")
    print(f"Versions written: {result['versions']}")
    print(f"Explicit sections written: {result['explicit_sections']}")
    print(f"Fallback full-song sections written: {result['fallback_full_song_sections']}")
    print(f"Catalog memberships written: {result['catalog_memberships']}")
    print(f"Override rows changed: {result['override_rows_changed']}")
    print(f"Override sections inserted: {result['override_entries_inserted']}")
    print(f"Override records written: {result['override_records_written']}")


if __name__ == "__main__":
    main()
