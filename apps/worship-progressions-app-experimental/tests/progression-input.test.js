import test from "node:test"
import assert from "node:assert/strict"

import { convertNashvilleToChords, interpretProgressionInput } from "../api/progression-input.js"

test("detects chord-letter input and converts it to Nashville in the best-fit key", () => {
  const interpretation = interpretProgressionInput("C D Em")

  assert.equal(interpretation.inputType, "chords")
  assert.equal(interpretation.detectedKey, "G")
  assert.equal(interpretation.nashvilleProgression, "4 5 6m")
})

test("handles longer chord progressions with repeated passing movement", () => {
  const interpretation = interpretProgressionInput("C Em D Em C")

  assert.equal(interpretation.detectedKey, "G")
  assert.equal(interpretation.nashvilleProgression, "4 6m 5 6m 4")
})

test("keeps Nashville input as Nashville", () => {
  const interpretation = interpretProgressionInput("4 5 6m 1/3")

  assert.equal(interpretation.inputType, "nashville")
  assert.equal(interpretation.detectedKey, null)
  assert.equal(interpretation.nashvilleProgression, "4 5 6m 1/3")
})

test("converts slash chords into slash Nashville degrees", () => {
  const interpretation = interpretProgressionInput("C/E D Em/B")

  assert.equal(interpretation.detectedKey, "G")
  assert.equal(interpretation.nashvilleProgression, "4/6 5 6m/3")
})

test("renders Nashville progressions back into chord letters for any key", () => {
  assert.equal(convertNashvilleToChords("4 5 6m", "C"), "F G Am")
  assert.equal(convertNashvilleToChords("4 5 6m 1/3", "G"), "C D Em G/B")
})

test("borrowed-chord input still finds the most musical major-key interpretation", () => {
  const interpretation = interpretProgressionInput("Bb C Dm")

  assert.equal(interpretation.detectedKey, "F")
  assert.equal(interpretation.nashvilleProgression, "4 5 6m")
})

test("mixed Nashville and chord-letter input returns a helpful error", () => {
  assert.throws(
    () => interpretProgressionInput("C 5 Em"),
    /either chord letters or Nashville numbers/i
  )
})
