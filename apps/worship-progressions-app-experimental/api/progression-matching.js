const ORNAMENTAL_ACCIDENTALS = new Set(["b2", "#4", "b6"])

function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim()
}

function tokenizeProgression(value) {
  return normalizeText(value).split(" ").filter(Boolean)
}

function escapeLikeToken(token) {
  return String(token || "").replace(/[%_]/g, "\\$&")
}

function simplifyToken(token) {
  return normalizeText(token).replace(/[^0-9a-z#bm/]/g, "").split("/", 1)[0]
}

function dedupeConsecutiveTokens(tokens) {
  const output = []
  for (const token of tokens || []) {
    if (!token) continue
    if (!output.length || output[output.length - 1] !== token) {
      output.push(token)
    }
  }
  return output
}

function collapseOrnamentalNeighbors(tokens) {
  const simplified = dedupeConsecutiveTokens(tokens)
  if (simplified.length < 3) return simplified

  const collapsed = []
  let index = 0
  while (index < simplified.length) {
    if (
      index + 2 < simplified.length
      && simplified[index] === simplified[index + 2]
      && ORNAMENTAL_ACCIDENTALS.has(simplified[index + 1])
    ) {
      if (!collapsed.length || collapsed[collapsed.length - 1] !== simplified[index]) {
        collapsed.push(simplified[index])
      }
      index += 3
      continue
    }

    if (!collapsed.length || collapsed[collapsed.length - 1] !== simplified[index]) {
      collapsed.push(simplified[index])
    }
    index += 1
  }

  return collapsed
}

function tokenizeSimplified(text) {
  return collapseOrnamentalNeighbors(tokenizeProgression(text).map(simplifyToken).filter(Boolean))
}

function reduceLoopTokens(tokens) {
  const input = dedupeConsecutiveTokens(tokens)
  const length = input.length
  if (length < 4) return input

  const maxLoop = Math.min(8, Math.floor(length / 2))
  for (let loopLength = 2; loopLength <= maxLoop; loopLength += 1) {
    if (length < loopLength * 2) continue
    const loop = input.slice(0, loopLength)
    let repeated = true
    for (let index = 0; index < length; index += 1) {
      if (input[index] !== loop[index % loopLength]) {
        repeated = false
        break
      }
    }
    if (repeated) return loop
  }
  return input
}

function getWindowSizes(length) {
  if (!length) return []
  if (length <= 3) return [length]

  const sizes = []
  for (let size = 3; size <= Math.min(length, 6); size += 1) {
    sizes.push(size)
  }
  return sizes
}

function getTokenWindows(tokens) {
  const normalized = reduceLoopTokens(tokens || [])
  if (!normalized.length) return []

  const sizes = getWindowSizes(normalized.length)
  const windows = []
  for (const size of sizes) {
    for (let start = 0; start <= normalized.length - size; start += 1) {
      windows.push(normalized.slice(start, start + size))
    }
  }

  return windows
}

function buildCoreVariants(tokens) {
  const base = reduceLoopTokens(tokens)
  const variants = new Map()

  function addVariant(variantTokens) {
    const normalized = reduceLoopTokens(dedupeConsecutiveTokens(variantTokens))
    if (!normalized.length) return
    variants.set(normalized.join(" "), normalized)
  }

  addVariant(base)

  for (let index = 1; index < base.length - 1; index += 1) {
    const current = base[index]
    const repeatsSoon = index + 2 < base.length && base[index + 2] === current
    const repeatedRecently = index - 2 >= 0 && base[index - 2] === current
    if (!(repeatsSoon || repeatedRecently)) continue

    const withoutCurrent = base.slice(0, index).concat(base.slice(index + 1))
    if (withoutCurrent.length >= 3) {
      addVariant(withoutCurrent)
    }
  }

  return Array.from(variants.values())
}

function buildOrderedPattern(tokens) {
  const normalized = dedupeConsecutiveTokens(tokens || []).filter(Boolean)
  if (!normalized.length) return ""
  return `%${normalized.map((token) => escapeLikeToken(token)).join("%")}%`
}

function addAnchorPatterns(anchorSet, tokens, includeWindows = false) {
  const normalized = reduceLoopTokens(dedupeConsecutiveTokens(tokens || []).filter(Boolean))
  if (!normalized.length) return

  const fullPattern = buildOrderedPattern(normalized)
  if (fullPattern) {
    anchorSet.add(fullPattern)
  }

  if (!includeWindows) return

  const windowSize = normalized.length >= 4 ? 3 : normalized.length
  if (windowSize < 2) return

  for (let start = 0; start <= normalized.length - windowSize; start += 1) {
    const windowPattern = buildOrderedPattern(normalized.slice(start, start + windowSize))
    if (windowPattern) {
      anchorSet.add(windowPattern)
    }
  }
}

function buildProgressionSearchAnchors(progression, mode = "flexible") {
  const normalizedMode = ["exact", "contains", "similar", "flexible", "mixed"].includes(mode) ? mode : "flexible"
  const rawTokens = tokenizeProgression(progression)
  const simplifiedTokens = dedupeConsecutiveTokens(tokenizeSimplified(progression))
  const anchorSet = new Set()

  addAnchorPatterns(anchorSet, rawTokens)
  addAnchorPatterns(anchorSet, simplifiedTokens)

  if (normalizedMode === "mixed" || normalizedMode === "similar" || normalizedMode === "flexible") {
    const coreVariants = buildCoreVariants(simplifiedTokens)
    for (const variant of coreVariants) {
      addAnchorPatterns(anchorSet, variant)
    }
  }

  if (!anchorSet.size) {
    const firstToken = rawTokens[0] || simplifiedTokens[0] || ""
    if (firstToken) {
      anchorSet.add(`%${escapeLikeToken(firstToken)}%`)
    }
  }

  return Array.from(anchorSet)
}

function containsTokenSequence(fullTokens, subTokens) {
  if (!Array.isArray(fullTokens) || !Array.isArray(subTokens)) return false
  if (!fullTokens.length || !subTokens.length || subTokens.length > fullTokens.length) return false

  const maxStart = fullTokens.length - subTokens.length
  for (let start = 0; start <= maxStart; start += 1) {
    let isMatch = true
    for (let offset = 0; offset < subTokens.length; offset += 1) {
      if (fullTokens[start + offset] !== subTokens[offset]) {
        isMatch = false
        break
      }
    }
    if (isMatch) return true
  }
  return false
}

function longestCommonSubsequenceLength(leftTokens, rightTokens) {
  if (!leftTokens.length || !rightTokens.length) return 0

  const rows = leftTokens.length + 1
  const cols = rightTokens.length + 1
  const table = Array.from({ length: rows }, () => Array(cols).fill(0))

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      if (leftTokens[i - 1] === rightTokens[j - 1]) {
        table[i][j] = table[i - 1][j - 1] + 1
      } else {
        table[i][j] = Math.max(table[i - 1][j], table[i][j - 1])
      }
    }
  }

  return table[leftTokens.length][rightTokens.length]
}

