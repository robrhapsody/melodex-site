param([ValidateRange(1024, 65535)][int]$Port = 3001)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'apps\worship-progressions-app-experimental\start-worship-app-experimental.ps1') -Port $Port
