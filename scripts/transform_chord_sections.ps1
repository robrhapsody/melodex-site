param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_slim.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_structured.csv" }

function New-CsvParser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($Path)
    $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
    $parser.SetDelimiters(",")
    $parser.HasFieldsEnclosedInQuotes = $true
    return $parser
}

function ConvertTo-CsvValue {
    param(
        [AllowNull()]
        [object]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    $text = [string]$Value
    if ($text.IndexOfAny([char[]]@(',', '"', "`r", "`n")) -ge 0) {
        return '"' + ($text -replace '"', '""') + '"'
    }

    return $text
}

function Normalize-NoteName {
    param(
        [string]$Note
    )

    if ([string]::IsNullOrWhiteSpace($Note)) {
        return $null
    }

    $trimmed = $Note.Trim()
    if ($trimmed.Length -eq 0) {
        return $null
    }

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
    param(
        [string]$Note
    )

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
    param(
        [int]$Semitone
    )

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
    param(
        [string]$Token
    )

    if ([string]::IsNullOrWhiteSpace($Token)) {
        return $null
    }

    $text = $Token.Trim()
    if ($text -match '^(?i:n\.?c\.?)$') {
        return $null
    }

    $parts = $text.Split('/', 2)
    $main = $parts[0]
    $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }

    if ($main -notmatch '^([A-Ga-g])([#bs]?)') {
        return $null
    }

    $root = Normalize-NoteName -Note ($matches[1] + $matches[2])
    $tail = $main.Substring($matches[0].Length).ToLowerInvariant()
    $isMinor = $false
    if ($tail -match '^m(?!aj)' -or $tail.Contains('min')) {
        $isMinor = $true
    }

    $normalized = if ($isMinor) { "$root" + "m" } else { $root }
    if (-not [string]::IsNullOrWhiteSpace($bass)) {
        if ($bass -match '^([A-Ga-g])([#bs]?)') {
            $bassRoot = Normalize-NoteName -Note ($matches[1] + $matches[2])
            if ($bassRoot) {
                $normalized = "$normalized/$bassRoot"
            }
        }
    }

    return $normalized
}

function Parse-Sections {
    param(
        [string]$ChordText
    )

    $result = [ordered]@{
        ParsedSuccessfully = $false
        intro = ""
        verse = ""
        chorus = ""
        bridge = ""
        outro = ""
    }

    if ([string]::IsNullOrWhiteSpace($ChordText)) {
        return [pscustomobject]$result
    }

    $pattern = '<([^>]+)>'
    $matches = [System.Text.RegularExpressions.Regex]::Matches($ChordText, $pattern)
    if ($matches.Count -eq 0) {
        return [pscustomobject]$result
    }

    $sectionMap = @{
        intro = "intro"
        verse = "verse"
        chorus = "chorus"
        bridge = "bridge"
        outro = "outro"
    }

    $capturedAny = $false

    for ($i = 0; $i -lt $matches.Count; $i++) {
        $rawName = $matches[$i].Groups[1].Value.ToLowerInvariant()
        $baseName = ($rawName -replace '_\d+$', '')
        if (-not $sectionMap.ContainsKey($baseName)) {
            continue
        }

        $normalizedName = $sectionMap[$baseName]
        if (-not [string]::IsNullOrWhiteSpace($result[$normalizedName])) {
            continue
        }

        $start = $matches[$i].Index + $matches[$i].Length
        $end = if ($i -lt $matches.Count - 1) { $matches[$i + 1].Index } else { $ChordText.Length }
        $sectionText = $ChordText.Substring($start, $end - $start).Trim()
        if ([string]::IsNullOrWhiteSpace($sectionText)) {
            continue
        }

        $result[$normalizedName] = $sectionText
        $capturedAny = $true
    }

    $result.ParsedSuccessfully = $capturedAny
    return [pscustomobject]$result
}

function Clean-ChordSequence {
    param(
        [string]$ChordText
    )

    if ([string]::IsNullOrWhiteSpace($ChordText)) {
        return ""
    }

    $cleaned = New-Object System.Collections.Generic.List[string]
    foreach ($token in ($ChordText -split '\s+')) {
        $normalized = Normalize-ChordToken -Token $token
        if ($normalized) {
            $cleaned.Add($normalized)
        }
    }

    return ($cleaned -join " ")
}

