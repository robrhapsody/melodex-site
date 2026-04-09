from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


CATALOG_ALL = "all"
CATALOG_BROAD = "broad_christian_worship"
CATALOG_WORSHIP = "worship_strict"
STANDARD_SECTIONS = ("intro", "verse", "pre_chorus", "chorus", "bridge", "tag", "interlude", "solo", "instrumental", "full_song", "outro")


@dataclass(slots=True)
class SectionProfile:
    name: str
    base_name: str
    text: str
    tokens: tuple[str, ...]
    simplified_tokens: tuple[str, ...]
    simplified_token_set: frozenset[str]
    core_tokens: tuple[str, ...]
    core_token_set: frozenset[str]
    simplified_windows: tuple[tuple[str, ...], ...]
    core_windows: tuple[tuple[str, ...], ...]
    window_keys: frozenset[str]


@dataclass(slots=True)
class SongRecord:
    row_id: str
    song_id: int
    spotify_song_id: str
    artist_id: str
    artist: str
    track: str
    year: str
    genre: str
    key: str
    bpm: float | None
    catalog_names: frozenset[str]
    catalog_buckets: tuple[str, ...]
    is_known_worship_artist: bool
    primary_catalog_label: str
    search_text: str
    sections: dict[str, str]
    section_entries: tuple[SectionProfile, ...]
    index_tokens: frozenset[str]
    window_keys: frozenset[str]


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.lower().split())


def normalize_section_name(name: str | None) -> str:
    if not name:
        return ""
    return normalize_text(name).replace("-", "_").replace(" ", "_")


def base_section_name(name: str | None) -> str:
    normalized = normalize_section_name(name)
    if not normalized:
        return ""
    parts = normalized.split("_")
    if parts and parts[-1].isdigit():
        parts = parts[:-1]
    return "_".join(parts)


def parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_artist_key(text: str | None) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    out_chars: list[str] = []
    for char in normalized:
        if char.isalnum() or char.isspace():
            out_chars.append(char)
        else:
            out_chars.append(" ")
    return " ".join("".join(out_chars).split())


