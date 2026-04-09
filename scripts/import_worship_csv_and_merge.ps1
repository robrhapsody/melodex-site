param(
    [string]$InputPath = "",
    [string]$DatabasePath = "",
    [string]$ParsedOutput = "",
    [string]$SkippedOutput = "",
    [string]$ConflictsOutput = "",
    [string]$QueuePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\raw\worship_songs.csv" }
if (-not $DatabasePath) { $DatabasePath = Join-Path $ProjectRoot "data\processed\melodex_phase1.sqlite" }
if (-not $ParsedOutput) { $ParsedOutput = Join-Path $ProjectRoot "data\processed\worship_csv_parsed_songs.csv" }
if (-not $SkippedOutput) { $SkippedOutput = Join-Path $ProjectRoot "data\review\worship_csv_skipped_missing_fields.csv" }
if (-not $ConflictsOutput) { $ConflictsOutput = Join-Path $ProjectRoot "data\review\worship_csv_detected_conflicts.csv" }
if (-not $QueuePath) { $QueuePath = Join-Path $ProjectRoot "data\review\worship_song_verification_queue_v2.csv" }

$PythonScript = Join-Path $PSScriptRoot "import_worship_csv_and_merge.py"

& python $PythonScript `
    --input $InputPath `
    --db $DatabasePath `
    --parsed-output $ParsedOutput `
    --skipped-output $SkippedOutput `
    --conflicts-output $ConflictsOutput `
    --queue-path $QueuePath
