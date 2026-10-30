param([Parameter(Mandatory=$true)][string]$PythonPath)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONUTF8 = '1'
& $PythonPath 'scripts/update_all.py' --mode auto --publish
exit $LASTEXITCODE
