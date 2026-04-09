param(
    [string]$SlimInputPath = "",
    [string]$WorshipFilterPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $SlimInputPath) { $SlimInputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_slim.csv" }
if (-not $WorshipFilterPath) { $WorshipFilterPath = Join-Path $ProjectRoot "data\processed\worship_songs_strict.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "apps\worship-progressions-app-experimental\data.js" }

function New-CsvParser {
    param([Parameter(Mandatory = $true)][string]$Path)
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($Path)
    $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
    $parser.SetDelimiters(",")
    $parser.HasFieldsEnclosedInQuotes = $true
    return $parser
}

function Normalize-Whitespace {
    param([AllowNull()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    return (($Text -replace '\s+', ' ').Trim())
}

function Escape-JavaScriptString {
    param([AllowNull()][string]$Text)
    if ($null -eq $Text) { return "" }
    return ($Text `
        -replace '\\', '\\' `
        -replace '"', '\"' `
        -replace "`r", '\r' `
        -replace "`n", '\n')
}

function Normalize-NoteName {
    param([string]$Note)
    if ([string]::IsNullOrWhiteSpace($Note)) { return $null }
    $trimmed = $Note.Trim()
    $root = $trimmed.Substring(0, 1).ToUpperInvariant()
    $suffix = if ($trimmed.Length -gt 1) { $trimmed.Substring(1) } else { "" }
    switch ($suffix.ToLowerInvariant()) {
        "s" { return "$root#" }
        "#" { return "$root#" }
        "b" { return "$root" + "b" }
        default { return $root }
    }
}

function Get-NoteSemitone {
    param([string]$Note)
    switch ($Note) {
        "C" { return 0 }
        "C#" { return 1 }
        "Db" { return 1 }
        "D" { return 2 }
        "D#" { return 3 }
        "Eb" { return 3 }
        "E" { return 4 }
        "F" { return 5 }
        "F#" { return 6 }
        "Gb" { return 6 }
        "G" { return 7 }
        "G#" { return 8 }
        "Ab" { return 8 }
        "A" { return 9 }
        "A#" { return 10 }
        "Bb" { return 10 }
        "B" { return 11 }
        default { return $null }
    }
}

function Get-CanonicalKeyName {
    param([int]$Semitone)
    switch ($Semitone % 12) {
        0 { return "C" }
        1 { return "C#" }
        2 { return "D" }
        3 { return "Eb" }
        4 { return "E" }
        5 { return "F" }
        6 { return "F#" }
        7 { return "G" }
        8 { return "Ab" }
        9 { return "A" }
        10 { return "Bb" }
        11 { return "B" }
        default { return $null }
    }
}

function Normalize-ChordToken {
    param([string]$Token)
    if ([string]::IsNullOrWhiteSpace($Token)) { return $null }
    $text = $Token.Trim()
    if ($text -match '^(?i:n\.?c\.?)$') { return $null }

    $parts = $text.Split('/', 2)
    $main = $parts[0]
    $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }

    if ($main -notmatch '^([A-Ga-g])([#bs]?)') { return $null }

    $root = Normalize-NoteName -Note ($matches[1] + $matches[2])
    $tail = $main.Substring($matches[0].Length).ToLowerInvariant()
    $isMinor = $false
    if ($tail -match '^m(?!aj)' -or $tail.Contains('min')) { $isMinor = $true }

    $normalized = if ($isMinor) { "$root" + "m" } else { $root }
    if (-not [string]::IsNullOrWhiteSpace($bass) -and $bass -match '^([A-Ga-g])([#bs]?)') {
        $bassRoot = Normalize-NoteName -Note ($matches[1] + $matches[2])
        if ($bassRoot) {
            $normalized = "$normalized/$bassRoot"
        }
    }

    return $normalized
}

function Clean-ChordSequence {
    param([string]$ChordText)
    if ([string]::IsNullOrWhiteSpace($ChordText)) { return "" }
    $cleaned = New-Object System.Collections.Generic.List[string]
    foreach ($token in ($ChordText -split '\s+')) {
        $normalized = Normalize-ChordToken -Token $token
        if ($normalized) {
            $cleaned.Add($normalized)
        }
    }
    return ($cleaned -join " ")
}

function Parse-AllSections {
    param([string]$ChordText)

    $entries = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($ChordText)) { return $entries }

    $pattern = '<([^>]+)>'
    $matches = [System.Text.RegularExpressions.Regex]::Matches($ChordText, $pattern)
    if ($matches.Count -eq 0) { return $entries }

    for ($i = 0; $i -lt $matches.Count; $i++) {
        $rawName = $matches[$i].Groups[1].Value
        $baseName = ($rawName.ToLowerInvariant() -replace '_\d+$', '')
        $start = $matches[$i].Index + $matches[$i].Length
        $end = if ($i -lt $matches.Count - 1) { $matches[$i + 1].Index } else { $ChordText.Length }
        $sectionText = $ChordText.Substring($start, $end - $start).Trim()
        $cleaned = Clean-ChordSequence -ChordText $sectionText
        if ([string]::IsNullOrWhiteSpace($cleaned)) { continue }

        $entries.Add([pscustomobject]@{
            name = $rawName.ToLowerInvariant()
            baseName = $baseName
            chords = $cleaned
        })
    }

    return $entries
}

function Get-ChordObjects {
    param([object[]]$SectionEntries)
    $chords = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $SectionEntries) {
        foreach ($token in ($entry.chords -split '\s+')) {
            $normalized = Normalize-ChordToken -Token $token
            if (-not $normalized) { continue }

            $parts = $normalized.Split('/', 2)
            $main = $parts[0]
            $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }
            $isMinor = $main.EndsWith("m")
            $root = if ($isMinor) { $main.Substring(0, $main.Length - 1) } else { $main }
            $rootSemitone = Get-NoteSemitone -Note $root
            if ($null -eq $rootSemitone) { continue }

            $bassSemitone = if ($bass) { Get-NoteSemitone -Note $bass } else { $null }
            $chords.Add([pscustomobject]@{
                RootSemitone = $rootSemitone
                IsMinor = $isMinor
                BassSemitone = $bassSemitone
            })
        }
    }
    return $chords.ToArray()
}

