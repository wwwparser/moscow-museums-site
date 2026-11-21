$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

python scripts/verify_data.py
if ($LASTEXITCODE) { throw 'Catalog verification failed' }
node --check web/telegram-feed.js
if ($LASTEXITCODE) { throw 'Telegram feed verification failed' }

$release = [guid]::NewGuid().ToString('N')
$archive = Join-Path ([IO.Path]::GetTempPath()) "museum-$release.tar.gz"
$remote = "museum-$release.tar.gz"
try {
    tar.exe -czf $archive -C web .
    if ($LASTEXITCODE) { throw 'Packaging failed' }
    $connection = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=8', '-o', 'ServerAliveCountMax=2')
    scp @connection $archive "podcast:$remote"
    if ($LASTEXITCODE) { throw 'Upload failed' }
    $command = 'set -eu; base=/var/www/moscow-museums; release=' + $release + '; archive=museum-$release.tar.gz; target=$base/releases/$release; sudo -n install -d -m 755 $target; sudo -n tar --no-same-owner -xzf $archive -C $target; test -s $target/index.html; test -s $target/data/catalog.json; sudo -n ln -s $target $base/current-$release; sudo -n mv -Tf $base/current-$release $base/current; rm -- $archive; curl -fsS --max-time 15 --resolve museum.optegra.ru:443:127.0.0.1 https://museum.optegra.ru/ -o /dev/null'
    ssh @connection podcast $command
    if ($LASTEXITCODE) { throw 'Server release failed' }
    Write-Output 'https://museum.optegra.ru/'
} finally {
    if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
}
