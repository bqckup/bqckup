import gzip
import logging
import subprocess
import os
from datetime import datetime
from constant import LOG_DIR
from pathlib import Path
from rich import print
from typing import Any, List, Dict, Optional


# Database Exceptions
class DatabaseException(Exception):
    pass


DATABASE_LOG = LOG_DIR / "database.log"

"""
should be compatible with to other database type
"""


class Database:
    # mysqli is temporary
    SUPPORTED_DATABASE = ("mysql", "postgresql", "sqlite")

    def __init__(self, type="mysql"):
        self.type = type.lower()

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

        label = f"{db_user}@{db_host}:{db_port}/{db_name}"
        command = [
            "mysqldump",
            f"--user={db_user}",
            f"--password={db_password}",
            f"--host={db_host}",
            f"--port={db_port}",
            "--no-tablespaces",
            "--skip-dump-date",
            db_name,
        ]

        with open(log_file, "ab") as log:
            now = datetime.now()
            log.write(f"Database export {label} > {output} at {now}\n".encode())
            log.flush()

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=log,
            )

            try:
                with gzip.open(output, "wb") as gz:
                    for chunk in iter(lambda: process.stdout.read(1048576), b""):
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