function Get-KeyScore {
    param([object[]]$Chords, [int]$TonicSemitone, [bool]$MinorMode)
    $score = 0.0
    $diatonicIntervals = if ($MinorMode) { @(0, 2, 3, 5, 7, 8, 10) } else { @(0, 2, 4, 5, 7, 9, 11) }
    $minorExpected = if ($MinorMode) {
        @{ 0 = $true; 2 = $false; 3 = $false; 5 = $true; 7 = $false; 8 = $false; 10 = $false }
    } else {
        @{ 0 = $false; 2 = $true; 4 = $true; 5 = $false; 7 = $false; 9 = $true; 11 = $false }
    }

    for ($i = 0; $i -lt $Chords.Count; $i++) {
        $chord = $Chords[$i]
        $interval = ($chord.RootSemitone - $TonicSemitone + 12) % 12
        $isDiatonic = $diatonicIntervals -contains $interval

        if ($isDiatonic) {
            $score += 2.0
            if ($minorExpected.ContainsKey($interval) -and $minorExpected[$interval] -eq $chord.IsMinor) {
                $score += 1.5
            } elseif ($MinorMode -and $interval -eq 7 -and -not $chord.IsMinor) {
                $score += 1.0
            }
        } else {
            $score -= 0.75
        }

        if ($interval -eq 0) { $score += 3.0 }
        elseif ($interval -eq 7) { $score += 1.25 }
        elseif ($interval -eq 5) { $score += 0.75 }
        if ($i -eq 0 -and $interval -eq 0) { $score += 1.0 }
        if ($i -eq $Chords.Count - 1 -and $interval -eq 0) { $score += 2.0 }
    }

    return $score
}

function Get-DetectedKey {
    param([object[]]$Chords)
    if (-not $Chords -or $Chords.Count -eq 0) { return $null }

    $bestMajor = $null
    $bestMinor = $null
    for ($tonic = 0; $tonic -lt 12; $tonic++) {
        $majorCandidate = [pscustomobject]@{
            Tonic = $tonic
            MinorMode = $false
            Score = Get-KeyScore -Chords $Chords -TonicSemitone $tonic -MinorMode $false
        }
        $minorCandidate = [pscustomobject]@{
            Tonic = $tonic
            MinorMode = $true
            Score = Get-KeyScore -Chords $Chords -TonicSemitone $tonic -MinorMode $true
        }

        if (-not $bestMajor -or $majorCandidate.Score -gt $bestMajor.Score) { $bestMajor = $majorCandidate }
        if (-not $bestMinor -or $minorCandidate.Score -gt $bestMinor.Score) { $bestMinor = $minorCandidate }
    }

    $selected = $bestMajor
    if ($bestMinor.Score -gt ($bestMajor.Score + 2.0)) {
        $selected = $bestMinor
    }

    $keyName = Get-CanonicalKeyName -Semitone $selected.Tonic
    $nashvilleTonic = $selected.Tonic
    $displayName = if ($selected.MinorMode) { "$keyName minor" } else { $keyName }
    if ($selected.MinorMode) {
        # Experimental mode: represent minor songs relative to their major scale.
        $nashvilleTonic = ($selected.Tonic + 3) % 12
        $displayName = Get-CanonicalKeyName -Semitone $nashvilleTonic
    }

    return [pscustomobject]@{
        Name = $displayName
        Tonic = $selected.Tonic
        NashvilleTonic = $nashvilleTonic
        RelativeMajorName = Get-CanonicalKeyName -Semitone $nashvilleTonic
        UsesRelativeMajorNumbers = [bool]$selected.MinorMode
    }
}

