import { createClient } from "@supabase/supabase-js"

export const CATALOG_ALL = "all"
export const CATALOG_BROAD = "broad_christian_worship"
export const CATALOG_WORSHIP = "worship_strict"
export const VALID_CATALOGS = new Set([CATALOG_ALL, CATALOG_BROAD, CATALOG_WORSHIP])
export const VALID_SECTIONS = new Set([
  "all",
  "intro",
  "verse",
  "pre_chorus",
  "chorus",
  "bridge",
  "tag",
  "interlude",
  "solo",
  "instrumental",
  "full_song",
  "outro",
])

const CATALOG_LABELS = {
  [CATALOG_ALL]: "All songs",
  [CATALOG_BROAD]: "Broad Christian / Worship",
  [CATALOG_WORSHIP]: "Worship",
}

let cachedCounts = { value: null, expiresAt: 0 }
let cachedBpmCoverage = { value: null, expiresAt: 0 }
const cachedCatalogSongSets = new Map()
const CACHE_TTL_MS = 10 * 60_000

export function getCatalogLabel(catalog) {
  return CATALOG_LABELS[catalog] || CATALOG_LABELS[CATALOG_ALL]
}

export function normalizeText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim()
}

export function normalizeSectionName(value) {
  return normalizeText(value).replace(/-/g, "_").replace(/\s+/g, "_")
}

export function baseSectionName(value) {
  return normalizeSectionName(value).replace(/_\d+$/, "")
}

export function parseCatalog(value, fallback = CATALOG_WORSHIP) {
  const normalized = normalizeText(value)
  if (VALID_CATALOGS.has(normalized)) {
    return normalized
  }
  return fallback
}

export function parseSection(value, fallback = "all") {
  const normalized = normalizeSectionName(value)
  if (VALID_SECTIONS.has(normalized)) {
    return normalized
  }
  return fallback
}

export function clampPositiveInteger(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value || ""), 10)
  if (Number.isNaN(parsed)) {
    return fallback
  }
  return Math.min(max, Math.max(min, parsed))
}

export function escapeForIlike(value) {
  return String(value || "").replace(/[%_]/g, "").trim()
}

export function tokenizeProgression(value) {
  return normalizeText(value).split(" ").filter(Boolean)
}

export function getSupabaseClient() {
  const url = process.env.SUPABASE_URL
  const anonKey = process.env.SUPABASE_ANON_KEY
  if (!url || !anonKey) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_ANON_KEY")
  }
  return createClient(url, anonKey)
}

export function chunkArray(items, size = 400) {
  const chunks = []
  for (let i = 0; i < items.length; i += size) {
    chunks.push(items.slice(i, i + size))
  }
  return chunks
}

export async function getCatalogCounts(supabase) {
  const now = Date.now()
  if (cachedCounts.value && cachedCounts.expiresAt > now) {
    return cachedCounts.value
  }

  const [
    songsCountResponse,
    broadCountResponse,
    worshipCountResponse,
  ] = await Promise.all([
    supabase.from("songs").select("id", { count: "exact", head: true }),
    supabase.from("song_catalog_memberships").select("song_id", { count: "exact", head: true }).eq("catalog_name", CATALOG_BROAD),
    supabase.from("song_catalog_memberships").select("song_id", { count: "exact", head: true }).eq("catalog_name", CATALOG_WORSHIP),
  ])

  if (songsCountResponse.error) throw songsCountResponse.error
  if (broadCountResponse.error) throw broadCountResponse.error
  if (worshipCountResponse.error) throw worshipCountResponse.error

  const counts = {
    [CATALOG_ALL]: songsCountResponse.count || 0,
    [CATALOG_BROAD]: broadCountResponse.count || 0,
    [CATALOG_WORSHIP]: worshipCountResponse.count || 0,
  }

  cachedCounts = { value: counts, expiresAt: now + CACHE_TTL_MS }
  return counts
}

export async function getBpmCoverageStats(supabase) {
  const now = Date.now()
  if (cachedBpmCoverage.value && cachedBpmCoverage.expiresAt > now) {
    return cachedBpmCoverage.value
  }

  const [songsCountResponse, tempoCountResponse] = await Promise.all([
    supabase.from("songs").select("id", { count: "exact", head: true }),
    supabase.from("song_audio_features").select("song_id", { count: "exact", head: true }).not("tempo", "is", null),
  ])

  if (songsCountResponse.error) throw songsCountResponse.error
  if (tempoCountResponse.error) throw tempoCountResponse.error

  const totalSongs = songsCountResponse.count || 0
  const songsWithTempo = tempoCountResponse.count || 0
  const songsMissingTempo = Math.max(0, totalSongs - songsWithTempo)
  const coveragePercent = totalSongs > 0 ? Number(((songsWithTempo / totalSongs) * 100).toFixed(1)) : 0

  const coverage = {
    totalSongs,
    songsWithTempo,
    songsMissingTempo,
    coveragePercent,
  }

  cachedBpmCoverage = { value: coverage, expiresAt: now + CACHE_TTL_MS }
  return coverage
}

export async function getCatalogSongIdSet(supabase, catalog) {
  if (catalog === CATALOG_ALL) {
    return null
  }

  const now = Date.now()
  const cached = cachedCatalogSongSets.get(catalog)
  if (cached && cached.expiresAt > now) {
    return cached.value
  }

  const { data, error } = await supabase
    .from("song_catalog_memberships")
    .select("song_id")
    .eq("catalog_name", catalog)

  if (error) throw error

  const idSet = new Set((data || []).map((row) => Number(row.song_id)).filter(Number.isFinite))
  cachedCatalogSongSets.set(catalog, { value: idSet, expiresAt: now + CACHE_TTL_MS })
  return idSet
}

export async function getMembershipRowsForSongIds(supabase, songIds) {
  const uniqueIds = Array.from(new Set(songIds.map(Number).filter(Number.isFinite)))
  if (!uniqueIds.length) {
    return []
  }

  const rows = []
  for (const idChunk of chunkArray(uniqueIds, 300)) {
    const { data, error } = await supabase
      .from("song_catalog_memberships")
      .select("song_id,catalog_name,catalog_bucket")
      .in("song_id", idChunk)
    if (error) throw error
    rows.push(...(data || []))
  }
  return rows
}

export function buildCatalogResolverFromMemberships(membershipRows) {
  const bySongId = new Map()
  for (const row of membershipRows) {
    const songId = Number(row.song_id)
    if (!Number.isFinite(songId)) continue
    if (!bySongId.has(songId)) bySongId.set(songId, new Set())
    bySongId.get(songId).add(String(row.catalog_name || ""))
  }

  return {
    membershipsBySongId: bySongId,
    getPrimaryLabel(songId) {
      const memberships = bySongId.get(Number(songId))
      if (!memberships || !memberships.size) return CATALOG_LABELS[CATALOG_ALL]
      if (memberships.has(CATALOG_WORSHIP)) return CATALOG_LABELS[CATALOG_WORSHIP]
      if (memberships.has(CATALOG_BROAD)) return CATALOG_LABELS[CATALOG_BROAD]
      return CATALOG_LABELS[CATALOG_ALL]
    },
    inCatalog(songId, catalog) {
      if (catalog === CATALOG_ALL) return true
      const memberships = bySongId.get(Number(songId))
      if (!memberships) return false
      return memberships.has(catalog)
    },
  }
}
