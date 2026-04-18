import {
  CATALOG_ALL,
  clampPositiveInteger,
  escapeForIlike,
  getCatalogCounts,
  getSupabaseClient,
  parseCatalog,
  normalizeText,
  getMembershipRowsForSongIds,
  buildCatalogResolverFromMemberships,
  chunkArray,
} from "./_shared.js"

async function getActiveVersionRowsBySongIds(supabase, songIds) {
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

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET")
    return res.status(405).json({ error: "Method not allowed" })
  }

  try {
    const supabase = getSupabaseClient()
    const catalog = parseCatalog(req.query.catalog, CATALOG_ALL)
    const queryText = String(req.query.q || "").trim()
    const counts = await getCatalogCounts(supabase)
    const catalogCount = counts[catalog] || 0

    if (normalizeText(queryText).length < 2) {
      return res.status(200).json({ catalogCount, suggestions: [] })
    }

    const ilikeTerm = escapeForIlike(queryText)
    const limit = clampPositiveInteger(req.query.limit, 12, 1, 40)
    const { data: songRows, error: songError } = await supabase
      .from("songs")
      .select("id,title,artist_name,year,genre,main_genre")
      .or(`title.ilike.%${ilikeTerm}%,artist_name.ilike.%${ilikeTerm}%`)
      .limit(80)

    if (songError) throw songError

    let filteredSongs = songRows || []
    if (catalog !== CATALOG_ALL) {
      const membershipRows = await getMembershipRowsForSongIds(supabase, filteredSongs.map((song) => song.id))
      const catalogResolver = buildCatalogResolverFromMemberships(membershipRows)
      filteredSongs = filteredSongs.filter((song) => catalogResolver.inCatalog(song.id, catalog))
    }

    filteredSongs.sort((a, b) => {
      const aTitle = normalizeText(a.title)
      const bTitle = normalizeText(b.title)
      const q = normalizeText(queryText)

      const aStarts = aTitle.startsWith(q) || normalizeText(a.artist_name).startsWith(q)
      const bStarts = bTitle.startsWith(q) || normalizeText(b.artist_name).startsWith(q)
      if (aStarts && !bStarts) return -1
      if (!aStarts && bStarts) return 1
      return aTitle.localeCompare(bTitle)
    })

    const selectedSongs = filteredSongs.slice(0, limit)
    const songIds = selectedSongs.map((song) => Number(song.id))
    const [versionRows, membershipRows] = await Promise.all([
      getActiveVersionRowsBySongIds(supabase, songIds),
      getMembershipRowsForSongIds(supabase, songIds),
    ])

    const versionBySongId = new Map(
      versionRows.map((row) => [Number(row.song_id), row])
    )
    const catalogResolver = buildCatalogResolverFromMemberships(membershipRows)

    const suggestions = selectedSongs.map((song) => {
      const version = versionBySongId.get(Number(song.id))
      return {
        rowId: String(song.id),
        track: song.title,
        artist: song.artist_name,
        year: song.year || "",
        genre: song.main_genre || song.genre || "",
        key: version?.display_key || "",
        primaryCatalogLabel: catalogResolver.getPrimaryLabel(song.id),
      }
    })

    return res.status(200).json({
      catalogCount,
      suggestions,
    })
  } catch (error) {
    return res.status(500).json({ error: error.message || "Internal server error" })
  }
}