function Get-NashvilleDegree {
    param([int]$SemitoneOffset)
    switch ($SemitoneOffset % 12) {
        0 { return "1" }
        1 { return "b2" }
        2 { return "2" }
        3 { return "b3" }
        4 { return "3" }
        5 { return "4" }
        6 { return "#4" }
        7 { return "5" }
        8 { return "b6" }
        9 { return "6" }
        10 { return "b7" }
        11 { return "7" }
        default { return "?" }
    }
}

function Convert-ToNashvilleSequence {
    param([string]$ChordText, [int]$TonicSemitone)
    if ([string]::IsNullOrWhiteSpace($ChordText)) { return "" }
    $numbers = New-Object System.Collections.Generic.List[string]
    foreach ($token in ($ChordText -split '\s+')) {
        $normalized = Normalize-ChordToken -Token $token
        if (-not $normalized) { continue }

        $parts = $normalized.Split('/', 2)
        $main = $parts[0]
        $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }
        $isMinor = $main.EndsWith("m")
        $root = if ($isMinor) { $main.Substring(0, $main.Length - 1) } else { $main }
        $rootSemitone = Get-NoteSemitone -Note $root
        if ($null -eq $rootSemitone) { continue }

        $degree = Get-NashvilleDegree -SemitoneOffset (($rootSemitone - $TonicSemitone + 12) % 12)
        $display = if ($isMinor) { "$degree" + "m" } else { $degree }

        if ($bass) {
            $bassSemitone = Get-NoteSemitone -Note $bass
            if ($null -ne $bassSemitone) {
                $bassDegree = Get-NashvilleDegree -SemitoneOffset (($bassSemitone - $TonicSemitone + 12) % 12)
                $display = "$display/$bassDegree"
            }
        }

        $numbers.Add($display)
    }
    return ($numbers -join " ")
}

$worshipSongIds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$filterRows = Import-Csv $WorshipFilterPath
foreach ($row in $filterRows) {
    if (-not [string]::IsNullOrWhiteSpace($row.spotify_song_id)) {
        [void]$worshipSongIds.Add($row.spotify_song_id)
    }
}

$appDirectory = Split-Path -Path $OutputPath -Parent
if (-not (Test-Path $appDirectory)) {
    New-Item -ItemType Directory -Path $appDirectory | Out-Null
}

