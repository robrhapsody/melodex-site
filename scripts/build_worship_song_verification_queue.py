from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


SUSPICIOUS_ACCIDENTALS = {"#4", "b6"}
COMMON_WORSHIP_DEGREES = {"1", "2m", "3m", "4", "5", "6m"}
SECTION_PRIORITY = {
    "pre_chorus": 5,
    "chorus": 4,
    "bridge": 3,
    "verse": 2,
    "tag": 1,
    "interlude": 1,
    "outro": 1,
    "intro": 0,
    "full_song": -1,
}
COMPARE_SECTION_TYPES = ("pre_chorus", "chorus", "verse", "bridge", "tag")


@dataclass
class SectionEntry:
    base_name: str
    name_raw: str
    text: str
    tokens: tuple[str, ...]


@dataclass
class VersionProfile:
    version_id: int
    song_id: int
    is_active: bool
    parse_status: str
    sections: list[SectionEntry] = field(default_factory=list)

    @property
    def all_tokens(self) -> tuple[str, ...]:
        joined: list[str] = []
        for section in sorted(self.sections, key=lambda item: (SECTION_PRIORITY.get(item.base_name, 0), item.name_raw)):
            joined.extend(section.tokens)
        return tuple(joined)


@dataclass
class SongRecord:
    song_id: int
    spotify_song_id: str
    spotify_artist_id: str
    title: str
    artist_name: str
    display_key: str
    genre: str
    parse_status: str
    version_id: int
    sections: list[SectionEntry] = field(default_factory=list)


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.lower().split())


def normalize_title_for_family(title: str) -> str:
    value = normalize_text(title)
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\b(live|acoustic|radio version|studio version|remix|edit)\b", "", value)
    value = re.sub(r"\s*-\s*(live|acoustic|radio version|studio version|remix|edit)\b", "", value)
    value = re.sub(r"[^a-z0-9\s]", "", value)
    value = normalize_text(value)
    return value


def simplify_token(token: str) -> str:
    normalized = normalize_text(token)
    if not normalized:
        return ""
    return normalized.split("/", 1)[0].strip()


