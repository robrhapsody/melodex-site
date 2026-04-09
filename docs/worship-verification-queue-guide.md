# Worship Verification Queue Guide

Use [worship_song_verification_queue_v2.csv](C:\Users\littl\Documents\Codex Projects\worship-song-finder\data\review\worship_song_verification_queue_v2.csv) as both:

- the list of songs to review
- the place where you enter approved progression fixes

The Phase 1 database build script now reads approved queue overrides automatically.

## Main fields to fill

- `review_status`
  Use `approved` when you want Melodex to apply your correction.
- `review_notes`
  A short note about why you changed it.
- `override_action`
  Use `replace_sections` for normal section fixes.
- `override_changes`
  Put one or more section fixes in a single cell.
- `source_urls`
  Optional. Add one or more links if you want a record of where the correction came from.

## `override_changes` format

Write each change as:

```text
section_name=progression
```

Use `||` between multiple changes in the same cell:

```text
verse=1 4 1 6m 5 4 || chorus=4 6m 5 1/3 6m 2m 5 1
```

You can also use `:` instead of `=` if that feels easier:

```text
verse: 1 4 1 6m 5 4 || chorus: 4 6m 5 1/3 6m 2m 5 1
```

## How section names work

- `verse`
  Updates all verse sections in that canonical song version.
- `chorus`
  Updates all chorus sections.
- `bridge`
  Updates all bridge sections.
- `pre_chorus`
  Updates all pre-chorus sections.
- `chorus_2`
  Updates only that exact occurrence if it exists.
- `pre_chorus_1`
  Updates only that exact occurrence if it exists.

If the named section does not exist yet, Melodex will insert it as a manual section for the canonical version.

## Examples

### Example 1: replace one section

- `review_status`: `approved`
- `review_notes`: `Verse should go to 5, not b6`
- `override_action`: `replace_sections`
- `override_changes`: `verse=1 4 1 6m 5 4`

### Example 2: replace two sections in one row

- `review_status`: `approved`
- `review_notes`: `Corrected verse and chorus from listening check`
- `override_action`: `replace_sections`
- `override_changes`: `verse=1 4 1 6m 5 4 || chorus=4 6m 5 1/3 6m 2m 5 1`

### Example 3: change only one repeated section

- `review_status`: `approved`
- `review_notes`: `Only chorus 2 is different`
- `override_action`: `replace_sections`
- `override_changes`: `chorus_2=4 5 6m 4`

### Example 4: reviewed but no correction needed

- `review_status`: `approved`
- `review_notes`: `Flag was reasonable, but the chart is correct`
- `override_action`: leave blank
- `override_changes`: leave blank

## Optional source links

`source_urls` is optional. Use it only if you want a breadcrumb later:

```text
https://example.com/source-1 || https://example.com/source-2
```

These links are stored as review evidence, but Melodex does not need them in order to apply your correction.

## Rebuild after edits

Run:

```powershell
C:\Users\littl\Documents\Codex Projects\worship-song-finder\scripts\build_melodex_phase1_db.ps1
```

That rebuild will:

- read the approved queue rows
- apply your section overrides to the canonical song version
- preserve a record of the applied override in the database
