Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "apps\worship-progressions-app-experimental\start-worship-app-experimental.ps1"

if (-not (Test-Path $scriptPath)) {
    throw "Could not find starter script: $scriptPath"
}

& $scriptPath -UseSupabase