function Get-ChordObjects {
    param(
        [string[]]$SectionTexts
    )

    $chords = New-Object System.Collections.Generic.List[object]
    foreach ($sectionText in $SectionTexts) {
        if ([string]::IsNullOrWhiteSpace($sectionText)) {
            continue
        }

        foreach ($token in ($sectionText -split '\s+')) {
            $normalized = Normalize-ChordToken -Token $token
            if (-not $normalized) {
                continue
            }

            $parts = $normalized.Split('/', 2)
            $main = $parts[0]
            $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }
            $isMinor = $main.EndsWith("m")
            $root = if ($isMinor) { $main.Substring(0, $main.Length - 1) } else { $main }
            $rootSemitone = Get-NoteSemitone -Note $root
            if ($null -eq $rootSemitone) {
                continue
            }

            $bassSemitone = if ($bass) { Get-NoteSemitone -Note $bass } else { $null }
            $chords.Add([pscustomobject]@{
                Display = $normalized
                Root = $root
                RootSemitone = $rootSemitone
                IsMinor = $isMinor
                Bass = $bass
                BassSemitone = $bassSemitone
            })
        }
    }

    return $chords.ToArray()
}

function Get-KeyScore {
    param(
        [object[]]$Chords,
        [int]$TonicSemitone,
        [bool]$MinorMode
    )

    $score = 0.0

    $diatonicIntervals = if ($MinorMode) { @(0, 2, 3, 5, 7, 8, 10) } else { @(0, 2, 4, 5, 7, 9, 11) }
    $minorExpected = if ($MinorMode) {
        @{
            0 = $true
            2 = $false
            3 = $false
            5 = $true
            7 = $false
            8 = $false
            10 = $false
        }
    }
    else {
        @{
            0 = $false
            2 = $true
            4 = $true
            5 = $false
            7 = $false
            9 = $true
            11 = $false
        }
    }

    for ($i = 0; $i -lt $Chords.Count; $i++) {
        $chord = $Chords[$i]
        $interval = ($chord.RootSemitone - $TonicSemitone + 12) % 12
        $isDiatonic = $diatonicIntervals -contains $interval

        if ($isDiatonic) {
            $score += 2.0
            if ($minorExpected.ContainsKey($interval) -and $minorExpected[$interval] -eq $chord.IsMinor) {
                $score += 1.5
            }
            elseif ($MinorMode -and $interval -eq 7 -and -not $chord.IsMinor) {
                # Allow a major V in minor keys.
                $score += 1.0
            }
        }
        else {
            $score -= 0.75
        }

        if ($interval -eq 0) {
            $score += 3.0
        }
        elseif ($interval -eq 7) {
            $score += 1.25
        }
        elseif ($interval -eq 5) {
            $score += 0.75
        }

        if ($i -eq 0 -and $interval -eq 0) {
            $score += 1.0
        }
        if ($i -eq $Chords.Count - 1 -and $interval -eq 0) {
            $score += 2.0
        }
    }

    return $score
}

function Get-DetectedKey {
    param(
        [object[]]$Chords
    )

    if (-not $Chords -or $Chords.Count -eq 0) {
        return $null
    }

    $bestMajor = $null
    $bestMinor = $null

    for ($tonic = 0; $tonic -lt 12; $tonic++) {
        $majorScore = Get-KeyScore -Chords $Chords -TonicSemitone $tonic -MinorMode $false
        $minorScore = Get-KeyScore -Chords $Chords -TonicSemitone $tonic -MinorMode $true

        $majorCandidate = [pscustomobject]@{
            Tonic = $tonic
            MinorMode = $false
            Score = $majorScore
        }
        $minorCandidate = [pscustomobject]@{
            Tonic = $tonic
            MinorMode = $true
            Score = $minorScore
        }

        if (-not $bestMajor -or $majorCandidate.Score -gt $bestMajor.Score) {
            $bestMajor = $majorCandidate
        }
        if (-not $bestMinor -or $minorCandidate.Score -gt $bestMinor.Score) {
            $bestMinor = $minorCandidate
        }
    }

    $selected = $bestMajor
    if ($bestMinor.Score -gt ($bestMajor.Score + 2.0)) {
        $selected = $bestMinor
    }

    $keyName = Get-CanonicalKeyName -Semitone $selected.Tonic
    return [pscustomobject]@{
        Name = if ($selected.MinorMode) { "$keyName minor" } else { $keyName }
        Tonic = $selected.Tonic
        MinorMode = $selected.MinorMode
    }
}

