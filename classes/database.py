import logging, os
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
    
    def __init__(self, type = "mysql"):
        self.type = type.lower()
        
    def export(self, output: str, db_user: str, db_password: str, db_name: str) -> None:
        command = [
                "mysqldump",
                f"--user={db_user}",
                f"--password={db_password}",
                db_name,
                "--no-tablespaces ",
                "--skip-dump-date",
                "|",
                "gzip",
                ">",
                output
            ]        
        with open(os.devnull, 'w') as devnull:
                subprocess.run(" ".join(command), shell=True, stdout=devnull, stderr=devnull)
    
    def test_connection(self, credentials: dict) -> bool:
        import mysql.connector
        try:
            c = mysql.connector.connect(
                user=credentials['user'],
                host=credentials['host'],
                password=credentials['password'],
                database=credentials['name'])
        
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
            # if the key is missing, default to backing up the database
            if not ("enabled" in database or "enable" in database):
                result.append(database)
                continue

            elif not (database.get("enabled") or database.get("enable")):
                continue

            result.append(database)

        return result