def load_known_worship_artists(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()

    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        names.add(normalize_artist_key(line))
    return frozenset(name for name in names if name)


def is_known_worship_artist_name(artist_name: str, known_artists: frozenset[str]) -> bool:
    key = normalize_artist_key(artist_name)
    if not key:
        return False
    return key in known_artists


def tokenize_progression(text: str | None) -> tuple[str, ...]:
    normalized = normalize_text(text)
    return tuple(token for token in normalized.split(" ") if token)


def simplify_token(token: str) -> str:
    normalized = normalize_text(token)
    if not normalized:
        return ""
    return normalized.split("/", 1)[0].strip()


def build_simplified_tokens(tokens: Iterable[str]) -> tuple[str, ...]:
    simplified: list[str] = []
    for token in tokens:
        value = simplify_token(token)
        if not value:
            continue
        if not simplified or simplified[-1] != value:
            simplified.append(value)

    # Treat common chromatic neighbor motion like 1 b2 1 as ornamental
    # rather than part of the core progression backbone.
    if len(simplified) < 3:
        return tuple(simplified)

    ornamental_accidentals = {"b2", "#4", "b6"}
    collapsed: list[str] = []
    index = 0
    while index < len(simplified):
        if (
            index + 2 < len(simplified)
            and simplified[index] == simplified[index + 2]
            and simplified[index + 1] in ornamental_accidentals
        ):
            if not collapsed or collapsed[-1] != simplified[index]:
                collapsed.append(simplified[index])
            index += 3
            continue

        if not collapsed or collapsed[-1] != simplified[index]:
            collapsed.append(simplified[index])
        index += 1

    return tuple(collapsed)


def build_core_tokens(tokens: Iterable[str]) -> tuple[str, ...]:
    simplified = build_simplified_tokens(tokens)
    if len(simplified) < 4:
        return simplified

    if len(simplified) == 5 and simplified[0] == simplified[4] and simplified[1] == simplified[3]:
        return (simplified[0], simplified[2], simplified[1])

    if len(simplified) == 4 and simplified[1] == simplified[3]:
        return (simplified[0], simplified[2], simplified[1])

    return simplified


def get_window_sizes(length: int) -> tuple[int, ...]:
    if length <= 3:
        return (length,) if length else ()
    return tuple(range(3, min(length, 6) + 1))


def get_token_windows(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    if len(tokens) <= 3:
        return (tokens,) if tokens else ()

    windows: list[tuple[str, ...]] = []
    for size in get_window_sizes(len(tokens)):
        for start in range(0, len(tokens) - size + 1):
            windows.append(tokens[start:start + size])
    return tuple(windows)


def create_progression_profile(text: str, name: str, base_name: str) -> SectionProfile:
    tokens = tokenize_progression(text)
    simplified_tokens = build_simplified_tokens(tokens)
    core_tokens = build_core_tokens(tokens)
    simplified_windows = get_token_windows(simplified_tokens)
    core_windows = get_token_windows(core_tokens)
    window_keys = frozenset(
        " ".join(window)
        for window in simplified_windows + core_windows
        if len(window) >= 3
    )
    return SectionProfile(
        name=name,
        base_name=base_name,
        text=text.strip(),
        tokens=tokens,
        simplified_tokens=simplified_tokens,
        simplified_token_set=frozenset(simplified_tokens),
        core_tokens=core_tokens,
        core_token_set=frozenset(core_tokens),
        simplified_windows=simplified_windows,
        core_windows=core_windows,
        window_keys=window_keys,
    )


def longest_common_token_run(left_tokens: tuple[str, ...], right_tokens: tuple[str, ...]) -> int:
    if not left_tokens or not right_tokens:
        return 0

    table = [0] * (len(right_tokens) + 1)
    best = 0
    for left_index in range(1, len(left_tokens) + 1):
        previous_diagonal = 0
        for right_index in range(1, len(right_tokens) + 1):
            current = table[right_index]
            if left_tokens[left_index - 1] == right_tokens[right_index - 1]:
                table[right_index] = previous_diagonal + 1
                if table[right_index] > best:
                    best = table[right_index]
            else:
                table[right_index] = 0
            previous_diagonal = current
    return best


def longest_common_subsequence(left_tokens: tuple[str, ...], right_tokens: tuple[str, ...]) -> int:
    if not left_tokens or not right_tokens:
        return 0

    previous = [0] * (len(right_tokens) + 1)
    current = [0] * (len(right_tokens) + 1)

    for left_index in range(1, len(left_tokens) + 1):
        for right_index in range(1, len(right_tokens) + 1):
            if left_tokens[left_index - 1] == right_tokens[right_index - 1]:
                current[right_index] = previous[right_index - 1] + 1
            else:
                current[right_index] = max(previous[right_index], current[right_index - 1])

        for right_index in range(len(right_tokens) + 1):
            previous[right_index] = current[right_index]
            current[right_index] = 0

    return previous[len(right_tokens)]


def get_best_windowed_ratio(
    reference_windows: tuple[tuple[str, ...], ...],
    candidate_windows: tuple[tuple[str, ...], ...],
) -> dict:
    if not reference_windows or not candidate_windows:
        return {"ratio": 0.0, "run": 0, "reference_window": (), "candidate_window": ()}

    best = {"ratio": 0.0, "run": 0, "reference_window": (), "candidate_window": ()}

    for reference_window in reference_windows:
        for candidate_window in candidate_windows:
            run = longest_common_subsequence(reference_window, candidate_window)
            base_length = min(len(reference_window), len(candidate_window))
            ratio = run / base_length if base_length else 0.0
            if ratio > best["ratio"] or (ratio == best["ratio"] and run > best["run"]):
                best = {
                    "ratio": ratio,
                    "run": run,
                    "reference_window": reference_window,
                    "candidate_window": candidate_window,
                }

    return best


def build_basic_metrics(reference_entry: SectionProfile, candidate_entry: SectionProfile) -> dict:
    reference_tokens = reference_entry.tokens
    candidate_tokens = candidate_entry.tokens
    reference_string = " ".join(reference_tokens)
    candidate_string = " ".join(candidate_tokens)
    exact = reference_string == candidate_string
    contains = candidate_string.find(reference_string) >= 0 or reference_string.find(candidate_string) >= 0

    contiguous_run = longest_common_token_run(reference_tokens, candidate_tokens)
    contiguous_ratio = contiguous_run / min(len(reference_tokens), len(candidate_tokens))

    subsequence_run = longest_common_subsequence(reference_tokens, candidate_tokens)
    subsequence_ratio = subsequence_run / min(len(reference_tokens), len(candidate_tokens))

    simplified_subsequence_run = longest_common_subsequence(
        reference_entry.simplified_tokens,
        candidate_entry.simplified_tokens,
    )
    simplified_base_length = min(len(reference_entry.simplified_tokens), len(candidate_entry.simplified_tokens))
    simplified_subsequence_ratio = simplified_subsequence_run / simplified_base_length if simplified_base_length else 0.0

    return {
        "exact": exact,
        "contains": contains,
        "contiguous_run": contiguous_run,
        "contiguous_ratio": contiguous_ratio,
        "subsequence_run": subsequence_run,
        "subsequence_ratio": subsequence_ratio,
        "simplified_subsequence_run": simplified_subsequence_run,
        "simplified_subsequence_ratio": simplified_subsequence_ratio,
    }


def build_flexible_metrics(reference_entry: SectionProfile, candidate_entry: SectionProfile) -> dict:
    core_window_match = get_best_windowed_ratio(reference_entry.core_windows, candidate_entry.core_windows)
    simplified_window_match = get_best_windowed_ratio(reference_entry.simplified_windows, candidate_entry.simplified_windows)
    return {
        "core_window_ratio": core_window_match["ratio"],
        "core_window_run": core_window_match["run"],
        "core_window_reference": core_window_match["reference_window"],
        "core_window_candidate": core_window_match["candidate_window"],
        "simplified_window_ratio": simplified_window_match["ratio"],
        "simplified_window_run": simplified_window_match["run"],
    }


def classify_basic_match(metrics: dict, mode: str) -> str:
    if mode == "exact":
        return "Exact" if metrics["exact"] else ""
    if mode == "contains":
        return "Contains" if metrics["contains"] else ""
    if mode == "similar":
        return "Similar" if metrics["contiguous_ratio"] >= 0.6 else ""

    if metrics["exact"]:
        return "Exact"
    if metrics["contains"]:
        return "Contains"
    if metrics["contiguous_ratio"] >= 0.6:
        return "Similar"
    return ""


def score_candidate_against_reference(reference_entry: SectionProfile, candidate_entry: SectionProfile, mode: str) -> dict | None:
    if not reference_entry.tokens or not candidate_entry.tokens:
        return None

    shared_token_count = len(
        (reference_entry.simplified_token_set & candidate_entry.simplified_token_set)
        | (reference_entry.core_token_set & candidate_entry.core_token_set)
    )
    if shared_token_count == 0:
        return None

    minimum_meaningful_length = min(len(reference_entry.simplified_tokens), len(candidate_entry.simplified_tokens))
    if minimum_meaningful_length >= 3 and shared_token_count < 2:
        return None

    if reference_entry.window_keys and candidate_entry.window_keys and not (reference_entry.window_keys & candidate_entry.window_keys):
        return None

    reference_string = reference_entry.text
    candidate_string = candidate_entry.text
    has_long_sequence = max(len(reference_entry.tokens), len(candidate_entry.tokens)) > 12

    if has_long_sequence:
        if reference_string == candidate_string and mode in {"exact", "mixed"}:
            score = 400 + min(len(reference_entry.tokens), len(candidate_entry.tokens)) * 8
            return {
                "score": score,
                "label": "Exact",
                "detail": "Exact token-for-token progression match.",
                "candidate_section": candidate_entry.name,
                "reference_section": reference_entry.name,
            }

        if (
            mode in {"contains", "mixed"}
            and (candidate_string.find(reference_string) >= 0 or reference_string.find(candidate_string) >= 0)
        ):
            score = 280 + min(len(reference_entry.tokens), len(candidate_entry.tokens)) * 6
            return {
                "score": score,
                "label": "Contains",
                "detail": "One progression fully contains the other.",
                "candidate_section": candidate_entry.name,
                "reference_section": reference_entry.name,
            }

        if mode not in {"flexible", "mixed", "similar"}:
            return None

        flexible_metrics = build_flexible_metrics(reference_entry, candidate_entry)
        flexible_ratio = max(flexible_metrics["core_window_ratio"], flexible_metrics["simplified_window_ratio"])
        if flexible_ratio < 0.8:
            return None

        detail = (
            "Strong core-window match: "
            f"{' '.join(flexible_metrics['core_window_reference'])} aligns with "
            f"{' '.join(flexible_metrics['core_window_candidate'])} after reducing passing-chord motion."
            if flexible_metrics["core_window_ratio"] >= flexible_metrics["simplified_window_ratio"]
            and flexible_metrics["core_window_ratio"] >= 0.8
            else "Shared progression backbone inside a longer unlabeled or expanded section."
        )
        score = 130 + round(flexible_ratio * 120) + max(
            flexible_metrics["core_window_run"],
            flexible_metrics["simplified_window_run"],
        ) * 4
        if reference_entry.name == candidate_entry.name:
            score += 20

        return {
            "score": score,
            "label": "Passing-chord aware" if mode != "similar" else "Similar",
            "detail": detail,
            "candidate_section": candidate_entry.name,
            "reference_section": reference_entry.name,
        }

    basic_metrics = build_basic_metrics(reference_entry, candidate_entry)
    basic_label = classify_basic_match(basic_metrics, mode)
    if basic_label:
        if basic_label == "Exact":
            score = 400 + basic_metrics["contiguous_run"] * 8
            detail = "Exact token-for-token progression match."
        elif basic_label == "Contains":
            score = 280 + basic_metrics["contiguous_run"] * 6
            detail = "One progression fully contains the other."
        else:
            score = 140 + round(basic_metrics["contiguous_ratio"] * 100) + basic_metrics["contiguous_run"] * 3
            detail = f"Shared contiguous run: {basic_metrics['contiguous_run']} chords."

        if reference_entry.name == candidate_entry.name:
            score += 20

        return {
            "score": score,
            "label": basic_label,
            "detail": detail,
            "candidate_section": candidate_entry.name,
            "reference_section": reference_entry.name,
        }

    if mode not in {"flexible", "mixed"}:
        return None

    flexible_metrics = build_flexible_metrics(reference_entry, candidate_entry)
    flexible_ratio = max(
        basic_metrics["subsequence_ratio"],
        basic_metrics["simplified_subsequence_ratio"],
        flexible_metrics["core_window_ratio"],
        flexible_metrics["simplified_window_ratio"],
    )

    if flexible_ratio < 0.75 and flexible_metrics["core_window_ratio"] < 0.8:
        return None

    score = 120 + round(flexible_ratio * 120) + max(
        basic_metrics["simplified_subsequence_run"],
        flexible_metrics["core_window_run"],
    ) * 4
    if flexible_metrics["core_window_ratio"] >= basic_metrics["simplified_subsequence_ratio"] and flexible_metrics["core_window_ratio"] >= 0.8:
        detail = (
            "Strong core-window match: "
            f"{' '.join(flexible_metrics['core_window_reference'])} aligns with "
            f"{' '.join(flexible_metrics['core_window_candidate'])} after reducing passing-chord motion."
        )
    else:
        detail = "Shared progression backbone after allowing inserted passing chords or inversions."

    if reference_entry.name == candidate_entry.name:
        score += 20

    return {
        "score": score,
        "label": "Passing-chord aware",
        "detail": detail,
        "candidate_section": candidate_entry.name,
        "reference_section": reference_entry.name,
    }


def score_song_lookup(song: SongRecord, query: str) -> int:
    if not query:
        return 0

    haystack = song.search_text
    joined_name = normalize_text(f"{song.track} {song.artist}")
    track_only = normalize_text(song.track)
    artist_only = normalize_text(song.artist)

    if track_only == query or joined_name == query:
        return 1000
    if query in track_only or query in joined_name:
        return 800 + len(query)
    if artist_only == query:
        return 700
    if query in haystack:
        return 500 + len(query)

    terms = [term for term in query.split(" ") if term]
    if not terms:
        return 0
    hits = sum(1 for term in terms if term in haystack)
    return hits * 50 if hits else 0


def title_case_bucket(bucket: str | None) -> str:
    if not bucket:
        return ""
    return bucket.replace("_", " ").title()


class SongStore:
    def __init__(
        self,
        db_path: Path,
        supabase_url: str | None = None,
        supabase_key: str | None = None,
        known_worship_artist_path: Path | None = None,
    ) -> None:
        self.db_path = db_path
        self.supabase_url = (supabase_url or "").rstrip("/")
        self.supabase_key = supabase_key or ""
        self.known_worship_artist_path = known_worship_artist_path
        self.known_worship_artists = load_known_worship_artists(known_worship_artist_path) if known_worship_artist_path else frozenset()
        self.source_name = "supabase" if self.supabase_url and self.supabase_key else "sqlite"
        self.loaded_at = time.time()
        self.songs_by_row_id: dict[str, SongRecord] = {}
        self.songs_by_catalog: dict[str, tuple[SongRecord, ...]] = {}
        self.catalog_counts: dict[str, int] = {}
        self._load()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _supabase_fetch_all(
        self,
        table: str,
        select: str,
        filters: dict[str, str] | None = None,
        order: str | None = None,
        page_size: int = 1000,
    ) -> list[dict]:
        if not self.supabase_url or not self.supabase_key:
            return []

        rows: list[dict] = []
        offset = 0
        while True:
            params: dict[str, str] = {"select": select}
            if filters:
                params.update(filters)
            if order:
                params["order"] = order
            query = urlencode(params)
            url = f"{self.supabase_url}/rest/v1/{table}?{query}"
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
                "Range": f"{offset}-{offset + page_size - 1}",
            }
            request = Request(url=url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Supabase request failed for {table}: HTTP {exc.code} {body}") from exc
            except URLError as exc:
                raise RuntimeError(f"Supabase request failed for {table}: {exc}") from exc

            if not payload:
                break
            rows.extend(payload)
            if len(payload) < page_size:
                break
            offset += page_size

        return rows

    def _fetch_rows_from_supabase(self) -> tuple[list[dict], list[dict], list[dict]]:
        membership_rows = self._supabase_fetch_all(
            table="song_catalog_memberships",
            select="song_id,catalog_name,catalog_bucket",
            order="id.asc",
        )
        section_rows = self._supabase_fetch_all(
            table="section_occurrences",
            select="song_version_id,name_raw,section_type_estimated,position_index,ordinal,nashville_relative_major,nashville,normalized_chords",
            order="id.asc",
        )
        version_rows = self._supabase_fetch_all(
            table="song_versions",
            select="id,song_id,display_key,is_active_canonical",
            filters={"is_active_canonical": "eq.true"},
            order="id.asc",
        )
        song_rows_raw = self._supabase_fetch_all(
            table="songs",
            select="id,spotify_song_id,spotify_artist_id,artist_name,title,year,main_genre,genre,source_genres",
            order="id.asc",
        )
        try:
            audio_rows = self._supabase_fetch_all(
                table="song_audio_features",
                select="song_id,tempo",
                order="song_id.asc",
            )
        except RuntimeError:
            audio_rows = []
        bpm_by_song_id = {int(row["song_id"]): parse_float(row.get("tempo")) for row in audio_rows if row.get("song_id") is not None}

        song_map = {int(row["id"]): row for row in song_rows_raw if row.get("id") is not None}
        song_rows: list[dict] = []
        for version in version_rows:
            song_id = int(version["song_id"])
            song = song_map.get(song_id)
            if not song:
                continue
            genre_display = song.get("main_genre") or song.get("genre") or song.get("source_genres") or ""
            song_rows.append(
                {
                    "row_id": version["id"],
                    "song_id": song_id,
                    "spotify_song_id": song.get("spotify_song_id") or "",
                    "spotify_artist_id": song.get("spotify_artist_id") or "",
                    "artist_name": song.get("artist_name") or "",
                    "track_name": song.get("title") or "",
                    "year": "" if song.get("year") is None else str(song.get("year")),
                    "genre_display": genre_display,
                    "display_key": version.get("display_key") or "",
                    "bpm": bpm_by_song_id.get(song_id),
                }
            )

        normalized_sections: list[dict] = []
        for section in section_rows:
            progression_text = section.get("nashville_relative_major") or section.get("nashville") or section.get("normalized_chords") or ""
            normalized_sections.append(
                {
                    "song_version_id": section.get("song_version_id"),
                    "name_raw": section.get("name_raw") or "",
                    "section_type_estimated": section.get("section_type_estimated") or "",
                    "position_index": section.get("position_index") or 0,
                    "ordinal": section.get("ordinal") or 0,
                    "progression_text": progression_text,
                }
            )

        return membership_rows, normalized_sections, song_rows

    def _fetch_rows_from_sqlite(self) -> tuple[list[dict], list[dict], list[dict]]:
        with self._connect() as connection:
            membership_rows = connection.execute(
                """
                SELECT song_id, catalog_name, catalog_bucket
                FROM song_catalog_memberships
                """
            ).fetchall()

            section_rows = connection.execute(
                """
                SELECT
                    so.song_version_id,
                    so.name_raw,
                    so.section_type_estimated,
                    so.position_index,
                    so.ordinal,
                    COALESCE(NULLIF(so.nashville_relative_major, ''), NULLIF(so.nashville, ''), NULLIF(so.normalized_chords, '')) AS progression_text
                FROM section_occurrences so
                JOIN song_versions sv ON sv.id = so.song_version_id
                WHERE sv.is_active_canonical = 1
                ORDER BY so.song_version_id, so.position_index, so.ordinal, so.id
                """
            ).fetchall()

            song_rows = connection.execute(
                """
                SELECT
                    sv.id AS row_id,
                    sv.song_id,
                    COALESCE(s.spotify_song_id, '') AS spotify_song_id,
                    COALESCE(s.spotify_artist_id, '') AS spotify_artist_id,
                    COALESCE(s.artist_name, '') AS artist_name,
                    COALESCE(s.title, '') AS track_name,
                    COALESCE(CAST(s.year AS TEXT), '') AS year,
                    COALESCE(NULLIF(s.main_genre, ''), NULLIF(s.genre, ''), NULLIF(s.source_genres, ''), '') AS genre_display,
                    COALESCE(sv.display_key, '') AS display_key,
                    saf.tempo AS bpm
                FROM song_versions sv
                JOIN songs s ON s.id = sv.song_id
                LEFT JOIN song_audio_features saf ON saf.song_id = s.id
                WHERE sv.is_active_canonical = 1
                ORDER BY sv.id
                """
            ).fetchall()

        return [dict(row) for row in membership_rows], [dict(row) for row in section_rows], [dict(row) for row in song_rows]

    def _load(self) -> None:
        if self.supabase_url and self.supabase_key:
            membership_rows, section_rows, song_rows = self._fetch_rows_from_supabase()
        else:
            membership_rows, section_rows, song_rows = self._fetch_rows_from_sqlite()

        memberships_by_song: dict[int, list[dict]] = {}
        for row in membership_rows:
            memberships_by_song.setdefault(int(row["song_id"]), []).append(row)

        sections_by_version: dict[int, list[dict]] = {}
        for row in section_rows:
            song_version_id = row.get("song_version_id")
            if song_version_id is None:
                continue
            sections_by_version.setdefault(int(song_version_id), []).append(row)

        all_songs: list[SongRecord] = []
        broad_songs: list[SongRecord] = []
        worship_songs: list[SongRecord] = []

        for row in song_rows:
            song_id = int(row["song_id"])
            memberships = memberships_by_song.get(song_id, [])
            catalog_names = frozenset(membership["catalog_name"] for membership in memberships)
            catalog_buckets = tuple(
                sorted(
                    {
                        membership["catalog_bucket"]
                        for membership in memberships
                        if membership["catalog_bucket"]
                    }
                )
            )

            if CATALOG_WORSHIP in catalog_names:
                primary_catalog_label = "Worship"
            elif catalog_buckets:
                primary_catalog_label = title_case_bucket(catalog_buckets[0])
            else:
                primary_catalog_label = ""

            raw_section_rows = sections_by_version.get(int(row["row_id"]), [])
            section_entries: list[SectionProfile] = []
            sections: dict[str, str] = {key: "" for key in STANDARD_SECTIONS}
            index_tokens: set[str] = set()
            window_keys: set[str] = set()

            for section_row in raw_section_rows:
                text = (section_row["progression_text"] or "").strip()
                if not text:
                    continue
                base_name = (section_row["section_type_estimated"] or section_row["name_raw"] or "").strip()
                profile = create_progression_profile(
                    text=text,
                    name=(section_row["name_raw"] or base_name or "").strip(),
                    base_name=base_name or "unknown",
                )
                if not profile.text:
                    continue
                section_entries.append(profile)
                if profile.base_name in sections and not sections[profile.base_name]:
                    sections[profile.base_name] = profile.text
                index_tokens.update(profile.simplified_tokens)
                index_tokens.update(profile.core_tokens)
                for window in profile.simplified_windows:
                    if len(window) >= 3:
                        window_keys.add(" ".join(window))
                for window in profile.core_windows:
                    if len(window) >= 3:
                        window_keys.add(" ".join(window))

            song = SongRecord(
                row_id=str(row["row_id"]),
                song_id=song_id,
                spotify_song_id=str(row["spotify_song_id"]),
                artist_id=str(row["spotify_artist_id"]),
                artist=str(row["artist_name"]),
                track=str(row["track_name"]),
                year=str(row["year"]),
                genre=str(row["genre_display"]),
                key=str(row["display_key"]),
                bpm=parse_float(row.get("bpm")),
                catalog_names=catalog_names,
                catalog_buckets=catalog_buckets,
                is_known_worship_artist=is_known_worship_artist_name(str(row["artist_name"]), self.known_worship_artists),
                primary_catalog_label=primary_catalog_label,
                search_text=normalize_text(
                    " ".join(
                        part
                        for part in (
                            row["artist_name"],
                            row["track_name"],
                            row["genre_display"],
                            row["display_key"],
                            primary_catalog_label,
                            " ".join(bucket for bucket in catalog_buckets if bucket),
                        )
                        if part
                    )
                ),
                sections=sections,
                section_entries=tuple(section_entries),
                index_tokens=frozenset(index_tokens),
                window_keys=frozenset(window_keys),
            )

            self.songs_by_row_id[song.row_id] = song
            all_songs.append(song)
            if CATALOG_BROAD in song.catalog_names:
                broad_songs.append(song)
            if CATALOG_WORSHIP in song.catalog_names:
                worship_songs.append(song)

        self.songs_by_catalog = {
            CATALOG_ALL: tuple(all_songs),
            CATALOG_BROAD: tuple(broad_songs),
            CATALOG_WORSHIP: tuple(worship_songs),
        }
        self.catalog_counts = {catalog: len(songs) for catalog, songs in self.songs_by_catalog.items()}

    def get_songs_for_catalog(self, catalog: str) -> tuple[SongRecord, ...]:
        return self.songs_by_catalog.get(catalog, self.songs_by_catalog[CATALOG_WORSHIP])

    def get_song(self, row_id: str) -> SongRecord | None:
        return self.songs_by_row_id.get(str(row_id))

    def suggest(self, query: str, catalog: str, limit: int = 8) -> list[dict]:
        normalized_query = normalize_text(query)
        if len(normalized_query) < 2:
            return []

        matches: list[tuple[int, SongRecord]] = []
        for song in self.get_songs_for_catalog(catalog):
            score = score_song_lookup(song, normalized_query)
            if score > 0:
                matches.append((score, song))

        matches.sort(key=lambda item: (-item[0], item[1].artist, item[1].track))
        return [serialize_song(match[1], include_sections=False) for match in matches[:limit]]

    def find_reference_song(self, song_query: str, reference_song_id: str | None, catalog: str) -> SongRecord | None:
        songs = self.get_songs_for_catalog(catalog)
        if reference_song_id:
            selected = self.get_song(reference_song_id)
            if selected and selected in songs:
                return selected

        normalized_query = normalize_text(song_query)
        if not normalized_query:
            return None

        best_song = None
        best_score = 0
        for song in songs:
            score = score_song_lookup(song, normalized_query)
            if score > best_score:
                best_song = song
                best_score = score
        return best_song if best_score > 0 else None

    def _compute_section_score(self, selected_section: str, candidate_section: str, reference_section: str) -> int:
        candidate_base = base_section_name(candidate_section)
        reference_base = base_section_name(reference_section)
        transition_sections = {"pre_chorus", "chorus", "bridge", "tag"}

        score = 0
        if selected_section != "all":
            if candidate_base == selected_section:
                score += 90
            else:
                score -= 35

        if candidate_base and reference_base and candidate_base == reference_base:
            score += 70
        elif candidate_base in transition_sections and reference_base in transition_sections:
            score += 25

        return score

    def _compute_worship_relevance_score(self, song: SongRecord, catalog: str) -> int:
        score = 0
        if song.is_known_worship_artist:
            score += 120

        if CATALOG_WORSHIP in song.catalog_names:
            score += 110
        elif CATALOG_BROAD in song.catalog_names:
            score += 55
        else:
            score -= 90

        if catalog == CATALOG_WORSHIP:
            score += 10

        return score

    def _compute_bpm_score(self, song: SongRecord, reference_song: SongRecord | None) -> tuple[int, float | None]:
        if not reference_song or reference_song.bpm is None or song.bpm is None:
            return 0, None

        bpm_difference = abs(song.bpm - reference_song.bpm)
        score = max(0, int(round(100 - bpm_difference * 1.8)))
        if bpm_difference <= 3:
            score += 20
        elif bpm_difference <= 6:
            score += 12
        return score, bpm_difference

    def _rank_match(
        self,
        song: SongRecord,
        best_match: dict,
        reference_song: SongRecord | None,
        selected_section: str,
        catalog: str,
    ) -> dict:
        progression_score = int(best_match["score"])
        section_score = self._compute_section_score(
            selected_section=selected_section,
            candidate_section=best_match["candidate_section"],
            reference_section=best_match["reference_section"],
        )
        worship_relevance_score = self._compute_worship_relevance_score(song, catalog)
        bpm_score, bpm_difference = self._compute_bpm_score(song, reference_song)

        combined_score = progression_score + section_score + worship_relevance_score + bpm_score
        should_filter = (
            catalog != CATALOG_WORSHIP
            and worship_relevance_score < 20
            and progression_score < 260
        )

        return {
            "combined_score": combined_score,
            "progression_score": progression_score,
            "section_score": section_score,
            "worship_relevance_score": worship_relevance_score,
            "bpm_score": bpm_score,
            "bpm_difference": bpm_difference,
            "should_filter": should_filter,
        }

    def search(
        self,
        catalog: str,
        song_query: str,
        reference_song_id: str | None,
        progression_query: str,
        selected_section: str,
        mode: str,
        limit: int,
    ) -> dict:
        songs = self.get_songs_for_catalog(catalog)
        reference_song = None if progression_query else self.find_reference_song(song_query, reference_song_id, catalog)

        if progression_query:
            section_name = "query" if selected_section == "all" else selected_section
            reference_entries = [create_progression_profile(progression_query, section_name, section_name)]
            reference_entries = [entry for entry in reference_entries if entry.tokens]
        elif reference_song:
            reference_entries = list(prioritize_reference_entries(get_section_entries(reference_song, selected_section), selected_section))
        else:
            reference_entries = []

        has_search = bool(progression_query or song_query)
        if not reference_entries:
            return {
                "hasSearch": has_search,
                "referenceSong": serialize_song(reference_song, include_sections=True) if reference_song else None,
                "progressionQuery": progression_query,
                "catalog": catalog,
                "catalogCount": self.catalog_counts.get(catalog, 0),
                "results": [],
            }

        gate_tokens = set()
        gate_window_keys = set()
        for entry in reference_entries:
            gate_tokens.update(entry.simplified_tokens)
            gate_tokens.update(entry.core_tokens)
            for window in entry.simplified_windows:
                if len(window) >= 3:
                    gate_window_keys.add(" ".join(window))
            for window in entry.core_windows:
                if len(window) >= 3:
                    gate_window_keys.add(" ".join(window))

        matches: list[dict] = []
        allowed_candidate_bases = {entry.base_name for entry in reference_entries}
        if selected_section == "all":
            allowed_candidate_bases.add("full_song")

        for song in songs:
            if reference_song and song.row_id == reference_song.row_id:
                continue
            if gate_window_keys:
                if not (song.window_keys & gate_window_keys):
                    continue
            elif gate_tokens and not (song.index_tokens & gate_tokens):
                continue

            candidate_entries = get_section_entries(song, selected_section)
            if selected_section == "all":
                candidate_entries = tuple(entry for entry in candidate_entries if entry.base_name in allowed_candidate_bases)
            if not candidate_entries:
                continue

            best_match = None
            for reference_entry in reference_entries:
                for candidate_entry in candidate_entries:
                    match = score_candidate_against_reference(reference_entry, candidate_entry, mode)
                    if not match:
                        continue
                    if best_match is None or match["score"] > best_match["score"]:
                        best_match = match

            if not best_match:
                continue

            ranking = self._rank_match(
                song=song,
                best_match=best_match,
                reference_song=reference_song,
                selected_section=selected_section,
                catalog=catalog,
            )
            if ranking["should_filter"]:
                continue

            song_payload = serialize_song(song, include_sections=True)
            song_payload.update(
                {
                    "score": ranking["combined_score"],
                    "progressionScore": ranking["progression_score"],
                    "sectionScore": ranking["section_score"],
                    "worshipRelevanceScore": ranking["worship_relevance_score"],
                    "bpmScore": ranking["bpm_score"],
                    "bpmDifference": ranking["bpm_difference"],
                    "matchLabel": best_match["label"],
                    "matchDetail": best_match["detail"],
                    "sectionLabel": best_match["candidate_section"],
                    "referenceSection": best_match["reference_section"],
                }
            )
            matches.append(song_payload)

        matches.sort(key=lambda item: (-item["score"], item["artist"], item["track"]))
        return {
            "hasSearch": has_search,
            "referenceSong": serialize_song(reference_song, include_sections=True) if reference_song else None,
            "progressionQuery": progression_query,
            "catalog": catalog,
            "catalogCount": self.catalog_counts.get(catalog, 0),
            "results": matches[:limit],
        }


def get_section_entries(song: SongRecord, selected_section: str) -> tuple[SectionProfile, ...]:
    if selected_section != "all":
        return tuple(entry for entry in song.section_entries if entry.base_name == selected_section)
    return song.section_entries


def prioritize_reference_entries(entries: tuple[SectionProfile, ...], selected_section: str) -> tuple[SectionProfile, ...]:
    if selected_section != "all" or len(entries) <= 1:
        return entries

    section_priority = {
        "pre_chorus": 6,
        "chorus": 5,
        "bridge": 4,
        "verse": 3,
        "tag": 2,
        "interlude": 2,
        "solo": 2,
        "instrumental": 2,
        "intro": 1,
        "outro": 1,
        "full_song": 0,
    }

    preferred_by_base: dict[str, SectionProfile] = {}

    def reference_entry_score(entry: SectionProfile) -> tuple[int, int, int]:
        return (
            40 - abs(len(entry.tokens) - 10),
            len(entry.window_keys),
            -len(entry.tokens),
        )

    for entry in entries:
        current = preferred_by_base.get(entry.base_name)
        if current is None or reference_entry_score(entry) > reference_entry_score(current):
            preferred_by_base[entry.base_name] = entry

    ranked = sorted(
        preferred_by_base.values(),
        key=lambda entry: (
            section_priority.get(entry.base_name, 0),
            *reference_entry_score(entry),
        ),
        reverse=True,
    )
    return tuple(ranked[:1])


def serialize_song(song: SongRecord | None, include_sections: bool) -> dict | None:
    if song is None:
        return None

    payload = {
        "rowId": song.row_id,
        "songId": song.spotify_song_id,
        "artistId": song.artist_id,
        "artist": song.artist,
        "track": song.track,
        "year": song.year,
        "genre": song.genre,
        "key": song.key,
        "bpm": song.bpm,
        "isKnownWorshipArtist": song.is_known_worship_artist,
        "primaryCatalogLabel": song.primary_catalog_label,
        "catalogNames": sorted(song.catalog_names),
        "catalogBuckets": list(song.catalog_buckets),
    }

    if include_sections:
        payload["sections"] = song.sections
        payload["sectionEntries"] = [
            {
                "name": entry.name,
                "baseName": entry.base_name,
                "text": entry.text,
            }
            for entry in song.section_entries
        ]

    return payload


class MelodexRequestHandler(SimpleHTTPRequestHandler):
    store: SongStore
    root: Path

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        relative = parsed.path.lstrip("/") or "index.html"
        safe = (self.root / relative).resolve()
        if not str(safe).startswith(str(self.root.resolve())):
            return str(self.root / "index.html")
        return str(safe)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api(parsed)
            return
        return super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        return super().log_message(format, *args)

    def handle_api(self, parsed) -> None:
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/stats":
                payload = {
                    "counts": self.store.catalog_counts,
                    "loadedAt": self.store.loaded_at,
                }
                self.send_json(payload)
                return

            if parsed.path == "/api/suggest":
                catalog = get_single_query_value(query, "catalog", CATALOG_WORSHIP)
                search_query = get_single_query_value(query, "q", "")
                payload = {
                    "catalog": catalog,
                    "catalogCount": self.store.catalog_counts.get(catalog, 0),
                    "suggestions": self.store.suggest(search_query, catalog),
                }
                self.send_json(payload)
                return

            if parsed.path == "/api/search":
                catalog = get_single_query_value(query, "catalog", CATALOG_WORSHIP)
                payload = self.store.search(
                    catalog=catalog,
                    song_query=get_single_query_value(query, "songQuery", ""),
                    reference_song_id=get_single_query_value(query, "referenceSongId", ""),
                    progression_query=get_single_query_value(query, "progressionQuery", ""),
                    selected_section=get_single_query_value(query, "section", "all"),
                    mode=get_single_query_value(query, "mode", "mixed"),
                    limit=max(1, min(100, int(get_single_query_value(query, "limit", "15") or "15"))),
                )
                self.send_json(payload)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")
        except Exception as exc:  # noqa: BLE001
            if is_client_disconnect(exc):
                return
            try:
                self.send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            except Exception as send_exc:  # noqa: BLE001
                if is_client_disconnect(send_exc):
                    return
                raise

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001
            if is_client_disconnect(exc):
                return
            raise


def is_client_disconnect(exc: Exception) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    if isinstance(exc, OSError):
        winerror = getattr(exc, "winerror", None)
        if winerror in {10053, 10054}:
            return True
    return False


def get_single_query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key, [])
    if not values:
        return default
    return values[0]


def build_handler(root: Path, store: SongStore):
    class Handler(MelodexRequestHandler):
        pass

    Handler.root = root
    Handler.store = store
    return Handler


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    project_root = root.parent.parent
    parser = argparse.ArgumentParser(description="Serve the Melodex progression lab.")
    parser.add_argument("--port", type=int, default=3001, help="Port to bind the local server.")
    parser.add_argument(
        "--db",
        default=str(project_root / "data" / "processed" / "melodex_phase1.sqlite"),
        help="Path to the Melodex SQLite database.",
    )
    parser.add_argument(
        "--supabase-url",
        default=os.getenv("SUPABASE_URL", ""),
        help="Supabase project URL (e.g. https://xyz.supabase.co). Uses local SQLite when omitted.",
    )
    parser.add_argument(
        "--supabase-service-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_MCP_TOKEN", "")),
        help="Supabase service-role key. Uses local SQLite when omitted.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Load the database and print counts without starting the server.",
    )
    parser.add_argument(
        "--known-worship-artists",
        default=str(project_root / "data" / "processed" / "youtube_artist_cleanup" / "youtube_artist_names_cleaned.txt"),
        help="Path to newline-delimited worship artist names used for ranking boost.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent
    db_path = Path(args.db)
    use_supabase = bool(args.supabase_url and args.supabase_service_key)
    if not use_supabase and not db_path.exists():
        raise FileNotFoundError(f"Melodex database not found: {db_path}")

    print("Loading Melodex lab store...", flush=True)
    started = time.time()
    store = SongStore(
        db_path,
        supabase_url=args.supabase_url if use_supabase else None,
        supabase_key=args.supabase_service_key if use_supabase else None,
        known_worship_artist_path=Path(args.known_worship_artists),
    )
    elapsed = time.time() - started
    print(
        f"Loaded {store.catalog_counts[CATALOG_ALL]:,} songs "
        f"({store.catalog_counts[CATALOG_BROAD]:,} broad Christian/Worship, "
        f"{store.catalog_counts[CATALOG_WORSHIP]:,} worship) in {elapsed:.1f}s "
        f"from {store.source_name}; "
        f"{len(store.known_worship_artists):,} known worship artist signals loaded"
        ,
        flush=True,
    )

    if args.check_only:
        return

    handler = build_handler(root, store)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Melodex Progression Lab running at http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