$parser = New-CsvParser -Path $SlimInputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $SlimInputPath"
    }

    $requiredColumns = @("artist_name", "track_name", "year", "main_genre", "chords", "spotify_song_id", "spotify_artist_id")
    $indexes = @{}
    foreach ($column in $requiredColumns) {
        $index = [Array]::IndexOf($headers, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in input CSV."
        }
        $indexes[$column] = $index
    }

    $writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine("window.SONG_DATA = [")

        $first = $true
        $rowsWritten = 0
        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if (-not $fields) { continue }

            $songId = if ($indexes.spotify_song_id -lt $fields.Count) { Normalize-Whitespace $fields[$indexes.spotify_song_id] } else { "" }
            if ([string]::IsNullOrWhiteSpace($songId) -or -not $worshipSongIds.Contains($songId)) {
                continue
            }

            $artist = Normalize-Whitespace $fields[$indexes.artist_name]
            $track = Normalize-Whitespace $fields[$indexes.track_name]
            $year = Normalize-Whitespace $fields[$indexes.year]
            $genre = Normalize-Whitespace $fields[$indexes.main_genre]
            $artistId = Normalize-Whitespace $fields[$indexes.spotify_artist_id]
            $rawChords = if ($indexes.chords -lt $fields.Count) { $fields[$indexes.chords] } else { "" }

            $sectionEntries = Parse-AllSections -ChordText $rawChords
            $detectedKey = Get-DetectedKey -Chords (Get-ChordObjects -SectionEntries $sectionEntries)

            $groupedFirstSections = @{}
            foreach ($entry in $sectionEntries) {
                $nashvilleValue = ""
                if ($detectedKey) {
                    $nashvilleValue = Convert-ToNashvilleSequence -ChordText $entry.chords -TonicSemitone $detectedKey.NashvilleTonic
                }
                $entry | Add-Member -NotePropertyName nashville -NotePropertyValue $nashvilleValue
                if (-not $groupedFirstSections.ContainsKey($entry.baseName)) {
                    $groupedFirstSections[$entry.baseName] = $entry
                }
            }

            $introValue = if ($groupedFirstSections.ContainsKey("intro")) { $groupedFirstSections["intro"].nashville } else { "" }
            $verseValue = if ($groupedFirstSections.ContainsKey("verse")) { $groupedFirstSections["verse"].nashville } else { "" }
            $chorusValue = if ($groupedFirstSections.ContainsKey("chorus")) { $groupedFirstSections["chorus"].nashville } else { "" }
            $bridgeValue = if ($groupedFirstSections.ContainsKey("bridge")) { $groupedFirstSections["bridge"].nashville } else { "" }
            $outroValue = if ($groupedFirstSections.ContainsKey("outro")) { $groupedFirstSections["outro"].nashville } else { "" }

            $allNashville = Normalize-Whitespace ((@($sectionEntries | ForEach-Object { $_.nashville }) -join " | "))
            $preview = Normalize-Whitespace ((@($sectionEntries | Select-Object -First 6 | ForEach-Object { "$($_.name): $($_.nashville)" }) -join " | "))
            $searchText = Normalize-Whitespace ((@($artist, $track, $genre, $(if ($detectedKey) { $detectedKey.Name } else { "" })) -join " ").ToLowerInvariant())

            $sectionEntryLines = @()
            foreach ($entry in $sectionEntries) {
                $entryName = Escape-JavaScriptString $entry.name
                $entryBaseName = Escape-JavaScriptString $entry.baseName
                $entryChords = Escape-JavaScriptString $entry.chords
                $entryNashville = Escape-JavaScriptString $entry.nashville
                $sectionEntryLines += "      { name: `"$entryName`", baseName: `"$entryBaseName`", chords: `"$entryChords`", nashville: `"$entryNashville`" }"
            }

            $artistValue = Escape-JavaScriptString $artist
            $trackValue = Escape-JavaScriptString $track
            $yearValue = Escape-JavaScriptString $year
            $genreValue = Escape-JavaScriptString $genre
            $keyValue = Escape-JavaScriptString $(if ($detectedKey) { $detectedKey.Name } else { "" })
            $songIdValue = Escape-JavaScriptString $songId
            $artistIdValue = Escape-JavaScriptString $artistId
            $introJsValue = Escape-JavaScriptString $introValue
            $verseJsValue = Escape-JavaScriptString $verseValue
            $chorusJsValue = Escape-JavaScriptString $chorusValue
            $bridgeJsValue = Escape-JavaScriptString $bridgeValue
            $outroJsValue = Escape-JavaScriptString $outroValue
            $allNashvilleValue = Escape-JavaScriptString $allNashville
            $previewValue = Escape-JavaScriptString $preview
            $searchTextValue = Escape-JavaScriptString $searchText

            $jsonLines = @(
                "  {"
                "    artist: `"$artistValue`","
                "    track: `"$trackValue`","
                "    year: `"$yearValue`","
                "    genre: `"$genreValue`","
                "    key: `"$keyValue`","
                "    songId: `"$songIdValue`","
                "    artistId: `"$artistIdValue`","
                "    intro: `"$introJsValue`","
                "    verse: `"$verseJsValue`","
                "    chorus: `"$chorusJsValue`","
                "    bridge: `"$bridgeJsValue`","
                "    outro: `"$outroJsValue`","
                "    allNashville: `"$allNashvilleValue`","
                "    preview: `"$previewValue`","
                "    searchText: `"$searchTextValue`","
                "    sectionEntries: ["
                ($sectionEntryLines -join ",`n")
                "    ]"
                "  }"
            )

            if (-not $first) {
                $writer.WriteLine(",")
            }
            $writer.Write(($jsonLines -join "`n"))
            $first = $false
            $rowsWritten++
        }

        $writer.WriteLine()
        $writer.WriteLine("];")
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $parser.Close()
}

Write-Host "Experimental worship app data written to: $OutputPath"
Write-Host "Rows written: $rowsWritten"
