param(
    [string]$DatabasePath = "",
    [string]$OutputDir = "",
    [ValidateSet("worship_and_broad","worship","all")]
    [string]$Scope = "worship_and_broad"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Path $PSScriptRoot -Parent
if (-not $DatabasePath) { $DatabasePath = Join-Path $ProjectRoot "data\processed\melodex_phase1.sqlite" }
if (-not $OutputDir) { $OutputDir = Join-Path $ProjectRoot "data\processed\supabase_import_bundle" }

$PythonScript = Join-Path $PSScriptRoot "export_supabase_import_bundle.py"

& python $PythonScript --db $DatabasePath --output-dir $OutputDir --scope $Scope
