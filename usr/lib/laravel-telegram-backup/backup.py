#!/usr/bin/python3
"""
Laravel backup: archive source + DB dump, upload to FTP.
Config: /etc/laravel-ftp-backup/config.json
"""

from __future__ import annotations

import argparse
import ftplib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def parse_timespan_seconds(value: Any) -> int | None:
    """
    Parse common systemd-like shorthand into seconds.

    Examples:
      - "120s" -> 120
      - "5min" -> 300
      - "2min" -> 120
      - "24h" -> 86400
      - "1d"   -> 86400
    """
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    try:
        if raw.endswith("s"):
            return int(raw[:-1].strip())
        if raw.endswith("min"):
            return int(raw[: -len("min")].strip()) * 60
        if raw.endswith("h"):
            return int(raw[: -len("h")].strip()) * 3600
        if raw.endswith("d"):
            return int(raw[: -len("d")].strip()) * 86400
        # Some users might provide seconds as a plain number.
        if raw.isdigit():
            return int(raw)
    except ValueError:
        return None
    return None


def warn_if_interval_too_short(data: dict[str, Any]) -> None:
    schedule = data.get("schedule") or {}
    if schedule.get("mode") != "interval":
        return

    every = schedule.get("every")
    seconds = parse_timespan_seconds(every)
    if seconds is None:
        return

    if seconds < 300:
        log.warning(
            "schedule.every=%s (%ss) is < 300s; interval this short can make systemd timer behavior unstable. Recommended: >=300s.",
            every,
            seconds,
        )

CONFIG_PATH = Path("/etc/laravel-ftp-backup/config.json")
DEFAULTS_CONFIG_PATH = Path(
    "/usr/share/doc/laravel-ftp-backup/examples/config.json"
)
TIMER_DROPIN_DIR = Path("/etc/systemd/system/laravel-ftp-backup.timer.d")
TIMER_DROPIN_FILE = TIMER_DROPIN_DIR / "schedule.conf"

log = logging.getLogger("laravel-ftp-backup")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )


def print_cli_help() -> None:
    use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    c_reset = "\033[0m" if use_color else ""
    c_title = "\033[1;36m" if use_color else ""
    c_step = "\033[1;33m" if use_color else ""
    c_cmd = "\033[0;32m" if use_color else ""
    c_line = "\033[0;34m" if use_color else ""

    line = "-" * 40
    print(f"{c_line}{line}{c_reset}")
    print(f"{c_title}LARAVEL FTP BACKUP CLI{c_reset}")
    print(f"{c_line}{line}{c_reset}")
    print(f"{c_title}Usage{c_reset}")
    print(f"  {c_cmd}lbf run{c_reset}")
    print(f"  {c_cmd}lbf validate-config{c_reset}")
    print(f"  {c_cmd}lbf sync-schedule{c_reset}")
    print("")
    print(f"{c_title}Post-install steps (recommended){c_reset}")
    print(
        f"{c_step}1) Edit config:{c_reset} "
        f"{c_cmd}sudo nano /etc/laravel-ftp-backup/config.json{c_reset}"
    )
    print(
        f"{c_step}2) Validate:{c_reset}    "
        f"{c_cmd}sudo lbf validate-config{c_reset}"
    )
    print(
        f"{c_step}3) Sync timer:{c_reset}  "
        f"{c_cmd}sudo lbf sync-schedule{c_reset}"
    )
    print(
        f"{c_step}4) Test run:{c_reset}    "
        f"{c_cmd}sudo lbf run{c_reset}"
    )
    print(
        f"{c_step}5) Check logs:{c_reset}  "
        f"{c_cmd}sudo systemctl status laravel-ftp-backup.timer{c_reset}"
    )
    print(
        "                 "
        f"{c_cmd}journalctl -u laravel-ftp-backup.service -n 100 --no-pager{c_reset}"
    )
    print(f"{c_line}{line}{c_reset}")


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing config: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_config(data: dict[str, Any]) -> None:
    if "projects" not in data or not isinstance(data["projects"], list):
        raise ValueError("config must contain a list 'projects'")
    for i, p in enumerate(data["projects"]):
        if not isinstance(p, dict):
            raise ValueError(f"projects[{i}] must be an object")
        for key in ("name", "project_path", "ftp", "database"):
            if key not in p:
                raise ValueError(f"projects[{i}] missing '{key}'")
        ftp = p["ftp"]
        for key in ("host", "username", "password", "remote_path"):
            if key not in ftp:
                raise ValueError(f"projects[{i}].ftp missing '{key}'")
        db = p["database"]
        if "driver" not in db:
            raise ValueError(f"projects[{i}].database needs driver")
        driver = db["driver"].lower()
        if driver == "sqlite":
            if "database" not in db:
                raise ValueError(f"projects[{i}].sqlite needs database path")
        else:
            for k in ("host", "database", "username", "password"):
                if k not in db:
                    raise ValueError(f"projects[{i}].database missing '{k}'")


