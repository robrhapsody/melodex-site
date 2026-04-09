from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


SECTION_LABEL_PATTERN = re.compile(r"^\[([A-Za-z0-9_ -]+)\]\s*$")
TOKEN_SPLIT_PATTERN = re.compile(r"\s+")
CHORD_TOKEN_PATTERN = re.compile(
    r"^[A-Ga-g](?:#|b|s)?(?:m(?![a-z])|maj7?|min|sus(?:2|4)?|add\d+|dim|aug|[0-9]*)*(?:/[A-Ga-g](?:#|b|s)?)?$",
    re.IGNORECASE,
)

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

SECTION_PREFIX_MAP = {
    "v": "verse",
    "c": "chorus",
    "b": "bridge",
    "p": "pre_chorus",
    "pc": "pre_chorus",
    "i": "intro",
    "o": "outro",
    "t": "tag",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_label(value: str | None) -> str:
    text = normalize_text(value).lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text)


def split_authors(author_text: str) -> list[str]:
    raw = normalize_text(author_text)
    if not raw:
        return []
    parts = re.split(r"\s*(?:,|;|/|&| and )\s*", raw, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def word_set(value: str | None) -> set[str]:
    words = re.findall(r"[A-Za-z0-9']+", normalize_text(value).lower())
    return {word for word in words if len(word) >= 3}


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


def semitone_for_note(note: str | None) -> int | None:
    if not note:
        return None
    return NOTE_TO_SEMITONE.get(note)


def parse_key_tonic(key_text: str | None) -> int | None:
    text = normalize_text(key_text)
    if not text:
        return None
    match = re.match(r"^([A-Ga-g])([#bs]?)(?:\s|_|$)", text)
    if not match:
        return None
    note = normalize_note_name(f"{match.group(1)}{match.group(2)}")
    return semitone_for_note(note)


def chord_token_to_parts(token: str) -> tuple[int, bool] | None:
    cleaned = token.strip().replace(".", "")
    if not cleaned:
        return None
    if re.fullmatch(r"(?i:n\.?c\.?)", cleaned):
        return None
    if not CHORD_TOKEN_PATTERN.fullmatch(cleaned):
        return None
    match = re.match(r"^([A-Ga-g])([#bs]?)(.*)$", cleaned)
    if not match:
        return None
    note = normalize_note_name(f"{match.group(1)}{match.group(2)}")
    semitone = semitone_for_note(note)
    if semitone is None:
        return None
    tail = (match.group(3) or "").lower()
    is_minor = bool(re.match(r"^m(?!aj)", tail) or "min" in tail)
    return semitone, is_minor


def chord_token_to_nashville(token: str, tonic: int | None) -> str | None:
    if tonic is None:
        return None
    parts = chord_token_to_parts(token)
    if not parts:
        return None
    semitone, is_minor = parts
    degree = DEGREE_MAP[(semitone - tonic + 12) % 12]
    return f"{degree}m" if is_minor else degree


def looks_like_chord_token(token: str) -> bool:
    return chord_token_to_parts(token) is not None


def parse_section_type(label: str) -> str:
    normalized = normalize_text(label).lower().replace("-", "").replace("_", "")
    if not normalized:
        return "unknown"
    prefix_match = re.match(r"^([a-z]+)", normalized)
    if not prefix_match:
        return "unknown"
    prefix = prefix_match.group(1)
    if prefix in SECTION_PREFIX_MAP:
        return SECTION_PREFIX_MAP[prefix]
    return "unknown"


def parse_opensong_file(path: Path) -> dict:
    try:
        xml_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        xml_text = path.read_text(encoding="latin-1")

    root = ET.fromstring(xml_text)
    title = normalize_text(root.findtext("title"))
    author = normalize_text(root.findtext("author"))
    key_text = normalize_text(root.findtext("key"))
    lyrics = root.findtext("lyrics") or ""
    tonic = parse_key_tonic(key_text)

    sections: dict[str, list[str]] = defaultdict(list)
    current_section = "unknown"
    for raw_line in lyrics.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section_match = SECTION_LABEL_PATTERN.match(line)
        if section_match:
            current_section = parse_section_type(section_match.group(1))
            continue

        tokens = [token for token in TOKEN_SPLIT_PATTERN.split(line) if token]
        chord_tokens = [token for token in tokens if looks_like_chord_token(token)]
        if not chord_tokens:
            continue

        for chord in chord_tokens:
            nash = chord_token_to_nashville(chord, tonic)
            if nash:
                sections[current_section].append(nash)

    section_strings = {
        name: " ".join(tokens)
        for name, tokens in sections.items()
        if tokens
    }

    all_tokens: list[str] = []
    for name in ("intro", "verse", "pre_chorus", "chorus", "bridge", "outro", "tag", "unknown"):
        section_text = section_strings.get(name, "")
        if section_text:
            all_tokens.extend(section_text.split())
    full_progression = " ".join(all_tokens)

    return {
        "file_name": path.name,
        "file_path": str(path),
        "title": title,
        "author": author,
        "authors": split_authors(author),
        "key": key_text,
        "tonic": tonic,
        "sections": section_strings,
        "full_progression": full_progression,
    }


def fetch_db_catalog(connection: sqlite3.Connection) -> tuple[list[dict], dict[str, list[dict]], dict[str, list[dict]]]:
    songs = connection.execute(
            """
            SELECT
                s.id AS song_id,
                sv.id AS song_version_id,
                COALESCE(s.spotify_song_id, '') AS spotify_song_id,
                COALESCE(s.spotify_artist_id, '') AS spotify_artist_id,
                COALESCE(s.title, '') AS title,
                COALESCE(s.artist_name, '') AS artist_name,
                COALESCE(s.main_genre, s.genre, '') AS genre,
                COALESCE(sv.display_key, '') AS display_key,
                COALESCE(sv.section_parse_status, '') AS parse_status,
                GROUP_CONCAT(DISTINCT scm.catalog_name) AS catalog_names
            FROM songs s
            JOIN song_versions sv ON sv.song_id = s.id AND sv.is_active_canonical = 1
            JOIN song_catalog_memberships scm ON scm.song_id = s.id
            WHERE scm.catalog_name IN ('worship_strict', 'broad_christian_worship')
            GROUP BY s.id, sv.id, s.spotify_song_id, s.spotify_artist_id, s.title, s.artist_name, s.main_genre, s.genre, sv.display_key, sv.section_parse_status
            """
        ).fetchall()

    sections = connection.execute(
            """
            SELECT
                so.song_version_id,
                so.section_type_estimated,
                so.name_raw,
                COALESCE(NULLIF(so.nashville_relative_major, ''), NULLIF(so.nashville, ''), NULLIF(so.normalized_chords, ''), '') AS progression
            FROM section_occurrences so
            JOIN song_versions sv ON sv.id = so.song_version_id
            WHERE sv.is_active_canonical = 1
            """
        ).fetchall()

    song_rows: list[dict] = []
    by_title: dict[str, list[dict]] = defaultdict(list)
    for row in songs:
        song = {
            "song_id": int(row["song_id"]),
            "song_version_id": int(row["song_version_id"]),
            "spotify_song_id": row["spotify_song_id"],
            "spotify_artist_id": row["spotify_artist_id"],
            "title": row["title"],
            "artist_name": row["artist_name"],
            "genre": row["genre"],
            "display_key": row["display_key"],
            "parse_status": row["parse_status"],
            "catalog_names": normalize_text(row["catalog_names"]),
            "sections": {},
        }
        song_rows.append(song)
        by_title[normalize_label(song["title"])].append(song)

    by_song_version = {song["song_version_id"]: song for song in song_rows}
    for row in sections:
        song = by_song_version.get(int(row["song_version_id"]))
        if not song:
            continue
        section_name = normalize_text(row["section_type_estimated"]) or normalize_text(row["name_raw"]) or "unknown"
        progression = normalize_text(row["progression"])
        if not progression:
            continue
        if section_name not in song["sections"]:
            song["sections"][section_name] = progression

    by_artist: dict[str, list[dict]] = defaultdict(list)
    for song in song_rows:
        by_artist[normalize_label(song["artist_name"])].append(song)

    return song_rows, by_title, by_artist


def ensure_catalog_membership(connection: sqlite3.Connection, song_id: int, catalog_name: str, source_file: str) -> None:
    exists = connection.execute(
        "SELECT 1 FROM song_catalog_memberships WHERE song_id = ? AND catalog_name = ? LIMIT 1",
        (song_id, catalog_name),
    ).fetchone()
    if exists:
        return
    connection.execute(
        """
        INSERT INTO song_catalog_memberships (song_id, catalog_name, catalog_bucket, source_file)
        VALUES (?, ?, ?, ?)
        """,
        (song_id, catalog_name, "worship", source_file),
    )


def insert_opensong_song(connection: sqlite3.Connection, parsed: dict, source_dir: Path) -> dict:
    display_key = parsed["key"] or ""
    raw_full = parsed["full_progression"]
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
            parsed["title"],
            parsed["author"] or "Unknown Artist",
            None,
            "worship",
            "worship",
            "imported_opensong",
            1,
            1 if parsed["sections"] else 0,
        ),
    ).lastrowid

    ensure_catalog_membership(connection, song_id, "worship_strict", str(source_dir))
    ensure_catalog_membership(connection, song_id, "broad_christian_worship", str(source_dir))

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
            "opensong_import",
            None,
            parsed["file_name"],
            parsed["file_path"],
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
            "opensong_import",
            display_key,
            display_key,
            display_key,
            "opensong_nashville_from_key",
            raw_full,
            raw_full,
            "sections_explicit" if parsed["sections"] else "unsectioned_full_song",
            1,
            "Imported from OpenSong files",
        ),
    ).lastrowid

    position = 0
    for section_name in ("intro", "verse", "pre_chorus", "chorus", "bridge", "tag", "outro", "unknown"):
        progression = normalize_text(parsed["sections"].get(section_name))
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

    if not parsed["sections"] and parsed["full_progression"]:
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
                "full_song_1",
                "full_song",
                1,
                0,
                None,
                parsed["full_progression"],
                parsed["full_progression"],
                parsed["full_progression"],
                None,
                0.75,
                0,
                1,
                len(parsed["full_progression"].split()),
            ),
        )

    return {
        "song_id": song_id,
        "song_version_id": version_id,
        "spotify_song_id": "",
        "spotify_artist_id": "",
        "title": parsed["title"],
        "artist_name": parsed["author"] or "Unknown Artist",
        "genre": "worship",
        "display_key": display_key,
        "parse_status": "sections_explicit" if parsed["sections"] else "unsectioned_full_song",
        "catalog_names": "worship_strict,broad_christian_worship",
        "sections": {k: v for k, v in parsed["sections"].items() if v},
    }


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
    base = max(len(left_tokens), len(right_tokens))
    return common / base if base else 0.0


