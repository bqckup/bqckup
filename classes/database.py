import gzip
import logging
import subprocess
from typing import Any, List, Dict


# Database Exceptions
class DatabaseException(Exception):
    pass


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
    ) -> None:
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

        with gzip.open(output, "wb") as f:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            for chunk in iter(lambda: process.stdout.read(4096), b""):
                f.write(chunk)

            process.wait()

            if process.returncode != 0:
                error = process.stderr.read().decode()
                raise Exception(error)

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
