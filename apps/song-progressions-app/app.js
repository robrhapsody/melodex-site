(function () {
  const data = Array.isArray(window.SONG_DATA) ? window.SONG_DATA : [];

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

  const sectionKeys = ["intro", "verse", "chorus", "bridge", "outro"];
  let selectedReferenceSongId = null;
  let songInputDebounceId = null;

  songCount.textContent = data.length.toLocaleString();

  const preparedSongs = data.map((song) => {
    const sections = {};
    for (const key of sectionKeys) {
      sections[key] = typeof song[key] === "string" ? song[key].trim() : "";
    }

    return {
      ...song,
      sections,
      searchText: normalizeText(song.searchText || `${song.artist} ${song.track} ${song.genre} ${song.key}`),
      displayName: `${song.track} - ${song.artist}`,
    };
  });

  function normalizeText(text) {
    return (text || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function tokenizeProgression(text) {
    return normalizeText(text)
      .split(" ")
      .map((token) => token.trim())
      .filter(Boolean);
  }

  function getSectionEntries(song, selectedSection) {
    if (selectedSection !== "all") {
      return [{ name: selectedSection, text: song.sections[selectedSection] || "" }];
    }

    return sectionKeys
      .map((name) => ({ name, text: song.sections[name] || "" }))
      .filter((entry) => entry.text);
  }

  function longestCommonTokenRun(leftTokens, rightTokens) {
    if (!leftTokens.length || !rightTokens.length) {
      return 0;
    }

    const table = Array(rightTokens.length + 1).fill(0);
    let best = 0;

    for (let i = 1; i <= leftTokens.length; i += 1) {
      let prevDiagonal = 0;
      for (let j = 1; j <= rightTokens.length; j += 1) {
        const temp = table[j];
        if (leftTokens[i - 1] === rightTokens[j - 1]) {
          table[j] = prevDiagonal + 1;
          if (table[j] > best) {
            best = table[j];
          }
        } else {
          table[j] = 0;
        }
        prevDiagonal = temp;
      }
    }

    return best;
  }

  function scoreSongLookup(song, query) {
    if (!query) {
      return 0;
    }

    const haystack = song.searchText;
    const joinedName = normalizeText(`${song.track} ${song.artist}`);
    const trackOnly = normalizeText(song.track);
    const artistOnly = normalizeText(song.artist);

    if (trackOnly === query || joinedName === query) {
      return 1000;
    }
    if (trackOnly.includes(query) || joinedName.includes(query)) {
      return 800 + query.length;
    }
    if (artistOnly === query) {
      return 700;
    }
    if (haystack.includes(query)) {
      return 500 + query.length;
    }

    const terms = query.split(" ").filter(Boolean);
    if (!terms.length) {
      return 0;
    }

    const hits = terms.filter((term) => haystack.includes(term)).length;
    return hits ? hits * 50 : 0;
  }

  function findReferenceSong(songQuery) {
    if (selectedReferenceSongId) {
      const selected = preparedSongs.find((song) => song.songId === selectedReferenceSongId);
      if (selected) {
        return selected;
      }
    }

    const normalizedQuery = normalizeText(songQuery);
    if (!normalizedQuery) {
      return null;
    }

    let bestSong = null;
    let bestScore = 0;

    for (const song of preparedSongs) {
      const score = scoreSongLookup(song, normalizedQuery);
      if (score > bestScore) {
        bestSong = song;
        bestScore = score;
      }
    }

    return bestScore > 0 ? bestSong : null;
  }

  function buildReferenceEntries(song, selectedSection) {
    if (!song) {
      return [];
    }

    return getSectionEntries(song, selectedSection)
      .map((entry) => ({
        name: entry.name,
        text: entry.text,
        tokens: tokenizeProgression(entry.text),
      }))
      .filter((entry) => entry.tokens.length);
  }

  function classifyMatch(exact, contains, similarityRatio, mode) {
    if (mode === "exact") {
      return exact ? "Exact" : "";
    }
    if (mode === "contains") {
      return contains ? "Contains" : "";
    }
    if (mode === "similar") {
      return similarityRatio >= 0.6 ? "Similar" : "";
    }

    if (exact) {
      return "Exact";
    }
    if (contains) {
      return "Contains";
    }
    if (similarityRatio >= 0.6) {
      return "Similar";
    }

    return "";
  }

  function scoreCandidateAgainstReference(referenceEntry, candidateEntry, mode) {
    const referenceTokens = referenceEntry.tokens;
    const candidateTokens = tokenizeProgression(candidateEntry.text);
    if (!referenceTokens.length || !candidateTokens.length) {
      return null;
    }

    const referenceString = referenceTokens.join(" ");
    const candidateString = candidateTokens.join(" ");
    const exact = referenceString === candidateString;
    const contains = candidateString.includes(referenceString) || referenceString.includes(candidateString);
    const commonRun = longestCommonTokenRun(referenceTokens, candidateTokens);
    const similarityRatio = commonRun / Math.min(referenceTokens.length, candidateTokens.length);
    const label = classifyMatch(exact, contains, similarityRatio, mode);

    if (!label) {
      return null;
    }

    let score = 0;
    if (label === "Exact") {
      score = 400 + commonRun * 8;
    } else if (label === "Contains") {
      score = 280 + commonRun * 6;
    } else {
      score = 140 + Math.round(similarityRatio * 100) + commonRun * 3;
    }

    if (referenceEntry.name === candidateEntry.name) {
      score += 20;
    }

    return {
      score,
      label,
      candidateSection: candidateEntry.name,
      referenceSection: referenceEntry.name,
    };
  }

  function evaluateSongByProgression(song, referenceEntries, selectedSection, mode) {
    if (!referenceEntries.length) {
      return null;
    }

    let bestMatch = null;
    const candidateEntries = getSectionEntries(song, selectedSection);

    for (const referenceEntry of referenceEntries) {
      for (const candidateEntry of candidateEntries) {
        const match = scoreCandidateAgainstReference(referenceEntry, candidateEntry, mode);
        if (!match) {
          continue;
        }

        if (!bestMatch || match.score > bestMatch.score) {
          bestMatch = match;
        }
      }
    }

    return bestMatch;
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
    referenceMeta.textContent = [song.year, song.genre, song.key].filter(Boolean).join(" - ");
    referenceSections.innerHTML = "";

    const entries = getSectionEntries(song, selectedSection === "all" ? "all" : selectedSection);
    for (const entry of entries) {
      if (!entry.text) {
        continue;
      }

      const block = document.createElement("div");
      block.className = "section-block";

      const label = document.createElement("h3");
      label.textContent = entry.name;
      block.appendChild(label);

      const text = document.createElement("p");
      text.textContent = entry.text;
      block.appendChild(text);

      referenceSections.appendChild(block);
    }
  }

  function renderSuggestions(query) {
    const normalizedQuery = normalizeText(query);
    songSuggestions.innerHTML = "";

    if (!normalizedQuery || normalizedQuery.length < 2) {
      songSuggestions.hidden = true;
      return;
    }

    const matches = preparedSongs
      .map((song) => ({ song, score: scoreSongLookup(song, normalizedQuery) }))
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, 8);

    if (!matches.length) {
      songSuggestions.hidden = true;
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const match of matches) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion-item";
      button.dataset.songId = match.song.songId;

      const title = document.createElement("span");
      title.className = "suggestion-title";
      title.textContent = `${match.song.track} - ${match.song.artist}`;
      button.appendChild(title);

      const meta = document.createElement("span");
      meta.className = "suggestion-meta";
      meta.textContent = [match.song.year, match.song.genre, match.song.key].filter(Boolean).join(" - ");
      button.appendChild(meta);

      button.addEventListener("click", () => {
        selectedReferenceSongId = match.song.songId;
        songQueryInput.value = `${match.song.track} - ${match.song.artist}`;
        songSuggestions.hidden = true;
        search();
      });

      fragment.appendChild(button);
    }

    songSuggestions.appendChild(fragment);
    songSuggestions.hidden = false;
  }

  function scheduleSongInputWork() {
    if (songInputDebounceId) {
      window.clearTimeout(songInputDebounceId);
    }

    songInputDebounceId = window.setTimeout(() => {
      renderSuggestions(songQueryInput.value);

      if (selectedReferenceSongId || progressionQueryInput.value.trim()) {
        search();
        return;
      }

      const typedQuery = songQueryInput.value.trim();
      if (!typedQuery) {
        search();
        return;
      }

      renderReferencePanel(null, sectionFilter.value);
      resultSummary.textContent = "Choose a song from the suggestions to use it as the reference.";
      resultsContainer.innerHTML = "";
    }, 120);
  }

  function renderResults(results, context) {
    resultsContainer.innerHTML = "";

    if (!context.hasSearch) {
      resultSummary.textContent = "Search by song title to use that song as the reference, or type a Nashville progression directly.";
      return;
    }

    if (!results.length) {
      resultSummary.textContent = context.referenceSong
        ? `No similar progressions found for ${context.referenceSong.track} by ${context.referenceSong.artist}.`
        : "No songs matched the current progression search.";
      return;
    }

    if (context.referenceSong) {
      resultSummary.textContent = `Showing ${results.length} songs ranked by progression similarity to ${context.referenceSong.track} by ${context.referenceSong.artist}.`;
    } else {
      resultSummary.textContent = `Showing ${results.length} songs ranked by progression similarity to "${context.progressionQuery}".`;
    }

    const fragment = document.createDocumentFragment();

    for (const result of results) {
      const node = resultTemplate.content.firstElementChild.cloneNode(true);
      node.querySelector(".result-title").textContent = `${result.track} - ${result.artist}`;
      node.querySelector(".result-meta").textContent = [result.year, result.genre].filter(Boolean).join(" - ");
      node.querySelector(".match-pill").textContent = result.matchLabel;
      node.querySelector(".result-score").textContent = `Matched ${result.sectionLabel} against reference ${result.referenceSection}. Score: ${result.score}.`;
      node.querySelector(".result-key").textContent = result.key ? `Detected key: ${result.key}` : "Detected key unavailable.";

      const sectionList = node.querySelector(".section-list");
      for (const key of sectionKeys) {
        const value = result.sections[key];
        if (!value) {
          continue;
        }

        const block = document.createElement("div");
        block.className = "section-block";

        const label = document.createElement("h3");
        label.textContent = key;
        block.appendChild(label);

        const text = document.createElement("p");
        text.textContent = value;
        block.appendChild(text);

        sectionList.appendChild(block);
      }

      fragment.appendChild(node);
    }

    resultsContainer.appendChild(fragment);
  }

  function search() {
    const songQuery = songQueryInput.value.trim();
    const progressionQuery = progressionQueryInput.value.trim();
    const selectedSection = sectionFilter.value;
    const mode = matchModeSelect.value;
    const limit = Number.parseInt(resultLimitSelect.value, 10) || 50;

    const referenceSong = progressionQuery ? null : findReferenceSong(songQuery);
    const referenceEntries = progressionQuery
      ? [{ name: selectedSection === "all" ? "query" : selectedSection, text: progressionQuery, tokens: tokenizeProgression(progressionQuery) }].filter((entry) => entry.tokens.length)
      : buildReferenceEntries(referenceSong, selectedSection);

    const context = {
      hasSearch: Boolean(progressionQuery || songQuery),
      progressionQuery,
      referenceSong,
    };

    renderReferencePanel(referenceSong, selectedSection);

    if (!referenceEntries.length) {
      renderResults([], context);
      return;
    }

    const matches = [];
    for (const song of preparedSongs) {
      if (referenceSong && song.songId === referenceSong.songId) {
        continue;
      }

      const bestMatch = evaluateSongByProgression(song, referenceEntries, selectedSection, mode);
      if (!bestMatch) {
        continue;
      }

      matches.push({
        ...song,
        score: bestMatch.score,
        matchLabel: bestMatch.label,
        sectionLabel: bestMatch.candidateSection,
        referenceSection: bestMatch.referenceSection,
      });
    }

    matches.sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      const artistCompare = left.artist.localeCompare(right.artist);
      if (artistCompare !== 0) {
        return artistCompare;
      }
      return left.track.localeCompare(right.track);
    });

    renderResults(matches.slice(0, limit), context);
  }

  songQueryInput.addEventListener("input", () => {
    selectedReferenceSongId = null;
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
      songSuggestions.hidden = true;
    }
  });

  progressionQueryInput.addEventListener("input", search);
  sectionFilter.addEventListener("change", search);
  matchModeSelect.addEventListener("change", search);
  resultLimitSelect.addEventListener("change", search);

  search();
})();
