from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


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

DEGREE_MAP = {
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

SECTION_COLS = [
    ("Intro", "intro"),
    ("Pre-Chorus", "pre_chorus"),
    ("Chorus", "chorus"),
    ("Bridge", "bridge"),
    ("Outro", "outro"),
]

APPEND_THRESHOLD = 0.35


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_label(value: str | None) -> str:
    text = normalize_text(value).lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_note_name(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    root = text[0].upper()
    suffix = text[1:].lower()
    if suffix in {"s", "#"}:
        return f"{root}#"
    if suffix == "b":
        return f"{root}b"
    return root


def parse_key_info(key_text: str) -> tuple[int | None, int | None, str]:
    text = normalize_text(key_text).replace("_", " ")
    if not text:
        return None, None, ""
    match = re.match(r"^([A-Ga-g])([#bs]?)(.*)$", text)
    if not match:
        return None, None, text
    note = normalize_note_name(f"{match.group(1)}{match.group(2)}")
    if note not in NOTE_TO_SEMITONE:
        return None, None, text
    tonic = NOTE_TO_SEMITONE[note]
    tail = (match.group(3) or "").lower()
    is_minor = "minor" in tail or re.search(r"\bm\b", tail) is not None
    relative_major = (tonic + 3) % 12 if is_minor else tonic
    display = note if not is_minor else semitone_to_name(relative_major)
    return tonic, relative_major, display


def semitone_to_name(semitone: int) -> str:
    for name, value in NOTE_TO_SEMITONE.items():
        if value == semitone and len(name) <= 2:
            return name
    return "C"


def normalize_chord_token(token: str) -> tuple[int, bool] | None:
    text = token.strip().strip(",;")
    if not text:
        return None
    text = text.rstrip(")")
    text = text.lstrip("(")
    text = text.replace("sus4", "sus").replace("sus2", "sus")
    match = re.match(r"^([A-Ga-g])([#bs]?)(.*)$", text)
    if not match:
        return None
    note = normalize_note_name(f"{match.group(1)}{match.group(2)}")
    if note not in NOTE_TO_SEMITONE:
        return None
    tail = (match.group(3) or "").lower()
    is_minor = bool(re.match(r"^m(?!aj)", tail) or "min" in tail)
    return NOTE_TO_SEMITONE[note], is_minor


def to_nashville(chord_text: str, tonic: int | None) -> str:
    if tonic is None:
        return ""
    out: list[str] = []
    for token in chord_text.split():
        parts = normalize_chord_token(token)
        if not parts:
            continue
        semitone, is_minor = parts
        degree = DEGREE_MAP[(semitone - tonic + 12) % 12]
        out.append(f"{degree}m" if is_minor else degree)
    return " ".join(out)


def sequence_similarity(left: str, right: str) -> float:
    left_tokens = left.split()
    right_tokens = right.split()
    if not left_tokens or not right_tokens:
        return 0.0
    common = 0
    right_counts: dict[str, int] = defaultdict(int)
    for token in right_tokens:
        right_counts[token] += 1
    for token in left_tokens:
        if right_counts[token] > 0:
            common += 1
            right_counts[token] -= 1
    return common / max(len(left_tokens), len(right_tokens))


def load_existing_queue_keys(queue_path: Path, issue_type: str) -> set[str]:
    keys: set[str] = set()
    if not queue_path.exists():
        return keys
    with queue_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            issue_types = normalize_text(row.get("issue_types"))
            if issue_type not in issue_types:
                continue
            key = f"{normalize_text(row.get('spotify_song_id'))}|{normalize_text(row.get('artist_name')).lower()}|{normalize_text(row.get('track_name')).lower()}"
            keys.add(key)
    return keys


def append_queue_rows(queue_path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    headers = [
        "artist_name",
        "track_name",
        "spotify_song_id",
        "spotify_artist_id",
        "display_key",
        "genre",
        "parse_status",
        "issue_count",
        "priority_score",
        "issue_types",
        "issue_summary",
        "source_version_count",
        "section_snapshot",
        "suggested_search_query",
        "review_status",
        "review_notes",
        "override_action",
        "override_changes",
        "source_urls",
    ]
    write_header = not queue_path.exists()
    with queue_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def fetch_db_catalog(connection: sqlite3.Connection) -> tuple[list[dict], dict[str, list[dict]]]:
    songs = connection.execute(
        """
        SELECT
            s.id AS song_id,
            COALESCE(s.spotify_song_id, '') AS spotify_song_id,
            COALESCE(s.spotify_artist_id, '') AS spotify_artist_id,
            COALESCE(s.title, '') AS title,
            COALESCE(s.artist_name, '') AS artist_name,
            COALESCE(s.main_genre, s.genre, '') AS genre,
            COALESCE(sv.display_key, '') AS display_key,
            COALESCE(sv.section_parse_status, '') AS parse_status,
            sv.id AS song_version_id
        FROM songs s
        JOIN song_versions sv ON sv.song_id = s.id AND sv.is_active_canonical = 1
        JOIN song_catalog_memberships scm ON scm.song_id = s.id
        WHERE scm.catalog_name IN ('worship_strict','broad_christian_worship')
        GROUP BY s.id, s.spotify_song_id, s.spotify_artist_id, s.title, s.artist_name, s.main_genre, s.genre, sv.display_key, sv.section_parse_status, sv.id
        """
    ).fetchall()

    section_rows = connection.execute(
        """
        SELECT
            so.song_version_id,
            COALESCE(so.section_type_estimated, so.name_raw, '') AS section_name,
            COALESCE(NULLIF(so.nashville_relative_major, ''), NULLIF(so.nashville, ''), '') AS progression
        FROM section_occurrences so
        JOIN song_versions sv ON sv.id = so.song_version_id
        WHERE sv.is_active_canonical = 1
        """
    ).fetchall()

    by_version: dict[int, dict[str, str]] = defaultdict(dict)
    for row in section_rows:
        name = normalize_text(row["section_name"])
        progression = normalize_text(row["progression"])
        if name and progression and name not in by_version[int(row["song_version_id"])]:
            by_version[int(row["song_version_id"])][name] = progression

    catalog: list[dict] = []
    by_title: dict[str, list[dict]] = defaultdict(list)
    for row in songs:
        item = {
            "song_id": int(row["song_id"]),
            "song_version_id": int(row["song_version_id"]),
            "spotify_song_id": row["spotify_song_id"],
            "spotify_artist_id": row["spotify_artist_id"],
            "title": row["title"],
            "artist_name": row["artist_name"],
            "genre": row["genre"],
            "display_key": row["display_key"],
            "parse_status": row["parse_status"],
            "sections": by_version.get(int(row["song_version_id"]), {}),
        }
        catalog.append(item)
        by_title[normalize_label(item["title"])].append(item)
    return catalog, by_title


def best_match(row: dict, title_index: dict[str, list[dict]]) -> dict | None:
    candidates = title_index.get(normalize_label(row["title"]), [])
    if not candidates:
        return None
    artist_tokens = set(re.findall(r"[a-z0-9]+", row["artist"].lower()))
    best = None
    best_score = 0
    for candidate in candidates:
        candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate["artist_name"].lower()))
        overlap = len(artist_tokens.intersection(candidate_tokens))
        if overlap > best_score:
            best_score = overlap
            best = candidate
    return best if best_score >= 1 else None


def ensure_membership(connection: sqlite3.Connection, song_id: int, catalog_name: str, source_file: str) -> None:
    existing = connection.execute(
        "SELECT 1 FROM song_catalog_memberships WHERE song_id = ? AND catalog_name = ? LIMIT 1",
        (song_id, catalog_name),
    ).fetchone()
    if existing:
        return
    connection.execute(
        """
        INSERT INTO song_catalog_memberships (song_id, catalog_name, catalog_bucket, source_file)
        VALUES (?, ?, ?, ?)
        """,
        (song_id, catalog_name, "worship", source_file),
    )


def insert_new_song(connection: sqlite3.Connection, row: dict, source_csv: Path) -> tuple[int, int]:
    song_id = connection.execute(
        """
        INSERT INTO songs (
            spotify_song_id,
            title,
            artist_name,
            spotify_artist_id,
            genre,
            main_genre,
            source_status,
            has_complete_structure,
            has_section_markers
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            None,
            row["title"],
            row["artist"],
            None,
            "worship",
            "worship",
            "imported_worship_csv",
            1,
            1,
        ),
    ).lastrowid

    ensure_membership(connection, song_id, "worship_strict", str(source_csv))
    ensure_membership(connection, song_id, "broad_christian_worship", str(source_csv))

    source_id = connection.execute(
        """
        INSERT INTO song_sources (
            song_id,
            source_type,
            source_url,
            external_source_id,
            raw_payload_path
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            song_id,
            "worship_csv_import",
            None,
            None,
            str(source_csv),
        ),
    ).lastrowid

    version_id = connection.execute(
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
            "worship_csv_import",
            row["display_key"],
            row["source_key"],
            row["display_key"],
            "relative_major_if_minor",
            row["raw_full"],
            row["nash_full"],
            "sections_explicit",
            1,
            "Imported from worship_songs.csv",
        ),
    ).lastrowid

    position = 0
    for section_name in ("intro", "pre_chorus", "chorus", "bridge", "outro"):
        progression = row["sections"].get(section_name, "")
        if not progression:
            continue
        connection.execute(
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
                f"{section_name}_1",
                section_name,
                1,
                position,
                None,
                progression,
                progression,
                progression,
                None,
                0.9,
                0,
                0,
                len(progression.split()),
            ),
        )
        position += 1

    return song_id, version_id


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Import worship_songs.csv and merge into Melodex DB.")
    parser.add_argument("--input", default=str(project_root / "data" / "raw" / "worship_songs.csv"))
    parser.add_argument("--db", default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"))
    parser.add_argument("--parsed-output", default=str(project_root / "data" / "processed" / "worship_csv_parsed_songs.csv"))
    parser.add_argument("--skipped-output", default=str(project_root / "data" / "review" / "worship_csv_skipped_missing_fields.csv"))
    parser.add_argument("--conflicts-output", default=str(project_root / "data" / "review" / "worship_csv_detected_conflicts.csv"))
    parser.add_argument("--queue-path", default=str(project_root / "data" / "review" / "worship_song_verification_queue_v2.csv"))
    args = parser.parse_args()

    input_path = Path(args.input)
    db_path = Path(args.db)
    parsed_output = Path(args.parsed_output)
    skipped_output = Path(args.skipped_output)
    conflicts_output = Path(args.conflicts_output)
    queue_path = Path(args.queue_path)

    parsed_rows: list[dict] = []
    skipped_rows: list[dict] = []
    conflicts_rows: list[dict] = []
    queue_rows: list[dict] = []

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        catalog, by_title = fetch_db_catalog(con)
        _ = catalog
        existing_keys = load_existing_queue_keys(queue_path, "worship_csv_conflict")

        with input_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                title = normalize_text(raw.get("Song Title"))
                artist = normalize_text(raw.get("Artist"))
                source_key = normalize_text(raw.get("Song Key"))

                section_nashville: dict[str, str] = {}
                raw_full_chunks: list[str] = []
                tonic_raw, tonic_relative, display_key = parse_key_info(source_key)
                for col_name, section_name in SECTION_COLS:
                    raw_value = normalize_text(raw.get(col_name))
                    if not raw_value:
                        continue
                    raw_full_chunks.append(raw_value)
                    progression = to_nashville(raw_value, tonic_relative)
                    if progression:
                        section_nashville[section_name] = progression

                full_nashville = " ".join(value for value in (section_nashville.get("intro", ""), section_nashville.get("pre_chorus", ""), section_nashville.get("chorus", ""), section_nashville.get("bridge", ""), section_nashville.get("outro", "")) if value)

                if not title or not artist or not full_nashville:
                    reasons = []
                    if not title:
                        reasons.append("missing_title")
                    if not artist:
                        reasons.append("missing_artist")
                    if not full_nashville:
                        reasons.append("missing_chords")
                    skipped_rows.append(
                        {
                            "title": title,
                            "artist": artist,
                            "song_key": source_key,
                            "reason": ",".join(reasons),
                        }
                    )
                    continue

                row = {
                    "title": title,
                    "artist": artist,
                    "source_key": source_key,
                    "display_key": display_key or source_key,
                    "sections": section_nashville,
                    "nash_full": full_nashville,
                    "raw_full": " | ".join(raw_full_chunks),
                }
                parsed_rows.append(
                    {
                        "title": title,
                        "artist": artist,
                        "song_key": source_key,
                        "display_key": row["display_key"],
                        "intro": section_nashville.get("intro", ""),
                        "pre_chorus": section_nashville.get("pre_chorus", ""),
                        "chorus": section_nashville.get("chorus", ""),
                        "bridge": section_nashville.get("bridge", ""),
                        "outro": section_nashville.get("outro", ""),
                        "full_progression": full_nashville,
                    }
                )

                match = best_match(row, by_title)
                if match:
                    worst_section = ""
                    worst_similarity = 1.0
                    for section_name in ("intro", "pre_chorus", "chorus", "bridge", "outro"):
                        left = row["sections"].get(section_name, "")
                        right = match["sections"].get(section_name, "")
                        if left and right:
                            score = sequence_similarity(left, right)
                            if score < worst_similarity:
                                worst_similarity = score
                                worst_section = section_name

                    if worst_section and worst_similarity < 0.55:
                        summary = (
                            f"worship_songs.csv differs in {worst_section} "
                            f"(similarity {worst_similarity:.2f}) for this likely matching song."
                        )
                        snapshot = (
                            f"db_{worst_section}={match['sections'].get(worst_section, '')} | "
                            f"csv_{worst_section}={row['sections'].get(worst_section, '')}"
                        )
                        conflicts_rows.append(
                            {
                                "title_csv": row["title"],
                                "artist_csv": row["artist"],
                                "spotify_song_id": match["spotify_song_id"],
                                "title_db": match["title"],
                                "artist_db": match["artist_name"],
                                "summary": summary,
                                "similarity_score": f"{worst_similarity:.2f}",
                                "section_snapshot": snapshot,
                            }
                        )

                        queue_key = f"{match['spotify_song_id']}|{match['artist_name'].lower()}|{match['title'].lower()}"
                        if worst_similarity <= APPEND_THRESHOLD and queue_key not in existing_keys:
                            existing_keys.add(queue_key)
                            queue_rows.append(
                                {
                                    "artist_name": match["artist_name"],
                                    "track_name": match["title"],
                                    "spotify_song_id": match["spotify_song_id"],
                                    "spotify_artist_id": match["spotify_artist_id"],
                                    "display_key": match["display_key"],
                                    "genre": match["genre"],
                                    "parse_status": match["parse_status"],
                                    "issue_count": "1",
                                    "priority_score": "70",
                                    "issue_types": "worship_csv_conflict",
                                    "issue_summary": f"{summary} (CSV similarity {worst_similarity:.2f})",
                                    "source_version_count": "1",
                                    "section_snapshot": snapshot,
                                    "suggested_search_query": f"{match['artist_name']} {match['title']} chords",
                                    "review_status": "",
                                    "review_notes": "worship_songs.csv comparison flagged this mismatch.",
                                    "override_action": "",
                                    "override_changes": "",
                                    "source_urls": str(input_path),
                                }
                            )
                    continue

                song_id, version_id = insert_new_song(con, row, input_path)
                by_title[normalize_label(row["title"])].append(
                    {
                        "song_id": song_id,
                        "song_version_id": version_id,
                        "spotify_song_id": "",
                        "spotify_artist_id": "",
                        "title": row["title"],
                        "artist_name": row["artist"],
                        "genre": "worship",
                        "display_key": row["display_key"],
                        "parse_status": "sections_explicit",
                        "sections": row["sections"],
                    }
                )

        con.commit()
    finally:
        con.close()

    write_csv(
        parsed_output,
        ["title", "artist", "song_key", "display_key", "intro", "pre_chorus", "chorus", "bridge", "outro", "full_progression"],
        parsed_rows,
    )
    write_csv(
        skipped_output,
        ["title", "artist", "song_key", "reason"],
        skipped_rows,
    )
    write_csv(
        conflicts_output,
        ["title_csv", "artist_csv", "spotify_song_id", "title_db", "artist_db", "summary", "similarity_score", "section_snapshot"],
        conflicts_rows,
    )
    appended = append_queue_rows(queue_path, queue_rows)

    print(f"Rows parsed: {len(parsed_rows)}")
    print(f"Rows skipped: {len(skipped_rows)}")
    print(f"Conflicts detected: {len(conflicts_rows)}")
    print(f"Queue rows appended: {appended}")


if __name__ == "__main__":
    main()
