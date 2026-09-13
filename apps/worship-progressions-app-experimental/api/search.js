import {
  CATALOG_ALL,
  CATALOG_BROAD,
  CATALOG_WORSHIP,
  baseSectionName,
  buildCatalogResolverFromMemberships,
  chunkArray,
  clampPositiveInteger,
  escapeForIlike,
  getCatalogCounts,
  getMembershipRowsForSongIds,
  getSupabaseClient,
  normalizeText,
  parseCatalog,
  parseSection,
  tokenizeProgression,
} from "./_shared.js"
import { convertNashvilleToChords, interpretProgressionInput } from "./progression-input.js"
import {
  buildCandidateSearchAnchors,
  buildReferenceTargets,
  createReferenceTargetMatcher,
  formatSectionLabel,
  pickBestReferenceCandidate,
} from "./search-matching.js"
const CANONICAL_WORSHIP_ARTISTS = [
  "bethel music",
  "elevation worship",
  "hillsong worship",
  "hillsong united",
  "hillsong young & free",
  "chris tomlin",
  "phil wickham",
  "brandon lake",
  "cory asbury",
  "pat barrett",
  "matt redman",
  "matt maher",
  "passion",
  "kristian stanfill",
  "crowder",
  "david crowder band",
  "jesus culture",
  "kim walker-smith",
  "chris quilala",
  "kari jobe",
  "cody carnes",
  "maverick city music",
  "upperroom",
  "housefires",
  "jonathan david helser",
  "melissa helser",
  "steffany gretzinger",
  "amanda cook",
  "jenn johnson",
  "brian johnson",
  "jeremy riddle",
  "josh baldwin",
  "kalley heiligenthal",
  "william matthews",
  "paul mcclure",
  "leeland",
  "lincoln brewster",
  "michael w. smith",
  "darlene zschech",
  "reuben morgan",
  "taya",
  "aodhan king",
  "joel houston",
  "matt crocker",
  "benjamin william hastings",
  "brooke ligertwood",
  "martin smith",
  "delirious",
  "tim hughes",
  "graham kendrick",
  "stuart townend",
  "keith getty",
  "kristyn getty",
  "casting crowns",
  "lauren daigle",
  "tasha cobbs leonard",
  "israel houghton",
  "israel & new breed",
  "fred hammond",
  "travis greene",
  "sinach",
  "william mcdowell",
  "don moen",
  "paul baloche",
  "gateway worship",
  "north point worship",
  "vertical worship",
  "cityalight",
  "sovereign grace music",
  "shane & shane",
  "the worship initiative",
  "austin stone worship",
  "desperation band",
  "new life worship",
  "forerunner music",
  "ihopkc",
  "jason upton",
  "misty edwards",
  "rick pino",
  "sean feucht",
  "united pursuit",
  "vineyard worship",
  "planetshakers",
  "influence music",
  "life worship",
  "lifepoint worship",
  "fresh life worship",
  "free chapel music",
  "hope darst",
  "tauren wells",
  "we the kingdom",
  "cain",
  "seu worship",
  "hillsong chapel",
]

const WORSHIP_COLLECTIVE_KEYWORDS = [
  "worship",
  "music",
  "church",
  "collective",
  "chapel",
  "initiative",
]
const TRANSITION_SECTION_TYPES = ["bridge", "pre_chorus", "chorus", "tag", "interlude"]

async function fetchSongRowsByIds(supabase, songIds) {
  const uniqueIds = Array.from(new Set(songIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) return []

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 300)) {
    const { data, error } = await supabase
      .from("songs")
      .select("id,title,artist_name,year,genre,main_genre")
      .in("id", idChunk)
    if (error) throw error
    rows.push(...(data || []))
  }
  return rows
}

async function fetchAudioFeatureRowsBySongIds(supabase, songIds) {
  const uniqueIds = Array.from(new Set(songIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) return []

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 300)) {
    const { data, error } = await supabase
      .from("song_audio_features")
      .select("song_id,tempo,energy,danceability")
      .in("song_id", idChunk)
    if (error) throw error
    rows.push(...(data || []))
  }
  return rows
}

