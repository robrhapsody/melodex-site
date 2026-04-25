import {
  getBpmCoverageStats,
  getCatalogCounts,
  getSupabaseClient,
} from "./_shared.js"

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET")
    return res.status(405).json({ error: "Method not allowed" })
  }

  try {
    const supabase = getSupabaseClient()
    const [counts, bpmCoverage] = await Promise.all([
      getCatalogCounts(supabase),
      getBpmCoverageStats(supabase),
    ])
    return res.status(200).json({ counts, bpmCoverage })
  } catch (error) {
    return res.status(500).json({ error: error.message || "Internal server error" })
  }
}