function longestContiguousRunLength(leftTokens, rightTokens) {
  if (!leftTokens.length || !rightTokens.length) return 0

  const rows = leftTokens.length + 1
  const cols = rightTokens.length + 1
  const table = Array.from({ length: rows }, () => Array(cols).fill(0))
  let longest = 0

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      if (leftTokens[i - 1] === rightTokens[j - 1]) {
        table[i][j] = table[i - 1][j - 1] + 1
        if (table[i][j] > longest) {
          longest = table[i][j]
        }
      }
    }
  }

  return longest
}

function tokenMetrics(targetTokens, candidateTokens) {
  const target = targetTokens || []
  const candidate = candidateTokens || []
  const shortestLength = Math.max(1, Math.min(target.length, candidate.length))
  const lcsLength = longestCommonSubsequenceLength(target, candidate)
  const contiguousLength = longestContiguousRunLength(target, candidate)
  const targetStr = target.join(" ")
  const candidateStr = candidate.join(" ")
  const startsWith = target.length > 0 && candidateStr.startsWith(`${targetStr} `)
  return {
    exact: target.length > 0 && targetStr === candidateStr,
    contains: containsTokenSequence(candidate, target),
    startsWith,
    lcsLength,
    contiguousLength,
    orderedRatio: lcsLength / shortestLength,
    contiguousRatio: contiguousLength / shortestLength,
    shortestLength,
  }
}

function windowMetrics(leftTokens, rightTokens) {
  return {
    lcsLength: longestCommonSubsequenceLength(leftTokens, rightTokens),
    contiguousLength: longestContiguousRunLength(leftTokens, rightTokens),
  }
}

