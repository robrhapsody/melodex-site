param(
    [string]$ArtistInputPath = "",
    [string]$SongInputPath = "",
    [string]$ArtistOutputPath = "",
    [string]$BroadSongOutputPath = "",
    [string]$WorshipSongOutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $ArtistInputPath) { $ArtistInputPath = Join-Path $ProjectRoot "data\review\christian_artist_review_enriched.csv" }
if (-not $SongInputPath) { $SongInputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_structured.csv" }
if (-not $ArtistOutputPath) { $ArtistOutputPath = Join-Path $ProjectRoot "data\review\christian_artist_review_refined.csv" }
if (-not $BroadSongOutputPath) { $BroadSongOutputPath = Join-Path $ProjectRoot "data\processed\christian_worship_songs_refined.csv" }
if (-not $WorshipSongOutputPath) { $WorshipSongOutputPath = Join-Path $ProjectRoot "data\processed\worship_songs_strict.csv" }

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

function Get-TagList {
    param([string]$TagText)
    if ([string]::IsNullOrWhiteSpace($TagText)) {
        return @()
    }

    return @($TagText.Split('|') | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
}

function Get-ArtistDecision {
    param(
        [string[]]$Tags,
        [string]$SampleGenre,
        [string]$ManualBucket
    )

    $worshipTags = @(
        "worship",
        "praise and worship",
        "praise & worship",
        "contemporary worship"
    )
    $gospelTags = @(
        "gospel",
        "contemporary gospel",
        "southern gospel",
        "black gospel",
        "brazilian gospel"
    )
    $christianStrongTags = @(
        "christian rock",
        "contemporary christian",
        "christian pop",
        "christian metal",
        "christian hip hop",
        "ccm",
        "christian alternative rock"
    )
    $christianWeakTags = @(
        "christian"
    )

    if (-not [string]::IsNullOrWhiteSpace($ManualBucket)) {
        return [pscustomobject]@{
            Bucket = $ManualBucket.Trim().ToLowerInvariant()
            Confidence = "manual"
            Reason = "manual_bucket"
        }
    }

    $tagSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($tag in $Tags) { [void]$tagSet.Add($tag) }
    $sampleGenreText = if ($null -eq $SampleGenre) { "" } else { $SampleGenre.Trim().ToLowerInvariant() }

    $worshipHits = @($Tags | Where-Object { $worshipTags -contains $_ })
    $gospelHits = @($Tags | Where-Object { $gospelTags -contains $_ })
    $christianStrongHits = @($Tags | Where-Object { $christianStrongTags -contains $_ })
    $christianWeakHits = @($Tags | Where-Object { $christianWeakTags -contains $_ })

    if ($worshipHits.Count -gt 0) {
        return [pscustomobject]@{
            Bucket = "worship"
            Confidence = "high"
            Reason = ($worshipHits -join " | ")
        }
    }

    if ($gospelHits.Count -gt 0) {
        return [pscustomobject]@{
            Bucket = "gospel"
            Confidence = "high"
            Reason = ($gospelHits -join " | ")
        }
    }

    if ($christianStrongHits.Count -gt 0) {
        return [pscustomobject]@{
            Bucket = "christian"
            Confidence = "high"
            Reason = ($christianStrongHits -join " | ")
        }
    }

    if ($christianWeakHits.Count -gt 0) {
        if ($sampleGenreText -match '^(rock|metal|pop|country|soul|alternative|rap|folk|jazz)$') {
            return [pscustomobject]@{
                Bucket = "christian"
                Confidence = "medium"
                Reason = "christian tag plus sample genre"
            }
        }

        if ($Tags.Count -ge 2) {
            return [pscustomobject]@{
                Bucket = "christian"
                Confidence = "medium"
                Reason = "christian tag in lastfm tags"
            }
        }
    }

    return [pscustomobject]@{
        Bucket = ""
        Confidence = ""
        Reason = ""
    }
}

function Read-CsvRows {
    param([string]$Path)
    $parser = New-CsvParser -Path $Path
    try {
        $headers = $parser.ReadFields()
        if (-not $headers) {
            throw "CSV is empty: $Path"
        }

        $rows = New-Object System.Collections.Generic.List[object]
        while (-not $parser.EndOfData) {
            $fields = $parser.ReadFields()
            if (-not $fields) { continue }

            $row = [ordered]@{}
            for ($i = 0; $i -lt $headers.Count; $i++) {
                $row[$headers[$i]] = if ($i -lt $fields.Count) { $fields[$i] } else { "" }
            }
            $rows.Add([pscustomobject]$row)
        }

        return [pscustomobject]@{
            Headers = $headers
            Rows = $rows
        }
    }
    finally {
        $parser.Close()
    }
}

$artistData = Read-CsvRows -Path $ArtistInputPath
$artistHeaders = @($artistData.Headers)
$artistRows = $artistData.Rows

$newArtistColumns = @("refined_bucket", "refined_confidence", "refined_reason")
foreach ($row in $artistRows) {
    foreach ($column in $newArtistColumns) {
        if (-not ($row.PSObject.Properties.Name -contains $column)) {
            Add-Member -InputObject $row -NotePropertyName $column -NotePropertyValue ""
        }
    }

    $decision = Get-ArtistDecision -Tags (Get-TagList $row.lastfm_top_tags) -SampleGenre ([string]$row.sample_genre) -ManualBucket ([string]$row.manual_bucket)
    $row.refined_bucket = $decision.Bucket
    $row.refined_confidence = $decision.Confidence
    $row.refined_reason = $decision.Reason
}

foreach ($column in $newArtistColumns) {
    if ($artistHeaders -notcontains $column) {
        $artistHeaders += $column
    }
}

$artistWriter = [System.IO.StreamWriter]::new($ArtistOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $artistWriter.WriteLine(($artistHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")
    foreach ($row in $artistRows) {
        $line = foreach ($header in $artistHeaders) { ConvertTo-CsvValue $row.$header }
        $artistWriter.WriteLine(($line -join ","))
    }
}
finally {
    $artistWriter.Dispose()
}

$broadArtistBuckets = @{}
$worshipArtistBuckets = @{}
foreach ($row in $artistRows) {
    $bucket = [string]$row.refined_bucket
    if ([string]::IsNullOrWhiteSpace($bucket)) { continue }

    $artistKey = if ([string]::IsNullOrWhiteSpace([string]$row.spotify_artist_id)) { [string]$row.artist_name } else { [string]$row.spotify_artist_id }
    if ([string]::IsNullOrWhiteSpace($artistKey)) { continue }

    if (@("christian", "gospel", "worship", "ccm", "southern gospel") -contains $bucket) {
        $broadArtistBuckets[$artistKey] = $bucket
    }
    if ($bucket -eq "worship") {
        $worshipArtistBuckets[$artistKey] = $bucket
    }
}

$songParser = New-CsvParser -Path $SongInputPath
try {
    $songHeaders = $songParser.ReadFields()
    if (-not $songHeaders) {
        throw "Song CSV is empty: $SongInputPath"
    }

    $artistIdIndex = [Array]::IndexOf($songHeaders, "spotify_artist_id")
    $artistNameIndex = [Array]::IndexOf($songHeaders, "artist_name")

    $broadWriter = [System.IO.StreamWriter]::new($BroadSongOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    $worshipWriter = [System.IO.StreamWriter]::new($WorshipSongOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $outputHeaders = @($songHeaders) + @("christian_bucket")
        $headerLine = ($outputHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ","
        $broadWriter.WriteLine($headerLine)
        $worshipWriter.WriteLine($headerLine)

        $broadRowsWritten = 0
        $worshipRowsWritten = 0

        while (-not $songParser.EndOfData) {
            $fields = $songParser.ReadFields()
            if (-not $fields) { continue }

            $artistId = if ($artistIdIndex -lt $fields.Count) { $fields[$artistIdIndex] } else { "" }
            $artistName = if ($artistNameIndex -lt $fields.Count) { $fields[$artistNameIndex] } else { "" }
            $artistKey = if ([string]::IsNullOrWhiteSpace($artistId)) { $artistName } else { $artistId }
            if ([string]::IsNullOrWhiteSpace($artistKey)) { continue }

            if ($broadArtistBuckets.ContainsKey($artistKey)) {
                $line = New-Object System.Collections.Generic.List[string]
                foreach ($field in $fields) {
                    $line.Add((ConvertTo-CsvValue $field))
                }
                $line.Add((ConvertTo-CsvValue $broadArtistBuckets[$artistKey]))
                $broadWriter.WriteLine(($line -join ","))
                $broadRowsWritten++
            }

            if ($worshipArtistBuckets.ContainsKey($artistKey)) {
                $line = New-Object System.Collections.Generic.List[string]
                foreach ($field in $fields) {
                    $line.Add((ConvertTo-CsvValue $field))
                }
                $line.Add((ConvertTo-CsvValue $worshipArtistBuckets[$artistKey]))
                $worshipWriter.WriteLine(($line -join ","))
                $worshipRowsWritten++
            }
        }
    }
    finally {
        $broadWriter.Dispose()
        $worshipWriter.Dispose()
    }
}
finally {
    $songParser.Close()
}

Write-Host "Refined artist review written to: $ArtistOutputPath"
Write-Host "Refined broad Christian/Worship songs written to: $BroadSongOutputPath"
Write-Host "Strict worship-only songs written to: $WorshipSongOutputPath"
Write-Host "Broad rows written: $broadRowsWritten"
Write-Host "Worship-only rows written: $worshipRowsWritten"
