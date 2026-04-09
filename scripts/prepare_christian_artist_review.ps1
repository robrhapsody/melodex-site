param(
    [string]$InputPath = "",
    [string]$ArtistOutputPath = "",
    [string]$SongOutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_structured.csv" }
if (-not $ArtistOutputPath) { $ArtistOutputPath = Join-Path $ProjectRoot "data\review\christian_artist_review.csv" }
if (-not $SongOutputPath) { $SongOutputPath = Join-Path $ProjectRoot "data\processed\christian_song_candidates.csv" }

function New-CsvParser {
    param([Parameter(Mandatory = $true)][string]$Path)
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($Path)
    $parser.TextFieldType = [Microsoft.VisualBasic.FileIO.FieldType]::Delimited
    $parser.SetDelimiters(",")
    $parser.HasFieldsEnclosedInQuotes = $true
    return $parser
}

function ConvertTo-CsvValue {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return "" }
    $text = [string]$Value
    if ($text.IndexOfAny([char[]]@(',', '"', "`r", "`n")) -ge 0) {
        return '"' + ($text -replace '"', '""') + '"'
    }
    return $text
}

function Get-ChristianSignal {
    param(
        [string]$ArtistName,
        [string]$Genre
    )

    $text = ("$ArtistName $Genre").ToLowerInvariant()
    $keywords = @(
        "christian",
        "worship",
        "gospel",
        "ccm",
        "praise",
        "hymn",
        "hymns",
        "southern gospel",
        "contemporary christian"
    )

    foreach ($keyword in $keywords) {
        if ($text.Contains($keyword)) {
            return $keyword
        }
    }

    return ""
}

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $InputPath"
    }

    $requiredColumns = @("artist_name", "main_genre", "spotify_artist_id", "track_name", "spotify_song_id", "year")
    $indexes = @{}
    foreach ($column in $requiredColumns) {
        $index = [Array]::IndexOf($headers, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in input CSV."
        }
        $indexes[$column] = $index
    }

    $artists = @{}
    $songCandidates = New-Object System.Collections.Generic.List[object]

    while (-not $parser.EndOfData) {
        $fields = $parser.ReadFields()
        if (-not $fields) { continue }

        $artistName = if ($indexes.artist_name -lt $fields.Count) { $fields[$indexes.artist_name] } else { "" }
        $mainGenre = if ($indexes.main_genre -lt $fields.Count) { $fields[$indexes.main_genre] } else { "" }
        $artistId = if ($indexes.spotify_artist_id -lt $fields.Count) { $fields[$indexes.spotify_artist_id] } else { "" }
        $trackName = if ($indexes.track_name -lt $fields.Count) { $fields[$indexes.track_name] } else { "" }
        $songId = if ($indexes.spotify_song_id -lt $fields.Count) { $fields[$indexes.spotify_song_id] } else { "" }
        $year = if ($indexes.year -lt $fields.Count) { $fields[$indexes.year] } else { "" }

        if ([string]::IsNullOrWhiteSpace($artistName)) { continue }

        $artistKey = if ([string]::IsNullOrWhiteSpace($artistId)) { $artistName } else { $artistId }
        $signal = Get-ChristianSignal -ArtistName $artistName -Genre $mainGenre

        if (-not $artists.ContainsKey($artistKey)) {
            $artists[$artistKey] = [ordered]@{
                artist_name = $artistName
                spotify_artist_id = $artistId
                sample_genre = $mainGenre
                christian_signal = $signal
                suggested_bucket = if ($signal) { "candidate" } else { "review" }
                manual_bucket = ""
                notes = ""
                song_count = 0
            }
        }

        $artists[$artistKey].song_count++

        if ($signal) {
            $songCandidates.Add([pscustomobject]@{
                artist_name = $artistName
                track_name = $trackName
                year = $year
                main_genre = $mainGenre
                spotify_song_id = $songId
                spotify_artist_id = $artistId
                christian_signal = $signal
            })
        }
    }
}
finally {
    $parser.Close()
}

$artistWriter = [System.IO.StreamWriter]::new($ArtistOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $artistHeaders = @("artist_name", "spotify_artist_id", "sample_genre", "christian_signal", "suggested_bucket", "manual_bucket", "notes", "song_count")
    $artistWriter.WriteLine(($artistHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")
    foreach ($artist in ($artists.Values | Sort-Object artist_name)) {
        $line = foreach ($header in $artistHeaders) { ConvertTo-CsvValue $artist[$header] }
        $artistWriter.WriteLine(($line -join ","))
    }
}
finally {
    $artistWriter.Dispose()
}

$songWriter = [System.IO.StreamWriter]::new($SongOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $songHeaders = @("artist_name", "track_name", "year", "main_genre", "spotify_song_id", "spotify_artist_id", "christian_signal")
    $songWriter.WriteLine(($songHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")
    foreach ($song in ($songCandidates | Sort-Object artist_name, track_name)) {
        $line = foreach ($header in $songHeaders) { ConvertTo-CsvValue $song.$header }
        $songWriter.WriteLine(($line -join ","))
    }
}
finally {
    $songWriter.Dispose()
}

Write-Host "Artist review file written to: $ArtistOutputPath"
Write-Host "Song candidate file written to: $SongOutputPath"
Write-Host "Unique artists: $($artists.Count)"
Write-Host "Keyword-based candidate songs: $($songCandidates.Count)"
