import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich import print

from constant import (
    DB_REPAIR_BASE_WARNING_THRESHOLD,
    DB_REPAIR_POLL_INTERVAL,
    DB_REPAIR_SECONDS_PER_100MB,
    LOG_DIR,
)


class DatabaseException(Exception):
    pass


class DatabaseCorruptException(DatabaseException):

    def __init__(
        self,
        message: str,
        repair_attempted: bool = False,
        repair_succeeded: bool = False,
        repair_started_at: Optional[float] = None,
        repair_duration_seconds: Optional[float] = None,
        first_seen_timestamp: Optional[int] = None,
        problem_age_seconds: Optional[int] = None,
        table_name: Optional[str] = None,
    ):
        super().__init__(message)
        self.repair_attempted = repair_attempted
        self.repair_succeeded = repair_succeeded
        self.repair_started_at = repair_started_at
        self.repair_duration_seconds = repair_duration_seconds
        self.first_seen_timestamp = first_seen_timestamp
        self.problem_age_seconds = problem_age_seconds
        self.table_name = table_name


DATABASE_LOG = LOG_DIR / "database.log"

CORRUPTION_KEYWORDS = (
    b"crashed",
    b"corrupt",
    b"incorrect key file",
    b"incorrect file format",
    b"try to repair",
    b"tablespace is missing",
    b"doesn't exist in engine",
    b"error: 130",  # Incorrect file format
    b"error: 126",  # Index file is crashed
    b"error: 127",  # Record file is crashed
    b"error: 134",  # Record file / storage engine corruption
    b"error: 144",  # Table is marked as crashed
    b"error: 145",  # Table marked as crashed and last repair failed
    b"error: 1034",  # Incorrect key file for table
    b"error: 1035",  # Old database file
    b"error: 1194",  # Table is marked as crashed
    b"error 194",  # Tablespace is missing for a table (InnoDB)
)

NON_REPAIRABLE_KEYWORDS = (
    b"not a myisam table",
)

TABLE_NAME_PATTERN = re.compile(rb"table\s*:?\s*'([^']+)'", re.IGNORECASE)


