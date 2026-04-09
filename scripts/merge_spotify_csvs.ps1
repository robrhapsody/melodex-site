param(
    [string]$MetadataPath = "",
    [string]$ChordPath = "",
    [string]$OutputPath = "",
    [string]$SlimOutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $MetadataPath) { $MetadataPath = Join-Path $ProjectRoot "data\raw\spotify_metadata.csv" }
if (-not $ChordPath) { $ChordPath = Join-Path $ProjectRoot "data\raw\chordonomicon.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords.csv" }
if (-not $SlimOutputPath) { $SlimOutputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_slim.csv" }

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

$metadataParser = New-CsvParser -Path $MetadataPath
try {
    $metadataHeaders = $metadataParser.ReadFields()
    if (-not $metadataHeaders) {
        throw "Metadata CSV is empty: $MetadataPath"
    }

    $metadataKey = "track_id"
    $metadataKeyIndex = [Array]::IndexOf($metadataHeaders, $metadataKey)
    if ($metadataKeyIndex -lt 0) {
        throw "Could not find '$metadataKey' in metadata CSV."
    }

    $metadataFieldSpecs = for ($i = 0; $i -lt $metadataHeaders.Count; $i++) {
        $header = $metadataHeaders[$i]
        if ([string]::IsNullOrWhiteSpace($header)) {
            continue
        }
        if ($header -eq $metadataKey) {
            continue
        }

        [pscustomobject]@{
            Index = $i
            Name = $header
        }
    }

    $metadataByTrackId = @{}
    $metadataRowCount = 0
    $duplicateMetadataIds = 0

    while (-not $metadataParser.EndOfData) {
        $fields = $metadataParser.ReadFields()
        if (-not $fields) {
            continue
        }

        $metadataRowCount++
        $trackId = $fields[$metadataKeyIndex]
        if ([string]::IsNullOrWhiteSpace($trackId)) {
            continue
        }

        $rowData = @{}
        foreach ($spec in $metadataFieldSpecs) {
            $rowData[$spec.Name] = if ($spec.Index -lt $fields.Count) { $fields[$spec.Index] } else { "" }
        }

        if ($metadataByTrackId.ContainsKey($trackId)) {
            $duplicateMetadataIds++
            continue
        }

        $metadataByTrackId[$trackId] = $rowData
    }
}
finally {
    $metadataParser.Close()
}

$chordParser = New-CsvParser -Path $ChordPath
try {
    $chordHeaders = $chordParser.ReadFields()
    if (-not $chordHeaders) {
        throw "Chord CSV is empty: $ChordPath"
    }

    $chordKey = "spotify_song_id"
    $chordKeyIndex = [Array]::IndexOf($chordHeaders, $chordKey)
    if ($chordKeyIndex -lt 0) {
        throw "Could not find '$chordKey' in chord CSV."
    }

    $outputHeaders = @($chordHeaders) + @($metadataFieldSpecs.Name)
    $writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine(($outputHeaders | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")

        $chordRowCount = 0
        $matchedRowCount = 0
        $unmatchedRowCount = 0

        while (-not $chordParser.EndOfData) {
            $fields = $chordParser.ReadFields()
            if (-not $fields) {
                continue
            }

            $chordRowCount++
            $spotifySongId = $fields[$chordKeyIndex]

            if ([string]::IsNullOrWhiteSpace($spotifySongId) -or -not $metadataByTrackId.ContainsKey($spotifySongId)) {
                $unmatchedRowCount++
                continue
            }

            $matchedRowCount++
            $metadataRow = $metadataByTrackId[$spotifySongId]

            $combinedValues = New-Object System.Collections.Generic.List[string]
            foreach ($value in $fields) {
                $combinedValues.Add((ConvertTo-CsvValue $value))
            }
            foreach ($name in $metadataFieldSpecs.Name) {
                $combinedValues.Add((ConvertTo-CsvValue $metadataRow[$name]))
            }

            $writer.WriteLine(($combinedValues -join ","))
        }
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $chordParser.Close()
}

Write-Host "Merged file written to: $OutputPath"
Write-Host "Metadata rows read: $metadataRowCount"
Write-Host "Chord rows read: $chordRowCount"
Write-Host "Matched rows written: $matchedRowCount"
Write-Host "Unmatched chord rows skipped: $unmatchedRowCount"
Write-Host "Duplicate metadata track IDs skipped: $duplicateMetadataIds"

$slimColumns = @(
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "chords",
    "spotify_song_id",
    "spotify_artist_id"
)

$fullParser = New-CsvParser -Path $OutputPath
try {
    $fullHeaders = $fullParser.ReadFields()
    if (-not $fullHeaders) {
        throw "Merged CSV is empty: $OutputPath"
    }

    $slimIndexes = foreach ($column in $slimColumns) {
        $index = [Array]::IndexOf($fullHeaders, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in merged CSV."
        }

        $index
    }

    $slimWriter = [System.IO.StreamWriter]::new($SlimOutputPath, $false, [System.Text.UTF8Encoding]::new($false))
    try {
        $slimWriter.WriteLine(($slimColumns | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")

        $slimRowCount = 0
        while (-not $fullParser.EndOfData) {
            $fields = $fullParser.ReadFields()
            if (-not $fields) {
                continue
            }

            $slimRowCount++
            $row = foreach ($index in $slimIndexes) {
                if ($index -lt $fields.Count) {
                    ConvertTo-CsvValue $fields[$index]
                }
                else {
                    ""
                }
            }

            $slimWriter.WriteLine(($row -join ","))
        }
    }
    finally {
        $slimWriter.Dispose()
    }
}
finally {
    $fullParser.Close()
}

Write-Host "Slim file written to: $SlimOutputPath"
Write-Host "Slim rows written: $slimRowCount"