function compareVariantWindows(targetVariant, candidateVariant) {
  const targetWindows = getTokenWindows(targetVariant)
  const candidateWindows = getTokenWindows(candidateVariant)
  const baseLength = Math.max(1, Math.min(targetVariant.length, candidateVariant.length))
  let best = null

  for (const targetWindow of targetWindows) {
    for (const candidateWindow of candidateWindows) {
      const metrics = windowMetrics(targetWindow, candidateWindow)
      const coverage = metrics.lcsLength / baseLength
      const contiguousCoverage = metrics.contiguousLength / baseLength
      const windowLengthDifference = Math.abs(targetWindow.length - candidateWindow.length)
      const candidate = {
        lcsLength: metrics.lcsLength,
        contiguousLength: metrics.contiguousLength,
        coverage,
        contiguousCoverage,
        windowLengthDifference,
        targetWindow,
        candidateWindow,
        targetVariant,
        candidateVariant,
      }

      if (
        !best
        || candidate.coverage > best.coverage
        || (candidate.coverage === best.coverage && candidate.contiguousCoverage > best.contiguousCoverage)
        || (
          candidate.coverage === best.coverage
          && candidate.contiguousCoverage === best.contiguousCoverage
          && candidate.windowLengthDifference < best.windowLengthDifference
        )
        || (
          candidate.coverage === best.coverage
          && candidate.contiguousCoverage === best.contiguousCoverage
          && candidate.windowLengthDifference === best.windowLengthDifference
          && candidate.lcsLength > best.lcsLength
        )
      ) {
        best = candidate
      }
    }
  }

  return best
}

