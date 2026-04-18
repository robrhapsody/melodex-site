import { buildProgressionMatch, buildProgressionSearchAnchors } from "./progression-matching.js"

const SECTION_PRIORITY = ["bridge", "pre_chorus", "chorus", "tag", "interlude", "verse", "intro", "outro", "full_song"]
const TRANSITION_SECTION_TYPES = new Set(["bridge", "pre_chorus", "chorus", "tag", "interlude"])
const SECTION_BASE_SCORES = {
  chorus: 18,
  pre_chorus: 16,
  bridge: 14,
  verse: 12,
  intro: 8,
  outro: 8,
  full_song: 6,
  interlude: 6,
  instrumental: 6,
  solo: 4,
  tag: 4,
}

function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim()
}

function tokenizeProgression(value) {
  return normalizeText(value).split(" ").filter(Boolean)
}

function formatSectionLabel(sectionName) {
  return String(sectionName || "section").replace(/_/g, " ")
}

function sectionPriorityIndex(sectionName) {
  const index = SECTION_PRIORITY.indexOf(sectionName)
  return index === -1 ? SECTION_PRIORITY.length : index
}

function resolveSectionScore(selectedSection, candidateSection) {
  if (selectedSection !== "all") {
    if (selectedSection === candidateSection) return 50
    const isChorusBridge = (selectedSection === "chorus" && candidateSection === "bridge")
      || (selectedSection === "bridge" && candidateSection === "chorus")
    if (isChorusBridge) return 20
    const isVerseChorus = (selectedSection === "verse" && candidateSection === "chorus")
      || (selectedSection === "chorus" && candidateSection === "verse")
    if (isVerseChorus) return 10
    return 0
  }
  return Math.round((SECTION_BASE_SCORES[candidateSection] || 6) * 0.8)
}

function resolveStructurePenalty(progressionMatch) {
  const targetLength = Number(progressionMatch?.targetLength)
  const candidateLength = Number(progressionMatch?.candidateLength)
  if (!Number.isFinite(targetLength) || !Number.isFinite(candidateLength)) return 0
  if (!targetLength || !candidateLength) return 0
  const difference = Math.abs(targetLength - candidateLength)
  if (difference <= 1) return 0
  if (difference <= 3) return -4
  if (difference <= 6) return -9
  return -15
}

function buildReferenceTargets(referenceEntries, selectedSection, manualProgression = "") {
  if (manualProgression) {
    return [{
      progression: normalizeText(manualProgression),
      baseName: selectedSection === "all" ? "all" : selectedSection,
      label: selectedSection === "all" ? "manual progression" : formatSectionLabel(selectedSection),
      sectionScoreKey: selectedSection === "all" ? "all" : selectedSection,
      isManual: true,
    }]
  }

  if (!Array.isArray(referenceEntries) || !referenceEntries.length) return []

  const orderedTargets = referenceEntries
    .filter((entry) => selectedSection === "all" || entry.baseName === selectedSection)
    .sort((left, right) => {
      const sectionDelta = sectionPriorityIndex(left.baseName) - sectionPriorityIndex(right.baseName)
      if (sectionDelta !== 0) return sectionDelta
      return String(left.name || "").localeCompare(String(right.name || ""))
    })
    .map((entry) => ({
      progression: normalizeText(entry.text),
      baseName: entry.baseName,
      label: formatSectionLabel(entry.baseName || entry.name || "section"),
      sectionScoreKey: entry.baseName || "all",
      isManual: false,
    }))

  if (selectedSection !== "all") {
    return orderedTargets
  }

  const transitionTargets = orderedTargets.filter((entry) => TRANSITION_SECTION_TYPES.has(entry.baseName))
  const candidates = transitionTargets.length ? transitionTargets : orderedTargets
  const byProgression = new Map()

  for (const entry of candidates) {
    const existing = byProgression.get(entry.progression)
    if (!existing || scoreReferenceEntry(entry) > scoreReferenceEntry(existing)) {
      byProgression.set(entry.progression, entry)
    }
  }

  return Array.from(byProgression.values())
    .sort((left, right) => {
      const scoreDelta = scoreReferenceEntry(right) - scoreReferenceEntry(left)
      if (scoreDelta !== 0) return scoreDelta
      return sectionPriorityIndex(left.baseName) - sectionPriorityIndex(right.baseName)
    })
    .slice(0, 3)
}

function countUniqueSimplifiedTokens(progression) {
  return new Set(
    tokenizeProgression(progression).map((token) => token.split("/", 1)[0]).filter(Boolean)
  ).size
}

