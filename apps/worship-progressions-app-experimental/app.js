(function () {
  const catalogFilter = document.getElementById("catalog-filter");
  const songQueryInput = document.getElementById("song-query");
  const progressionQueryInput = document.getElementById("progression-query");
  const sectionFilter = document.getElementById("section-filter");
  const matchModeSelect = document.getElementById("match-mode");
  const resultLimitSelect = document.getElementById("result-limit");
  const songSuggestions = document.getElementById("song-suggestions");
  const referencePanel = document.getElementById("reference-panel");
  const referenceTitle = document.getElementById("reference-title");
  const referenceMeta = document.getElementById("reference-meta");
  const referenceSections = document.getElementById("reference-sections");
  const songCount = document.getElementById("song-count");
  const resultSummary = document.getElementById("result-summary");
  const resultsContainer = document.getElementById("results");
  const resultTemplate = document.getElementById("result-template");
  const modeHelpText = document.getElementById("mode-help-text");

  const state = {
    stats: { counts: {} },
    catalog: catalogFilter.value,
    selectedReferenceSongId: null,
    songInputDebounceId: null,
    progressionInputDebounceId: null,
    suggestionsAbortController: null,
    searchAbortController: null,
  };

  const catalogLabels = {
    all: "All songs",
    broad_christian_worship: "Broad Christian / Worship",
    worship_strict: "Worship",
  };
  const flowPriority = ["pre_chorus", "chorus", "bridge", "tag", "interlude", "verse", "intro", "outro", "full_song"];
  const modeDescriptions = {
    balanced: "Balanced: keeps chord order and returns close in-order matches.",
    strict: "Strict sequence: progression must appear in order (slash chords still map to base chords).",
    flexible: "Flexible (default): passing/slash chords are simplified (for example, 1/3 can match 1).",
  };

  function normalizeText(text) {
    return (text || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function getCatalogLabel(catalog) {
    return catalogLabels[catalog] || "Current catalog";
  }

  function getApiMatchMode(selectedMode) {
    if (selectedMode === "strict") {
      return "contains";
    }
    if (selectedMode === "balanced") {
      return "mixed";
    }
    if (selectedMode === "flexible") {
      return "flexible";
    }
    return "flexible";
  }

  function updateModeHelpText() {
    if (!modeHelpText) {
      return;
    }
    const selectedMode = matchModeSelect.value || "balanced";
    modeHelpText.textContent = modeDescriptions[selectedMode] || modeDescriptions.balanced;
  }

  function updateSongCount(count) {
    const value = typeof count === "number" ? count : (state.stats.counts[state.catalog] || 0);
    songCount.textContent = value.toLocaleString();
  }

  function songMetaText(song) {
    return [song.primaryCatalogLabel, song.year, song.genre, song.key].filter(Boolean).join(" - ");
  }

  function normalizeSectionName(name) {
    return String(name || "").toLowerCase().replace(/\s+/g, "_").replace(/-+/g, "_");
  }

  function baseSectionName(name) {
    const normalized = normalizeSectionName(name);
    return normalized.replace(/_\d+$/, "");
  }

  function renderChordPills(sequenceText) {
    const wrapper = document.createElement("div");
    wrapper.className = "chord-pills";
    const tokens = String(sequenceText || "").trim().split(/\s+/).filter(Boolean).slice(0, 24);
    tokens.forEach((token, index) => {
      const pill = document.createElement("span");
      pill.className = `chord-pill c${index % 4}`;
      pill.textContent = token;
      wrapper.appendChild(pill);
    });
    return wrapper;
  }

  function formatSignedScore(value) {
    if (typeof value !== "number" || Number.isNaN(value)) {
      return "0";
    }
    if (value > 0) {
      return `+${value}`;
    }
    return `${value}`;
  }

  function renderScoreBreakdown(result) {
    const wrapper = document.createElement("div");
    wrapper.className = "score-breakdown";

    const parts = [
      { label: "Progression", value: result.progressionScore },
      { label: "Section", value: result.sectionScore },
      { label: "Worship", value: result.worshipRelevanceScore },
      { label: "BPM", value: result.bpmScore },
      { label: "Familiarity", value: result.familiarityScore },
      { label: "Structure", value: result.structurePenalty },
    ];

    for (const part of parts) {
      const chip = document.createElement("span");
      chip.className = "score-chip";
      chip.innerHTML = `${part.label}: <strong>${formatSignedScore(part.value)}</strong>`;
      wrapper.appendChild(chip);
    }

    if (typeof result.bpmDifference === "number" && Number.isFinite(result.bpmDifference)) {
      const bpmDiffChip = document.createElement("span");
      bpmDiffChip.className = "score-chip";
      bpmDiffChip.innerHTML = `Δ BPM: <strong>${result.bpmDifference.toFixed(1)}</strong>`;
      wrapper.appendChild(bpmDiffChip);
    }

    if (result.usedCoreProgression) {
      const coreChip = document.createElement("span");
      coreChip.className = "score-chip";
      coreChip.innerHTML = `Core match: <strong>passing chords tolerated</strong>`;
      wrapper.appendChild(coreChip);
    }

    return wrapper;
  }

  function chooseFlowEntries(entries, selectedSection, emphasizedSection, limit = 3) {
    const items = Array.isArray(entries) ? entries.filter((entry) => entry && entry.text) : [];
    if (!items.length) {
      return [];
    }

    const baseFiltered = selectedSection === "all"
      ? items
      : items.filter((entry) => baseSectionName(entry.baseName || entry.name) === selectedSection);

    const candidates = baseFiltered.length ? baseFiltered : items;
    const emphasizedBase = baseSectionName(emphasizedSection || "");
    const selectedBases = new Set();
    const output = [];

    function tryPush(entry) {
      const base = baseSectionName(entry.baseName || entry.name);
      if (!base || selectedBases.has(base)) {
        return;
      }
      selectedBases.add(base);
      output.push(entry);
    }

    if (emphasizedBase) {
      for (const entry of candidates) {
        if (baseSectionName(entry.baseName || entry.name) === emphasizedBase) {
          tryPush(entry);
          break;
        }
      }
    }

    for (const sectionName of flowPriority) {
      if (output.length >= limit) {
        break;
      }
      for (const entry of candidates) {
        if (baseSectionName(entry.baseName || entry.name) === sectionName) {
          tryPush(entry);
          break;
        }
      }
    }

    if (!output.length) {
      tryPush(candidates[0]);
    }

    return output.slice(0, limit);
  }

  function setLoadingSummary(message) {
    resultSummary.textContent = message;
  }

  async function fetchJson(url, controller) {
    const response = await fetch(url, { signal: controller ? controller.signal : undefined });
    if (!response.ok) {
      let message = `Request failed: ${response.status}`;
      try {
        const payload = await response.json();
        if (payload && payload.error) {
          message = payload.error;
        }
      } catch (_error) {
        // Fall back to the status-based message if the response is not JSON.
      }
      throw new Error(message);
    }
    return response.json();
  }

  function formatQueryInterpretation(queryInterpretation) {
    if (!queryInterpretation) {
      return "";
    }

    if (queryInterpretation.inputType === "chords") {
      const alternatives = Array.isArray(queryInterpretation.alternativeKeys)
        ? queryInterpretation.alternativeKeys.map((item) => item.key).filter(Boolean).slice(0, 2)
        : [];
      const altText = alternatives.length ? ` Other plausible keys: ${alternatives.join(", ")}.` : "";
      return `Interpreted "${queryInterpretation.rawInput}" in ${queryInterpretation.detectedKey} as ${queryInterpretation.nashvilleProgression}.${altText}`;
    }

    return `Searching Nashville progression ${queryInterpretation.nashvilleProgression}.`;
  }

  async function loadStats() {
    const payload = await fetchJson("/api/stats");
    state.stats = payload;
    updateSongCount(payload.counts[state.catalog] || 0);
  }

  function clearSuggestions() {
    songSuggestions.innerHTML = "";
    songSuggestions.hidden = true;
  }

  function renderReferencePanel(song, selectedSection) {
    if (!song) {
      referencePanel.hidden = true;
      referenceTitle.textContent = "";
      referenceMeta.textContent = "";
      referenceSections.innerHTML = "";
      return;
    }

    referencePanel.hidden = false;
    referenceTitle.textContent = `${song.track} - ${song.artist}`;
    referenceMeta.textContent = songMetaText(song);
    referenceSections.innerHTML = "";

    const flowEntries = chooseFlowEntries(song.sectionEntries, selectedSection, selectedSection, 3);
    for (const entry of flowEntries) {
      const row = document.createElement("div");
      row.className = "flow-row";

      const label = document.createElement("span");
      label.className = "flow-label";
      label.textContent = baseSectionName(entry.baseName || entry.name).replace(/_/g, " ");
      row.appendChild(label);

      row.appendChild(renderChordPills(entry.text));
      referenceSections.appendChild(row);
    }
  }

  function renderResults(results, context) {
    resultsContainer.innerHTML = "";

    if (!context.hasSearch) {
      resultSummary.textContent = `Pick a song or progression to discover smooth transitions into your next song.`;
      return;
    }

    if (!results.length) {
      resultSummary.textContent = context.referenceSong
        ? `No similar progressions found for ${context.referenceSong.track} by ${context.referenceSong.artist} in ${getCatalogLabel(state.catalog)}.`
        : `No songs matched the current progression search in ${getCatalogLabel(state.catalog)}. ${formatQueryInterpretation(context.queryInterpretation)}`.trim();
      return;
    }

    if (context.referenceSong) {
      resultSummary.textContent = `Showing ${results.length} songs ranked by progression similarity to ${context.referenceSong.track} by ${context.referenceSong.artist} in ${getCatalogLabel(state.catalog)}.`;
    } else {
      const interpretationText = formatQueryInterpretation(context.queryInterpretation);
      resultSummary.textContent = `Showing ${results.length} songs ranked by progression similarity to "${context.progressionQuery}" in ${getCatalogLabel(state.catalog)}.${interpretationText ? ` ${interpretationText}` : ""}`;
    }

    const fragment = document.createDocumentFragment();

    for (const result of results) {
      const node = resultTemplate.content.firstElementChild.cloneNode(true);
      node.querySelector(".result-title").textContent = `${result.track} - ${result.artist}`;
      node.querySelector(".result-meta").textContent = songMetaText(result);
      node.querySelector(".match-pill").textContent = result.matchLabel;
      node.querySelector(".result-score").textContent = `Matched ${result.sectionLabel} against reference ${result.referenceSection}. Score: ${result.score}.`;
      node.querySelector(".result-detail").textContent = result.matchDetail;
      node.querySelector(".result-key").textContent = result.key ? `Song key: ${result.key}` : "Song key unavailable.";
      const progressionLines = [];
      if (result.matchedProgressionNashville) {
        progressionLines.push(`Nashville: ${result.matchedProgressionNashville}`);
      }
      if (result.matchedProgressionInSongKey) {
        progressionLines.push(`In ${result.key || "song key"}: ${result.matchedProgressionInSongKey}`);
      }
      if (
        context.queryInterpretation
        && context.queryInterpretation.inputType === "chords"
        && context.queryInterpretation.detectedKey
        && result.matchedProgressionInInputKey
      ) {
        progressionLines.push(`In ${context.queryInterpretation.detectedKey}: ${result.matchedProgressionInInputKey}`);
      }
      node.querySelector(".result-progressions").textContent = progressionLines.join("\n");
      node.querySelector(".score-breakdown").appendChild(renderScoreBreakdown(result));

      const sectionList = node.querySelector(".flow-list");
      const flowEntries = chooseFlowEntries(
        result.sectionEntries || [],
        sectionFilter.value,
        result.sectionLabel,
        3
      );
      for (const entry of flowEntries) {
        const row = document.createElement("div");
        row.className = "flow-row";

        const label = document.createElement("span");
        label.className = "flow-label";
        label.textContent = baseSectionName(entry.baseName || entry.name).replace(/_/g, " ");
        row.appendChild(label);

        row.appendChild(renderChordPills(entry.text));
        sectionList.appendChild(row);
      }

      fragment.appendChild(node);
    }

    resultsContainer.appendChild(fragment);
  }

  async function renderSuggestions(query) {
    const normalizedQuery = normalizeText(query);
    songSuggestions.innerHTML = "";

    if (!normalizedQuery || normalizedQuery.length < 2) {
      clearSuggestions();
      return;
    }

    if (state.suggestionsAbortController) {
      state.suggestionsAbortController.abort();
    }
    state.suggestionsAbortController = new AbortController();

    try {
      const payload = await fetchJson(
        `/api/suggest?catalog=${encodeURIComponent(state.catalog)}&q=${encodeURIComponent(query)}`,
        state.suggestionsAbortController
      );

      updateSongCount(payload.catalogCount);
      const matches = Array.isArray(payload.suggestions) ? payload.suggestions : [];
      if (!matches.length) {
        clearSuggestions();
        return;
      }

      const fragment = document.createDocumentFragment();
      for (const match of matches) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "suggestion-item";
        button.dataset.songId = match.rowId;

        const title = document.createElement("span");
        title.className = "suggestion-title";
        title.textContent = `${match.track} - ${match.artist}`;
        button.appendChild(title);

        const meta = document.createElement("span");
        meta.className = "suggestion-meta";
        meta.textContent = songMetaText(match);
        button.appendChild(meta);

        button.addEventListener("click", () => {
          state.selectedReferenceSongId = match.rowId;
          songQueryInput.value = `${match.track} - ${match.artist}`;
          clearSuggestions();
          search();
        });

        fragment.appendChild(button);
      }

      songSuggestions.appendChild(fragment);
      songSuggestions.hidden = false;
    } catch (error) {
      if (error.name !== "AbortError") {
        clearSuggestions();
      }
    }
  }

  function scheduleSongInputWork() {
    if (state.songInputDebounceId) {
      window.clearTimeout(state.songInputDebounceId);
    }

    state.songInputDebounceId = window.setTimeout(async () => {
      await renderSuggestions(songQueryInput.value);

      if (state.selectedReferenceSongId || progressionQueryInput.value.trim()) {
        search();
        return;
      }

      const typedQuery = songQueryInput.value.trim();
      if (!typedQuery) {
        search();
        return;
      }

      renderReferencePanel(null, sectionFilter.value);
      resultsContainer.innerHTML = "";
      resultSummary.textContent = `Choose a song from the suggestions to use it as the reference within ${getCatalogLabel(state.catalog)}.`;
    }, 160);
  }

  async function search() {
    const songQuery = songQueryInput.value.trim();
    const progressionQuery = progressionQueryInput.value.trim();
    const selectedSection = sectionFilter.value;
    const selectedMode = matchModeSelect.value;
    const mode = getApiMatchMode(selectedMode);
    const limit = Number.parseInt(resultLimitSelect.value, 10) || 15;

    if (!progressionQuery && !state.selectedReferenceSongId) {
      renderReferencePanel(null, selectedSection);
      renderResults([], { hasSearch: false });
      updateSongCount();
      return;
    }

    if (state.searchAbortController) {
      state.searchAbortController.abort();
    }
    state.searchAbortController = new AbortController();

    setLoadingSummary(`Searching ${getCatalogLabel(state.catalog)}...`);

    try {
      const payload = await fetchJson(
        `/api/search?catalog=${encodeURIComponent(state.catalog)}&songQuery=${encodeURIComponent(songQuery)}&referenceSongId=${encodeURIComponent(state.selectedReferenceSongId || "")}&progressionQuery=${encodeURIComponent(progressionQuery)}&section=${encodeURIComponent(selectedSection)}&mode=${encodeURIComponent(mode)}&limit=${encodeURIComponent(String(limit))}`,
        state.searchAbortController
      );

      updateSongCount(payload.catalogCount);
      const context = {
        hasSearch: Boolean(payload.hasSearch),
        progressionQuery: payload.progressionQueryRaw || progressionQuery,
        referenceSong: payload.referenceSong || null,
        queryInterpretation: payload.queryInterpretation || null,
      };

      if (!payload.referenceSong && !progressionQuery && state.selectedReferenceSongId) {
        state.selectedReferenceSongId = null;
      }

      renderReferencePanel(payload.referenceSong, selectedSection);
      renderResults(Array.isArray(payload.results) ? payload.results : [], context);
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      renderReferencePanel(null, selectedSection);
      resultsContainer.innerHTML = "";
      resultSummary.textContent = error.message || "The search request failed. Please try again.";
    }
  }

  songQueryInput.addEventListener("input", () => {
    state.selectedReferenceSongId = null;
    scheduleSongInputWork();
  });

  songQueryInput.addEventListener("focus", () => {
    renderSuggestions(songQueryInput.value);
  });

  songQueryInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }

    const suggestions = songSuggestions.querySelectorAll(".suggestion-item");
    if (!suggestions.length) {
      return;
    }

    event.preventDefault();
    suggestions[0].click();
  });

  document.addEventListener("click", (event) => {
    if (!songSuggestions.contains(event.target) && event.target !== songQueryInput) {
      clearSuggestions();
    }
  });

  progressionQueryInput.addEventListener("input", () => {
    window.clearTimeout(state.songInputDebounceId);
    window.clearTimeout(state.progressionInputDebounceId);
    state.progressionInputDebounceId = window.setTimeout(() => {
      search();
    }, 280);
  });

  catalogFilter.addEventListener("change", () => {
    state.catalog = catalogFilter.value;
    state.selectedReferenceSongId = null;
    clearSuggestions();
    updateSongCount();

    if (!songQueryInput.value.trim() && !progressionQueryInput.value.trim()) {
      renderReferencePanel(null, sectionFilter.value);
      resultsContainer.innerHTML = "";
      resultSummary.textContent = `Pick a song or progression to discover smooth transitions into your next song.`;
      return;
    }

    scheduleSongInputWork();
  });

  sectionFilter.addEventListener("change", search);
  matchModeSelect.addEventListener("change", () => {
    updateModeHelpText();
    search();
  });
  resultLimitSelect.addEventListener("change", search);

  (async function init() {
    try {
      await loadStats();
      updateModeHelpText();
      resultSummary.textContent = "Pick a song or progression to discover smooth transitions into your next song.";
    } catch (error) {
      updateModeHelpText();
      resultSummary.textContent = "The lab API is unavailable. Restart the experimental app server and try again.";
    }
  })();
})();
