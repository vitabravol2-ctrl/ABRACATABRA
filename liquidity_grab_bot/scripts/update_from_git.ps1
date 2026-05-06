$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$envBackup = Join-Path $Root '.env.backup'
$envFile = Join-Path $Root '.env'

try {
    if (Test-Path $envFile) {
        Copy-Item -Force $envFile $envBackup
    }

    git fetch --all
    git reset --hard origin/main
    git clean -fd -e .env -e .env.backup

    if (Test-Path $envBackup) {
        Copy-Item -Force $envBackup $envFile
        Remove-Item -Force $envBackup
    }

    Write-Host 'UPDATED'
} catch {
    Write-Error "Update failed: $($_.Exception.Message)"
    if (Test-Path $envBackup) {
        Copy-Item -Force $envBackup $envFile
        Remove-Item -Force $envBackup
    }
    exit 1
}
