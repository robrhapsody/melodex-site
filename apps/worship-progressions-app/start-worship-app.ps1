$nodePath = "C:\Program Files\nodejs\node.exe"
$appPath = $PSScriptRoot

if (-not (Test-Path $nodePath)) {
    throw "Node.js was not found at $nodePath"
}

Push-Location $appPath
try {
    Write-Host "Starting Worship Progression Finder at http://localhost:3000"
    & $nodePath "server.js"
}
finally {
    Pop-Location
}
