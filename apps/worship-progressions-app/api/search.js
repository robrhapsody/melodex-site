import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
)

const WORSHIP_ARTISTS = [
  "Bethel Music",
  "Elevation Worship",
  "Hillsong Worship",
  "Hillsong UNITED",
  "Passion",
  "Maverick City Music",
  "Phil Wickham",
  "Chris Tomlin",
  "Brandon Lake",
  "Cory Asbury"
]

function scoreSong(target, candidate, section) {
  let score = 0

  // 1. Progression match
  if (candidate === target) {
    score += 50
  } else if (candidate?.includes(target) || target?.includes(candidate)) {
    score += 30
  }

  // 2. Worship artist boost
  if (WORSHIP_ARTISTS.includes(candidate.artist)) {
    score += 40
  }

  return score
}

export default async function handler(req, res) {
  try {
    const { song, progression, section = "chorus" } = req.body

    let targetProgression = progression

    // If searching by song, find its progression
    if (song) {
      const { data: found } = await supabase
        .from("songs")
        .select("*")
        .ilike("song_name", `%${song}%`)
        .limit(1)

      if (!found || found.length === 0) {
        return res.status(404).json({ error: "Song not found" })
      }

      targetProgression = found[0][`${section}_nashville`]
    }

    if (!targetProgression) {
      return res.status(400).json({ error: "No progression provided" })
    }

    // Get candidates
    const { data: songs } = await supabase
      .from("songs")
      .select("*")
      .not(`${section}_nashville`, "is", null)

    // Score + filter
    const results = songs.map((s) => {
      const candidate = s[`${section}_nashville`]

      return {
        song_name: s.song_name,
        artist: s.artist,
        bpm: s.bpm,
        section,
        progression: candidate,
        score: scoreSong(targetProgression, { ...s, progression: candidate }, section)
      }
    })

    // Sort + limit
    const sorted = results
      .filter(r => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 20)

    res.status(200).json({
      target: targetProgression,
      results: sorted
    })

  } catch (err) {
    res.status(500).json({ error: err.message })
  }
}