def schedule_to_timer_ini(schedule: dict[str, Any]) -> str:
    mode = schedule.get("mode", "calendar")
    lines = ["[Timer]"]
    if mode == "interval":
        def normalize_systemd_timespan(ts: str) -> str:
            """Normalize common shorthand to a plain seconds-based systemd time span.

            systemd time span parsing can vary slightly between builds/environments,
            so we convert frequent patterns ourselves for consistent behavior.
            """
            raw = str(ts).strip().lower()
            if raw.endswith("min"):
                try:
                    minutes = int(raw[: -len("min")].strip())
                    return f"{minutes * 60}s"
                except ValueError:
                    return ts
            if raw.endswith("h"):
                try:
                    hours = int(raw[: -len("h")].strip())
                    return f"{hours * 3600}s"
                except ValueError:
                    return ts
            if raw.endswith("d"):
                try:
                    days = int(raw[: -len("d")].strip())
                    return f"{days * 86400}s"
                except ValueError:
                    return ts
            # Keep as-is for forms like "7200s", "24h" (if systemd accepts), etc.
            return ts

        every_raw = schedule.get("every", "24h")
        every = normalize_systemd_timespan(every_raw)

        boot = normalize_systemd_timespan(schedule.get("on_boot_sec", "2min"))
        # Disable calendar trigger from base unit; use timer-based activation instead.
        lines.append("OnCalendar=")
        # Avoid RandomizedDelaySec from base timer (default is 300s), which can be
        # larger than short intervals and makes NextElapse sometimes appear as n/a.
        lines.append("RandomizedDelaySec=0")
        # Recur based on the activated service unit; this gives stable repeat behavior
        # across runs (instead of one-shot behavior observed with OnActiveSec here).
        lines.append(f"OnUnitActiveSec={every}")
        lines.append(f"OnBootSec={boot}")
    else:
        cal = schedule.get("on_calendar", "daily")
        lines.append(f"OnCalendar={cal}")
    persist = schedule.get("persistent", True)
    lines.append(f"Persistent={'true' if persist else 'false'}")
    return "\n".join(lines) + "\n"


def cmd_sync_schedule(config_path: Path) -> int:
    data = load_config(config_path)
    validate_config(data)
    warn_if_interval_too_short(data)
    schedule = data.get("schedule") or {
        "mode": "calendar",
        "on_calendar": "daily",
        "persistent": True,
    }
    ini = schedule_to_timer_ini(schedule)
    TIMER_DROPIN_DIR.mkdir(parents=True, exist_ok=True)
    TIMER_DROPIN_FILE.write_text(ini, encoding="utf-8")
    os.chmod(TIMER_DROPIN_FILE, 0o644)
    log.info("Wrote %s", TIMER_DROPIN_FILE)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    r = subprocess.run(
        ["systemctl", "restart", "laravel-ftp-backup.timer"],
        check=False,
    )
    if r.returncode != 0:
        log.warning(
            "systemctl restart laravel-ftp-backup.timer returned %s (timer may not be installed yet)",
            r.returncode,
        )
    return 0


def cmd_validate(config_path: Path) -> int:
    data = load_config(config_path)
    validate_config(data)
    warn_if_interval_too_short(data)
    log.info("Config OK: %s project(s)", len(data["projects"]))
    return 0


def json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def merge_defaults_preserve_user(user_val: Any, default_val: Any) -> Any:
    """Deep-merge where existing user values always win."""
    if isinstance(user_val, dict) and isinstance(default_val, dict):
        merged = dict(user_val)
        for k, default_item in default_val.items():
            if k in user_val:
                merged[k] = merge_defaults_preserve_user(user_val[k], default_item)
            else:
                merged[k] = json_clone(default_item)
        return merged
    if isinstance(user_val, list) and isinstance(default_val, list):
        # Keep user arrays as-is to avoid accidental destructive changes.
        return list(user_val)
    return user_val


