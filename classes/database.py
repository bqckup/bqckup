import logging, os
import subprocess

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