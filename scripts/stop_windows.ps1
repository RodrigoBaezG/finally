# scripts/stop_windows.ps1 - Stop and remove the FinAlly container on Windows.
# The 'finally-data' volume is NOT removed so the SQLite DB persists.
# Idempotent: safe to run when container is already stopped/absent.

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ContainerName = "finally"

$existingContainer = (docker ps -a --filter "name=^${ContainerName}$" --format "{{.Names}}" | Out-String).Trim()

if ($existingContainer -eq $ContainerName) {
    Write-Host "Stopping container '$ContainerName' ..."
    cmd.exe /c "docker stop $ContainerName >nul 2>&1"

    Write-Host "Removing container '$ContainerName' ..."
    cmd.exe /c "docker rm $ContainerName >nul 2>&1"

    Write-Host "Container stopped and removed."
    Write-Host "(Volume 'finally-data' was kept - your data is safe.)"
} else {
    Write-Host "No container named '$ContainerName' found. Nothing to do."
}
