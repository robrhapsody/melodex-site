-- Melodex Phase 1 / Phase 2 schema draft
-- This is a first practical schema for storing richer song structure
-- while keeping the current app free to evolve experimentally.

CREATE TABLE songs (
    id INTEGER PRIMARY KEY,
    spotify_song_id TEXT UNIQUE,
    title TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    spotify_artist_id TEXT,
    release_date TEXT,
    year INTEGER,
    genre TEXT,
    main_genre TEXT,
    source_genres TEXT,
    decade TEXT,
    rock_genre TEXT,
    country TEXT,
    source_status TEXT DEFAULT 'imported',
    has_complete_structure INTEGER DEFAULT 0,
    has_section_markers INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE song_audio_features (
    song_id INTEGER PRIMARY KEY,
    popularity INTEGER,
    danceability REAL,
    energy REAL,
    spotify_key INTEGER,
    loudness REAL,
    spotify_mode INTEGER,
    speechiness REAL,
    acousticness REAL,
    instrumentalness REAL,
    liveness REAL,
    valence REAL,
    tempo REAL,
    duration_ms INTEGER,
    time_signature INTEGER,
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

CREATE TABLE song_catalog_memberships (
    id INTEGER PRIMARY KEY,
    song_id INTEGER NOT NULL,
    catalog_name TEXT NOT NULL,
    catalog_bucket TEXT,
    source_file TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

CREATE TABLE song_sources (
    id INTEGER PRIMARY KEY,
    song_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    external_source_id TEXT,
    license_notes TEXT,
    fetched_at TEXT,
    raw_payload_path TEXT,
    confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

CREATE TABLE song_versions (
    id INTEGER PRIMARY KEY,
    song_id INTEGER NOT NULL,
    source_id INTEGER,
    version_label TEXT,
    display_key TEXT,
    detected_key_raw TEXT,
    detected_key_relative_major TEXT,
    normalization_mode TEXT,
    raw_chords_full TEXT,
    normalized_chords_full TEXT,
    section_parse_status TEXT,
    is_active_canonical INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_id) REFERENCES songs(id),
    FOREIGN KEY (source_id) REFERENCES song_sources(id)
);

CREATE TABLE section_occurrences (
    id INTEGER PRIMARY KEY,
    song_version_id INTEGER NOT NULL,
    name_raw TEXT NOT NULL,
    section_type_estimated TEXT,
    ordinal INTEGER,
    position_index INTEGER,
    raw_chords TEXT,
    normalized_chords TEXT,
    nashville TEXT,
    nashville_relative_major TEXT,
    core_progression TEXT,
    confidence REAL,
    is_repeating INTEGER DEFAULT 0,
    is_fallback_full_song INTEGER DEFAULT 0,
    length_chords INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_version_id) REFERENCES song_versions(id)
);

CREATE TABLE sequence_blocks (
    id INTEGER PRIMARY KEY,
    song_version_id INTEGER NOT NULL,
    section_occurrence_id INTEGER,
    block_type TEXT NOT NULL,
    start_chord_index INTEGER,
    end_chord_index INTEGER,
    raw_sequence TEXT,
    normalized_sequence TEXT,
    nashville_sequence TEXT,
    core_sequence TEXT,
    occurrence_count INTEGER DEFAULT 1,
    covers_full_section INTEGER DEFAULT 0,
    confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (song_version_id) REFERENCES song_versions(id),
    FOREIGN KEY (section_occurrence_id) REFERENCES section_occurrences(id)
);

CREATE TABLE similarity_edges (
    id INTEGER PRIMARY KEY,
    from_song_version_id INTEGER NOT NULL,
    to_song_version_id INTEGER NOT NULL,
    from_block_id INTEGER,
    to_block_id INTEGER,
    match_type TEXT NOT NULL,
    score REAL NOT NULL,
    confidence REAL,
    matched_sequence TEXT,
    explanation TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_song_version_id) REFERENCES song_versions(id),
    FOREIGN KEY (to_song_version_id) REFERENCES song_versions(id),
    FOREIGN KEY (from_block_id) REFERENCES sequence_blocks(id),
    FOREIGN KEY (to_block_id) REFERENCES sequence_blocks(id)
);

CREATE TABLE manual_overrides (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    created_by TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_songs_title_artist ON songs(title, artist_name);
CREATE INDEX idx_song_catalog_memberships_song_id ON song_catalog_memberships(song_id);
CREATE INDEX idx_song_catalog_memberships_catalog_name ON song_catalog_memberships(catalog_name);
CREATE INDEX idx_song_versions_song_id ON song_versions(song_id);
CREATE INDEX idx_song_versions_parse_status ON song_versions(section_parse_status);
CREATE INDEX idx_section_occurrences_song_version ON section_occurrences(song_version_id);
CREATE INDEX idx_section_occurrences_section_type ON section_occurrences(section_type_estimated);
CREATE INDEX idx_sequence_blocks_song_version ON sequence_blocks(song_version_id);
CREATE INDEX idx_sequence_blocks_block_type ON sequence_blocks(block_type);
CREATE INDEX idx_similarity_edges_from_song ON similarity_edges(from_song_version_id);
CREATE INDEX idx_similarity_edges_to_song ON similarity_edges(to_song_version_id);