def cmd_config_migrate(config_path: Path, defaults_path: Path) -> int:
    defaults = load_config(defaults_path)
    validate_config(defaults)

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(defaults, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(config_path, 0o600)
        log.info("Config not found, created from defaults: %s", config_path)
        return 0

    user_cfg = load_config(config_path)
    merged = merge_defaults_preserve_user(user_cfg, defaults)

    if "config_schema_version" in defaults:
        merged["config_schema_version"] = defaults["config_schema_version"]

    validate_config(merged)

    ts = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    backup_path = config_path.with_name(f"{config_path.name}.bak.{ts}")
    shutil.copy2(config_path, backup_path)

    config_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(config_path, 0o600)
    log.info("Migrated config in-place and created backup: %s", backup_path)
    return 0


def zip_source(
    project_path: Path,
    excludes: list[str],
    out_zip: Path,
) -> None:
    if not project_path.is_dir():
        raise FileNotFoundError(f"project_path is not a directory: {project_path}")
    artisan = project_path / "artisan"
    if not artisan.is_file():
        log.warning("No artisan in %s — not a typical Laravel root?", project_path)

    normalized_excludes: list[str] = []
    for pat in excludes:
        norm = pat.strip().replace("\\", "/")
        if not norm:
            continue
        if norm.startswith("./"):
            norm = norm[2:]
        if norm.endswith("/"):
            norm = f"{norm}*"
        elif not any(ch in norm for ch in "*?[]"):
            maybe_dir = project_path / norm
            if maybe_dir.is_dir():
                norm = f"{norm}/*"
        normalized_excludes.append(norm)

    exclude_args: list[str] = []
    for pat in normalized_excludes:
        exclude_args.extend(["-x", pat])

    cmd = [
        "zip",
        "-r",
        "-q",
        str(out_zip),
        ".",
        *exclude_args,
    ]
    r = subprocess.run(cmd, cwd=project_path, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"zip source failed: {r.stderr or r.stdout}")


def dump_mysql(db: dict[str, Any], out_sql: Path) -> None:
    port = int(db.get("port", 3306))
    cnf = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".cnf",
        delete=False,
        encoding="utf-8",
    )
    try:
        cnf.write("[client]\n")
        cnf.write(f"host={db['host']}\n")
        cnf.write(f"port={port}\n")
        cnf.write(f"user={db['username']}\n")
        cnf.write(f"password={db['password']}\n")
        cnf.close()
        os.chmod(cnf.name, 0o600)
        cmd = [
            "mysqldump",
            f"--defaults-extra-file={cnf.name}",
            "--single-transaction",
            "--quick",
            db["database"],
        ]
        with out_sql.open("wb") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        if r.returncode != 0:
            err = (r.stderr or b"").decode("utf-8", errors="replace")
            raise RuntimeError(f"mysqldump failed: {err}")
    finally:
        try:
            os.unlink(cnf.name)
        except OSError:
            pass


def dump_pgsql(db: dict[str, Any], out_sql: Path) -> None:
    port = str(db.get("port", 5432))
    env = os.environ.copy()
    env["PGPASSWORD"] = str(db["password"])
    cmd = [
        "pg_dump",
        "-h",
        str(db["host"]),
        "-p",
        port,
        "-U",
        str(db["username"]),
        "-d",
        str(db["database"]),
        "-f",
        str(out_sql),
    ]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {r.stderr or r.stdout}")


def dump_sqlite(db: dict[str, Any], out_sql: Path) -> None:
    db_path = Path(db["database"]).expanduser()
    if not db_path.is_file():
        raise FileNotFoundError(f"SQLite file not found: {db_path}")
    cmd = ["sqlite3", str(db_path), ".dump"]
    with out_sql.open("wb") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"sqlite3 dump failed: {err}")


def dump_database(db: dict[str, Any], out_sql: Path) -> None:
    driver = db["driver"].lower()
    if driver in ("mysql", "mariadb"):
        dump_mysql(db, out_sql)
    elif driver in ("pgsql", "postgres", "postgresql"):
        dump_pgsql(db, out_sql)
    elif driver == "sqlite":
        dump_sqlite(db, out_sql)
    else:
        raise ValueError(f"Unsupported database driver: {driver}")


def zip_file(src: Path, out_zip: Path) -> None:
    cmd = ["zip", "-q", "-j", str(out_zip), str(src)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"zip failed: {r.stderr or r.stdout}")


def connect_ftp(ftp_cfg: dict[str, Any]) -> ftplib.FTP:
    host = str(ftp_cfg["host"])
    port = int(ftp_cfg.get("port", 21))
    username = str(ftp_cfg["username"])
    password = str(ftp_cfg["password"])
    use_tls = bool(ftp_cfg.get("use_tls", False))
    passive_mode = bool(ftp_cfg.get("passive_mode", True))

    if use_tls:
        ftp: ftplib.FTP = ftplib.FTP_TLS()
    else:
        ftp = ftplib.FTP()

    ftp.connect(host=host, port=port, timeout=60)
    ftp.login(user=username, passwd=password)
    ftp.set_pasv(passive_mode)

    if use_tls and isinstance(ftp, ftplib.FTP_TLS):
        ftp.prot_p()

    return ftp


