[CmdletBinding()]
param(
    [string]$Python = "py -3.11",
    [string]$OutputRoot = "dist"
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildDir = Join-Path $projectDir "build"
$venvDir = Join-Path $buildDir "portable-venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$distDir = Join-Path $projectDir $OutputRoot
$workDir = Join-Path $buildDir "pyinstaller"
$specDir = Join-Path $buildDir "spec"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    $parts = $Python -split " ", 2
    if ($parts.Count -eq 2) {
        & $parts[0] $parts[1] -m venv $venvDir
    } else {
        & $parts[0] -m venv $venvDir
    }
}

& $pythonExe -m pip install --disable-pip-version-check -r (Join-Path $projectDir "requirements.txt") "pyinstaller==6.22.2"

& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name "PickupCodeOCR" `
    --distpath $distDir `
    --workpath $workDir `
    --specpath $specDir `
    --collect-all rapidocr `
    --collect-all onnxruntime `
    --collect-all cv2 `
    (Join-Path $projectDir "pickup_code_ocr.py")

Write-Host "Portable build created at: $(Join-Path $distDir 'PickupCodeOCR')"