def pick_best_db_match(opensong: dict, title_index: dict[str, list[dict]], artist_index: dict[str, list[dict]]) -> dict | None:
    title_key = normalize_label(opensong["title"])
    if not title_key:
        return None
    candidates = title_index.get(title_key, [])
    if not candidates:
        return None

    author_word_sets = [word_set(name) for name in opensong["authors"] if word_set(name)]
    artist_scores: list[tuple[int, dict]] = []
    for candidate in candidates:
        candidate_words = word_set(candidate["artist_name"])
        score = 0
        for author_words in author_word_sets:
            overlap = candidate_words.intersection(author_words)
            score = max(score, len(overlap))
        artist_scores.append((score, candidate))

    artist_scores.sort(key=lambda item: item[0], reverse=True)
    if artist_scores and artist_scores[0][0] >= 1:
        top_score = artist_scores[0][0]
        top_candidates = [candidate for score, candidate in artist_scores if score == top_score]
        return top_candidates[0] if len(top_candidates) == 1 else None

    # Require at least some artist/author signal; skip title-only matches.
    return None


def compare_sections(opensong: dict, db_song: dict) -> tuple[bool, str, str, float]:
    opensong_sections = opensong["sections"]
    db_sections = db_song["sections"]
    common_sections = [name for name in ("verse", "pre_chorus", "chorus", "bridge", "intro", "outro", "tag") if name in opensong_sections and name in db_sections]

    if common_sections:
        worst_section = ""
        worst_score = 1.0
        for section in common_sections:
            score = sequence_similarity(opensong_sections[section], db_sections[section])
            if score < worst_score:
                worst_score = score
                worst_section = section
        if worst_score < 0.55:
            summary = (
                f"OpenSong comparison found a low similarity in {worst_section} "
                f"(similarity {worst_score:.2f}) for this likely matching song."
            )
            snapshot = (
                f"db_{worst_section}={db_sections.get(worst_section, '')} | "
                f"opensong_{worst_section}={opensong_sections.get(worst_section, '')}"
            )
            return True, summary, snapshot, worst_score

    if opensong["full_progression"] and db_sections:
        db_primary = ""
        for section_name in ("verse", "chorus", "bridge", "pre_chorus", "full_song"):
            if section_name in db_sections:
                db_primary = db_sections[section_name]
                break
        if db_primary:
            score = sequence_similarity(opensong["full_progression"], db_primary)
            if score < 0.35:
                summary = f"OpenSong full progression differs strongly from current canonical progression (similarity {score:.2f})."
                snapshot = f"db_reference={db_primary} | opensong_full={opensong['full_progression']}"
                return True, summary, snapshot, score

    return False, "", "", 1.0


