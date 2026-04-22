# scripts/start_windows.ps1 - Build (if needed) and run the FinAlly container on Windows.
# Idempotent: safe to run multiple times.
#
# Usage:
#   .\scripts\start_windows.ps1              # build image if missing, start container
#   .\scripts\start_windows.ps1 -Build       # force a fresh image build before starting
#   .\scripts\start_windows.ps1 -NoBrowser   # suppress automatic browser open
#   .\scripts\start_windows.ps1 -Help        # show usage

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoBrowser,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ImageName     = "finally:latest"
$ContainerName = "finally"
$Port          = 8000
$Url           = "http://localhost:$Port"
$EnvFile       = ".env"

if ($Help) {
    Write-Host "Usage:"
    Write-Host "  .\scripts\start_windows.ps1              # build if missing, start"
    Write-Host "  .\scripts\start_windows.ps1 -Build       # force rebuild"
    Write-Host "  .\scripts\start_windows.ps1 -NoBrowser   # skip opening browser"
    Write-Host "  .\scripts\start_windows.ps1 -Help        # show this help"
    exit 0
}

# Change to project root (parent of the scripts\ folder)
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

# Ensure .env exists
if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env not found."
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example. Edit it to add your OPENROUTER_API_KEY."
    } else {
        Write-Warning "  No .env.example found either. Container will start without env vars."
        $EnvFile = $null
    }
}

# Build image if missing or --Build flag passed.
# We probe via cmd.exe so the stderr redirection happens outside PowerShell - in
# Windows PowerShell 5.1 with $ErrorActionPreference = "Stop", `... 2>$null` on
# a native executable wraps stderr lines as NativeCommandError and aborts.
cmd.exe /c "docker image inspect $ImageName >nul 2>&1"
$imageExists = ($LASTEXITCODE -eq 0)
if ($Build -or -not $imageExists) {
    Write-Host "Building Docker image $ImageName ..."
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed." }
} else {
    Write-Host "Image $ImageName already exists. Skipping build (pass -Build to force)."
}

# Stop and remove any existing container with the same name (idempotency)
$existingContainer = (docker ps -a --filter "name=^${ContainerName}$" --format "{{.Names}}" | Out-String).Trim()
if ($existingContainer -eq $ContainerName) {
    Write-Host "Stopping and removing existing container '$ContainerName' ..."
    cmd.exe /c "docker stop $ContainerName >nul 2>&1"
    cmd.exe /c "docker rm $ContainerName >nul 2>&1"
}

# Build docker run arguments
$dockerArgs = @(
    "run",
    "--detach",
    "--name", $ContainerName,
    "-p", "${Port}:${Port}",
    "-v", "finally-data:/app/db"
)

if ($EnvFile) {
    $dockerArgs += "--env-file", $EnvFile
}

$dockerArgs += $ImageName

Write-Host "Starting container '$ContainerName' ..."
& docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw "docker run failed." }

Write-Host ""
Write-Host "FinAlly is running at: $Url"
Write-Host ""
Write-Host "To stop:  .\scripts\stop_windows.ps1"
Write-Host "To logs:  docker logs -f $ContainerName"

# Open browser
if (-not $NoBrowser) {
    Start-Sleep -Seconds 2
    Start-Process $Url
}
