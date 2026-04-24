#!/bin/sh
# One-command installer for Ubuntu/Debian users.
set -e

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET="$(printf '\033[0m')"
  C_TITLE="$(printf '\033[1;36m')"
  C_STEP="$(printf '\033[1;33m')"
  C_CMD="$(printf '\033[0;32m')"
  C_LINE="$(printf '\033[0;34m')"
else
  C_RESET=""
  C_TITLE=""
  C_STEP=""
  C_CMD=""
  C_LINE=""
fi

print_post_install_setup() {
  echo ""
  printf "%s----------------------------------------%s\n" "$C_LINE" "$C_RESET"
  printf "%sPOST-INSTALL SETUP%s\n" "$C_TITLE" "$C_RESET"
  printf "%s----------------------------------------%s\n" "$C_LINE" "$C_RESET"
  printf "%sStep 1:%s Edit configuration file\n" "$C_STEP" "$C_RESET"
  printf "  %ssudo nano /etc/laravel-ftp-backup/config.json%s\n" "$C_CMD" "$C_RESET"
  echo ""
  printf "%sStep 2:%s Validate configuration\n" "$C_STEP" "$C_RESET"
  printf "  %ssudo lbf validate-config%s\n" "$C_CMD" "$C_RESET"
  echo ""
  printf "%sStep 3:%s Apply schedule changes\n" "$C_STEP" "$C_RESET"
  printf "  %ssudo lbf sync-schedule%s\n" "$C_CMD" "$C_RESET"
  echo ""
  printf "%sStep 4:%s Run a test backup\n" "$C_STEP" "$C_RESET"
  printf "  %ssudo lbf run%s\n" "$C_CMD" "$C_RESET"
  echo ""
  printf "%sStep 5:%s Check timer and logs\n" "$C_STEP" "$C_RESET"
  printf "  %ssudo systemctl status laravel-ftp-backup.timer%s\n" "$C_CMD" "$C_RESET"
  printf "  %sjournalctl -u laravel-ftp-backup.service -n 50 --no-pager%s\n" "$C_CMD" "$C_RESET"
  printf "%s----------------------------------------%s\n" "$C_LINE" "$C_RESET"
}

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PKG_NAME="laravel-ftp-backup"
VERSION="${VERSION:-1.0.0}"
DEB_FILE="$ROOT/${PKG_NAME}_${VERSION}_all.deb"

echo "[1/5] Installing build/runtime dependencies..."
$SUDO apt-get update
$SUDO apt-get install -y dpkg-dev python3 curl zip coreutils

echo "[2/5] Building .deb package..."
chmod +x "$ROOT/build-deb.sh"
VERSION="$VERSION" "$ROOT/build-deb.sh"

if [ ! -f "$DEB_FILE" ]; then
  echo "ERROR: Package file not found: $DEB_FILE" >&2
  exit 1
fi

echo "[3/5] Installing package..."
$SUDO apt-get install -y "$DEB_FILE"

echo "[4/5] Preparing config template..."
$SUDO mkdir -p /etc/laravel-ftp-backup
if [ ! -f /etc/laravel-ftp-backup/config.json ]; then
  $SUDO cp /usr/share/doc/laravel-ftp-backup/examples/config.json /etc/laravel-ftp-backup/config.json
  $SUDO chmod 600 /etc/laravel-ftp-backup/config.json
  echo "Created: /etc/laravel-ftp-backup/config.json"
else
  echo "Config already exists: /etc/laravel-ftp-backup/config.json"
fi

echo "[5/5] Done."
print_post_install_setup
