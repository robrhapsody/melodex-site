param([ValidateRange(1024, 65535)][int]$Port = 3001)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Flowset needs Node.js 24. Install it, then run this shortcut again.'
}
if ((& node -p "process.versions.node.split('.')[0]") -ne '24') {
    throw 'Flowset uses Node.js 24, matching the hosted app. Please use that version.'
}
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path 'node_modules/vercel/dist/vc.js')) {
        Write-Host "Installing Flowset's development tools from the saved dependency list..."
        & npm.cmd ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the message above.' }
    }
    Write-Host "Starting Flowset at http://localhost:$Port using the website's JavaScript API."
    Write-Host 'Leave this window open. Press Ctrl+C to stop.'
    & node 'node_modules/vercel/dist/vc.js' dev --listen "127.0.0.1:$Port"
    if ($LASTEXITCODE -ne 0) {
        throw "Flowset did not start. If Vercel reports an expired login, run 'node node_modules/vercel/dist/vc.js login' from this app folder, then try again."
    }
}
finally { Pop-Location }
