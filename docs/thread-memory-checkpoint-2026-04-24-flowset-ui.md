# Thread Memory Checkpoint - Flowset UI and Matching

Date: 2026-04-24

## Project Context

- Repository: `worship-song-finder`
- Remote: `https://github.com/robrhapsody/melodex-site.git`
- Current working branch during this checkpoint: `codex/publish-code-no-datasets`
- `codex/UI` and `codex/publish-code-no-datasets` pointed to the same commit before this work, so the current branch was kept as the working branch.
- The main active app is `apps/worship-progressions-app-experimental`.

## User Goals

- Rebuild useful Antigravity UI/UX ideas into the current project directly, without blindly copying the Antigravity snapshot.
- Preserve integrations and avoid breaking current API/data behavior.
- Keep chord/full-chart exposure purpose-limited for fair-use risk.
- Push the finished changes to GitHub and publish the live Vercel app.

## Implemented Product Changes

- Search results now show a match quality pill with the label and percent, e.g. `MATCH QUALITY / 100%`.
- The result body no longer repeats the percentage; it only describes the flow relationship, e.g. `Source bridge into this bridge`.
- Result cards show only the matching result section snippet, not all sections from the matched song.
- Added a `Show chord names` toggle and chord-key selector for result snippets only.
- Reference song sections remain in Nashville numbers; chord-name conversion is not applied to full reference-song material.
- Reference panel is now purpose-limited:
  - shows short previews only for transition sections used for matching;
  - prioritizes bridge, pre-chorus, chorus, tag, and interlude;
  - dedupes repeated progressions;
  - caps previews at 8 tokens;
  - shows other indexed sections as names only, with no chord pills.
- Search mode was moved into an `Advanced search` details menu.
- Added a `Feel` filter driven by light energy/danceability scoring.
- API scoring now treats direct BPM as a moderate supporting signal and half/double-time BPM as a weak signal.
- API now reads `tempo`, `energy`, and `danceability` from `song_audio_features`.

## Matching / API Notes

- `apps/worship-progressions-app-experimental/api/search.js`
  - `fetchTempoRowsBySongIds` was expanded into `fetchAudioFeatureRowsBySongIds`.
  - `resolveBpmScore` supports weak half-time and double-time matches.
  - `resolveAudioFeelScore` uses Spotify-style `energy` and `danceability` as a small score nudge.
  - `resolveMatchQualityPercent` creates user-facing quality percent without exposing internal category scores.
- `apps/worship-progressions-app-experimental/api/progression-matching.js`
  - added `startsWith` / phase-aligned matching behavior while keeping existing test expectations for original labels.
- `apps/worship-progressions-app-experimental/api/search.test.js`
  - added tests for weak half/double-time scoring, audio-feel scoring, match-quality calculation, and phase-aligned matches.

## Fair-Use Product Boundary

- Do not display a full reference song as a complete chord chart.
- It is acceptable to show short, purpose-limited Nashville previews of source sections that drive matching.
- Result snippets may be shown and optionally converted to chord names because they are short comparison snippets.
- Do not add chord-name conversion for full reference songs.

## Validation Performed

- `node --check app.js`
- `node --check api/search.js`
- `node --check api/progression-matching.js`
- `node --test api/search.test.js tests/progression-input.test.js`
  - Passing count after changes: `24/24`
- Vercel dev server verified at `http://localhost:3001`.
- Browser checks with headless Chrome verified:
  - advanced match mode is hidden until opened;
  - result card chord toggle converts `4 5 6m 1` to `C D Em G` in key of G;
  - source-song flow shows phrases like `Source bridge into this bridge`;
  - reference panel shows 4 short preview rows and names-only other sections for `Build My Life`;
  - mobile viewport has no horizontal overflow.

## Files Intentionally In Scope For Commit

- `apps/worship-progressions-app-experimental/api/_shared.js`
- `apps/worship-progressions-app-experimental/api/stats.js`
- `apps/worship-progressions-app-experimental/api/progression-matching.js`
- `apps/worship-progressions-app-experimental/api/search.js`
- `apps/worship-progressions-app-experimental/api/search.test.js`
- `apps/worship-progressions-app-experimental/app.js`
- `apps/worship-progressions-app-experimental/index.html`
- `apps/worship-progressions-app-experimental/styles.css`
- `docs/thread-memory-checkpoint-2026-04-24-flowset-ui.md`

## Files / Folders Not In Scope

- `.codex/`
- `Antigravity Projects/`
- untracked BPM enrichment scripts and tests under `scripts/`

These were present in the working tree but should not be staged unless the user explicitly asks.