function buildProgressionMatch(targetProgression, candidateProgression, mode) {
  const target = normalizeText(targetProgression)
  const candidate = normalizeText(candidateProgression)
  const targetTokens = tokenizeProgression(target)
  const candidateTokens = tokenizeProgression(candidate)
  const targetSimplifiedTokens = dedupeConsecutiveTokens(tokenizeSimplified(target))
  const candidateSimplifiedTokens = dedupeConsecutiveTokens(tokenizeSimplified(candidate))
  const rawMetrics = tokenMetrics(targetTokens, candidateTokens)
  const simplifiedMetrics = tokenMetrics(targetSimplifiedTokens, candidateSimplifiedTokens)
  const effectiveOrderedRatio = Math.max(rawMetrics.orderedRatio, simplifiedMetrics.orderedRatio)
  const effectiveContiguousRatio = Math.max(rawMetrics.contiguousRatio, simplifiedMetrics.contiguousRatio)
  const orderedFullCoverage = targetTokens.length > 0 && rawMetrics.lcsLength >= targetTokens.length
  const simplifiedFullCoverage = targetSimplifiedTokens.length > 0
    && simplifiedMetrics.lcsLength >= targetSimplifiedTokens.length
  const requiresLocalWindowMatch = targetSimplifiedTokens.length >= 3 && candidateSimplifiedTokens.length >= 3
  let simplifiedWindowMetrics = null
  if (requiresLocalWindowMatch && (orderedFullCoverage || simplifiedFullCoverage)) {
    simplifiedWindowMetrics = compareVariantWindows(targetSimplifiedTokens, candidateSimplifiedTokens)
  }
  const hasStrongSimplifiedWindow = Boolean(
    simplifiedWindowMetrics
    && simplifiedWindowMetrics.coverage >= 0.8
    && simplifiedWindowMetrics.contiguousCoverage >= 0.8
    && simplifiedWindowMetrics.windowLengthDifference <= 1
  )
  const canUseOrderedFallback = (
    (orderedFullCoverage || simplifiedFullCoverage)
    && (!requiresLocalWindowMatch || hasStrongSimplifiedWindow)
  )

  const normalizedMode = ["exact", "contains", "similar", "flexible", "mixed"].includes(mode) ? mode : "flexible"

  if (normalizedMode === "exact" && !rawMetrics.exact && !simplifiedMetrics.exact) return null
  if (normalizedMode === "contains" && !rawMetrics.contains && !simplifiedMetrics.contains) return null

  let progressionScore = 0
  let matchLabel = "Related"
  let matchDetail = "Harmonic shape is related."
  let usedCoreProgression = false

  if (rawMetrics.exact) {
    progressionScore = 70
    matchLabel = "Exact"
    matchDetail = "Exact progression match."
  } else if (simplifiedMetrics.exact) {
    progressionScore = 64
    matchLabel = "Exact (Normalized)"
    matchDetail = "Exact match after slash-chord normalization."
  } else if (rawMetrics.startsWith) {
    progressionScore = 60
    matchLabel = "Starts With"
    matchDetail = "Candidate section begins with the reference progression."
  } else if (simplifiedMetrics.startsWith) {
    progressionScore = 56
    matchLabel = "Starts With (Normalized)"
    matchDetail = "Candidate section begins with the normalized reference progression."
  } else if (rawMetrics.contains || simplifiedMetrics.contains) {
    progressionScore = 52
    matchLabel = "Contains"
    matchDetail = rawMetrics.contains
      ? "Candidate contains the reference progression in order."
      : "Candidate contains the normalized reference progression in order."
  } else if (normalizedMode === "mixed" && canUseOrderedFallback) {
    if (effectiveContiguousRatio >= 0.75) {
      progressionScore = 42
      matchLabel = "Strong Similarity"
      matchDetail = "All target chords appear in order with strong contiguous overlap."
    } else {
      progressionScore = 34
      matchLabel = "Similar"
      matchDetail = "All target chords appear in order."
    }
  } else if (normalizedMode === "similar") {
    if (effectiveOrderedRatio < 0.65 || effectiveContiguousRatio < 0.35) {
      return null
    }
    progressionScore = effectiveOrderedRatio >= 0.85 ? 40 : 30
    matchLabel = effectiveOrderedRatio >= 0.85 ? "Strong Similarity" : "Similar"
    matchDetail = "Ordered progression similarity."
  } else if (normalizedMode === "flexible" && effectiveOrderedRatio >= 0.65 && canUseOrderedFallback) {
    progressionScore = 24
    matchLabel = "Flexible Similarity"
    matchDetail = "Ordered similarity after simplifying passing/inversion chords."
  }

  let bestCore = null
  if (targetSimplifiedTokens.length >= 3 && candidateSimplifiedTokens.length >= 3) {
    const targetCoreVariants = buildCoreVariants(targetSimplifiedTokens)
    const candidateCoreVariants = buildCoreVariants(candidateSimplifiedTokens)

    for (const targetVariant of targetCoreVariants) {
      for (const candidateVariant of candidateCoreVariants) {
        const coreMetrics = tokenMetrics(targetVariant, candidateVariant)
        if (coreMetrics.shortestLength < 3) continue

        let coreScore = 0
        let coreLabel = ""
        let coreDetail = ""
        let coreWindowMetrics = null
        if (coreMetrics.exact) {
          coreScore = 66
          coreLabel = "Core Exact"
          coreDetail = "Core harmonic movement matches after removing passing chords."
        } else if (coreMetrics.contains && coreMetrics.shortestLength >= 3) {
          coreScore = 58
          coreLabel = "Core Contains"
          coreDetail = "Candidate contains the core harmonic movement with passing chords ignored."
        } else {
          coreWindowMetrics = compareVariantWindows(targetVariant, candidateVariant)
          if (
            coreWindowMetrics
            && coreWindowMetrics.coverage >= 0.85
            && coreWindowMetrics.contiguousCoverage >= 0.8
            && coreWindowMetrics.windowLengthDifference <= 1
          ) {
            coreScore = 50
            coreLabel = "Core Similarity"
            coreDetail = "Core progression is strongly similar with passing-chord tolerance."
          }
        }

        if (!coreScore) continue
        const candidate = {
          score: coreScore,
          label: coreLabel,
          detail: coreDetail,
          metrics: coreWindowMetrics || coreMetrics,
          targetVariant,
          candidateVariant,
        }
        if (!bestCore || candidate.score > bestCore.score) {
          bestCore = candidate
        }
      }
    }
  }

  if (
    bestCore
    && (
      progressionScore < 52
      || (progressionScore <= 58 && bestCore.score >= progressionScore + 8)
    )
  ) {
    progressionScore = bestCore.score
    matchLabel = bestCore.label
    matchDetail = `${bestCore.detail} Core target: ${bestCore.targetVariant.join(" ")}. Core candidate: ${bestCore.candidateVariant.join(" ")}.`
    usedCoreProgression = true
  } else {
    const hasTraditionalMatch = progressionScore > 0
    const hasCoreMatch = Boolean(bestCore)
    const hasStrongOrderedSimilarity = normalizedMode === "mixed" && canUseOrderedFallback
    const hasFlexibleOrderedSimilarity = normalizedMode === "flexible"
      && effectiveOrderedRatio >= 0.65
      && canUseOrderedFallback
    const hasExplicitSimilarity = normalizedMode === "similar"
      && effectiveOrderedRatio >= 0.65
      && effectiveContiguousRatio >= 0.35

    if (!hasTraditionalMatch && !hasCoreMatch && !hasStrongOrderedSimilarity && !hasFlexibleOrderedSimilarity && !hasExplicitSimilarity) {
      return null
    }
  }

  return {
    progressionScore,
    matchLabel,
    matchDetail,
    exact: rawMetrics.exact,
    exactSimplified: simplifiedMetrics.exact,
    contains: rawMetrics.contains || simplifiedMetrics.contains,
    startsWith: rawMetrics.startsWith || simplifiedMetrics.startsWith,
    orderedRatio: rawMetrics.orderedRatio,
    contiguousRatio: rawMetrics.contiguousRatio,
    simplifiedOrderedRatio: simplifiedMetrics.orderedRatio,
    simplifiedContiguousRatio: simplifiedMetrics.contiguousRatio,
    usedCoreProgression,
    targetLength: targetSimplifiedTokens.length,
    candidateLength: candidateSimplifiedTokens.length,
  }
}

export { buildProgressionMatch, buildProgressionSearchAnchors }
