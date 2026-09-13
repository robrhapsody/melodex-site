import test from "node:test"
import assert from "node:assert/strict"

import { buildProgressionMatch } from "./progression-matching.js"
import {
  resolveAudioFeelScore,
  resolveBpmScore,
  resolveMatchQualityPercent,
} from "./search.js"
import {
  buildCandidateSearchAnchors,
  buildReferenceTargets,
  findBestReferenceTargetMatch,
  pickBestReferenceCandidate,
} from "./search-matching.js"

test("matches passing-chord variants through the core progression path", () => {
  const match = buildProgressionMatch("4 5 6m 4", "4 6m 5 6m 4", "flexible")

  assert.ok(match)
  assert.equal(match.usedCoreProgression, true)
  assert.equal(match.matchLabel, "Core Exact")
})

test("rejects arbitrary inserted chords that are not a real passing-chord reduction", () => {
  const match = buildProgressionMatch("4 5 6m", "4 1 2m 5 6m", "flexible")

  assert.equal(match, null)
})

test("rejects reordered long-shape matches that only share a broad subsequence", () => {
  const match = buildProgressionMatch("4 5 6m 4", "4 1 5 6m 4", "flexible")

  assert.equal(match, null)
})

test("still allows a contiguous lead-in before the same core movement", () => {
  const match = buildProgressionMatch("4 5 6m", "1 4 5 6m", "flexible")

  assert.ok(match)
  assert.equal(match.contains, true)
  assert.equal(match.usedCoreProgression, false)
})

test("collapses ornamental chromatic neighbor motion during simplified matching", () => {
  const match = buildProgressionMatch("1 6m 4 1 5", "1 b2 1 6m 4 1 5", "flexible")

  assert.ok(match)
  assert.equal(match.exactSimplified, true)
})

test("balanced and flexible keep valid strict contains matches", () => {
  const strictMatch = buildProgressionMatch("4 5 6m 1/3", "1 4 5 6m 1 4", "contains")
  const balancedMatch = buildProgressionMatch("4 5 6m 1/3", "1 4 5 6m 1 4", "mixed")
  const flexibleMatch = buildProgressionMatch("4 5 6m 1/3", "1 4 5 6m 1 4", "flexible")

  assert.ok(strictMatch)
  assert.ok(balancedMatch)
  assert.ok(flexibleMatch)
  assert.equal(balancedMatch.matchLabel, "Contains")
  assert.equal(flexibleMatch.matchLabel, "Contains")
})

test("phase-aligned matches score above later contains matches", () => {
  const startsWithMatch = buildProgressionMatch("4 5 6m", "4 5 6m 1", "flexible")
  const containsMatch = buildProgressionMatch("4 5 6m", "1 4 5 6m", "flexible")

  assert.ok(startsWithMatch)
  assert.ok(containsMatch)
  assert.equal(startsWithMatch.matchLabel, "Starts With")
  assert.ok(startsWithMatch.progressionScore > containsMatch.progressionScore)
})

test("half and double time BPM matches stay weaker than near-tempo matches", () => {
  const nearTempo = resolveBpmScore(72, 75)
  const doubleTime = resolveBpmScore(72, 144)
  const halfTime = resolveBpmScore(144, 72)

  assert.equal(nearTempo.bpmScore, 30)
  assert.ok(doubleTime.bpmScore > 0)
  assert.ok(halfTime.bpmScore > 0)
  assert.ok(nearTempo.bpmScore > doubleTime.bpmScore * 3)
  assert.ok(nearTempo.bpmScore > halfTime.bpmScore * 3)
})

test("energy and danceability add only a light feel signal", () => {
  const matchedFeel = resolveAudioFeelScore(
    { energy: 0.72, danceability: 0.52 },
    { energy: 0.7, danceability: 0.55 },
    "bright"
  )
  const mismatchedFeel = resolveAudioFeelScore(
    { energy: 0.72, danceability: 0.52 },
    { energy: 0.2, danceability: 0.28 },
    "bright"
  )

  assert.ok(matchedFeel.audioFeelScore > mismatchedFeel.audioFeelScore)
  assert.ok(matchedFeel.audioFeelScore <= 12)
})

