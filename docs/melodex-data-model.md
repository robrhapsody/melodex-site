# Melodex Data Model Proposal

## Purpose

Melodex should feel simple in the UI while doing richer harmonic analysis behind the scenes.
The user-facing product goal is still a search engine that returns similar songs accurately,
especially when section labels are unreliable and chord progressions vary because of passing
chords, inversions, repeated sections, or transcription differences.

This proposal defines a backend-facing data model that supports:

- better similarity search
- repeated section preservation
- retention of full raw chord text for reparsing
- fallback handling for unlabeled songs
- preservation of Spotify audio features for future ranking/filtering
- catalog-aware filtering for worship and broad Christian song subsets
- core progression extraction
- phrase and loop matching
- future continuation and transition analysis
- source provenance and manual correction

## Design Principles

1. Preserve more than the first labeled section occurrence.
   - Keep `chorus_2`, `bridge_2`, `verse_3`, etc.
   - Do not collapse repeated sections too early.

2. Keep multiple harmonic representations.
   - raw normalized progression
   - slash-simplified progression
   - relative-major Nashville progression
   - experimental core progression

3. Preserve the source, even when parsing is incomplete.
   - Keep the original full chord field
   - Keep unlabeled songs searchable instead of turning them into empty rows

4. Separate user-facing simplicity from backend richness.
   - UI should stay easy to navigate
   - backend should store enough detail to support accurate matching

5. Track provenance.
   - Every canonical song version should know where it came from
   - Corrections should be traceable

6. Treat section labels as useful but unreliable.
   - Preserve source labels
   - Allow estimated section types
   - Support phrase/block matching beyond labels

## Recommended Entities

### songs

Canonical identity and user-facing song metadata.

Suggested fields:

- `id`
- `spotify_song_id`
- `title`
- `artist_name`
- `spotify_artist_id`
- `release_date`
- `year`
- `genre`
- `main_genre`
- `source_genres`
- `decade`
- `rock_genre`
- `country`
- `source_status`
- `has_complete_structure`
- `has_section_markers`
- `created_at`
- `updated_at`

### song_audio_features

Stores Spotify listening and mood-adjacent metadata that may help later as filters,
ranking signals, or similarity hints.

Suggested fields:

- `song_id`
- `popularity`
- `danceability`
- `energy`
- `spotify_key`
- `loudness`
- `spotify_mode`
- `speechiness`
- `acousticness`
- `instrumentalness`
- `liveness`
- `valence`
- `tempo`
- `duration_ms`
- `time_signature`

### song_catalog_memberships

Stores curated song-set membership that should drive top-level app filtering better than
raw genre labels alone.

Suggested fields:

- `id`
- `song_id`
- `catalog_name`
- `catalog_bucket`
- `source_file`
- `created_at`

Examples of `catalog_name`:

- `broad_christian_worship`
- `worship_strict`

Examples of `catalog_bucket`:

- `christian`
- `gospel`
- `worship`

### song_sources

Tracks where the song structure/chords came from.

Suggested fields:

- `id`
- `song_id`
- `source_type`
- `source_url`
- `external_source_id`
- `license_notes`
- `fetched_at`
- `raw_payload_path`
- `confidence`

Examples of `source_type`:

- `csv_import`
- `harmonydb_reference`
- `ultimate_guitar`
- `manual_curated`

### song_versions

Represents a processed interpretation of a song from a particular source.

Suggested fields:

- `id`
- `song_id`
- `source_id`
- `version_label`
- `display_key`
- `detected_key_raw`
- `detected_key_relative_major`
- `normalization_mode`
- `raw_chords_full`
- `normalized_chords_full`
- `section_parse_status`
- `is_active_canonical`
- `notes`

This allows Melodex to keep:

- raw minor-centered interpretation
- relative-major interpretation
- manually curated interpretation
- the original one-field chord text for reparsing or recovery
- a parse status for songs that did not have section labels

without losing history.

### section_occurrences

Stores repeated sections as actual occurrences instead of collapsing them.

Suggested fields:

- `id`
- `song_version_id`
- `name_raw`
- `section_type_estimated`
- `ordinal`
- `position_index`
- `raw_chords`
- `normalized_chords`
- `nashville`
- `nashville_relative_major`
- `core_progression`
- `confidence`
- `is_repeating`
- `is_fallback_full_song`
- `length_chords`

Examples:

- `chorus_1`
- `chorus_2`
- `pre_chorus_1`
- `tag_1`
- `unknown_1`

`section_type_estimated` should allow values like:

- `intro`
- `verse`
- `pre_chorus`
- `chorus`
- `bridge`
- `tag`
- `interlude`
- `outro`
- `unknown`

### sequence_blocks

Phrase-level harmonic blocks extracted from section occurrences.

This is the most important structural layer beyond section labels.

Suggested fields:

- `id`
- `song_version_id`
- `section_occurrence_id`
- `block_type`
- `start_chord_index`
- `end_chord_index`
- `raw_sequence`
- `normalized_sequence`
- `nashville_sequence`
- `core_sequence`
- `occurrence_count`
- `covers_full_section`
- `confidence`

Examples of `block_type`:

- `loop`
- `sequence`
- `entry`
- `exit`
- `transition`
- `round_robin`

### similarity_edges

Stores precomputed or cached similarity relationships between songs or blocks.

Suggested fields:

- `id`
- `from_song_version_id`
- `to_song_version_id`
- `from_block_id`
- `to_block_id`
- `match_type`
- `score`
- `confidence`
- `matched_sequence`
- `explanation`
- `created_at`

Examples of `match_type`:

- `exact`
- `contains`
- `core`
- `flexible`
- `windowed`

### manual_overrides

Tracks corrections and curation changes.

Suggested fields:

- `id`
- `entity_type`
- `entity_id`
- `field_name`
- `old_value`
- `new_value`
- `reason`
- `created_by`
- `created_at`

## Near-Term Architecture

For the current phase, the best path is not a large research platform. It is a trustworthy
search engine with a richer backend model.

Recommended implementation path:

1. Keep the current static apps as prototypes and labs.
2. Preserve the full raw chord text and audio features from import.
3. Store catalog membership from the refined Christian/Worship outputs.
4. Preserve repeated section occurrences in structured form.
5. Build canonical progression profiles for each occurrence:
   - raw normalized
   - slash-simplified
   - relative-major Nashville
   - core progression
6. Use a fallback full-song occurrence for unlabeled songs.
7. Extract phrase and loop blocks.
8. Search across those blocks and explain why matches were returned.

## Suggested Matching Pipeline

1. Normalize chords.
2. Simplify slash chords when needed.
3. Convert to relative-major Nashville numbers.
4. Extract core progression heuristics.
5. Preserve repeated occurrences.
6. Extract phrase windows and loop blocks.
7. Compare by:
   - exact match
   - contains match
   - core match
   - flexible/passing-chord-aware match
   - sliding-window match

## UI Implications

The user should not have to understand the full data model.

Primary UI can stay simple:

- search by song
- search by progression
- show similar songs
- show matched phrase
- show estimated section
- show match type
- show confidence

Advanced analysis can stay separate:

- continuation maps
- loop statistics
- tonalities analysis
- transition analysis
- uniqueness metrics

## API Trace And External Source Links

### API trace

HarmonyDB's API trace appears to be meant for developers who want to inspect:

- the request parameters
- the response payload
- the structure of the underlying API query

This can be useful as a reference for:

- understanding how another harmony tool models data
- learning what payload shapes might be useful
- debugging how a result was generated

It should not be treated as Melodex's primary data source.

### Source links

If a song page links to the original chord/structure source, those links can be valuable as
source leads for Melodex.

Potential uses:

- improve bad or incomplete songs in the current dataset
- recover missing sections
- find songs not present in the current CSV

Important caveats:

- respect source terms and licensing
- do not assume source data is correct
- store provenance and confidence for every imported source
- build source-specific parsers instead of one-off scraping when possible

## Recommended Build Order

### Phase 1

- `songs`
- `song_sources`
- `song_versions`
- `section_occurrences`

### Phase 2

- `sequence_blocks`
- block extraction logic
- phrase-level matching

### Phase 3

- `similarity_edges`
- cached/explained similarity results
- continuation and transition relationships

### Phase 4

- analytics and exploration layers
- uniqueness
- modulation analysis
- lyrics/mood clustering

## Why This Fits Melodex

This model supports the current vision:

- easy to navigate UI
- accurate similarity search
- strong handling of chord-variation edge cases
- room to grow into richer analysis later

It also matches the current known problem areas:

- missing or mislabeled pre-choruses
- repeated sections being collapsed
- minor songs being easier to reason about in relative-major Nashville space
- phrase-level similarity being more important than exact literal section equality
