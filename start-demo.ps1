$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:DEMO_MODE = 'true'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the environment first with: uv sync --locked'
}
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000
