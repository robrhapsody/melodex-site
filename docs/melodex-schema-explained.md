# Melodex Schema Explained

## What this is

This is the beginner-friendly version of the Melodex data plan.

You do not need to know SQL to use this. Think of it as a description of:

- what information the app should store
- why that information matters
- how it will help song similarity search become more accurate

## Why we need a better structure

Right now, some important information gets lost too early.

Examples:

- `chorus_2` may be different from `chorus_1`
- a `pre-chorus` may be mislabeled as `chorus_2`
- a passing chord may make two similar progressions look different
- a minor song may be easier to compare if it is expressed in the relative major
- many songs have useful chords but no section labels at all
- Spotify audio features like tempo, energy, and valence may become useful later for similarity and mood interpretation

So instead of storing only one simplified version of a song, Melodex should keep more layers of information.

## The main idea

We want to organize the app like a music library with several levels:

1. The song itself
2. Where the song data came from
3. Different interpreted versions of the song
4. The full imported chord text, even before sections are split out
5. Which catalogs the song belongs to
6. The section occurrences inside the song
7. Smaller repeating or meaningful chord phrases inside those sections
8. Similarity relationships between songs and phrases

## The main groups of information

### 1. Songs

This is the basic identity of each song.

Examples of what we store:

- title
- artist
- Spotify ID
- year
- genre

This is the part users would most naturally recognize.

### 2. Song sources

This tells us where the chord or structure data came from.

Examples:

- CSV import
- a reference site
- a manual correction
- a future source page

Why this matters:

- some sources are more reliable than others
- a song may have multiple versions from different places
- later, we may want to improve one song by pulling from a better source

### 3. Song versions

This stores a processed interpretation of the song.

Why this matters:

The same song may have:

- a raw version
- a version converted to relative-major Nashville numbers
- a manually corrected version

Instead of overwriting one version with another, Melodex can keep track of which version is currently the best one to use.

Song versions should also keep:

- the full raw chord field from the source
- the cleaned full-song chord progression
- whether the section parsing worked cleanly, partially, or not at all

Why this matters:

- the original one-field chord text still contains structure clues we may need later
- a song without section labels should still be searchable
- future parsers may recover more structure from the same raw source

### 3b. Song audio features

This stores Spotify-style listening metadata such as:

- popularity
- danceability
- energy
- valence
- tempo
- duration
- time signature

Why this matters:

- these features are not the main similarity engine
- but they may become useful as supporting filters or ranking hints later
- preserving them now avoids reworking the pipeline later

### 3c. Song catalog memberships

This stores whether a song belongs to special curated catalogs such as:

- broad Christian / worship
- strict worship

Why this matters:

- the user may want one app with a top-level filter instead of separate apps forever
- genre alone is not reliable enough to identify worship songs
- these curated catalogs are more trustworthy because they come from the Last.fm-enriched and refined artist review workflow

### 4. Section occurrences

This is one of the most important improvements.

Instead of only storing:

- verse
- chorus
- bridge

we store each occurrence separately when possible.

Examples:

- `verse_1`
- `verse_2`
- `chorus_1`
- `chorus_2`
- `pre_chorus_1`

Why this matters:

- repeated sections are not always identical
- later choruses sometimes contain the actual progression that should match another song
- mislabels become easier to recover from
- songs with no section labels can still be stored as a fallback `full_song_1` occurrence instead of becoming blank

### 5. Sequence blocks

These are smaller harmonic chunks found inside section occurrences.

Examples:

- a repeated loop
- an entry phrase
- an exit phrase
- a transition phrase

Why this matters:

Sometimes the most useful match is not the whole chorus.
It might only be a smaller phrase inside the chorus or pre-chorus.

This is especially helpful for:

- matching songs by flow
- finding transition ideas
- understanding where a loop exits

### 6. Similarity relationships

This stores why one song or phrase matched another.

Examples of match types:

- exact
- contains
- core
- flexible
- windowed

Why this matters:

The app should not just say "these songs are similar."
It should be able to explain:

- what part matched
- what kind of match it was
- how confident the system is

## What this means for the user experience

The user does not need to see the whole backend structure.

The UI can still stay simple:

- search by song
- search by progression
- see similar songs
- see the matched phrase
- see the estimated section
- see why it matched

The backend just stores more structure so the results become more trustworthy.

## Why this helps the Holy Forever problem

A song like `Holy Forever` may have:

- a progression that really belongs to a pre-chorus idea
- repeated chorus blocks that are not all the same
- a progression that only matches after removing passing-chord motion

If Melodex stores:

- repeated section occurrences
- core progressions
- smaller phrase blocks

then it has a much better chance of recognizing the relationship correctly.

## What we should build first

### Phase 1

Start by storing:

- songs
- song audio features
- song catalog memberships
- song sources
- song versions
- section occurrences

This already gives a much better foundation than the current flattened data.

### Phase 2

Then add:

- sequence blocks
- phrase extraction
- loop extraction

This is where Melodex becomes much stronger for matching.

### Phase 3

Then add:

- stored similarity results
- explanations
- transition and continuation links

### Phase 4

Later, add deeper analysis like:

- uniqueness
- modulation
- lyric/theme relationships

## Simple summary

If the current app is like storing one simplified note card per song, the new schema is like storing:

- the song
- where it came from
- every important section occurrence
- the important repeating phrases inside it
- and the reasons two songs match

That is what will make Melodex much more accurate without forcing the user to interact with a complicated interface.
