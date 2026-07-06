import gzip
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich import print

from constant import LOG_DIR


class DatabaseException(Exception):
    pass


class DatabaseCorruptException(DatabaseException):
    """Raised when a database backup fails because of a corrupt table and
    the automatic repair attempt did not resolve the issue (either it
    failed, or the database engine does not support auto-repair).

    Additional optional metadata fields are provided but kept backward
    compatible: `repair_attempted`, `repair_succeeded`, `repair_started_at`,
    `repair_duration_seconds`, `first_seen_timestamp`, `problem_age_seconds`.
    """

    def __init__(
        self,
        message: str,
        repair_attempted: bool = False,
        repair_succeeded: bool = False,
        repair_started_at: Optional[float] = None,
        repair_duration_seconds: Optional[float] = None,
        first_seen_timestamp: Optional[int] = None,
        problem_age_seconds: Optional[int] = None,
    ):
        super().__init__(message)
        self.repair_attempted = repair_attempted
        self.repair_succeeded = repair_succeeded
        self.repair_started_at = repair_started_at
        self.repair_duration_seconds = repair_duration_seconds
        self.first_seen_timestamp = first_seen_timestamp
        self.problem_age_seconds = problem_age_seconds


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

# Keywords that indicate a corruption scenario that is NOT suitable for
# automatic repair. Keep this conservative to avoid skipping repairs which
# might succeed.
NON_REPAIRABLE_KEYWORDS = (
    b"not a MyISAM table",
    b"not repairable",
    b"cannot be repaired",
)


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

    def _repair_mysql_database(
        self,
        db_user: str,
        db_password: str,
        db_name: str,
        db_host: str,
        db_port: int,
        log_file: Path,
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

        repair_started_at = time.time()

        with open(log_file, "ab") as log:
            now_dt = datetime.now()
            log.write(
                f"\n[{now_dt}] Starting AUTO-REPAIR for database {db_name}...\n".encode()
            )
            log.flush()

            process = subprocess.run(command, stdout=log, stderr=log)

            repair_duration = time.time() - repair_started_at

            if process.returncode == 0:
                log.write(b"[SUCCESS] Auto-repair completed.\n")
            else:
                log.write(
                    f"[FAILED] Auto-repair failed with return code {process.returncode}.\n".encode()
                )

            log.write(f"[INFO] repair_started_at={repair_started_at}, duration_seconds={repair_duration}\n".encode())
            log.flush()

            return (process.returncode == 0, repair_started_at, repair_duration)

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
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent)) as tf:
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
            try:
                with open(log_file, "rb") as f:
                    f.seek(log_offset)
                    log_content = f.read().lower()
                is_corrupt = self._is_corruption_detected(log_content)
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
                    )

                print(
                    f"[yellow]Corrupt table detected in '{db_name}'. Running auto-repair...[/yellow]"
                )
                repair_attempted = True
                repair_result = self._repair_mysql_database(
                    db_user, db_password, db_name, db_host, db_port, log_file
                )

                # _repair_mysql_database now returns (succeeded, started_at, duration)
                if isinstance(repair_result, tuple):
                    repair_succeeded, repair_started_at, repair_duration = repair_result
                else:
                    repair_succeeded = bool(repair_result)
                    repair_started_at = None
                    repair_duration = None

                if repair_succeeded:
                    # clear any manual intervention marker if repair succeeded
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
                    )

                if not repair_attempted:
                    repair_note = "was not attempted"
                elif repair_succeeded:
                    repair_note = "reported success, but the table is still failing to export"
                else:
                    repair_note = "failed"

                raise DatabaseCorruptException(
                    f"Database backup for '{db_name}' failed because a corrupt table was "
                    f"detected and automatic repair {repair_note}. Manual intervention "
                    f"required. The last successful backup was left untouched. "
                    f"See log {log_file} for details.",
                    repair_attempted=repair_attempted,
                    repair_succeeded=repair_succeeded,
                    repair_started_at=locals().get('repair_started_at'),
                    repair_duration_seconds=locals().get('repair_duration'),
                    first_seen_timestamp=locals().get('first_seen'),
                    problem_age_seconds=locals().get('age'),
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