def ensure_remote_dir(ftp: ftplib.FTP, path: str) -> None:
    clean = path.strip()
    if not clean:
        return

    is_abs = clean.startswith("/")
    parts = [part for part in clean.split("/") if part]

    if is_abs:
        ftp.cwd("/")

    for part in parts:
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def upload_file_ftp(ftp: ftplib.FTP, local_file: Path, remote_filename: str) -> None:
    with local_file.open("rb") as f:
        ftp.storbinary(f"STOR {remote_filename}", f)


def run_one_project(
    proj: dict[str, Any],
    work_root: Path,
) -> None:
    name = proj["name"]
    project_path = Path(proj["project_path"]).expanduser().resolve()
    ftp_cfg = proj["ftp"]
    db = proj["database"]

    default_excludes = [
        "vendor",
        "node_modules",
        ".git",
        "storage/logs",
        "storage/framework/cache",
        "storage/framework/sessions",
        "storage/framework/views",
        "bootstrap/cache",
    ]
    ex = proj.get("zip_excludes")
    excludes = list(default_excludes) if ex is None else list(ex)

    ts = time.strftime("%d%m%Y-%H%M%S", time.gmtime())
    work = work_root / f"{name}-{ts}"
    work.mkdir(parents=True)

    source_arc = work / "source.zip"
    db_sql = work / "database.sql"
    db_zip = work / "database.sql.zip"

    log.info("[%s] Archiving source…", name)
    zip_source(project_path, excludes, source_arc)

    log.info("[%s] Dumping database (%s)…", name, db["driver"])
    dump_database(db, db_sql)
    zip_file(db_sql, db_zip)

    source_size = source_arc.stat().st_size
    db_size = db_zip.stat().st_size
    log.info("[%s] Source archive size %s bytes", name, source_size)
    log.info("[%s] DB dump archive size %s bytes", name, db_size)

    remote_base = str(ftp_cfg["remote_path"]).rstrip("/")
    remote_run_dir = f"{remote_base}/{name}/{ts}"

    log.info("[%s] Uploading files to FTP path %s", name, remote_run_dir)
    ftp = connect_ftp(ftp_cfg)
    try:
        ensure_remote_dir(ftp, remote_run_dir)
        upload_file_ftp(ftp, source_arc, "source.zip")
        upload_file_ftp(ftp, db_zip, "database.sql.zip")
    finally:
        ftp.quit()

    log.info("[%s] Upload complete", name)


def cmd_run(config_path: Path) -> int:
    data = load_config(config_path)
    validate_config(data)
    projects = data["projects"]
    if not projects:
        log.info("No projects configured; nothing to do.")
        return 0

    failures = 0
    with tempfile.TemporaryDirectory(prefix="ltb-") as tmp:
        root = Path(tmp)
        for proj in projects:
            try:
                run_one_project(proj, root)
            except Exception as e:
                failures += 1
                log.error("[%s] FAILED: %s", proj.get("name", "?"), e)

    return 1 if failures else 0


def main(argv: list[str]) -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Laravel FTP backup")
    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        choices=[
            "run",
            "sync-schedule",
            "validate-config",
            "config-migrate",
            "help",
        ],
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"Config file (default: {CONFIG_PATH})",
    )
    parser.add_argument(
        "--defaults",
        type=Path,
        default=DEFAULTS_CONFIG_PATH,
        help=f"Defaults config for migration (default: {DEFAULTS_CONFIG_PATH})",
    )
    args = parser.parse_args(argv)

    if args.command == "help":
        print_cli_help()
        return 0

    if args.command == "run":
        try:
            return cmd_run(args.config)
        except FileNotFoundError as e:
            log.error("%s", e)
            return 1
        except (ValueError, json.JSONDecodeError) as e:
            log.error("Invalid config: %s", e)
            return 1

    if args.command == "sync-schedule":
        try:
            return cmd_sync_schedule(args.config)
        except Exception as e:
            log.error("%s", e)
            return 1

    if args.command == "validate-config":
        try:
            return cmd_validate(args.config)
        except Exception as e:
            log.error("%s", e)
            return 1

    if args.command == "config-migrate":
        try:
            return cmd_config_migrate(args.config, args.defaults)
        except Exception as e:
            log.error("%s", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
