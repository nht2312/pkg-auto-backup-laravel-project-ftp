#!/bin/sh
# Build laravel-ftp-backup_<version>_all.deb from this tree.
set -e
ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
VERSION="${VERSION:-1.0.0}"
PKG="laravel-ftp-backup"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/lib/systemd/system"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/lib/laravel-ftp-backup"
mkdir -p "$STAGE/usr/share/doc/$PKG/examples"

install -m 755 "$ROOT/usr/bin/lbf" "$STAGE/usr/bin/"
install -m 755 "$ROOT/usr/bin/laravel-ftp-backup" "$STAGE/usr/bin/"
install -m 644 "$ROOT/usr/lib/laravel-ftp-backup/backup.py" "$STAGE/usr/lib/laravel-ftp-backup/"
install -m 644 "$ROOT/lib/systemd/system/laravel-ftp-backup.service" "$STAGE/lib/systemd/system/"
install -m 644 "$ROOT/lib/systemd/system/laravel-ftp-backup.timer" "$STAGE/lib/systemd/system/"
install -m 644 "$ROOT/usr/share/doc/laravel-ftp-backup/examples/config.json" "$STAGE/usr/share/doc/$PKG/examples/"
install -m 644 "$ROOT/usr/share/doc/laravel-ftp-backup/README.md" "$STAGE/usr/share/doc/$PKG/"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: Unmaintained Package <root@localhost>
Depends: python3 (>= 3.7), curl, zip, coreutils
Recommends: default-mysql-client | mariadb-client, postgresql-client, sqlite3
Description: Backup Laravel apps and upload archives to FTP
 Automates zip of project trees, database dumps (MySQL, PostgreSQL, SQLite),
 and uploads compressed bundles to an FTP server. Uses
 systemd timer for scheduled runs.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
case "$1" in
configure)
  mkdir -p /etc/laravel-ftp-backup
  chmod 755 /etc/laravel-ftp-backup

  CFG=/etc/laravel-ftp-backup/config.json
  DEF=/usr/share/doc/laravel-ftp-backup/examples/config.json
  TS="$(date -u +%Y%m%d%H%M%S 2>/dev/null || date +%Y%m%d%H%M%S)"
  BAK="${CFG}.bak.${TS}"

  if [ -f /etc/laravel-ftp-backup/config.json ]; then
    cp -a "$CFG" "$BAK" 2>/dev/null || true

    if lbf config-migrate --config "$CFG" --defaults "$DEF" && lbf validate-config --config "$CFG"; then
      lbf sync-schedule --config "$CFG" 2>/dev/null || true
    else
      echo "WARNING: config migration failed; restoring previous config" >&2
      if [ -f "$BAK" ]; then
        cp -a "$BAK" "$CFG" 2>/dev/null || true
      fi
    fi
  else
    lbf config-migrate --config "$CFG" --defaults "$DEF" 2>/dev/null || true
    lbf sync-schedule --config "$CFG" 2>/dev/null || true
  fi

  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
    systemctl enable --now laravel-ftp-backup.timer || true
  fi
  ;;
esac
exit 0
EOF

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
remove|deconfigure)
  if command -v systemctl >/dev/null 2>&1; then
    systemctl stop laravel-ftp-backup.timer 2>/dev/null || true
    systemctl disable laravel-ftp-backup.timer 2>/dev/null || true
    systemctl daemon-reload || true
  fi
  ;;
upgrade|failed-upgrade)
  ;;
*)
  ;;
esac
exit 0
EOF

chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm"

dpkg-deb --root-owner-group --build "$STAGE" "$ROOT/${PKG}_${VERSION}_all.deb"
echo "Built $ROOT/${PKG}_${VERSION}_all.deb"
