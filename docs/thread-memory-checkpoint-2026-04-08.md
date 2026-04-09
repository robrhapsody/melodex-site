# Thread Memory Checkpoint (2026-04-08)

## What This Captures
Concise project state so context loss does not erase decisions or implementation progress.

## Core Direction (Confirmed)
- Product focus: a worship-first song similarity search engine for smooth transitions/mashups.
- Matching should handle progression variation (including passing-chord behavior), while preserving the original stricter matching path.
- User-facing UX should stay simple; deeper analysis can happen behind the scenes.

## Data / Pipeline Status
- Existing pipeline remains in place (merge, section parsing, Nashville conversion, key detection, Christian/Worship refinement, review queues).
- Additional data ingestion work already done:
  - OpenSong files imported/parsed and compared.
  - New worship CSV imported and merged.
  - Conflict/review artifacts produced in `data/review` (including worship verification queues).
- Outputs exist for both broader Christian/Worship and strict worship datasets.

## Experimental App Status
App path:
- `apps/worship-progressions-app-experimental`

Key backend behavior already implemented:
- Flexible/passing-chord-aware matching mode exists in the experimental app.
- Improved server resilience for local disconnect noise (`WinError 10053/10054` handling) so aborted browser requests are less disruptive.
- Supabase-backed mode added with fallback behavior (see Supabase section below).

Recent UI/UX pass completed:
- `index.html`, `styles.css`, `app.js` redesigned for a cleaner dark “Harmonic Flow” experience.
- Visual system upgraded (hero, nav, cards, chord pills, responsive layout).
- Results simplified to flow-relevant sections (instead of showing every section by default).
- Summary/copy aligned to transition use case: “find songs you can transition into.”

## Supabase Integration (Implemented)
Supabase MCP:
- Connection was configured and successfully accessed from this thread.

Schema/import groundwork:
- SQL schema setup work was prepared/applied to align with import data.
- Export/import bundle generated at:
  - `data/processed/supabase_import_bundle`
  - Includes `songs.csv`, `song_versions.csv`, `section_occurrences.csv`, `song_sources.csv`, `song_catalog_memberships.csv`, `song_audio_features.csv`, plus import-order notes.

Experimental app Supabase support:
- `server.py` supports Supabase mode (URL + service key based connection path), with local fallback.
- `start-worship-app-experimental.ps1` supports Supabase launch arguments (including `-UseSupabase` and URL input).
- Practical note from troubleshooting:
  - In PowerShell, script invocation must use call operator:
    - `& "C:\...\start-worship-app-experimental.ps1" -UseSupabase -SupabaseUrl "https://<project-ref>.supabase.co"`
  - “No Supabase URL provided” means the URL arg/env was missing.

## Important Decisions Preserved
- Keep stable/original app behavior intact; experimentation happens in separate experimental app.
- Simplification to relative-major display was requested to reduce minor-key confusion for end users.
- Section labels in source data are imperfect; matching should prefer musical function/flow signals rather than trusting labels blindly.

## Current Known Next Steps
- Continue UI polish + usability tweaks in experimental app (optional toggles like flow-only vs all-sections).
- Continue verification queue workflow for suspicious progression entries.
- Apply manual review queue overrides and rebuild worship outputs when user completes review.
- Continue moving toward Supabase-backed runtime as primary data source.

