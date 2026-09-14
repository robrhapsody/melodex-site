# Relative-major display and tempo coverage — September 13, 2026

## User decision

Display all songs in major-key coordinates, using the relative major for minor songs. Keep minor chord qualities: A minor becomes C-major numbering, with Am as 6m. Do not exclude minor songs or turn their chords into major chords. The user also wants help obtaining tempos for every song and questioned whether an API is necessary.

## Implementation

Branch: `codex/relative-major-tempo`. Changes are local/branch work, not a production deployment.

- Reference sections, candidate retrieval filters, matching, and returned snippets now consistently use `nashville_relative_major`, aliased to the existing Nashville response field. No raw source data was overwritten.
- Live read-only audit: 39,154 sections; zero missing relative-major progressions; zero minor-labelled display keys. Temple (song180/version190) has C as display key; chorus now reads `4 6m 5 2m`, producing `F Am G Dm`.
- Major-only dropdown labels replace paired major/minor labels. The default is labelled Relative major key. Manual chord input already evaluates major keys; numeric input is interpreted as supplied in major coordinates.
- Null, blank, nonnumeric, zero, and negative tempos no longer produce a tempo bonus. Null energy/danceability no longer invent gentle/similar-feel evidence.
- Candidate audio metadata is fetched for progression-only searches as well. Previously those searches hid known tempos and displayed 0 BPM. Missing values now display Tempo unknown.
- 27 tests pass, including a Supabase query-contract/Temple regression and missing-metadata regressions. Syntax checks pass. Browser verified major-only controls and a `4 5 6m` search returning 15 songs with actual tempos, zero 0-BPM results. Local Temple chorus search returns key C and relative-major numbers.
- Existing raw-dataset/import scripts, unrelated local files, and cloud data remain untouched. Candidate-retrieval caps and the third-reference-target issue remain separate work.

## Tempo audit and plan

Live read-only counts: 11,638 total songs, 6,562 with positive tempo, 5,076 missing. Worship catalog: 8,520 songs, 3,444 with tempo, 5,076 missing. Every current gap is in Worship; catalog-wide coverage overstates coverage for the primary user audience.

Past local reports: GetSongBPM main report has 4,259 matched rows; loose and loose-retry reports add 54 and 394 matched rows, respectively. These are report counts, not guaranteed unique additions to the current database. AcousticBrainz's 55-row trial had 2 matched, 25 review, 28 missing. No MP3/WAV files were found under project data.

Some missing records contain inconsistent names, misspellings, and translated titles (for example Call Upon The Lordcall and Halelujah Here Below). Exact normalized title/artist comparison found 26 missing songs with one existing measured candidate each. Saved `data/review/tempo-existing-match-review-2026-09-13.csv`, marked needs_recording_verification. No tempos were copied automatically: matching song names does not establish the same recording or arrangement.

Recommended sequence:

1. Review the 26 existing-data candidates, checking recording/arrangement identity and tempo provenance.
2. Clean artist aliases/title mistakes into a review mapping, then retry only unresolved records against available sources. Do not merge different recordings or apply fuzzy matches without review.
3. Import exact arrangement tempos from user-provided chart/song records if available, preserving their source and arrangement identity.
4. Use existing GetSongBPM access for unresolved exact recordings, if available; its current API is free with required attribution and a key. An API does not guarantee coverage.
5. For songs with available audio, estimate tempo locally using a tool such as librosa, then review half/double-time ambiguity and live tempo changes. This needs audio but not an external API.
6. Keep unknown values honest. Store provenance, recording/arrangement, and review status when expanding the tempo data model. Distinguish recording BPM from a worship leader's chosen count (e.g.144 vs72); do not halve values indiscriminately.

User was asked which resources they have (audio, charts/Planning Center records, existing GetSongBPM access, or none). Response pending at checkpoint creation. No paid service, bulk API run, data migration, or production deployment was performed.

Sources checked September13:

- [GetSongBPM API](https://getsongbpm.com/api): key required, free with backlink, documented rate limit.
- [librosa beat tracking](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html): estimate tempo from audio; this is an estimate needing musical validation.
- [AcousticBrainz downloads](https://acousticbrainz.org/download): discontinued collection, historical archives/extractor remain; not a growing source for newer songs.
- [Spotify Web API changes](https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api): restrictions on new-app audio-features access mean obtaining a new Spotify key is not a reliable tempo plan.

## Correction to prior verification wording

The step-one checkpoint used `progression=` in its direct API parity probe, but the endpoint expects `progressionQuery=`. That direct probe compared empty search responses, not actual progression results. The browser search itself was valid. This turn explicitly verified `progressionQuery=4%205%206m`: hasSearch true, 15 results, all15 with positive BPM.
