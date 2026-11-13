#!/usr/bin/env bash
# Kotsu installer for Linux/macOS.
#   curl -fsSL https://raw.githubusercontent.com/Sera-DAI/kotsu/main/install.sh | bash
# Checks Python (3.11+) and pipx, then installs Kotsu. Does not use sudo.
# To update, run it again.
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
  echo 'Python 3.11 or newer not found. Install it with your package manager' >&2
  echo '(e.g. sudo apt install python3, sudo pacman -S python) and run this again.' >&2
  exit 1
fi

if ! command -v pipx >/dev/null 2>&1; then
  echo 'pipx is not installed. Install it with your package manager and run this again:' >&2
  echo '  Debian/Ubuntu: sudo apt install pipx' >&2
  echo '  Arch:          sudo pacman -S python-pipx' >&2
  echo '  Fedora:        sudo dnf install pipx' >&2
  echo '  macOS:         brew install pipx' >&2
  exit 1
fi

echo 'Installing Kotsu...'
pipx install --force "$REPO"
pipx ensurepath >/dev/null 2>&1 || true

echo
echo 'Done! Reopen the terminal and run: kotsu'
echo 'To update, run this installer again.'
