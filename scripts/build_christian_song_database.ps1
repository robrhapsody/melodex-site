param(
    [string]$SongInputPath = "",
    [string]$ArtistReviewPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $SongInputPath) { $SongInputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_structured.csv" }
if (-not $ArtistReviewPath) { $ArtistReviewPath = Join-Path $ProjectRoot "data\review\christian_artist_review.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\processed\christian_worship_songs.csv" }

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

$includeBuckets = @(
    "christian",
    "worship",
    "gospel",
    "ccm",
    "christian rock",
    "christian pop",
    "southern gospel",
    "include"
)

$artistBuckets = @{}
$artistParser = New-CsvParser -Path $ArtistReviewPath
try {
    $artistHeaders = $artistParser.ReadFields()
    if (-not $artistHeaders) {
        throw "Artist review CSV is empty: $ArtistReviewPath"
    }

    $artistIdIndex = [Array]::IndexOf($artistHeaders, "spotify_artist_id")
    $artistNameIndex = [Array]::IndexOf($artistHeaders, "artist_name")
    $manualBucketIndex = [Array]::IndexOf($artistHeaders, "manual_bucket")
    $suggestedBucketIndex = [Array]::IndexOf($artistHeaders, "suggested_bucket")

    while (-not $artistParser.EndOfData) {
        $fields = $artistParser.ReadFields()
        if (-not $fields) { continue }

        $artistId = if ($artistIdIndex -lt $fields.Count) { $fields[$artistIdIndex] } else { "" }
        $artistName = if ($artistNameIndex -lt $fields.Count) { $fields[$artistNameIndex] } else { "" }
        $manualBucket = if ($manualBucketIndex -lt $fields.Count) { $fields[$manualBucketIndex] } else { "" }
        $suggestedBucket = if ($suggestedBucketIndex -lt $fields.Count) { $fields[$suggestedBucketIndex] } else { "" }

        $bucket = if (-not [string]::IsNullOrWhiteSpace($manualBucket)) { $manualBucket } else { $suggestedBucket }
        if ([string]::IsNullOrWhiteSpace($bucket)) { continue }

        $normalizedBucket = $bucket.Trim().ToLowerInvariant()
        if ($includeBuckets -notcontains $normalizedBucket) { continue }

        $key = if ([string]::IsNullOrWhiteSpace($artistId)) { $artistName } else { $artistId }
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            $artistBuckets[$key] = $normalizedBucket
        }
    }
}
finally {
    $artistParser.Close()
}

$songParser = New-CsvParser -Path $SongInputPath
try {
    $songHeaders = $songParser.ReadFields()
    if (-not $songHeaders) {
        throw "Song CSV is empty: $SongInputPath"
    }

    $artistIdIndex = [Array]::IndexOf($songHeaders, "spotify_artist_id")
    $artistNameIndex = [Array]::IndexOf($songHeaders, "artist_name")

    $writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $outputHeaders = @($songHeaders) + @("christian_bucket")
        $writer.WriteLine(($outputHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")

        $rowsWritten = 0
        while (-not $songParser.EndOfData) {
            $fields = $songParser.ReadFields()
            if (-not $fields) { continue }

            $artistId = if ($artistIdIndex -lt $fields.Count) { $fields[$artistIdIndex] } else { "" }
            $artistName = if ($artistNameIndex -lt $fields.Count) { $fields[$artistNameIndex] } else { "" }
            $key = if ([string]::IsNullOrWhiteSpace($artistId)) { $artistName } else { $artistId }

            if (-not $artistBuckets.ContainsKey($key)) {
                continue
            }

            $line = New-Object System.Collections.Generic.List[string]
            foreach ($field in $fields) {
                $line.Add((ConvertTo-CsvValue $field))
            }
            $line.Add((ConvertTo-CsvValue $artistBuckets[$key]))
            $writer.WriteLine(($line -join ","))
            $rowsWritten++
        }
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $songParser.Close()
}

Write-Host "Christian/Worship song database written to: $OutputPath"
Write-Host "Included artist buckets: $($includeBuckets -join ', ')"
Write-Host "Rows written: $rowsWritten"