test("match quality favors harmonic fit over tempo and feel support", () => {
  const exact = buildProgressionMatch("4 5 6m", "4 5 6m", "flexible")
  const contains = buildProgressionMatch("4 5 6m", "1 4 5 6m", "flexible")

  const exactQuality = resolveMatchQualityPercent({
    progressionMatch: exact,
    sectionScore: 12,
    bpmScore: 0,
    audioFeelScore: 0,
  })
  const containsQuality = resolveMatchQualityPercent({
    progressionMatch: contains,
    sectionScore: 50,
    bpmScore: 30,
    audioFeelScore: 12,
  })

  assert.ok(exactQuality > containsQuality)
})

test("song-style reference matching chooses the best actual reference section", () => {
  const referenceTargets = buildReferenceTargets([
    { name: "Chorus", baseName: "chorus", text: "1 5 6m 4" },
    { name: "Bridge", baseName: "bridge", text: "4 5 6m 1/3" },
  ], "all")

  const bestMatch = findBestReferenceTargetMatch(referenceTargets, "4 5 6m 1", "bridge", "flexible")

  assert.ok(bestMatch)
  assert.equal(bestMatch.referenceTarget.baseName, "bridge")
  assert.equal(bestMatch.referenceTarget.label, "bridge")
})

test("flexible search anchors stay selective and include the core variant", () => {
  const referenceTargets = buildReferenceTargets([], "all", "4 6m 5 6m 4")
  const anchors = buildCandidateSearchAnchors(referenceTargets, "flexible")

  assert.ok(anchors.includes("%4%6m%5%6m%4%"))
  assert.ok(anchors.includes("%4%5%6m%4%"))
  assert.ok(!anchors.includes("%4%5%6m%"))
  assert.ok(!anchors.includes("%5%6m%4%"))
})

test("manual progression search uses the same simplified anchor for 1 and 1/3", () => {
  const plainAnchors = buildCandidateSearchAnchors(buildReferenceTargets([], "all", "4 5 6m 1"), "contains")
  const slashAnchors = buildCandidateSearchAnchors(buildReferenceTargets([], "all", "4 5 6m 1/3"), "contains")

  assert.ok(plainAnchors.includes("%4%5%6m%1%"))
  assert.ok(slashAnchors.includes("%4%5%6m%1%"))
})

test("anchors are ordered from most specific to least specific", () => {
  const anchors = buildCandidateSearchAnchors(buildReferenceTargets([], "all", "4 5 6m 1/3"), "flexible")

  assert.deepEqual(anchors, ["%4%5%6m%1/3%", "%4%5%6m%1%"])
})

test("matcher treats terminal inversions as the same exact harmonic arrival", () => {
  const match = buildProgressionMatch("4 5 6m 1", "4 5 6m 1/3", "exact")

  assert.ok(match)
  assert.equal(match.exact, false)
  assert.equal(match.exactSimplified, true)
  assert.equal(match.matchLabel, "Exact (Normalized)")
})

test("reference candidate ranking prefers the stronger bridge-driven Build My Life variant", () => {
  const best = pickBestReferenceCandidate([
    {
      song: { title: "Build My Life", artist_name: "Housefires" },
      version: { id: 1 },
      sectionEntries: [
        { baseName: "bridge", text: "4 5 1 1 4 5 1 1" },
      ],
    },
    {
      song: { title: "Build My Life", artist_name: "Bethel Music" },
      version: { id: 2 },
      sectionEntries: [
        { baseName: "bridge", text: "4 5 6m 1/3 4 5 6m 1/3" },
      ],
    },
  ], "Build My Life")

  assert.ok(best)
  assert.equal(best.song.artist_name, "Bethel Music")
})

test("all-sections song search keeps transition-capable sections and excludes verse-only anchors", () => {
  const targets = buildReferenceTargets([
    { name: "Chorus", baseName: "chorus", text: "2m 1/5 6m 4 2m 1/5 6m" },
    { name: "Bridge", baseName: "bridge", text: "4 5 6m 1/3 4 5 6m 1/3" },
    { name: "Verse", baseName: "verse", text: "1 4 1 4 1 4 1 4" },
    { name: "Pre-Chorus", baseName: "pre_chorus", text: "6m 4 1 5" },
  ], "all")

  assert.equal(targets.length, 3)
  assert.equal(targets[0].baseName, "bridge")
  assert.equal(targets[0].progression, "4 5 6m 1/3 4 5 6m 1/3")
  assert.equal(targets[1].baseName, "pre_chorus")
  assert.equal(targets[2].baseName, "chorus")
})