async function fetchActiveVersionRowsBySongIds(supabase, songIds) {
  const uniqueIds = Array.from(new Set(songIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) return []

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 300)) {
    const { data, error } = await supabase
      .from("song_versions")
      .select("id,song_id,display_key,is_active_canonical")
      .in("song_id", idChunk)
      .eq("is_active_canonical", true)
    if (error) throw error
    rows.push(...(data || []))
  }
  return rows
}

async function fetchVersionRowsByIds(supabase, versionIds) {
  const uniqueIds = Array.from(new Set(versionIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) return []

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 300)) {
    const { data, error } = await supabase
      .from("song_versions")
      .select("id,song_id,display_key,is_active_canonical")
      .in("id", idChunk)
      .eq("is_active_canonical", true)
    if (error) throw error
    rows.push(...(data || []))
  }
  return rows
}

async function fetchSectionRowsByVersionIds(supabase, versionIds, section = "all") {
  const uniqueIds = Array.from(new Set(versionIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) return []

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 250)) {
    let query = supabase
      .from("section_occurrences")
      .select("id,song_version_id,name_raw,section_type_estimated,nashville,position_index")
      .in("song_version_id", idChunk)
      .not("nashville", "is", null)

    if (section !== "all") {
      query = query.eq("section_type_estimated", section)
    }

    const { data, error } = await query.order("position_index", { ascending: true }).limit(2000)
    if (error) throw error
    rows.push(...(data || []))
  }

  return rows
}

function createCandidateSectionQuery(supabase, section, sectionTypes = null) {
  let query = supabase
    .from("section_occurrences")
    .select("id,song_version_id,name_raw,section_type_estimated,nashville,position_index")
    .not("nashville", "is", null)
    .order("id", { ascending: true })

  if (section !== "all") {
    query = query.eq("section_type_estimated", section)
  } else if (Array.isArray(sectionTypes) && sectionTypes.length) {
    query = query.in("section_type_estimated", sectionTypes)
  }

  return query
}

async function fetchCandidateRows(
  supabase,
  referenceTargets,
  section,
  mode,
  fallbackToken,
  requestedLimit = 15,
  sectionTypes = null
) {
  const retrievalTargets = referenceTargets.length <= 1 ? referenceTargets : referenceTargets.slice(0, 2)
  const normalizedLimit = clampPositiveInteger(requestedLimit, 15, 1, 100)
  const totalRowCap = retrievalTargets.length <= 1
    ? Math.max(2500, normalizedLimit * 40)
    : Math.max(900, normalizedLimit * 14)
  const perTargetRowCap = retrievalTargets.length <= 1
    ? totalRowCap
    : Math.max(450, Math.ceil(totalRowCap / retrievalTargets.length))
  const pageSize = retrievalTargets.length <= 1
    ? Math.min(1000, totalRowCap)
    : Math.min(400, Math.max(225, Math.ceil(totalRowCap / 3)))
  const rowsById = new Map()
  const executedAnchors = new Set()

  for (const target of retrievalTargets || []) {
    const anchors = buildCandidateSearchAnchors([target], mode)
    let collectedForTarget = 0

    for (let index = 0; index < anchors.length; index += 1) {
      if (rowsById.size >= totalRowCap || collectedForTarget >= perTargetRowCap) break

      const anchor = anchors[index]
      if (executedAnchors.has(anchor)) continue
      executedAnchors.add(anchor)
      let offset = 0

      while (rowsById.size < totalRowCap && collectedForTarget < perTargetRowCap) {
        const remainingForTarget = perTargetRowCap - collectedForTarget
        const remainingTotal = totalRowCap - rowsById.size
        const rowLimit = Math.min(pageSize, remainingForTarget, remainingTotal)
        if (rowLimit <= 0) break

        const { data, error } = await createCandidateSectionQuery(supabase, section, sectionTypes)
          .ilike("nashville", anchor)
          .range(offset, offset + rowLimit - 1)
        if (error) throw error

        const rows = data || []
        for (const row of rows) {
          const rowId = Number(row.id)
          if (!Number.isFinite(rowId) || rowsById.has(rowId)) continue
          rowsById.set(rowId, row)
          collectedForTarget += 1
          if (rowsById.size >= totalRowCap || collectedForTarget >= perTargetRowCap) break
        }

        if (rows.length < rowLimit) break
        offset += rows.length
      }
    }
  }

  if (rowsById.size || !fallbackToken) {
    return Array.from(rowsById.values())
  }

  const { data, error } = await createCandidateSectionQuery(supabase, section, sectionTypes)
    .ilike("nashville", `%${escapeForIlike(fallbackToken)}%`)
    .range(0, 1999)
  if (error) throw error
  return data || []
}

