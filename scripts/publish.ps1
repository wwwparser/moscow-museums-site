$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
python scripts/verify_data.py
if ($LASTEXITCODE -ne 0) { throw 'Data verification failed' }
node --check web/app.js
if ($LASTEXITCODE -ne 0) { throw 'JavaScript validation failed' }
node --check web/telegram-feed.js
if ($LASTEXITCODE -ne 0) { throw 'Telegram feed validation failed' }
node --check web/admission-view.js
if ($LASTEXITCODE -ne 0) { throw 'Admission view validation failed' }
git push origin main
if ($LASTEXITCODE -ne 0) { throw 'Source push failed' }
git subtree push --prefix web origin gh-pages
if ($LASTEXITCODE -ne 0) { throw 'Pages push failed' }
Write-Output 'Site: https://wwwparser.github.io/moscow-museums-site/'
