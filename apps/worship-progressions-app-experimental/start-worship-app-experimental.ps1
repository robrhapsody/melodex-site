param(
    [switch]$UseSupabase = $false,
    [string]$SupabaseUrl = ""
)

$pythonCommand = "python"
$appPath = $PSScriptRoot
$projectRoot = Split-Path -Path (Split-Path -Path $PSScriptRoot -Parent) -Parent
$databasePath = Join-Path $projectRoot "data\processed\melodex_phase1.sqlite"
$buildDatabaseScriptPath = Join-Path $projectRoot "scripts\build_melodex_phase1_db.ps1"

if (-not (Get-Command $pythonCommand -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH."
}

if (-not (Test-Path $databasePath)) {
    if (-not (Test-Path $buildDatabaseScriptPath)) {
        throw "The Melodex database build script was not found at $buildDatabaseScriptPath"
    }

    Write-Host "Melodex database not found. Building it now..."
    & $buildDatabaseScriptPath
}

Push-Location $appPath
try {
    Write-Host "Starting Melodex Progression Lab at http://localhost:3001"
    $token = $env:SUPABASE_SERVICE_ROLE_KEY
    if (-not $token) { $token = $env:SUPABASE_MCP_TOKEN }
    if (-not $SupabaseUrl) { $SupabaseUrl = $env:SUPABASE_URL }

    if ($UseSupabase) {
        if (-not $SupabaseUrl) {
            throw "UseSupabase was requested, but no Supabase URL was provided. Pass -SupabaseUrl or set SUPABASE_URL."
        }
        if (-not $token) {
            throw "UseSupabase was requested, but no service token was found. Set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_MCP_TOKEN."
        }
        & $pythonCommand "-u" "server.py" "--supabase-url" $SupabaseUrl "--supabase-service-key" $token
    }
    else {
        & $pythonCommand "-u" "server.py"
    }
}
finally {
    Pop-Location
}
