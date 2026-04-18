import { getSupabaseClient } from "./_shared.js"

function isAuthorized(req) {
  const configured = process.env.CRON_SECRET
  if (!configured) {
    // Fail open if no secret is configured, so cron can still keep the DB warm.
    return true
  }

  const authHeader = req.headers.authorization || ""
  const expected = `Bearer ${configured}`
  return authHeader === expected
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET")
    return res.status(405).json({ error: "Method not allowed" })
  }

  if (!isAuthorized(req)) {
    return res.status(401).json({ error: "Unauthorized" })
  }

  try {
    const supabase = getSupabaseClient()
    const { count, error } = await supabase
      .from("songs")
      .select("id", { head: true, count: "exact" })
      .limit(1)

    if (error) throw error

    return res.status(200).json({
      ok: true,
      checkedAt: new Date().toISOString(),
      songsCount: count ?? null,
    })
  } catch (error) {
    return res.status(500).json({
      ok: false,
      error: error.message || "Internal server error",
    })
  }
}
