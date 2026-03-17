import gzip
import logging
import subprocess
import os
from datetime import datetime
from constant import LOG_DIR
from pathlib import Path
from rich import print
from typing import Any, List, Dict, Optional


class DatabaseException(Exception):
    pass


DATABASE_LOG = LOG_DIR / "database.log"


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
        log_file = Path(log_dir) / "database.log" if log_dir else DATABASE_LOG

        if not log_file.parent.exists():
            log_file.parent.mkdir(parents=True, exist_ok=True)

        label = (
            f"{db_user}@{db_host}:{db_port}/{db_name}"
            if self.type != "sqlite"
            else f"sqlite:{db_name}"
        )

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

        with open(log_file, "ab") as log:
            now = datetime.now()
            log.write(f"Database export {label} > {output} at {now}\n".encode())
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

                if process.returncode != 0:
                    raise DatabaseException(
                        f"Database export failed, see log {log_file} for details: return code {process.returncode}"
                    )

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
        return

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
        return

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
            # if enabled key is missing, default to true
            if not ("enabled" in database or "enable" in database):
                result.append(database)
                continue

            elif not (database.get("enabled") or database.get("enable")):
                continue

            result.append(database)

        return result
