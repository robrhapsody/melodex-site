param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_structured.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "apps\song-progressions-app\data.js" }

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

function Normalize-Whitespace {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    return (($Text -replace '\s+', ' ').Trim())
}

function Escape-JavaScriptString {
    param(
        [AllowNull()]
        [string]$Text
    )

    if ($null -eq $Text) {
        return ""
    }

    return ($Text `
        -replace '\\', '\\' `
        -replace '"', '\"' `
        -replace "`r", '\r' `
        -replace "`n", '\n')
}

$columns = @(
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "detected_key",
    "intro",
    "verse",
    "chorus",
    "bridge",
    "outro",
    "intro_nashville",
    "verse_nashville",
    "chorus_nashville",
    "bridge_nashville",
    "outro_nashville",
    "spotify_song_id",
    "spotify_artist_id"
)

$appDirectory = Split-Path -Path $OutputPath -Parent
if (-not (Test-Path $appDirectory)) {
    New-Item -ItemType Directory -Path $appDirectory | Out-Null
}

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $InputPath"
    }

    $indexes = @{}
    foreach ($column in $columns) {
        $index = [Array]::IndexOf($headers, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in input CSV."
        }
        $indexes[$column] = $index
    }

    $writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine("window.SONG_DATA = [")

        $rowsWritten = 0
        $first = $true
        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if (-not $fields) {
                continue
            }

            $row = @{}
            foreach ($column in $columns) {
                $index = $indexes[$column]
                $row[$column] = if ($index -lt $fields.Count) { Normalize-Whitespace $fields[$index] } else { "" }
            }

            $allNashville = Normalize-Whitespace ((@(
                $row.intro_nashville
                $row.verse_nashville
                $row.chorus_nashville
                $row.bridge_nashville
                $row.outro_nashville
            ) -join " | "))

            $searchText = Normalize-Whitespace ((@(
                $row.artist_name
                $row.track_name
                $row.main_genre
                $row.detected_key
            ) -join " "))

            $sectionPreview = Normalize-Whitespace ((@(
                if ($row.verse_nashville) { "Verse: $($row.verse_nashville)" }
                if ($row.chorus_nashville) { "Chorus: $($row.chorus_nashville)" }
                if ($row.bridge_nashville) { "Bridge: $($row.bridge_nashville)" }
                if ($row.intro_nashville) { "Intro: $($row.intro_nashville)" }
                if ($row.outro_nashville) { "Outro: $($row.outro_nashville)" }
            ) -join " | "))

            $artistValue = Escape-JavaScriptString $row.artist_name
            $trackValue = Escape-JavaScriptString $row.track_name
            $yearValue = Escape-JavaScriptString $row.year
            $genreValue = Escape-JavaScriptString $row.main_genre
            $keyValue = Escape-JavaScriptString $row.detected_key
            $songIdValue = Escape-JavaScriptString $row.spotify_song_id
            $artistIdValue = Escape-JavaScriptString $row.spotify_artist_id
            $introValue = Escape-JavaScriptString $row.intro_nashville
            $verseValue = Escape-JavaScriptString $row.verse_nashville
            $chorusValue = Escape-JavaScriptString $row.chorus_nashville
            $bridgeValue = Escape-JavaScriptString $row.bridge_nashville
            $outroValue = Escape-JavaScriptString $row.outro_nashville
            $allNashvilleValue = Escape-JavaScriptString $allNashville
            $sectionPreviewValue = Escape-JavaScriptString $sectionPreview
            $searchTextValue = Escape-JavaScriptString ($searchText.ToLowerInvariant())

            $jsonLine = @(
                "  {"
                "    artist: `"$artistValue`","
                "    track: `"$trackValue`","
                "    year: `"$yearValue`","
                "    genre: `"$genreValue`","
                "    key: `"$keyValue`","
                "    songId: `"$songIdValue`","
                "    artistId: `"$artistIdValue`","
                "    intro: `"$introValue`","
                "    verse: `"$verseValue`","
                "    chorus: `"$chorusValue`","
                "    bridge: `"$bridgeValue`","
                "    outro: `"$outroValue`","
                "    allNashville: `"$allNashvilleValue`","
                "    preview: `"$sectionPreviewValue`","
                "    searchText: `"$searchTextValue`""
                "  }"
            ) -join "`n"

            if (-not $first) {
                $writer.WriteLine(",")
            }
            $writer.Write($jsonLine)
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

Write-Host "Search data written to: $OutputPath"
Write-Host "Rows written: $rowsWritten"
