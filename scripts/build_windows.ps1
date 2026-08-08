param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "The Windows executable must be built on Windows."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Create it with: python -m venv .venv"
}

Push-Location $projectRoot
try {
    & $python -m pip install --requirement requirements-build.lock
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install build dependencies."
    }

    if (-not $SkipTests) {
        & $python -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed; executable was not built."
        }
        & $python -m ruff check .
        if ($LASTEXITCODE -ne 0) {
            throw "Ruff check failed; executable was not built."
        }
    }

    & $python -m PyInstaller --noconfirm --clean packaging\DocOpsAgent.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    $artifact = Join-Path $projectRoot "dist\DocOpsAgent.exe"
    if (-not (Test-Path -LiteralPath $artifact)) {
        throw "Build completed without producing dist\DocOpsAgent.exe."
    }
    Get-Item -LiteralPath $artifact | Select-Object FullName, Length, LastWriteTime
}
finally {
    Pop-Location
}
