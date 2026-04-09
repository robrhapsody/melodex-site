param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName Microsoft.VisualBasic

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords_slim.csv" }

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

$columns = @(
    "artist_name",
    "track_name",
    "year",
    "main_genre",
    "chords",
    "spotify_song_id",
    "spotify_artist_id"
)

$parser = New-CsvParser -Path $InputPath
try {
    $headers = $parser.ReadFields()
    if (-not $headers) {
        throw "Input CSV is empty: $InputPath"
    }

    $indexes = foreach ($column in $columns) {
        $index = [Array]::IndexOf($headers, $column)
        if ($index -lt 0) {
            throw "Could not find '$column' in input CSV."
        }

        $index
    }

    $rows = New-Object System.Collections.Generic.List[object]
    while (-not $parser.EndOfData) {
        $fields = $parser.ReadFields()
        if (-not $fields) {
            continue
        }

        $row = [ordered]@{}
        foreach ($i in 0..($columns.Count - 1)) {
            $index = $indexes[$i]
            $row[$columns[$i]] = if ($index -lt $fields.Count) { $fields[$index] } else { "" }
        }

        $rows.Add([pscustomobject]$row)
    }
}
finally {
    $parser.Close()
}

$writer = [System.IO.StreamWriter]::new($OutputPath, $false, [System.Text.UTF8Encoding]::new($false))
try {
    $writer.WriteLine(($columns | ForEach-Object { ConvertTo-CsvValue $_ }) -join ",")

    $rowsWritten = 0
    foreach ($row in ($rows.ToArray() | Sort-Object artist_name, track_name, spotify_song_id)) {
        $line = foreach ($column in $columns) {
            ConvertTo-CsvValue $row.$column
        }

        $writer.WriteLine(($line -join ","))
        $rowsWritten++
    }
}
finally {
    $writer.Dispose()
}

Write-Host "Slim file written to: $OutputPath"
Write-Host "Rows written: $rowsWritten"
