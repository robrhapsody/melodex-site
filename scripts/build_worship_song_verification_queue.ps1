param(
    [string]$DatabasePath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $DatabasePath) { $DatabasePath = Join-Path $ProjectRoot "data\processed\melodex_phase1.sqlite" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "data\review\worship_song_verification_queue.csv" }

$PythonScript = Join-Path $PSScriptRoot "build_worship_song_verification_queue.py"

& python $PythonScript --db $DatabasePath --output $OutputPath
