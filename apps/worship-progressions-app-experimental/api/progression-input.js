const NOTE_TO_PITCH = new Map([
  ["C", 0],
  ["B#", 0],
  ["C#", 1],
  ["DB", 1],
  ["D", 2],
  ["D#", 3],
  ["EB", 3],
  ["E", 4],
  ["FB", 4],
  ["F", 5],
  ["E#", 5],
  ["F#", 6],
  ["GB", 6],
  ["G", 7],
  ["G#", 8],
  ["AB", 8],
  ["A", 9],
  ["A#", 10],
  ["BB", 10],
  ["B", 11],
  ["CB", 11],
])

const SHARP_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
const FLAT_NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
const CANONICAL_MAJOR_KEYS = [
  { name: "C", pitch: 0 },
  { name: "Db", pitch: 1 },
  { name: "D", pitch: 2 },
  { name: "Eb", pitch: 3 },
  { name: "E", pitch: 4 },
  { name: "F", pitch: 5 },
  { name: "F#", pitch: 6 },
  { name: "G", pitch: 7 },
  { name: "Ab", pitch: 8 },
  { name: "A", pitch: 9 },
  { name: "Bb", pitch: 10 },
  { name: "B", pitch: 11 },
]
const FLAT_MAJOR_KEYS = new Set(["F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"])
const DIATONIC_INTERVALS = new Map([
  [0, { degree: "1", quality: "major" }],
  [2, { degree: "2", quality: "minor" }],
  [4, { degree: "3", quality: "minor" }],
  [5, { degree: "4", quality: "major" }],
  [7, { degree: "5", quality: "major" }],
  [9, { degree: "6", quality: "minor" }],
  [11, { degree: "7", quality: "diminished" }],
])
const BORROWED_INTERVALS = new Map([
  [1, "b2"],
  [3, "b3"],
  [6, "#4"],
  [8, "b6"],
  [10, "b7"],
])
const ALL_INTERVAL_DEGREES = new Map([
  [0, "1"],
  [1, "b2"],
  [2, "2"],
  [3, "b3"],
  [4, "3"],
  [5, "4"],
  [6, "#4"],
  [7, "5"],
  [8, "b6"],
  [9, "6"],
  [10, "b7"],
  [11, "7"],
])

function normalizeWhitespace(value) {
  return String(value || "").replace(/\s+/g, " ").trim()
}

function normalizeAccidentals(value) {
  return String(value || "")
    .replace(/♭/g, "b")
    .replace(/♯/g, "#")
    .replace(/–|—/g, "-")
}

function mod(value, divisor) {
  return ((value % divisor) + divisor) % divisor
}

function tokenizeProgressionInput(value) {
  const normalized = normalizeAccidentals(value)
    .replace(/[|,]+/g, " ")
    .replace(/\s+-\s+/g, " ")

  return normalizeWhitespace(normalized)
    .split(" ")
    .filter(Boolean)
}

