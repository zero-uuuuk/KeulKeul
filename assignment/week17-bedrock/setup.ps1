$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
exit $LASTEXITCODE
