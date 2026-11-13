# Kotsu installer for Windows (PowerShell).
#   irm https://raw.githubusercontent.com/Sera-DAI/kotsu/main/install.ps1 | iex
# Checks Python (3.11+), installs pipx if missing, then installs Kotsu.
# No administrator needed. To update, run it again.
$ErrorActionPreference = 'Stop'
$repo = 'kotsu-cli'

function Find-Python {
    foreach ($c in @(@('py', '-3'), @('python'), @('python3'))) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $args1 = @()
        if ($c.Count -gt 1) { $args1 = $c[1..($c.Count - 1)] }
        try {
            $ok = & $c[0] @args1 -c 'import sys; print(int(sys.version_info >= (3, 11)))' 2>$null
            if ($ok -eq '1') { return , $c }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3.11 or newer not found.' -ForegroundColor Yellow
    Write-Host 'Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH") and run this command again.'
    exit 1
}
$exe = $py[0]
$pre = @()
if ($py.Count -gt 1) { $pre = $py[1..($py.Count - 1)] }

& $exe @pre -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing pipx...'
    & $exe @pre -m pip install --user --quiet pipx
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install pipx.' }
}
& $exe @pre -m pipx ensurepath *> $null

Write-Host 'Installing Kotsu...'
& $exe @pre -m pipx install --force $repo
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Kotsu.' }

Write-Host ''
Write-Host 'Done! Close and reopen the terminal and run: kotsu' -ForegroundColor Green
Write-Host 'To update, run this installer again.'