def read_existing_queue_keys(queue_path: Path) -> set[str]:
    if not queue_path.exists():
        return set()
    keys: set[str] = set()
    with queue_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            issue_types = normalize_text(row.get("issue_types"))
            if "opensong_conflict" not in issue_types:
                continue
            song_id = normalize_text(row.get("spotify_song_id"))
            title = normalize_text(row.get("track_name")).lower()
            artist = normalize_text(row.get("artist_name")).lower()
            keys.add(f"{song_id}|{artist}|{title}")
    return keys


def append_rows_to_queue(queue_path: Path, rows: list[dict]) -> int:
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


def write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Import OpenSong files and compare with Melodex DB.")
    parser.add_argument("--opensong-dir", default=str(project_root / "data" / "raw" / "opensong"))
    parser.add_argument("--db", default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"))
    parser.add_argument("--parsed-output", default=str(project_root / "data" / "processed" / "opensong_parsed_songs.csv"))
    parser.add_argument("--skipped-output", default=str(project_root / "data" / "review" / "opensong_skipped_missing_fields.csv"))
    parser.add_argument("--conflicts-output", default=str(project_root / "data" / "review" / "opensong_detected_conflicts.csv"))
    parser.add_argument("--queue-path", default=str(project_root / "data" / "review" / "worship_song_verification_queue_v2.csv"))
    parser.add_argument(
        "--queue-max-similarity",
        type=float,
        default=0.35,
        help="Only append OpenSong conflicts into the queue when similarity is <= this value.",
    )
    args = parser.parse_args()

    opensong_dir = Path(args.opensong_dir)
    db_path = Path(args.db)
    parsed_output = Path(args.parsed_output)
    skipped_output = Path(args.skipped_output)
    conflicts_output = Path(args.conflicts_output)
    queue_path = Path(args.queue_path)

    parsed_rows: list[dict] = []
    skipped_rows: list[dict] = []
    conflict_rows: list[dict] = []
    queue_candidate_rows: list[dict] = []
    existing_queue_keys = read_existing_queue_keys(queue_path)
    inserted_rows = 0

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        song_rows, by_title, by_artist = fetch_db_catalog(con)
        _ = by_artist, song_rows

        for path in sorted(opensong_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                parsed = parse_opensong_file(path)
            except Exception as exc:  # noqa: BLE001
                skipped_rows.append(
                    {
                        "file_name": path.name,
                        "file_path": str(path),
                        "title": "",
                        "author": "",
                        "key": "",
                        "reason": f"parse_error: {exc}",
                    }
                )
                continue

            missing = []
            if not parsed["title"]:
                missing.append("missing_title")
            if not parsed["author"]:
                missing.append("missing_author")
            if not parsed["full_progression"]:
                missing.append("missing_chords")

            if missing:
                skipped_rows.append(
                    {
                        "file_name": parsed["file_name"],
                        "file_path": parsed["file_path"],
                        "title": parsed["title"],
                        "author": parsed["author"],
                        "key": parsed["key"],
                        "reason": ",".join(missing),
                    }
                )
                continue

            parsed_rows.append(
                {
                    "file_name": parsed["file_name"],
                    "file_path": parsed["file_path"],
                    "title": parsed["title"],
                    "author": parsed["author"],
                    "key": parsed["key"],
                    "verse": parsed["sections"].get("verse", ""),
                    "pre_chorus": parsed["sections"].get("pre_chorus", ""),
                    "chorus": parsed["sections"].get("chorus", ""),
                    "bridge": parsed["sections"].get("bridge", ""),
                    "full_progression": parsed["full_progression"],
                }
            )

            match = pick_best_db_match(parsed, by_title, by_artist)
            if not match:
                inserted = insert_opensong_song(con, parsed, opensong_dir)
                by_title[normalize_label(inserted["title"])].append(inserted)
                by_artist[normalize_label(inserted["artist_name"])].append(inserted)
                inserted_rows += 1
                continue

            is_conflict, summary, snapshot, similarity_score = compare_sections(parsed, match)
            if not is_conflict:
                continue

            conflict_rows.append(
                {
                    "file_name": parsed["file_name"],
                    "title": parsed["title"],
                    "author": parsed["author"],
                    "spotify_song_id": match["spotify_song_id"],
                    "artist_name_db": match["artist_name"],
                    "track_name_db": match["title"],
                    "summary": summary,
                    "similarity_score": f"{similarity_score:.2f}",
                    "section_snapshot": snapshot,
                    "opensong_source_path": parsed["file_path"],
                }
            )

            key = f"{match['spotify_song_id']}|{match['artist_name'].lower()}|{match['title'].lower()}"
            if key in existing_queue_keys:
                continue
            existing_queue_keys.add(key)
            if similarity_score > args.queue_max_similarity:
                continue

            queue_candidate_rows.append(
                {
                    "artist_name": match["artist_name"],
                    "track_name": match["title"],
                    "spotify_song_id": match["spotify_song_id"],
                    "spotify_artist_id": match["spotify_artist_id"],
                    "display_key": match["display_key"],
                    "genre": match["genre"],
                    "parse_status": match["parse_status"],
                    "issue_count": "1",
                    "priority_score": "72",
                    "issue_types": "opensong_conflict",
                    "issue_summary": f"{summary} (OpenSong similarity {similarity_score:.2f})",
                    "source_version_count": "1",
                    "section_snapshot": snapshot,
                    "suggested_search_query": f"{match['artist_name']} {match['title']} chords",
                    "review_status": "",
                    "review_notes": "OpenSong comparison flagged this as a likely progression mismatch.",
                    "override_action": "",
                    "override_changes": "",
                    "source_urls": parsed["file_path"],
                }
            )
        con.commit()
    finally:
        con.close()

    write_csv(
        parsed_output,
        parsed_rows,
        ["file_name", "file_path", "title", "author", "key", "verse", "pre_chorus", "chorus", "bridge", "full_progression"],
    )
    write_csv(
        skipped_output,
        skipped_rows,
        ["file_name", "file_path", "title", "author", "key", "reason"],
    )
    write_csv(
        conflicts_output,
        conflict_rows,
        ["file_name", "title", "author", "spotify_song_id", "artist_name_db", "track_name_db", "summary", "similarity_score", "section_snapshot", "opensong_source_path"],
    )

    appended_count = append_rows_to_queue(queue_path, queue_candidate_rows)

    print(f"OpenSong files processed: {len(parsed_rows) + len(skipped_rows)}")
    print(f"Parsed songs written: {len(parsed_rows)} -> {parsed_output}")
    print(f"Skipped songs written: {len(skipped_rows)} -> {skipped_output}")
    print(f"Inserted new songs into DB: {inserted_rows}")
    print(f"Conflicts detected: {len(conflict_rows)} -> {conflicts_output}")
    print(f"Queue rows appended: {appended_count} -> {queue_path}")


if __name__ == "__main__":
    main()
