# Instalador do Kotsu para Windows (PowerShell).
#   irm https://raw.githubusercontent.com/Sera-DAI/kotsu/main/instalar.ps1 | iex
# Verifica o Python (3.11+), instala o pipx se faltar e instala o Kotsu.
# Não precisa de administrador. Para atualizar, rode de novo.
$ErrorActionPreference = 'Stop'
$repo = 'git+https://github.com/Sera-DAI/kotsu.git'

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
    Write-Host 'Python 3.11 ou mais recente não encontrado.' -ForegroundColor Yellow
    Write-Host 'Instale em https://www.python.org/downloads/ (marque "Add python.exe to PATH") e rode este comando de novo.'
    exit 1
}
$exe = $py[0]
$pre = @()
if ($py.Count -gt 1) { $pre = $py[1..($py.Count - 1)] }

& $exe @pre -m pipx --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Instalando o pipx...'
    & $exe @pre -m pip install --user --quiet pipx
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o pipx.' }
}
& $exe @pre -m pipx ensurepath *> $null

Write-Host 'Instalando o Kotsu...'
& $exe @pre -m pipx install --force $repo
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o Kotsu.' }

Write-Host ''
Write-Host 'Pronto! Feche e reabra o terminal e rode: kotsu' -ForegroundColor Green
Write-Host 'Para atualizar, rode este instalador de novo.'
