param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\review\christian_artist_review_refined.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\review\christian_artist_review_queue.csv" }

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

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $InputPath"
    }

    $rows = New-Object System.Collections.Generic.List[object]
    while (-not $parser.EndOfData) {
        $fields = $parser.ReadFields()
        if (-not $fields) { continue }

        $row = [ordered]@{}
        for ($i = 0; $i -lt $headers.Count; $i++) {
            $row[$headers[$i]] = if ($i -lt $fields.Count) { $fields[$i] } else { "" }
        }

        if ($row.refined_confidence -ne "medium") {
            continue
        }

        $rows.Add([pscustomobject]$row)
    }
}
finally {
    $parser.Close()
}

$outputHeaders = @(
    "artist_name",
    "spotify_artist_id",
    "sample_genre",
    "song_count",
    "lastfm_top_tags",
    "refined_bucket",
    "refined_confidence",
    "refined_reason",
    "manual_bucket",
    "notes"
)

$writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $writer.WriteLine(($outputHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")
    foreach ($row in ($rows | Sort-Object refined_bucket, artist_name)) {
        $line = foreach ($header in $outputHeaders) {
            ConvertTo-CsvValue $row.$header
        }
        $writer.WriteLine(($line -join ","))
    }
}
finally {
    $writer.Dispose()
}

Write-Host "Christian review queue written to: $OutputPath"
Write-Host "Rows written: $($rows.Count)"