function normalizeNashvilleToken(token) {
  const cleaned = normalizeAccidentals(token).replace(/\s+/g, "")
  const match = cleaned.match(/^([b#]?[1-7])(m)?(?:\/([b#]?[1-7]))?$/i)
  if (!match) return null

  const degree = match[1].toLowerCase()
  const minor = match[2] ? "m" : ""
  const bass = match[3] ? `/${match[3].toLowerCase()}` : ""
  return `${degree}${minor}${bass}`
}

function isMinorSuffix(suffix) {
  const lowered = String(suffix || "").toLowerCase()
  return lowered.startsWith("m") && !lowered.startsWith("maj")
}

function getChordQuality(suffix) {
  const lowered = String(suffix || "").toLowerCase()
  if (!lowered) return "major"
  if (/(dim|°|ø|mb5)/.test(lowered)) return "diminished"
  if (isMinorSuffix(lowered) || lowered.includes("min")) return "minor"
  return "major"
}

function noteNameToPitch(letter, accidental = "") {
  return NOTE_TO_PITCH.get(`${String(letter || "").toUpperCase()}${String(accidental || "").replace(/♭/g, "b").replace(/♯/g, "#").toUpperCase()}`) ?? null
}

function canonicalizeChordToken(rootLetter, accidental = "", suffix = "", bassLetter = "", bassAccidental = "") {
  const root = `${String(rootLetter || "").toUpperCase()}${String(accidental || "").replace(/♭/g, "b").replace(/♯/g, "#")}`
  const bass = bassLetter
    ? `/${String(bassLetter || "").toUpperCase()}${String(bassAccidental || "").replace(/♭/g, "b").replace(/♯/g, "#")}`
    : ""
  return `${root}${String(suffix || "")}${bass}`
}

function parseChordToken(token) {
  const cleaned = normalizeAccidentals(token).replace(/\s+/g, "")
  const match = cleaned.match(/^([A-Ga-g])([#b]?)([^/]*)?(?:\/([A-Ga-g])([#b]?))?$/)
  if (!match) return null

  const rootPitch = noteNameToPitch(match[1], match[2] || "")
  if (!Number.isFinite(rootPitch)) return null

  const bassPitch = match[4]
    ? noteNameToPitch(match[4], match[5] || "")
    : null

  return {
    token: canonicalizeChordToken(match[1], match[2] || "", match[3] || "", match[4] || "", match[5] || ""),
    rootPitch,
    bassPitch,
    quality: getChordQuality(match[3] || ""),
  }
}

function intervalToDegree(interval) {
  return ALL_INTERVAL_DEGREES.get(mod(interval, 12)) || "1"
}

function getKeyNamePitch(keyName) {
  const match = normalizeAccidentals(keyName).trim().match(/^([A-Ga-g])([#b]?)/)
  if (!match) return null
  const pitch = noteNameToPitch(match[1], match[2] || "")
  if (!Number.isFinite(pitch)) return null
  return {
    name: `${match[1].toUpperCase()}${match[2] || ""}`,
    pitch,
  }
}

function preferFlatNoteNames(keyName) {
  const parsed = getKeyNamePitch(keyName)
  if (!parsed) return false
  return FLAT_MAJOR_KEYS.has(parsed.name)
}

function pitchToNoteName(pitch, keyName) {
  const names = preferFlatNoteNames(keyName) ? FLAT_NOTE_NAMES : SHARP_NOTE_NAMES
  return names[mod(pitch, 12)]
}

function scoreChordForKey(chord, keyPitch) {
  const interval = mod(chord.rootPitch - keyPitch, 12)
  const diatonic = DIATONIC_INTERVALS.get(interval)
  const borrowed = BORROWED_INTERVALS.get(interval)
  let score = -1.5
  let degree = intervalToDegree(interval)

  if (diatonic) {
    degree = diatonic.degree
    score = 4

    if (chord.quality === diatonic.quality) {
      score += 2
    } else if (chord.quality === "diminished" && diatonic.quality === "diminished") {
      score += 2
    } else {
      score += 0.5
    }
  } else if (borrowed) {
    degree = borrowed
    score = 1.5
    if (chord.quality === "minor") {
      score += 0.25
    }
  }

  if (Number.isFinite(chord.bassPitch)) {
    const bassInterval = mod(chord.bassPitch - keyPitch, 12)
    if (ALL_INTERVAL_DEGREES.has(bassInterval)) {
      score += 0.2
    }
  }

  return {
    interval,
    degree,
    score,
  }
}

function scoreKeyForProgression(chords, key) {
  const chordScores = chords.map((chord) => scoreChordForKey(chord, key.pitch))
  const total = chordScores.reduce((sum, item) => sum + item.score, 0)
  const firstDegree = chordScores[0]?.degree || ""
  const lastDegree = chordScores[chordScores.length - 1]?.degree || ""
  let cadenceBonus = 0

  if (["1", "4", "5", "6"].includes(firstDegree)) {
    cadenceBonus += 0.5
  }
  if (lastDegree === "1") {
    cadenceBonus += 1
  } else if (lastDegree === "5") {
    cadenceBonus += 0.6
  } else if (lastDegree === "6") {
    cadenceBonus += 0.2
  }

  return {
    ...key,
    score: total + cadenceBonus,
    chordScores,
  }
}

function chordToNashvilleToken(chord, keyPitch) {
  const interval = mod(chord.rootPitch - keyPitch, 12)
  const degree = intervalToDegree(interval)
  const qualitySuffix = chord.quality === "minor" ? "m" : ""
  let token = `${degree}${qualitySuffix}`

  if (Number.isFinite(chord.bassPitch)) {
    const bassDegree = intervalToDegree(mod(chord.bassPitch - keyPitch, 12))
    token += `/${bassDegree}`
  }

  return token
}

function parseNashvilleToken(token) {
  const normalized = normalizeNashvilleToken(token)
  if (!normalized) return null

  const match = normalized.match(/^([b#]?[1-7])(m)?(?:\/([b#]?[1-7]))?$/)
  if (!match) return null

  return {
    degree: match[1],
    minor: Boolean(match[2]),
    bass: match[3] || "",
  }
}

function nashvilleTokenToChord(token, keyName) {
  const key = getKeyNamePitch(keyName)
  const parsed = parseNashvilleToken(token)
  if (!key || !parsed) return token

  const rootPitch = mod(key.pitch + degreeToInterval(parsed.degree), 12)
  const chordName = `${pitchToNoteName(rootPitch, key.name)}${parsed.minor ? "m" : ""}`
  if (!parsed.bass) return chordName

  const bassPitch = mod(key.pitch + degreeToInterval(parsed.bass), 12)
  return `${chordName}/${pitchToNoteName(bassPitch, key.name)}`
}

function degreeToInterval(degree) {
  for (const [interval, label] of ALL_INTERVAL_DEGREES.entries()) {
    if (label === degree) return interval
  }
  return 0
}

function convertNashvilleToChords(progressionText, keyName) {
  const tokens = tokenizeProgressionInput(progressionText).map((token) => normalizeNashvilleToken(token)).filter(Boolean)
  if (!tokens.length || !keyName) return ""
  return tokens.map((token) => nashvilleTokenToChord(token, keyName)).join(" ")
}

function detectInputType(tokens) {
  if (!tokens.length) {
    throw new Error("Enter a progression using chord letters like C D Em or Nashville numbers like 4 5 6m.")
  }

  const chordCandidates = tokens.map(parseChordToken)
  if (chordCandidates.every(Boolean)) {
    return {
      type: "chords",
      parsed: chordCandidates,
      normalizedTokens: chordCandidates.map((item) => item.token),
    }
  }

  const nashvilleCandidates = tokens.map((token) => normalizeNashvilleToken(token))
  if (nashvilleCandidates.every(Boolean)) {
    return {
      type: "nashville",
      parsed: nashvilleCandidates,
      normalizedTokens: nashvilleCandidates,
    }
  }

  const containsChordLike = tokens.some((token) => /^[A-Ga-g]/.test(normalizeAccidentals(token)))
  const containsNashvilleLike = tokens.some((token) => /^[b#]?[1-7]/i.test(normalizeAccidentals(token)))

  if (containsChordLike && containsNashvilleLike) {
    throw new Error("Use either chord letters or Nashville numbers in the same progression search, not both together.")
  }

  throw new Error("Couldn't understand that progression. Try chord letters like C D Em or Nashville numbers like 4 5 6m.")
}

function interpretChordProgression(chords, normalizedTokens, rawInput) {
  const rankedKeys = CANONICAL_MAJOR_KEYS
    .map((key) => scoreKeyForProgression(chords, key))
    .sort((left, right) => right.score - left.score)

  const bestKey = rankedKeys[0]
  const alternatives = rankedKeys
    .slice(1)
    .filter((item) => bestKey.score - item.score <= 1.5)
    .slice(0, 2)
    .map((item) => ({
      key: item.name,
      score: Number(item.score.toFixed(2)),
      nashvilleProgression: chords.map((chord) => chordToNashvilleToken(chord, item.pitch)).join(" "),
    }))

  return {
    rawInput,
    inputType: "chords",
    normalizedInput: normalizedTokens.join(" "),
    detectedKey: bestKey.name,
    alternativeKeys: alternatives,
    nashvilleProgression: chords.map((chord) => chordToNashvilleToken(chord, bestKey.pitch)).join(" "),
  }
}

function interpretProgressionInput(value) {
  const rawInput = normalizeWhitespace(value)
  const tokens = tokenizeProgressionInput(rawInput)
  const detected = detectInputType(tokens)

  if (detected.type === "nashville") {
    return {
      rawInput,
      inputType: "nashville",
      normalizedInput: detected.normalizedTokens.join(" "),
      detectedKey: null,
      alternativeKeys: [],
      nashvilleProgression: detected.normalizedTokens.join(" "),
    }
  }

  return interpretChordProgression(detected.parsed, detected.normalizedTokens, rawInput)
}

export {
  convertNashvilleToChords,
  interpretProgressionInput,
  normalizeNashvilleToken,
  parseChordToken,
  tokenizeProgressionInput,
}
