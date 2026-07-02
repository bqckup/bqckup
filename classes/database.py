import gzip
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich import print

from constant import LOG_DIR


class DatabaseException(Exception):
    pass


class DatabaseCorruptException(DatabaseException):
    """Raised when a database backup fails because of a corrupt table and
    the automatic repair attempt did not resolve the issue (either it
    failed, or the database engine does not support auto-repair).
    """

    def __init__(
        self,
        message: str,
        repair_attempted: bool = False,
        repair_succeeded: bool = False,
    ):
        super().__init__(message)
        self.repair_attempted = repair_attempted
        self.repair_succeeded = repair_succeeded


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
    ) -> bool:
        """Menjalankan mysqlcheck untuk mereparasi tabel yang korup secara otomatis.

        Returns:
            True if mysqlcheck reported success (return code 0), False otherwise.
        """
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

        with open(log_file, "ab") as log:
            now = datetime.now()
            log.write(
                f"\n[{now}] Memulai AUTO-REPAIR untuk database {db_name}...\n".encode()
            )
            log.flush()

            process = subprocess.run(command, stdout=log, stderr=log)

            if process.returncode == 0:
                log.write(b"[SUCCESS] Auto-repair selesai.\n")
            else:
                log.write(
                    f"[FAILED] Auto-repair gagal dengan return code {process.returncode}.\n".encode()
                )
            log.flush()

            return process.returncode == 0

    @staticmethod
    def _is_corruption_detected(log_content: bytes) -> bool:
        """Check a chunk of (lower-cased) log output for corrupt-table indicators."""
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
        """Mengekspor database ke file zip, dilengkapi dengan auto-repair untuk MySQL."""
        # 1. Resolve Command
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

        # 2. Execution Loop (with Retry Logic)
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
                    # 'wb' akan menimpa file yang mungkin corrupt di percobaan sebelumnya
                    with gzip.open(output, "wb") as gz:
                        for chunk in iter(lambda: process.stdout.read(4096), b""):
                            gz.write(chunk)

                    process.wait()

                    if process.returncode == 0:
                        return  # Backup berhasil, keluar dari loop

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

            # 3. Handle Failure & Auto-Repair
            is_corrupt = False
            try:
                with open(log_file, "rb") as f:
                    f.seek(log_offset)
                    log_content = f.read().lower()
                is_corrupt = self._is_corruption_detected(log_content)
            except OSError:
                pass  # Jika log tidak bisa dibaca, biarkan exception utama terlempar

            if is_corrupt and self.type == "mysql" and attempt < max_retries:
                print(
                    f"[yellow]Tabel korup terdeteksi di {db_name}! Menjalankan proses auto-repair...[/yellow]"
                )
                repair_attempted = True
                repair_succeeded = self._repair_mysql_database(
                    db_user, db_password, db_name, db_host, db_port, log_file
                )

                if repair_succeeded:
                    continue  # Lanjutkan iterasi untuk mencoba backup lagi

                print(
                    f"[red]Auto-repair untuk {db_name} gagal. Backup dibatalkan agar "
                    f"backup sukses terakhir tidak ditimpa/terhapus.[/red]"
                )

            # Jangan biarkan file backup yang gagal/tidak lengkap tertinggal di disk,
            # supaya tidak pernah tertukar/menimpa backup valid sebelumnya.
            if os.path.exists(output):
                os.remove(output)

            if is_corrupt:
                if self.type != "mysql":
                    raise DatabaseCorruptException(
                        f"Database backup for '{db_name}' failed because a corrupt table was "
                        f"detected, but automatic repair is only supported for MySQL. Manual "
                        f"intervention required. The last successful backup was left untouched. "
                        f"See log {log_file} for details.",
                        repair_attempted=False,
                        repair_succeeded=False,
                    )

                if not repair_attempted:
                    repair_note = "was not attempted"
                elif repair_succeeded:
                    # mysqlcheck reported success, but the export still fails with a
                    # corruption-like error (e.g. an InnoDB tablespace that mysqlcheck
                    # cannot actually rebuild). Treat this as an unresolved failure.
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
                )

            # Jika gagal bukan karena korup, atau retry sudah habis
            raise DatabaseException(
                f"Database export failed, see log {log_file} for details: return code {process.returncode}"
            )

    # ==========================================
    # CONNECTION TESTING
    # ==========================================

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

    # ==========================================
    # UTILITIES
    # ==========================================

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
