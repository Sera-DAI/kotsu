#!/usr/bin/env bash
# Instalador do Kotsu para Linux/macOS.
#   curl -fsSL https://raw.githubusercontent.com/Sera-DAI/kotsu/main/instalar.sh | bash
# Verifica o Python (3.11+) e o pipx e instala o Kotsu. Não usa sudo.
# Para atualizar, rode de novo.
set -euo pipefail

REPO='kotsu-cli'

py=''
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 \
     && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    py="$c"
    break
  fi
done
if [ -z "$py" ]; then
  echo 'Python 3.11 ou mais recente não encontrado. Instale pelo gerenciador de pacotes' >&2
  echo '(ex.: sudo apt install python3, sudo pacman -S python) e rode de novo.' >&2
  exit 1
fi

if ! command -v pipx >/dev/null 2>&1; then
  echo 'O pipx não está instalado. Instale com o gerenciador de pacotes e rode de novo:' >&2
  echo '  Debian/Ubuntu: sudo apt install pipx' >&2
  echo '  Arch:          sudo pacman -S python-pipx' >&2
  echo '  Fedora:        sudo dnf install pipx' >&2
  echo '  macOS:         brew install pipx' >&2
  exit 1
fi

echo 'Instalando o Kotsu...'
pipx install --force "$REPO"
pipx ensurepath >/dev/null 2>&1 || true

echo
echo 'Pronto! Reabra o terminal e rode: kotsu'
echo 'Para atualizar, rode este instalador de novo.'
