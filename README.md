# Laravel FTP Backup (Ubuntu)

Tự động backup nhiều dự án Laravel (source + database) và upload lên FTP.  
Chạy nền bằng `systemd timer`, tự chạy lại sau reboot.

## Features

- Backup nhiều project trong một file JSON
- Zip source với exclude patterns
- Dump DB: MySQL/MariaDB, PostgreSQL, SQLite
- Upload lên FTP theo từng lần chạy với thư mục timestamp chi tiết
- Lịch chạy linh hoạt qua `OnCalendar` hoặc `OnUnitActiveSec`

## Cài nhanh cho người dùng cuối

```bash
curl -fsSL https://raw.githubusercontent.com/nht2312/pkg-auto-backup-laravel-project-ftp/main/install-remote.sh | bash -s -- --repo nht2312/pkg-auto-backup-laravel-project-ftp
```

## Cài từ source

```bash
chmod +x install.sh && ./install.sh
```

## Cấu hình nhanh

```bash
sudo nano /etc/laravel-ftp-backup/config.json
sudo lbf validate-config
sudo lbf sync-schedule
sudo lbf run
```

## Cấu trúc backup trên FTP

Mỗi lần backup tạo thư mục mới theo format `DDMMYYYY-HHMMSS`.

- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/source.zip`
- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/database.sql.zip`

Ví dụ:

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

Push tag `vX.Y.Z` để auto build và publish `.deb`:

```bash
git tag v1.0.1
git push origin v1.0.1
```

Workflow: `.github/workflows/release.yml`
