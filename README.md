# Laravel FTP Backup (Ubuntu)

Automatically backs up multiple Laravel projects (source + database) and uploads them to FTP.  
Runs in the background with `systemd timer` and continues after reboot.

## Features

- Back up multiple projects from one JSON file
- Zip source code with exclude patterns
- Dump DB: MySQL/MariaDB, PostgreSQL, SQLite
- Upload to FTP per run with a detailed timestamp folder
- Flexible scheduling via `OnCalendar` or `OnUnitActiveSec`
- Co-exists with `laravel-telegram-backup` on the same machine (no shared package paths)

## Quick Install for End Users

```bash
curl -fsSL https://raw.githubusercontent.com/nht2312/pkg-auto-backup-laravel-project-ftp/main/install-remote.sh | bash -s -- --repo nht2312/pkg-auto-backup-laravel-project-ftp
```

## Install from Source

```bash
chmod +x install.sh && ./install.sh
```

## Quick Setup

```bash
sudo nano /etc/laravel-ftp-backup/config.json
sudo lbf validate-config
sudo lbf sync-schedule
sudo lbf run
```

## FTP Backup Structure

Each backup run creates a new folder with format `DDMMYYYY-HHMMSS`.

- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/source.zip`
- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/database.sql.zip`

Example:

- `/backups/laravel/my-app/24042026-153045/source.zip`
- `/backups/laravel/my-app/24042026-153045/database.sql.zip`

## Main Commands

- `lbf run`
- `lbf validate-config`
- `lbf sync-schedule`
- `lbf config-migrate`

## Check Status

```bash
sudo systemctl status laravel-ftp-backup.timer
journalctl -u laravel-ftp-backup.service -n 100 --no-pager
```

## Build .deb

```bash
chmod +x build-deb.sh
./build-deb.sh
```

## CI/CD Release

Push a `vX.Y.Z` tag to automatically build and publish a `.deb`:

```bash
git tag v1.0.1
git push origin v1.0.1
```

Workflow file: `.github/workflows/release.yml`
