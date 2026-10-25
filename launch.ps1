$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot ".runtime\temp"
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot ".runtime\pip-cache"
$env:PYTHONDONTWRITEBYTECODE = "1"
$taskPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $taskPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $PSScriptRoot ".venv")
    } else {
        & python -m venv (Join-Path $PSScriptRoot ".venv")
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create .venv. Install Python 3.12 and retry." }
}
& $taskPython -c "import streamlit,plotly,pandas,numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $taskPython -m ensurepip --upgrade
    & $taskPython -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "App dependency installation failed." }
}
& $taskPython -m streamlit run (Join-Path $PSScriptRoot "app.py") --server.address 127.0.0.1 --server.headless false
