$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Use a predictable, supported Python version for InsightFace/ONNX packaging.
py -3.11 --version
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.11 is required. Install Python 3.11 x64 and the Python Launcher."
}

if (Test-Path ".venv") { Remove-Item ".venv" -Recurse -Force }
if (Test-Path "backend-dist") { Remove-Item "backend-dist" -Recurse -Force }
py -3.11 -m venv .venv

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip wheel setuptools
& $VenvPython -m pip install "Cython<3"
& $VenvPython -m pip install -r backend\requirements.txt pyinstaller

& $VenvPython -m PyInstaller --noconfirm --clean --onedir `
    --name FaceSearchBackend `
    --paths backend `
    --hidden-import app.main `
    --collect-submodules app `
    --collect-all insightface `
    --collect-all onnxruntime `
    --collect-all cv2 `
    --collect-all skimage `
    --add-data "config\config.yaml;config" `
    --distpath backend-dist `
    backend\run_backend.py

$Nested = "backend-dist\FaceSearchBackend"
if (!(Test-Path (Join-Path $Nested "FaceSearchBackend.exe"))) {
    throw "PyInstaller did not produce the backend executable."
}

# Flatten the onedir output while preserving its runtime DLL directory.
Get-ChildItem $Nested -Force | Move-Item -Destination "backend-dist" -Force
Remove-Item $Nested -Recurse -Force

Push-Location frontend
npm ci
npm run build
Pop-Location

Push-Location desktop
npm ci
npm run dist:win
Pop-Location

Write-Host "Windows installer is in desktop\dist."