function Get-NashvilleDegree {
    param(
        [int]$SemitoneOffset
    )

    switch ($SemitoneOffset) {
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
    param(
        [string]$ChordText,
        [int]$TonicSemitone
    )

    if ([string]::IsNullOrWhiteSpace($ChordText)) {
        return ""
    }

    $numbers = New-Object System.Collections.Generic.List[string]
    foreach ($token in ($ChordText -split '\s+')) {
        $normalized = Normalize-ChordToken -Token $token
        if (-not $normalized) {
            continue
        }

        $parts = $normalized.Split('/', 2)
        $main = $parts[0]
        $bass = if ($parts.Count -gt 1) { $parts[1] } else { $null }
        $isMinor = $main.EndsWith("m")
        $root = if ($isMinor) { $main.Substring(0, $main.Length - 1) } else { $main }
        $rootSemitone = Get-NoteSemitone -Note $root
        if ($null -eq $rootSemitone) {
            continue
        }

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

$inputColumns = @(
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "chords",
    "spotify_song_id",
    "spotify_artist_id"
)

$sectionColumns = @("intro", "verse", "chorus", "bridge", "outro")
$nashvilleColumns = @("intro_nashville", "verse_nashville", "chorus_nashville", "bridge_nashville", "outro_nashville")
$outputColumns = @(
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "chords",
    "intro",
    "verse",
    "chorus",
    "bridge",
    "outro",
    "detected_key",
    "intro_nashville",
    "verse_nashville",
    "chorus_nashville",
    "bridge_nashville",
    "outro_nashville",
    "spotify_song_id",
    "spotify_artist_id"
)

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $InputPath"
    }

    $indexes = @{}
    foreach ($column in $inputColumns) {
        $index = [Array]::IndexOf($headers, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in input CSV."
        }
        $indexes[$column] = $index
    }

    $writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine(($outputColumns | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")

        $rowsWritten = 0
        $rowsParsed = 0
        $rowsUnparsed = 0

        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if (-not $fields) {
                continue
            }

            $row = [ordered]@{}
            foreach ($column in $inputColumns) {
                $index = $indexes[$column]
                $row[$column] = if ($index -lt $fields.Count) { $fields[$index] } else { "" }
            }

            $parsedSections = Parse-Sections -ChordText $row.chords
            foreach ($section in $sectionColumns) {
                $row[$section] = ""
                $row["${section}_nashville"] = ""
            }
            $row.detected_key = ""

            if ($parsedSections.ParsedSuccessfully) {
                foreach ($section in $sectionColumns) {
                    $row[$section] = Clean-ChordSequence -ChordText $parsedSections.$section
                }

                $chordObjects = Get-ChordObjects -SectionTexts @(
                    $row.intro,
                    $row.verse,
                    $row.chorus,
                    $row.bridge,
                    $row.outro
                )

                $detectedKey = Get-DetectedKey -Chords $chordObjects
                if ($detectedKey) {
                    $row.detected_key = $detectedKey.Name
                    foreach ($section in $sectionColumns) {
                        $row["${section}_nashville"] = Convert-ToNashvilleSequence -ChordText $row[$section] -TonicSemitone $detectedKey.Tonic
                    }
                }

                $row.chords = ""
                $rowsParsed++
            }
            else {
                $rowsUnparsed++
            }

            $line = foreach ($column in $outputColumns) {
                ConvertTo-CsvValue $row[$column]
            }

            $writer.WriteLine(($line -join ","))
            $rowsWritten++
        }
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $parser.Close()
}

Write-Host "Structured file written to: $OutputPath"
Write-Host "Rows written: $rowsWritten"
Write-Host "Rows parsed into sections: $rowsParsed"
Write-Host "Rows left in original chords column: $rowsUnparsed"
