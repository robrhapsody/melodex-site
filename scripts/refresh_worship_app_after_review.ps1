Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

& (Join-Path $PSScriptRoot "refine_christian_catalog.ps1")
& (Join-Path $PSScriptRoot "build_christian_review_queue.ps1")
& (Join-Path $PSScriptRoot "build_worship_app_data.ps1")