function sectionEntriesByVersionId(sectionRows) {
  const byVersionId = new Map()

  for (const row of sectionRows) {
    const versionId = Number(row.song_version_id)
    if (!Number.isFinite(versionId)) continue

    const text = String(row.nashville || "").trim()
    if (!text) continue

    if (!byVersionId.has(versionId)) byVersionId.set(versionId, [])
    byVersionId.get(versionId).push({
      name: String(row.name_raw || row.section_type_estimated || "section"),
      baseName: baseSectionName(row.section_type_estimated || row.name_raw || "section"),
      text,
      positionIndex: Number.isFinite(Number(row.position_index)) ? Number(row.position_index) : 0,
    })
  }

  for (const [versionId, entries] of byVersionId.entries()) {
    entries.sort((a, b) => a.positionIndex - b.positionIndex)
    const deduped = []
    const seen = new Set()
    for (const entry of entries) {
      const key = `${entry.baseName}|${entry.text}`
      if (seen.has(key)) continue
      seen.add(key)
      deduped.push({
        name: entry.name,
        baseName: entry.baseName,
        text: entry.text,
      })
    }
    byVersionId.set(versionId, deduped)
  }

  return byVersionId
}

function normalizeArtistName(value) {
  return normalizeText(value)
    .replace(/\b(feat|featuring|ft)\b/g, " ")
    .replace(/[,&/|]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function isCanonicalWorshipArtist(artistName) {
  const normalized = normalizeArtistName(artistName)
  if (!normalized) return false
  return CANONICAL_WORSHIP_ARTISTS.some((artist) => {
    const canonical = normalizeArtistName(artist)
    return normalized.includes(canonical) || canonical.includes(normalized)
  })
}

function isWorshipCollectiveLike(artistName) {
  const normalized = normalizeArtistName(artistName)
  if (!normalized) return false
  return WORSHIP_COLLECTIVE_KEYWORDS.some((keyword) => normalized.includes(keyword))
}

function resolveWorshipScore(song, primaryCatalogLabel) {
  const artist = song.artist_name || ""
  if (isCanonicalWorshipArtist(artist)) return 60
  if (isWorshipCollectiveLike(artist)) return 35
  if (primaryCatalogLabel === "Worship") return 30
  if (primaryCatalogLabel === "Broad Christian / Worship") return 12
  return -10
}

function toFiniteNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function resolveBpmScore(referenceBpm, candidateBpm) {
  if (!Number.isFinite(referenceBpm) || !Number.isFinite(candidateBpm)) {
    return { bpmScore: 0, bpmDifference: null, bpmRelationship: "" }
  }

  const directDifference = Math.abs(candidateBpm - referenceBpm)
  if (directDifference <= 3) {
    return { bpmScore: 30, bpmDifference: directDifference, bpmRelationship: "same tempo" }
  }
  if (directDifference <= 6) {
    return { bpmScore: 24, bpmDifference: directDifference, bpmRelationship: "near tempo" }
  }
  if (directDifference <= 10) {
    return { bpmScore: 18, bpmDifference: directDifference, bpmRelationship: "near tempo" }
  }
  if (directDifference <= 15) {
    return { bpmScore: 10, bpmDifference: directDifference, bpmRelationship: "loose tempo" }
  }
  if (directDifference <= 20) {
    return { bpmScore: 5, bpmDifference: directDifference, bpmRelationship: "loose tempo" }
  }

  const halfDoubleCandidates = [
    { difference: Math.abs(candidateBpm - referenceBpm / 2), relationship: "half-time feel" },
    { difference: Math.abs(candidateBpm - referenceBpm * 2), relationship: "double-time feel" },
  ].sort((left, right) => left.difference - right.difference)
  const bestHalfDouble = halfDoubleCandidates[0]

  if (bestHalfDouble.difference <= 3) {
    return { bpmScore: 8, bpmDifference: bestHalfDouble.difference, bpmRelationship: bestHalfDouble.relationship }
  }
  if (bestHalfDouble.difference <= 6) {
    return { bpmScore: 5, bpmDifference: bestHalfDouble.difference, bpmRelationship: bestHalfDouble.relationship }
  }
  if (bestHalfDouble.difference <= 10) {
    return { bpmScore: 2, bpmDifference: bestHalfDouble.difference, bpmRelationship: bestHalfDouble.relationship }
  }

  return { bpmScore: 0, bpmDifference: directDifference, bpmRelationship: "" }
}

function resolveFamiliarityScore(song, primaryCatalogLabel) {
  if (isCanonicalWorshipArtist(song.artist_name || "")) return 20
  if (primaryCatalogLabel === "Worship") return 12
  if (primaryCatalogLabel === "Broad Christian / Worship") return 6
  return 0
}

function normalizeFeelPreference(value) {
  const normalized = normalizeText(value || "any")
  return ["any", "bright", "steady", "gentle"].includes(normalized) ? normalized : "any"
}

function classifyFeel(features) {
  const energy = toFiniteNumber(features?.energy)
  const danceability = toFiniteNumber(features?.danceability)
  if (!Number.isFinite(energy) && !Number.isFinite(danceability)) return ""

  const energyValue = Number.isFinite(energy) ? energy : 0.5
  const danceabilityValue = Number.isFinite(danceability) ? danceability : 0.5
  if (energyValue >= 0.66 || danceabilityValue >= 0.68) return "bright"
  if (energyValue <= 0.38 && danceabilityValue <= 0.55) return "gentle"
  return "steady"
}

function resolveAudioFeelScore(referenceFeatures, candidateFeatures, feelPreference = "any") {
  const candidateFeel = classifyFeel(candidateFeatures)
  let audioFeelScore = 0
  const detailParts = []

  const energyPairs = [
    [toFiniteNumber(referenceFeatures?.energy), toFiniteNumber(candidateFeatures?.energy)],
    [toFiniteNumber(referenceFeatures?.danceability), toFiniteNumber(candidateFeatures?.danceability)],
  ].filter(([referenceValue, candidateValue]) => Number.isFinite(referenceValue) && Number.isFinite(candidateValue))

  if (energyPairs.length) {
    const similarity = energyPairs.reduce((sum, [referenceValue, candidateValue]) => {
      return sum + Math.max(0, 1 - Math.abs(referenceValue - candidateValue))
    }, 0) / energyPairs.length

    if (similarity >= 0.88) {
      audioFeelScore += 8
      detailParts.push("very similar energy")
    } else if (similarity >= 0.74) {
      audioFeelScore += 5
      detailParts.push("similar energy")
    } else if (similarity >= 0.58) {
      audioFeelScore += 2
      detailParts.push("somewhat similar energy")
    } else {
      audioFeelScore -= 2
    }
  }

  const normalizedPreference = normalizeFeelPreference(feelPreference)
  if (normalizedPreference !== "any" && candidateFeel) {
    if (candidateFeel === normalizedPreference) {
      audioFeelScore += 6
      detailParts.push(`${candidateFeel} feel`)
    } else if (normalizedPreference === "steady") {
      audioFeelScore += 2
    } else {
      audioFeelScore -= 3
    }
  }

  return {
    audioFeelScore: Math.max(-5, Math.min(12, audioFeelScore)),
    audioFeelLabel: detailParts.join(", "),
    candidateFeel,
  }
}

function applyScoringWeights(
  progressionScore,
  sectionScore,
  worshipRelevanceScore,
  bpmScore,
  familiarityScore,
  structurePenalty,
  audioFeelScore = 0
) {
  // Keep harmonic flow dominant, then section context, then worship relevance.
  return (
    progressionScore * 1.6
    + sectionScore * 1.0
    + worshipRelevanceScore * 0.8
    + bpmScore * 0.6
    + familiarityScore * 0.4
    + structurePenalty
    + audioFeelScore * 0.5
  )
}

function resolveMatchQualityPercent({
  progressionMatch,
  sectionScore = 0,
  bpmScore = 0,
  audioFeelScore = 0,
  structurePenalty = 0,
}) {
  let baseQuality = 45
  if (progressionMatch?.exact) {
    baseQuality = 96
  } else if (progressionMatch?.exactSimplified) {
    baseQuality = 91
  } else if (progressionMatch?.startsWith) {
    baseQuality = 86
  } else if (progressionMatch?.usedCoreProgression) {
    baseQuality = progressionMatch.matchLabel === "Core Exact" ? 84 : 78
  } else if (progressionMatch?.contains) {
    baseQuality = 76
  } else if (progressionMatch?.progressionScore >= 40) {
    baseQuality = 66
  } else if (progressionMatch?.progressionScore >= 30) {
    baseQuality = 58
  }

  const sectionBonus = Math.max(0, Math.min(5, Math.round(sectionScore / 10)))
  const bpmBonus = Math.max(0, Math.min(3, Math.round(bpmScore / 10)))
  const feelBonus = Math.max(-2, Math.min(2, Math.round(audioFeelScore / 4)))
  const structureAdjustment = structurePenalty < 0 ? Math.max(-5, Math.round(structurePenalty / 3)) : 0

  return Math.max(30, Math.min(100, baseQuality + sectionBonus + bpmBonus + feelBonus + structureAdjustment))
}

async function findReferenceSong(supabase, referenceSongId, songQuery, catalog) {
  let songRows = []

  const idNumber = Number.parseInt(String(referenceSongId || ""), 10)
  if (Number.isFinite(idNumber) && idNumber > 0) {
    const { data, error } = await supabase
      .from("songs")
      .select("id,title,artist_name,year,genre,main_genre")
      .eq("id", idNumber)
      .limit(1)
    if (error) throw error
    songRows = data || []
  } else if (normalizeText(songQuery)) {
    const q = escapeForIlike(songQuery)
    const { data, error } = await supabase
      .from("songs")
      .select("id,title,artist_name,year,genre,main_genre")
      .or(`title.ilike.%${q}%,artist_name.ilike.%${q}%`)
      .limit(10)
    if (error) throw error
    songRows = data || []
  } else {
    return null
  }

  if (!songRows.length) return null
  let filteredSongs = songRows
  if (catalog !== CATALOG_ALL) {
    const membershipRows = await getMembershipRowsForSongIds(supabase, songRows.map((row) => row.id))
    const catalogResolver = buildCatalogResolverFromMemberships(membershipRows)
    filteredSongs = songRows.filter((row) => catalogResolver.inCatalog(row.id, catalog))
  }
  if (!filteredSongs.length) return null

  const versionRows = await fetchActiveVersionRowsBySongIds(supabase, filteredSongs.map((row) => row.id))
  const versionBySongId = new Map(versionRows.map((row) => [Number(row.song_id), row]))
  const sectionRows = await fetchSectionRowsByVersionIds(supabase, versionRows.map((row) => row.id), "all")
  const entriesMap = sectionEntriesByVersionId(sectionRows)

  const candidates = filteredSongs.map((song) => {
    const version = versionBySongId.get(Number(song.id)) || null
    return {
      song,
      version,
      sectionEntries: version ? (entriesMap.get(Number(version.id)) || []) : [],
    }
  })

  const best = pickBestReferenceCandidate(candidates, songQuery)
  if (!best) return null

  return {
    song: best.song,
    version: best.version,
    sectionEntries: best.sectionEntries || [],
  }
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET")
    return res.status(405).json({ error: "Method not allowed" })
  }

  try {
    const supabase = getSupabaseClient()
    const catalog = parseCatalog(req.query.catalog, CATALOG_WORSHIP)
    const section = parseSection(req.query.section, "all")
    const mode = normalizeText(req.query.mode || "flexible") || "flexible"
    const feelPreference = normalizeFeelPreference(req.query.feel)
    const limit = clampPositiveInteger(req.query.limit, 15, 1, 100)

    const songQuery = String(req.query.songQuery || "").trim()
    const progressionQuery = String(req.query.progressionQuery || "").trim()
    const referenceSongId = String(req.query.referenceSongId || "").trim()

    const counts = await getCatalogCounts(supabase)
    const catalogCount = counts[catalog] || 0

    const reference = await findReferenceSong(supabase, referenceSongId, songQuery, catalog)

    let targetProgression = normalizeText(progressionQuery)
    let queryInterpretation = null
    if (progressionQuery) {
      queryInterpretation = interpretProgressionInput(progressionQuery)
      targetProgression = normalizeText(queryInterpretation.nashvilleProgression)
    }
    const referenceTargets = buildReferenceTargets(reference?.sectionEntries || [], section, targetProgression)
    if (!targetProgression && referenceTargets.length) {
      targetProgression = referenceTargets[0].progression
    }

    const referenceSongIdNumber = reference ? Number(reference.song.id) : null
    const referenceVersionId = reference?.version ? Number(reference.version.id) : null

    let referenceTempo = null
    let referenceAudioFeatures = null
    let referenceSongPayload = null
    if (reference) {
      const membershipRows = await getMembershipRowsForSongIds(supabase, [reference.song.id])
      const resolver = buildCatalogResolverFromMemberships(membershipRows)
      const audioFeatureRows = await fetchAudioFeatureRowsBySongIds(supabase, [reference.song.id])
      referenceAudioFeatures = audioFeatureRows[0] || null
      referenceTempo = Number(referenceAudioFeatures?.tempo)
      if (!Number.isFinite(referenceTempo)) referenceTempo = null

      referenceSongPayload = {
        rowId: String(reference.song.id),
        track: reference.song.title,
        artist: reference.song.artist_name,
        year: reference.song.year || "",
        genre: reference.song.main_genre || reference.song.genre || "",
        key: reference.version?.display_key || "",
        bpm: referenceTempo,
        primaryCatalogLabel: resolver.getPrimaryLabel(reference.song.id),
        sectionEntries: reference.sectionEntries || [],
      }
    }

    if (!targetProgression) {
      return res.status(200).json({
        hasSearch: false,
        progressionQuery: "",
        progressionQueryRaw: progressionQuery,
        queryInterpretation,
        referenceSong: referenceSongPayload,
        results: [],
        catalogCount,
      })
    }

    const firstToken = tokenizeProgression(targetProgression)[0] || targetProgression
    const restrictCandidateSections = !progressionQuery && reference && section === "all"
      ? TRANSITION_SECTION_TYPES
      : null
    const candidateRows = await fetchCandidateRows(
      supabase,
      referenceTargets,
      section,
      mode,
      firstToken,
      limit,
      restrictCandidateSections
    )
    const matchReferenceTarget = createReferenceTargetMatcher(referenceTargets, mode)

    const candidateVersionIds = (candidateRows || []).map((row) => Number(row.song_version_id)).filter(Number.isFinite)
    const versionRows = await fetchVersionRowsByIds(supabase, candidateVersionIds)
    const versionById = new Map(versionRows.map((row) => [Number(row.id), row]))

    const candidateSongIds = Array.from(new Set(
      versionRows.map((row) => Number(row.song_id)).filter(Number.isFinite)
    ))
    const shouldFetchCandidateAudio = Number.isFinite(referenceTempo)
      || Number.isFinite(toFiniteNumber(referenceAudioFeatures?.energy))
      || Number.isFinite(toFiniteNumber(referenceAudioFeatures?.danceability))
      || feelPreference !== "any"
    const [songRows, audioFeatureRows, membershipRows] = await Promise.all([
      fetchSongRowsByIds(supabase, candidateSongIds),
      shouldFetchCandidateAudio ? fetchAudioFeatureRowsBySongIds(supabase, candidateSongIds) : Promise.resolve([]),
      getMembershipRowsForSongIds(supabase, candidateSongIds),
    ])

    const songById = new Map(songRows.map((row) => [Number(row.id), row]))
    const audioFeaturesBySongId = new Map(
      audioFeatureRows
        .map((row) => [Number(row.song_id), row])
        .filter((pair) => Number.isFinite(pair[0]))
    )
    const catalogResolver = buildCatalogResolverFromMemberships(membershipRows)

    const bestResultBySongId = new Map()
    for (const row of candidateRows || []) {
      const version = versionById.get(Number(row.song_version_id))
      if (!version || !version.is_active_canonical) continue
      const song = songById.get(Number(version.song_id))
      if (!song) continue

      const songId = Number(song.id)
      if (Number.isFinite(referenceSongIdNumber) && songId === referenceSongIdNumber) continue
      if (!catalogResolver.inCatalog(songId, catalog)) continue

      const candidateSection = baseSectionName(row.section_type_estimated || row.name_raw || "section")
      const referenceTargetMatch = matchReferenceTarget(row.nashville, candidateSection)
      if (!referenceTargetMatch) continue

      const { progressionMatch, referenceTarget, sectionScore, structurePenalty } = referenceTargetMatch
      const primaryCatalogLabel = catalogResolver.getPrimaryLabel(song.id)
      const worshipRelevanceScore = resolveWorshipScore(song, primaryCatalogLabel)
      const candidateAudioFeatures = audioFeaturesBySongId.get(songId) || null
      const candidateTempo = Number(candidateAudioFeatures?.tempo)
      const { bpmScore, bpmDifference, bpmRelationship } = resolveBpmScore(referenceTempo, candidateTempo)
      const { audioFeelScore, audioFeelLabel, candidateFeel } = resolveAudioFeelScore(
        referenceAudioFeatures,
        candidateAudioFeatures,
        feelPreference
      )
      const familiarityScore = resolveFamiliarityScore(song, primaryCatalogLabel)
      const score = applyScoringWeights(
        progressionMatch.progressionScore,
        sectionScore,
        worshipRelevanceScore,
        bpmScore,
        familiarityScore,
        structurePenalty,
        audioFeelScore
      )
      const matchQualityPercent = resolveMatchQualityPercent({
        progressionMatch,
        sectionScore,
        bpmScore,
        audioFeelScore,
        structurePenalty,
      })
      const result = {
        rowId: String(song.id),
        track: song.title,
        artist: song.artist_name,
        year: song.year || "",
        genre: song.main_genre || song.genre || "",
        key: version.display_key || "",
        bpm: Number.isFinite(candidateTempo) ? candidateTempo : null,
        energy: toFiniteNumber(candidateAudioFeatures?.energy),
        danceability: toFiniteNumber(candidateAudioFeatures?.danceability),
        primaryCatalogLabel,
        sectionLabel: candidateSection || "section",
        exactSectionLabel: row.name_raw || row.section_type_estimated || candidateSection || "section",
        referenceSection: referenceTarget?.label || (section === "all" ? "all sections" : formatSectionLabel(section)),
        matchLabel: progressionMatch.matchLabel,
        matchDetail: progressionMatch.matchDetail,
        matchQualityPercent,
        score: Math.round(score),
        progressionScore: progressionMatch.progressionScore,
        sectionScore,
        worshipRelevanceScore,
        bpmScore,
        audioFeelScore,
        audioFeelLabel,
        candidateFeel,
        familiarityScore,
        structurePenalty,
        bpmDifference,
        bpmRelationship,
        usedCoreProgression: progressionMatch.usedCoreProgression,
        matchedProgressionNashville: row.nashville,
        _versionId: Number(version.id),
      }

      const existing = bestResultBySongId.get(songId)
      if (!existing || result.score > existing.score) {
        bestResultBySongId.set(songId, result)
      }
    }

    const ranked = Array.from(bestResultBySongId.values())
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)

    const results = ranked.map((result) => ({
      ...result,
      matchedProgressionInSongKey: result.key
        ? convertNashvilleToChords(result.matchedProgressionNashville, result.key)
        : "",
      matchedProgressionInInputKey: queryInterpretation?.detectedKey
        ? convertNashvilleToChords(result.matchedProgressionNashville, queryInterpretation.detectedKey)
        : "",
      _versionId: undefined,
    }))

    return res.status(200).json({
      hasSearch: true,
      progressionQuery: targetProgression,
      progressionQueryRaw: progressionQuery,
      queryInterpretation,
      referenceSong: referenceSongPayload,
      results,
      catalogCount,
    })
  } catch (error) {
    const message = error.message || "Internal server error"
    const statusCode = /couldn't understand|enter a progression|use either chord letters/i.test(message) ? 400 : 500
    return res.status(statusCode).json({ error: message })
  }
}

export {
  resolveAudioFeelScore,
  resolveBpmScore,
  resolveMatchQualityPercent,
}
