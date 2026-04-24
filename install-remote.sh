#!/bin/sh
# Remote one-liner installer:
# curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install-remote.sh | bash -s -- --repo <owner>/<repo>
set -e

REPO=""
VERSION=""

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$REPO" ]; then
  echo "Usage: install-remote.sh --repo <owner>/<repo> [--version <tag>]" >&2
  exit 1
fi

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

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Ubuntu/Debian (apt-get)." >&2
  exit 1
fi

prepare_config() {
  echo "[5/6] Preparing config template..."
  $SUDO mkdir -p /etc/laravel-ftp-backup
  if [ ! -f /etc/laravel-ftp-backup/config.json ]; then
    $SUDO cp /usr/share/doc/laravel-ftp-backup/examples/config.json /etc/laravel-ftp-backup/config.json
    $SUDO chmod 600 /etc/laravel-ftp-backup/config.json
    echo "Created: /etc/laravel-ftp-backup/config.json"
  else
    echo "Config already exists: /etc/laravel-ftp-backup/config.json"
  fi
}

print_next_steps() {
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

echo "[1/6] Installing base dependencies..."
$SUDO apt-get update
$SUDO apt-get install -y curl ca-certificates python3

API_BASE="https://api.github.com/repos/$REPO/releases"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

RELEASE_JSON=""
DEB_URL=""
if [ -n "$VERSION" ]; then
  echo "[2/6] Fetching release tag: $VERSION"
  if RELEASE_JSON="$(curl -fsSL "$API_BASE/tags/$VERSION" 2>/dev/null)"; then
    :
  else
    echo "Release API unavailable for tag '$VERSION', switching to source fallback."
  fi
else
  echo "[2/6] Fetching latest release"
  if RELEASE_JSON="$(curl -fsSL "$API_BASE/latest" 2>/dev/null)"; then
    :
  else
    echo "No latest release found (404), switching to source fallback."
  fi
fi

if [ -n "$RELEASE_JSON" ]; then
  DEB_URL="$(printf '%s' "$RELEASE_JSON" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((a["browser_download_url"] for a in d.get("assets",[]) if a.get("name","").endswith("_all.deb")), ""))')"
fi

if [ -n "$DEB_URL" ]; then
  echo "[3/6] Release mode: downloading .deb asset..."
  DEB_FILE="$TMP_DIR/package.deb"
  curl -fL "$DEB_URL" -o "$DEB_FILE"

  echo "[4/6] Installing package..."
  $SUDO apt-get install -y "$DEB_FILE"
  prepare_config
  echo "[6/6] Done."
  print_next_steps
  exit 0
fi

echo "[3/6] Fallback mode: installing build dependencies..."
$SUDO apt-get install -y git dpkg-dev zip coreutils

SRC_DIR="$TMP_DIR/src"
REPO_URL="https://github.com/$REPO.git"

echo "[4/6] Cloning source and running local installer..."
if [ -n "$VERSION" ]; then
  git clone --depth 1 --branch "$VERSION" "$REPO_URL" "$SRC_DIR"
else
  git clone --depth 1 "$REPO_URL" "$SRC_DIR"
fi

if [ ! -x "$SRC_DIR/install.sh" ]; then
  chmod +x "$SRC_DIR/install.sh"
fi
"$SRC_DIR/install.sh"
