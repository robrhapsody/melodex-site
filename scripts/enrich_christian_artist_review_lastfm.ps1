param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKey,
    [string]$InputPath = "",
    [string]$OutputPath = "",
    [int]$StartIndex = 0,
    [int]$Limit = 250,
    [int]$DelayMilliseconds = 250
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\review\christian_artist_review.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\review\christian_artist_review_enriched.csv" }

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

function Get-LastFmUrl {
    param(
        [string]$ArtistName,
        [string]$ApiKey
    )

    $encodedArtist = [System.Uri]::EscapeDataString($ArtistName)
    return "https://ws.audioscrobbler.com/2.0/?method=artist.gettoptags&artist=$encodedArtist&autocorrect=1&api_key=$ApiKey&format=json"
}

function Classify-ChristianBucket {
    param(
        [string[]]$Tags
    )

    $normalizedTags = $Tags | ForEach-Object { $_.ToLowerInvariant() }

    $strongInclude = @(
        "worship",
        "christian",
        "ccm",
        "contemporary christian",
        "christian pop",
        "christian rock",
        "christian hip hop",
        "gospel",
        "southern gospel",
        "praise and worship"
    )

    foreach ($tag in $normalizedTags) {
        if ($strongInclude -contains $tag) {
            return $tag
        }
    }

    foreach ($tag in $normalizedTags) {
        if ($tag -like "*christian*" -or $tag -like "*worship*" -or $tag -like "*gospel*") {
            return $tag
        }
    }

    return ""
}

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Artist review CSV is empty: $InputPath"
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
}
finally {
    $parser.Close()
}

$newColumns = @("lastfm_top_tags", "lastfm_christian_signal", "lastfm_suggested_bucket", "lastfm_lookup_status")
foreach ($column in $newColumns) {
    if ($headers -notcontains $column) {
        $headers += $column
    }
}

foreach ($row in $rows) {
    foreach ($column in $newColumns) {
        if (-not ($row.PSObject.Properties.Name -contains $column)) {
            Add-Member -InputObject $row -NotePropertyName $column -NotePropertyValue ""
        }
    }
}

$endIndex = [Math]::Min($rows.Count, $StartIndex + $Limit)
for ($i = $StartIndex; $i -lt $endIndex; $i++) {
    $row = $rows[$i]
    $artistName = [string]$row.artist_name
    if ([string]::IsNullOrWhiteSpace($artistName)) {
        continue
    }

    try {
        $url = Get-LastFmUrl -ArtistName $artistName -ApiKey $ApiKey
        $response = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 30
        $tags = @()
        if ($response.toptags.tag) {
            foreach ($tag in $response.toptags.tag) {
                if ($tag.name) {
                    $tags += [string]$tag.name
                }
            }
        }

        $topTags = $tags | Select-Object -First 8
        $signal = Classify-ChristianBucket -Tags $topTags

        $row.lastfm_top_tags = ($topTags -join " | ")
        $row.lastfm_christian_signal = $signal
        $row.lastfm_lookup_status = "ok"

        if ($signal) {
            $row.lastfm_suggested_bucket = if ($signal -like "*worship*") { "worship" } elseif ($signal -like "*gospel*") { "gospel" } else { "christian" }
            if (-not $row.manual_bucket) {
                $row.suggested_bucket = $row.lastfm_suggested_bucket
            }
        }
        else {
            $row.lastfm_suggested_bucket = ""
        }
    }
    catch {
        $row.lastfm_lookup_status = "error"
    }

    Start-Sleep -Milliseconds $DelayMilliseconds
}

$writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $writer.WriteLine(($headers | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")
    foreach ($row in $rows) {
        $line = foreach ($header in $headers) {
            ConvertTo-CsvValue $row.$header
        }
        $writer.WriteLine(($line -join ","))
    }
}
finally {
    $writer.Dispose()
}

Write-Host "Enriched artist review written to: $OutputPath"
Write-Host "Artists processed in this batch: $($endIndex - $StartIndex)"
Write-Host "StartIndex: $StartIndex"
Write-Host "EndIndexExclusive: $endIndex"