class Database:
    SUPPORTED_DATABASE = ("mysql", "postgresql", "sqlite")

    def __init__(self, type="mysql"):
        self.type = type.lower()

    def _get_mysql_command(
        self,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str,
        db_port: int,
    ) -> list:
        return [
            "mysqldump",
            f"--user={db_user}",
            f"--password={db_password}",
            f"--host={db_host}",
            f"--port={db_port}",
            "--no-tablespaces",
            "--skip-dump-date",
            db_name,
        ]

    def _get_postgresql_command(
        self,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str,
        db_port: int,
    ) -> tuple:
        env = os.environ.copy()
        env["PGPASSWORD"] = db_password

        command = [
            "pg_dump",
            "-U",
            db_user,
            "-h",
            db_host,
            "-p",
            str(db_port),
            db_name,
        ]

        return command, env

    def _get_sqlite_command(self, db_name: str) -> list:
        return ["sqlite3", db_name, ".dump"]

    def _estimate_warning_threshold(
        self,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str,
        db_port: int,
        table_name: Optional[str] = None,
    ) -> int:
        
        try:
            import mysql.connector

            conn = mysql.connector.connect(
                user=db_user, password=db_password, host=db_host, port=db_port
            )
            try:
                cursor = conn.cursor()
                if table_name:
                    cursor.execute(
                        "SELECT data_length + index_length FROM information_schema.tables "
                        "WHERE table_schema = %s AND table_name = %s",
                        (db_name, table_name),
                    )
                else:
                    cursor.execute(
                        "SELECT SUM(data_length + index_length) FROM information_schema.tables "
                        "WHERE table_schema = %s",
                        (db_name,),
                    )
                row = cursor.fetchone()
                cursor.close()
            finally:
                conn.close()

            size_bytes = row[0] if row and row[0] else 0
            size_mb = size_bytes / (1024**2)

            return max(
                DB_REPAIR_BASE_WARNING_THRESHOLD,
                int((size_mb / 100) * DB_REPAIR_SECONDS_PER_100MB),
            )
        except Exception:
            return DB_REPAIR_BASE_WARNING_THRESHOLD

    @staticmethod
    def _read_log_tail(
        log_file: Path, offset: int, max_chars: int = 1000
    ) -> Optional[str]:
        """Best-effort read of whatever has been written to the repair log so
        far (since `offset`), so a long-running-repair warning can surface
        any partial error/warning output the tool has already produced -
        even though the repair itself hasn't finished yet.
        """
        try:
            with open(log_file, "rb") as f:
                f.seek(offset)
                content = f.read().decode(errors="replace").strip()
            return content[-max_chars:] if content else None
        except OSError:
            return None

    def _notify_long_running_repair(
        self,
        db_name: str,
        elapsed_seconds: float,
        threshold_seconds: Optional[int] = None,
        log_snippet: Optional[str] = None,
    ) -> None:
  
        try:
            from humanfriendly import format_timespan

            from lib.notifications.discord import send_notification
            from lib.notifications.email import (
                send_notification as send_email_notification,
            )

            duration_label = format_timespan(elapsed_seconds)
            threshold_label = (
                format_timespan(threshold_seconds) if threshold_seconds else None
            )

            description = (
                f"Automatic repair for database `{db_name}` has been "
                f"running for **{duration_label}** without finishing yet.\n\n"
            )
            if threshold_label:
                description += (
                    f"Based on the size of the data being repaired, this is longer "
                    f"than the expected time of ~{threshold_label}.\n\n"
                )
            description += (
                "This can still be normal for very large databases, so the repair "
                "is left running rather than aborted. If it keeps running much "
                "longer, consider checking on it manually."
            )

            fields = [
                {"name": "Database", "value": db_name, "inline": True},
                {"name": "Running For", "value": duration_label, "inline": True},
            ]
            if threshold_label:
                fields.append(
                    {
                        "name": "Expected Threshold (by size)",
                        "value": threshold_label,
                        "inline": True,
                    }
                )
            if log_snippet:
                fields.append(
                    {
                        "name": "Latest Repair Log Output",
                        "value": log_snippet,
                        "inline": False,
                    }
                )

            payload = {
                "embeds": [
                    {
                        "title": (
                            f"\u23f3 Database Repair Still Running \u2014 Manual Check "
                            f"Recommended ({db_name})"
                        ),
                        "description": description,
                        "color": 16776960,
                        "fields": fields,
                    }
                ]
            }
            send_notification(payload)
            send_email_notification(payload)
        except Exception as e:
            print(
                f"[yellow]Failed to send long-running repair notification: {e}[/yellow]"
            )

    def _repair_mysql_database(
        self,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str,
        db_port: int,
        log_file: Path,
        table_name: Optional[str] = None,
    ) -> Tuple[bool, float, float]:

        command = [
            "mysqlcheck",
            "--repair",
            "--auto-repair",
            f"--user={db_user}",
            f"--password={db_password}",
            f"--host={db_host}",
            f"--port={db_port}",
            db_name,
        ]

        warning_threshold = self._estimate_warning_threshold(
            db_user, db_password, db_name, db_host, db_port, table_name
        )

        repair_started_at = time.time()
        log_offset_before_repair = log_file.stat().st_size if log_file.exists() else 0
        result_holder: Dict[str, int] = {}

        def _run_repair() -> None:
            with open(log_file, "ab") as log:
                now_dt = datetime.now()
                log.write(
                    f"\n[{now_dt}] Starting AUTO-REPAIR for database {db_name}...\n".encode()
                )
                log.flush()
                process = subprocess.run(command, stdout=log, stderr=log)
                result_holder["returncode"] = process.returncode

        repair_thread = threading.Thread(target=_run_repair, daemon=True)
        repair_thread.start()

        warned = False
        while repair_thread.is_alive():
            repair_thread.join(timeout=DB_REPAIR_POLL_INTERVAL)
            if repair_thread.is_alive() and not warned:
                elapsed = time.time() - repair_started_at
                if elapsed >= warning_threshold:
                    warned = True
                    log_snippet = self._read_log_tail(
                        log_file, log_offset_before_repair
                    )
                    self._notify_long_running_repair(
                        db_name, elapsed, warning_threshold, log_snippet
                    )

        repair_duration = time.time() - repair_started_at
        succeeded = result_holder.get("returncode") == 0

        with open(log_file, "ab") as log:
            if succeeded:
                log.write(b"[SUCCESS] Auto-repair completed.\n")
            else:
                log.write(
                    f"[FAILED] Auto-repair failed with return code {result_holder.get('returncode')}.\n".encode()
                )
            log.write(
                f"[INFO] repair_started_at={repair_started_at}, duration_seconds={repair_duration}\n".encode()
            )
            log.flush()

        return (succeeded, repair_started_at, repair_duration)

    @staticmethod
    def _meta_file_path() -> Path:
        return LOG_DIR / "db_corrupt_meta.json"

    @staticmethod
    def _read_meta() -> Dict[str, Any]:
        path = Database._meta_file_path()
        try:
            if path.exists():
                with open(path, "r") as f:
                    return json.load(f)
        except Exception:
            print(f"[yellow]Failed to read DB corrupt meta {path}, ignoring.[/yellow]")
        return {}

    @staticmethod
    def _write_meta(data: Dict[str, Any]) -> None:
        path = Database._meta_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # atomic write
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=str(path.parent)
            ) as tf:
                json.dump(data, tf)
                tf.flush()
                tmpname = tf.name
            shutil.move(tmpname, str(path))
        except Exception:
            print(f"[yellow]Failed to write DB corrupt meta {path}, ignoring.[/yellow]")

    @staticmethod
    def _mark_manual_intervention(db_label: str) -> int:
        data = Database._read_meta()
        now_ts = int(time.time())
        if db_label not in data:
            data[db_label] = {"first_seen": now_ts}
            Database._write_meta(data)
        return data[db_label]["first_seen"]

    @staticmethod
    def _clear_manual_intervention(db_label: str) -> None:
        data = Database._read_meta()
        if db_label in data:
            try:
                del data[db_label]
                Database._write_meta(data)
            except Exception:
                pass

    @staticmethod
    def _get_problem_age(db_label: str) -> Optional[int]:
        data = Database._read_meta()
        if db_label in data and "first_seen" in data[db_label]:
            return int(time.time()) - int(data[db_label]["first_seen"])
        return None

    @staticmethod
    def _is_corruption_detected(log_content: bytes) -> bool:
        return any(keyword in log_content for keyword in CORRUPTION_KEYWORDS)

    @staticmethod
    def _extract_table_name(log_content: bytes) -> Optional[str]:
        """Best-effort extraction of the offending table name from the error
        log, e.g. "Table './db/demo' is marked as crashed" -> "demo". Returns
        None if no table name could be identified.
        """
        match = TABLE_NAME_PATTERN.search(log_content)
        if not match:
            return None
        raw_name = match.group(1).decode(errors="replace")
        return raw_name.rsplit("/", 1)[-1]

    def export(
        self,
        output: str,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str = "localhost",
        db_port: int = 3306,
        log_dir: Optional[str] = None,
    ) -> None:

        if self.type == "mysql":
            command = self._get_mysql_command(
                db_user, db_password, db_name, db_host, db_port
            )
            env = None
        elif self.type == "postgresql":
            command, env = self._get_postgresql_command(
                db_user, db_password, db_name, db_host, db_port
            )
        elif self.type == "sqlite":
            command = self._get_sqlite_command(db_name)
            env = None
        else:
            raise DatabaseException(f"Unsupported database type: {self.type}")

        label = (
            f"{db_user}@{db_host}:{db_port}/{db_name}"
            if self.type != "sqlite"
            else f"sqlite:{db_name}"
        )
        log_file = Path(log_dir) / "database.log" if log_dir else DATABASE_LOG

        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(
                f"[yellow]Cannot create log directory {log_file.parent} ({e})[/yellow]"
            )

        max_retries = 1
        repair_attempted = False
        repair_succeeded = False

        for attempt in range(max_retries + 1):
            try:
                log_offset = log_file.stat().st_size if log_file.exists() else 0
            except OSError:
                log_offset = 0

            try:
                log = open(log_file, "ab")
            except OSError as e:
                print(
                    f"[yellow]Cannot write export log to {log_file} ({e}); continuing without file log[/yellow]"
                )
                log = open(os.devnull, "ab")

            with log:
                now = datetime.now()
                attempt_label = f" (Attempt {attempt + 1})" if attempt > 0 else ""
                log.write(
                    f"Database export {label} > {output} at {now}{attempt_label}\n".encode()
                )
                log.flush()

                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=log,
                    env=env if env else os.environ,
                )

                try:
                    with gzip.open(output, "wb") as gz:
                        for chunk in iter(lambda: process.stdout.read(4096), b""):
                            gz.write(chunk)

                    process.wait()

                    if process.returncode == 0:
                        return

                except KeyboardInterrupt:
                    print("\nDatabase export cancelled by user.")
                    process.terminate()

                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()

                    if os.path.exists(output):
                        os.remove(output)
                        print(f"Incomplete file {output} removed.")
                    raise

            is_corrupt = False
            corrupt_table_name = None
            try:
                with open(log_file, "rb") as f:
                    f.seek(log_offset)
                    log_content = f.read().lower()
                is_corrupt = self._is_corruption_detected(log_content)
                if is_corrupt:
                    corrupt_table_name = self._extract_table_name(log_content)
            except OSError:
                pass

            if is_corrupt and self.type == "mysql" and attempt < max_retries:
                # Repair assessment: check if log contains any non-repairable
                # patterns. If so, mark manual intervention and raise.
                non_repairable = any(k in log_content for k in NON_REPAIRABLE_KEYWORDS)

                if non_repairable:
                    print(
                        f"[red]Detected non-repairable corruption in '{db_name}'. Manual intervention required.[/red]"
                    )
                    first_seen = Database._mark_manual_intervention(label)
                    age = Database._get_problem_age(label)
                    raise DatabaseCorruptException(
                        f"Database backup for '{db_name}' failed because a corrupt table was "
                        f"detected and it appears not to be automatically repairable. Manual "
                        f"intervention required. The last successful backup was left untouched. "
                        f"See log {log_file} for details.",
                        repair_attempted=False,
                        repair_succeeded=False,
                        first_seen_timestamp=first_seen,
                        problem_age_seconds=age,
                        table_name=corrupt_table_name,
                    )

                print(
                    f"[yellow]Corrupt table detected in '{db_name}'. Running auto-repair...[/yellow]"
                )
                repair_attempted = True
                repair_result = self._repair_mysql_database(
                    db_user,
                    db_password,
                    db_name,
                    db_host,
                    db_port,
                    log_file,
                    table_name=corrupt_table_name,
                )

                if isinstance(repair_result, tuple):
                    repair_succeeded, repair_started_at, repair_duration = repair_result
                else:
                    repair_succeeded = bool(repair_result)
                    repair_started_at = None
                    repair_duration = None

                if repair_succeeded:
                    Database._clear_manual_intervention(label)
                    continue

                print(
                    f"[red]Auto-repair for '{db_name}' failed. "
                    f"Backup aborted to preserve the last successful backup.[/red]"
                )
                # mark manual intervention first_seen if not set
                first_seen = Database._mark_manual_intervention(label)
                age = Database._get_problem_age(label)

            if os.path.exists(output):
                os.remove(output)

            if is_corrupt:
                if self.type != "mysql":
                    first_seen = Database._mark_manual_intervention(label)
                    age = Database._get_problem_age(label)
                    raise DatabaseCorruptException(
                        f"Database backup for '{db_name}' failed because a corrupt table was "
                        f"detected, but automatic repair is only supported for MySQL. Manual "
                        f"intervention required. The last successful backup was left untouched. "
                        f"See log {log_file} for details.",
                        repair_attempted=False,
                        repair_succeeded=False,
                        first_seen_timestamp=first_seen,
                        problem_age_seconds=age,
                        table_name=corrupt_table_name,
                    )

                if not repair_attempted:
                    repair_note = "was not attempted"
                elif repair_succeeded:
                    repair_note = (
                        "reported success, but the table is still failing to export"
                    )
                else:
                    repair_note = "failed"

                raise DatabaseCorruptException(
                    f"Database backup for '{db_name}' failed because a corrupt table was "
                    f"detected and automatic repair {repair_note}. Manual intervention "
                    f"required. The last successful backup was left untouched. "
                    f"See log {log_file} for details.",
                    repair_attempted=repair_attempted,
                    repair_succeeded=repair_succeeded,
                    repair_started_at=locals().get("repair_started_at"),
                    repair_duration_seconds=locals().get("repair_duration"),
                    first_seen_timestamp=locals().get("first_seen"),
                    problem_age_seconds=locals().get("age"),
                    table_name=corrupt_table_name,
                )
            raise DatabaseException(
                f"Database export failed, see log {log_file} for details: return code {process.returncode}"
            )

    def test_connection(self, credentials: dict) -> None:
        if self.type == "mysql":
            self._test_mysql_connection(credentials)
        elif self.type == "postgresql":
            self._test_postgresql_connection(credentials)
        elif self.type == "sqlite":
            self._test_sqlite_connection(credentials)
        else:
            raise DatabaseException(f"Unsupported database type: {self.type}")

    def _test_mysql_connection(self, credentials: dict) -> None:
        import mysql.connector

        try:
            c = mysql.connector.connect(
                user=credentials["user"],
                host=credentials["host"],
                port=credentials["port"],
                password=credentials["password"],
                database=credentials["name"],
            )
        except mysql.connector.Error as e:
            logging.error(e)
            raise DatabaseException("Failed to connect database, see log for details")
        else:
            c.close()

    def _test_postgresql_connection(self, credentials: dict) -> None:
        import psycopg2

        try:
            c = psycopg2.connect(
                user=credentials["user"],
                host=credentials["host"],
                port=credentials["port"],
                password=credentials["password"],
                dbname=credentials["name"],
            )
        except psycopg2.Error as e:
            logging.error(e)
            raise DatabaseException("Failed to connect database, see log for details")
        else:
            c.close()

    def _test_sqlite_connection(self, credentials: dict) -> None:
        db_path = credentials.get("name")
        if not db_path:
            raise DatabaseException("SQLite database path (name) is required")

        if not os.path.exists(db_path):
            raise DatabaseException(f"SQLite database file not found: {db_path}")

        import sqlite3

        try:
            c = sqlite3.connect(db_path)
            c.close()
        except sqlite3.Error as e:
            logging.error(e)
            raise DatabaseException(
                "Failed to connect to SQLite database, see log for details"
            )

    @staticmethod
    def get_all(site_config: dict) -> List[Dict[str, Any]]:
        """Return a list of databases that are enabled for backup"""
        result = []
        databases: list = site_config.get("databases", []).copy()

        if database := site_config.get("database", {}):
            databases.append(database)

        for database in databases:
            if not ("enabled" in database or "enable" in database):
                result.append(database)
                continue
            elif not (database.get("enabled") or database.get("enable")):
                continue

            result.append(database)

        return result