def tokenize_progression(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    return tuple(token for token in normalize_text(text).split(" ") if token)


def simplified_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for token in tokens:
        value = simplify_token(token)
        if not value:
            continue
        if not result or result[-1] != value:
            result.append(value)
    return tuple(result)


def longest_common_subsequence(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    if not left or not right:
        return 0

    previous = [0] * (len(right) + 1)
    current = [0] * (len(right) + 1)

    for left_index in range(1, len(left) + 1):
        for right_index in range(1, len(right) + 1):
            if left[left_index - 1] == right[right_index - 1]:
                current[right_index] = previous[right_index - 1] + 1
            else:
                current[right_index] = max(previous[right_index], current[right_index - 1])

        for right_index in range(len(right) + 1):
            previous[right_index] = current[right_index]
            current[right_index] = 0

    return previous[len(right)]


def progression_similarity(left_text: str, right_text: str) -> float:
    left = simplified_tokens(tokenize_progression(left_text))
    right = simplified_tokens(tokenize_progression(right_text))
    if not left or not right:
        return 0.0
    base_length = min(len(left), len(right))
    if not base_length:
        return 0.0
    return longest_common_subsequence(left, right) / base_length


def representative_section(entries: list[SectionEntry]) -> SectionEntry | None:
    if not entries:
        return None

    def score(entry: SectionEntry) -> tuple[int, int, int]:
        token_count = len(entry.tokens)
        return (
            SECTION_PRIORITY.get(entry.base_name, 0),
            30 - abs(token_count - 10),
            -token_count,
        )

    return max(entries, key=score)


def suspicious_accidentals(tokens: tuple[str, ...]) -> set[str]:
    return {simplify_token(token) for token in tokens if simplify_token(token) in SUSPICIOUS_ACCIDENTALS}


def common_worship_ratio(tokens: tuple[str, ...]) -> float:
    simplified = simplified_tokens(tokens)
    if not simplified:
        return 0.0
    common = sum(1 for token in simplified if token in COMMON_WORSHIP_DEGREES)
    return common / len(simplified)


def build_section_snapshot(sections: list[SectionEntry]) -> str:
    grouped: dict[str, list[SectionEntry]] = defaultdict(list)
    for section in sections:
        grouped[section.base_name].append(section)

    preview_parts: list[str] = []
    for base_name in ("verse", "pre_chorus", "chorus", "bridge", "full_song"):
        entry = representative_section(grouped.get(base_name, []))
        if not entry:
            continue
        preview_parts.append(f"{base_name}={entry.text[:140]}")
    return " | ".join(preview_parts)


def fetch_song_data(connection: sqlite3.Connection) -> tuple[dict[int, SongRecord], dict[int, list[VersionProfile]]]:
    song_rows = connection.execute(
        """
        SELECT
            s.id AS song_id,
            COALESCE(s.spotify_song_id, '') AS spotify_song_id,
            COALESCE(s.spotify_artist_id, '') AS spotify_artist_id,
            COALESCE(s.title, '') AS title,
            COALESCE(s.artist_name, '') AS artist_name,
            COALESCE(sv.display_key, '') AS display_key,
            COALESCE(NULLIF(s.main_genre, ''), NULLIF(s.genre, ''), NULLIF(s.source_genres, ''), '') AS genre_display,
            COALESCE(sv.section_parse_status, '') AS parse_status,
            sv.id AS version_id
        FROM songs s
        JOIN song_catalog_memberships scm
            ON scm.song_id = s.id
           AND scm.catalog_name = 'worship_strict'
        JOIN song_versions sv
            ON sv.song_id = s.id
           AND sv.is_active_canonical = 1
        ORDER BY s.artist_name, s.title
        """
    ).fetchall()

    version_rows = connection.execute(
        """
        SELECT
            sv.id AS version_id,
            sv.song_id,
            sv.is_active_canonical,
            COALESCE(sv.section_parse_status, '') AS parse_status
        FROM song_versions sv
        JOIN song_catalog_memberships scm
            ON scm.song_id = sv.song_id
           AND scm.catalog_name = 'worship_strict'
        ORDER BY sv.song_id, sv.id
        """
    ).fetchall()

    section_rows = connection.execute(
        """
        SELECT
            so.song_version_id,
            COALESCE(so.section_type_estimated, '') AS base_name,
            COALESCE(so.name_raw, '') AS name_raw,
            COALESCE(NULLIF(so.nashville_relative_major, ''), NULLIF(so.nashville, ''), NULLIF(so.normalized_chords, '')) AS progression
        FROM section_occurrences so
        JOIN song_versions sv ON sv.id = so.song_version_id
        JOIN song_catalog_memberships scm
            ON scm.song_id = sv.song_id
           AND scm.catalog_name = 'worship_strict'
        ORDER BY so.song_version_id, so.position_index, so.ordinal, so.id
        """
    ).fetchall()

    sections_by_version: dict[int, list[SectionEntry]] = defaultdict(list)
    for row in section_rows:
        text = (row["progression"] or "").strip()
        if not text:
            continue
        sections_by_version[int(row["song_version_id"])].append(
            SectionEntry(
                base_name=row["base_name"] or "unknown",
                name_raw=row["name_raw"] or (row["base_name"] or "unknown"),
                text=text,
                tokens=tokenize_progression(text),
            )
        )

    versions_by_song: dict[int, list[VersionProfile]] = defaultdict(list)
    for row in version_rows:
        version = VersionProfile(
            version_id=int(row["version_id"]),
            song_id=int(row["song_id"]),
            is_active=bool(row["is_active_canonical"]),
            parse_status=row["parse_status"],
            sections=sections_by_version.get(int(row["version_id"]), []),
        )
        versions_by_song[version.song_id].append(version)

    songs: dict[int, SongRecord] = {}
    for row in song_rows:
        song_id = int(row["song_id"])
        songs[song_id] = SongRecord(
            song_id=song_id,
            spotify_song_id=row["spotify_song_id"],
            spotify_artist_id=row["spotify_artist_id"],
            title=row["title"],
            artist_name=row["artist_name"],
            display_key=row["display_key"],
            genre=row["genre_display"],
            parse_status=row["parse_status"],
            version_id=int(row["version_id"]),
            sections=sections_by_version.get(int(row["version_id"]), []),
        )

    return songs, versions_by_song


def build_queue_rows(songs: dict[int, SongRecord], versions_by_song: dict[int, list[VersionProfile]]) -> list[dict[str, str]]:
    issues_by_song: dict[int, list[dict]] = defaultdict(list)

    def add_issue(song_id: int, issue_type: str, priority: int, summary: str) -> None:
        issues_by_song[song_id].append(
            {
                "issue_type": issue_type,
                "priority": priority,
                "summary": summary,
            }
        )

    for song in songs.values():
        if song.parse_status == "unsectioned_full_song":
            add_issue(
                song.song_id,
                "no_sections",
                42,
                "No labeled sections were parsed; this song is currently using a full-song fallback only.",
            )

        versions = versions_by_song.get(song.song_id, [])
        active_version = next((version for version in versions if version.is_active), None)
        if active_version and len(versions) > 1:
            active_text = " ".join(active_version.all_tokens)
            for version in versions:
                if version.version_id == active_version.version_id:
                    continue
                other_text = " ".join(version.all_tokens)
                similarity = progression_similarity(active_text, other_text)
                if version.parse_status != active_version.parse_status or similarity < 0.45:
                    add_issue(
                        song.song_id,
                        "source_version_conflict",
                        78,
                        (
                            f"Imported versions disagree for this same song. Active parse status is "
                            f"{active_version.parse_status}, alternate version is {version.parse_status}, "
                            f"and progression similarity is {similarity:.2f}."
                        ),
                    )
                    break

        grouped_sections: dict[str, list[SectionEntry]] = defaultdict(list)
        for section in song.sections:
            grouped_sections[section.base_name].append(section)

        for base_name, entries in grouped_sections.items():
            if len(entries) < 2 or base_name not in COMPARE_SECTION_TYPES:
                continue

            worst_similarity = 1.0
            worst_pair: tuple[SectionEntry, SectionEntry] | None = None
            for index, left in enumerate(entries):
                for right in entries[index + 1:]:
                    if min(len(left.tokens), len(right.tokens)) < 6:
                        continue
                    similarity = progression_similarity(left.text, right.text)
                    if similarity < worst_similarity:
                        worst_similarity = similarity
                        worst_pair = (left, right)

            if worst_pair and worst_similarity < 0.6:
                add_issue(
                    song.song_id,
                    "repeated_section_disagreement",
                    64,
                    (
                        f"{base_name} occurrences differ more than expected "
                        f"({worst_pair[0].name_raw} vs {worst_pair[1].name_raw}, similarity {worst_similarity:.2f})."
                    ),
                )

        representative_candidates: list[SectionEntry] = []
        for base_name in COMPARE_SECTION_TYPES:
            entry = representative_section(grouped_sections.get(base_name, []))
            if entry:
                representative_candidates.append(entry)

        best_accidental_issue: tuple[int, str] | None = None
        for entry in representative_candidates:
            accidentals = suspicious_accidentals(entry.tokens)
            if not accidentals:
                continue
            if len(entry.tokens) < 6 or len(entry.tokens) > 20:
                continue
            ratio = common_worship_ratio(entry.tokens)
            if ratio < 0.6:
                continue
            priority = 48 + min(10, len(accidentals) * 4)
            summary = (
                f"{entry.name_raw} contains suspicious accidental degrees "
                f"({', '.join(sorted(accidentals))}) inside an otherwise common worship-style pattern: {entry.text[:140]}"
            )
            if best_accidental_issue is None or priority > best_accidental_issue[0]:
                best_accidental_issue = (priority, summary)

        if best_accidental_issue:
            add_issue(song.song_id, "odd_accidental", best_accidental_issue[0], best_accidental_issue[1])

    family_groups: dict[str, list[SongRecord]] = defaultdict(list)
    for song in songs.values():
        family_title = normalize_title_for_family(song.title)
        if family_title:
            family_groups[family_title].append(song)

    for family_title, family_songs in family_groups.items():
        if len(family_songs) < 2 or len(family_songs) > 5:
            continue
        if len(family_title.split()) < 2:
            continue

        for left_index, left_song in enumerate(family_songs):
            for right_song in family_songs[left_index + 1:]:
                if normalize_text(left_song.artist_name) == normalize_text(right_song.artist_name):
                    continue

                left_sections: dict[str, SectionEntry] = {
                    base: representative_section([section for section in left_song.sections if section.base_name == base])
                    for base in COMPARE_SECTION_TYPES
                }
                right_sections: dict[str, SectionEntry] = {
                    base: representative_section([section for section in right_song.sections if section.base_name == base])
                    for base in COMPARE_SECTION_TYPES
                }

                for base_name in COMPARE_SECTION_TYPES:
                    left_entry = left_sections.get(base_name)
                    right_entry = right_sections.get(base_name)
                    if not left_entry or not right_entry:
                        continue

                    similarity = progression_similarity(left_entry.text, right_entry.text)
                    left_accidentals = suspicious_accidentals(left_entry.tokens)
                    right_accidentals = suspicious_accidentals(right_entry.tokens)
                    if similarity >= 0.65 and left_accidentals != right_accidentals and (left_accidentals or right_accidentals):
                        add_issue(
                            left_song.song_id,
                            "title_family_variant_conflict",
                            86,
                            (
                                f"{left_song.title} has a {base_name} that is broadly similar to "
                                f"{right_song.artist_name}'s version, but the accidentals differ "
                                f"({', '.join(sorted(left_accidentals)) or 'none'} vs {', '.join(sorted(right_accidentals)) or 'none'})."
                            ),
                        )
                        add_issue(
                            right_song.song_id,
                            "title_family_variant_conflict",
                            86,
                            (
                                f"{right_song.title} has a {base_name} that is broadly similar to "
                                f"{left_song.artist_name}'s version, but the accidentals differ "
                                f"({', '.join(sorted(right_accidentals)) or 'none'} vs {', '.join(sorted(left_accidentals)) or 'none'})."
                            ),
                        )
                        break

    queue_rows: list[dict[str, str]] = []
    for song_id, issues in issues_by_song.items():
        song = songs[song_id]
        unique_types: list[str] = []
        seen_types: set[str] = set()
        for issue in sorted(issues, key=lambda item: item["priority"], reverse=True):
            if issue["issue_type"] not in seen_types:
                unique_types.append(issue["issue_type"])
                seen_types.add(issue["issue_type"])

        issues_sorted = sorted(issues, key=lambda item: item["priority"], reverse=True)
        priority_score = min(100, sum(issue["priority"] for issue in issues_sorted[:3]))
        queue_rows.append(
            {
                "artist_name": song.artist_name,
                "track_name": song.title,
                "spotify_song_id": song.spotify_song_id,
                "spotify_artist_id": song.spotify_artist_id,
                "display_key": song.display_key,
                "genre": song.genre,
                "parse_status": song.parse_status,
                "issue_count": str(len(unique_types)),
                "priority_score": str(priority_score),
                "issue_types": " | ".join(unique_types),
                "issue_summary": " || ".join(issue["summary"] for issue in issues_sorted[:3]),
                "source_version_count": str(len(versions_by_song.get(song.song_id, []))),
                "section_snapshot": build_section_snapshot(song.sections),
                "suggested_search_query": f"{song.artist_name} {song.title} chords",
                "review_status": "",
                "review_notes": "",
                "override_action": "",
                "override_changes": "",
                "source_urls": "",
            }
        )

    queue_rows.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            -int(row["issue_count"]),
            row["artist_name"].lower(),
            row["track_name"].lower(),
        )
    )
    return queue_rows


def write_csv(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build the worship-song verification queue.")
    parser.add_argument(
        "--db",
        default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"),
        help="Path to the Melodex SQLite database.",
    )
    parser.add_argument(
        "--output",
        default=str(project_root / "data" / "review" / "worship_song_verification_queue.csv"),
        help="Path to the output review queue CSV.",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row
    try:
        songs, versions_by_song = fetch_song_data(connection)
        rows = build_queue_rows(songs, versions_by_song)
    finally:
        connection.close()

    output_path = Path(args.output)
    write_csv(output_path, rows)

    print(f"Worship verification queue written to: {output_path}")
    print(f"Songs in queue: {len(rows)}")


if __name__ == "__main__":
    main()
