param(
    [string]$InputPath = "",
    [string]$OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $InputPath) { $InputPath = Join-Path $ProjectRoot "data\processed\worship_songs_strict.csv" }
if (-not $OutputPath) { $OutputPath = Join-Path $ProjectRoot "apps\worship-progressions-app\data.js" }

& (Join-Path $PSScriptRoot "build_song_search_data.ps1") -InputPath $InputPath -OutputPath $OutputPath