function scoreReferenceEntry(entry) {
  const sectionWeight = {
    bridge: 80,
    pre_chorus: 72,
    chorus: 64,
    tag: 56,
    interlude: 48,
    verse: 24,
    intro: 16,
    outro: 12,
    full_song: 8,
  }
  const progression = normalizeText(entry?.text)
  const tokens = tokenizeProgression(progression)
  const simplifiedTokenSet = new Set(tokens.map((token) => token.split("/", 1)[0]).filter(Boolean))
  const uniqueCount = simplifiedTokenSet.size
  const hasSlash = progression.includes("/")
  const hasDominantToRelative = simplifiedTokenSet.has("5") && simplifiedTokenSet.has("6m")

  return (
    (sectionWeight[entry?.baseName] || 0)
    + uniqueCount * 5
    + (hasSlash ? 6 : 0)
    + (hasDominantToRelative ? 6 : 0)
  )
}

function scoreReferenceCandidate(candidate, songQuery) {
  const normalizedQuery = normalizeText(songQuery)
  const normalizedTitle = normalizeText(candidate?.song?.title)
  const entryScores = (candidate?.sectionEntries || []).map(scoreReferenceEntry)
  const bestEntryScore = entryScores.length ? Math.max(...entryScores) : 0

  let titleScore = 0
  if (normalizedQuery && normalizedTitle === normalizedQuery) {
    titleScore = 240
  } else if (normalizedQuery && normalizedTitle.startsWith(normalizedQuery)) {
    titleScore = 120
  } else if (normalizedQuery && normalizedTitle.includes(normalizedQuery)) {
    titleScore = 60
  }

  return titleScore + bestEntryScore
}

function pickBestReferenceCandidate(candidates, songQuery) {
  let best = null

  for (const candidate of candidates || []) {
    const score = scoreReferenceCandidate(candidate, songQuery)
    if (!best || score > best.score) {
      best = { ...candidate, score }
    }
  }

  return best
}

function buildCandidateSearchAnchors(referenceTargets, mode) {
  const anchors = new Set()

  for (const target of referenceTargets || []) {
    for (const anchor of buildProgressionSearchAnchors(target.progression, mode)) {
      anchors.add(anchor)
    }
  }

  return Array.from(anchors).sort((left, right) => {
    const leftSlash = left.includes("/")
    const rightSlash = right.includes("/")
    if (leftSlash !== rightSlash) return leftSlash ? -1 : 1
    return right.length - left.length
  })
}

function createReferenceTargetMatcher(referenceTargets, mode) {
  const progressionMatchCache = new Map()
  const bestMatchCache = new Map()

  return function matchReferenceTarget(candidateProgression, candidateSection) {
    const normalizedProgression = normalizeText(candidateProgression)
    const bestKey = `${candidateSection || "section"}|${normalizedProgression}`
    if (bestMatchCache.has(bestKey)) {
      return bestMatchCache.get(bestKey)
    }

    let best = null

    for (const target of referenceTargets || []) {
      const progressionKey = `${target.progression}|${normalizedProgression}|${mode}`
      let progressionMatch
      if (progressionMatchCache.has(progressionKey)) {
        progressionMatch = progressionMatchCache.get(progressionKey)
      } else {
        progressionMatch = buildProgressionMatch(target.progression, normalizedProgression, mode)
        progressionMatchCache.set(progressionKey, progressionMatch || null)
      }
      if (!progressionMatch) continue

      const sectionScore = resolveSectionScore(target.sectionScoreKey || "all", candidateSection)
      const structurePenalty = resolveStructurePenalty(progressionMatch)
      const comparisonScore = progressionMatch.progressionScore * 1.6 + sectionScore + structurePenalty
      const candidate = {
        referenceTarget: target,
        progressionMatch,
        sectionScore,
        structurePenalty,
        comparisonScore,
      }

      if (
        !best
        || candidate.comparisonScore > best.comparisonScore
        || (
          candidate.comparisonScore === best.comparisonScore
          && candidate.progressionMatch.progressionScore > best.progressionMatch.progressionScore
        )
        || (
          candidate.comparisonScore === best.comparisonScore
          && candidate.progressionMatch.progressionScore === best.progressionMatch.progressionScore
          && candidate.sectionScore > best.sectionScore
        )
      ) {
        best = candidate
      }
    }

    bestMatchCache.set(bestKey, best)
    return best
  }
}

function findBestReferenceTargetMatch(referenceTargets, candidateProgression, candidateSection, mode) {
  return createReferenceTargetMatcher(referenceTargets, mode)(candidateProgression, candidateSection)
}

export {
  buildCandidateSearchAnchors,
  buildReferenceTargets,
  createReferenceTargetMatcher,
  findBestReferenceTargetMatch,
  formatSectionLabel,
  pickBestReferenceCandidate,
  resolveSectionScore,
  resolveStructurePenalty,
  scoreReferenceCandidate,
}
