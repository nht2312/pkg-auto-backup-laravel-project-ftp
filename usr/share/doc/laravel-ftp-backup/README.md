# laravel-ftp-backup

Định kỳ backup source Laravel (zip) và dump database, sau đó upload lên FTP.

## Cài nhanh

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install-remote.sh | bash -s -- --repo <owner>/<repo>
```

Hoặc cài từ source:

```bash
chmod +x install.sh && ./install.sh
```

## Cấu hình

```bash
sudo mkdir -p /etc/laravel-ftp-backup
sudo cp /usr/share/doc/laravel-ftp-backup/examples/config.json /etc/laravel-ftp-backup/config.json
sudo chmod 600 /etc/laravel-ftp-backup/config.json
sudo nano /etc/laravel-ftp-backup/config.json
```

Các key bắt buộc cho từng project:
- `name`
- `project_path`
- `ftp.host`, `ftp.username`, `ftp.password`, `ftp.remote_path`
- `database.*` theo driver

## Cấu trúc folder trên FTP

Mỗi lần chạy tạo thư mục timestamp định dạng `DDMMYYYY-HHMMSS`:

- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/source.zip`
- `<remote_path>/<project_name>/<DDMMYYYY-HHMMSS>/database.sql.zip`

Ví dụ:

- `/backups/laravel/my-app/24042026-153045/source.zip`
- `/backups/laravel/my-app/24042026-153045/database.sql.zip`

## Lệnh CLI

- `lbf run`
- `lbf validate-config`
- `lbf sync-schedule`
- `lbf config-migrate`

## systemd

- Timer: `laravel-ftp-backup.timer`
- Service: `laravel-ftp-backup.service`

```bash
sudo systemctl status laravel-ftp-backup.timer
journalctl -u laravel-ftp-backup.service -n 50 --no-pager
```
