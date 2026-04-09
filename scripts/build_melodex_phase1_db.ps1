param(
    [string]$InputPath = "",
    [string]$SchemaPath = "",
    [string]$OutputPath = "",
    [string]$BroadCatalogPath = "",
    [string]$WorshipCatalogPath = "",
    [string]$ReviewQueuePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\merged_spotify_chords.csv" }
if (-not $SchemaPath) { $SchemaPath = Join-Path $ProjectRoot "docs\melodex-schema.sql" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\processed\melodex_phase1.sqlite" }
if (-not $BroadCatalogPath) { $BroadCatalogPath = Join-Path $ProjectRoot "data\processed\christian_worship_songs_refined.csv" }
if (-not $WorshipCatalogPath) { $WorshipCatalogPath = Join-Path $ProjectRoot "data\processed\worship_songs_strict.csv" }
if (-not $ReviewQueuePath) {
    $ReviewQueuePath = Join-Path $ProjectRoot "data\review\worship_song_verification_queue_v2.csv"
    if (-not (Test-Path $ReviewQueuePath)) {
        $ReviewQueuePath = Join-Path $ProjectRoot "data\review\worship_song_verification_queue.csv"
    }
}

$PythonScript = Join-Path $PSScriptRoot "build_melodex_phase1_db.py"

& python $PythonScript --input $InputPath --schema $SchemaPath --output $OutputPath --broad-catalog $BroadCatalogPath --worship-catalog $WorshipCatalogPath --review-queue $ReviewQueuePath
