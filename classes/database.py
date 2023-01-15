import logging, os

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
        os.system(f"mysqldump -u {db_user} -p{db_password} {db_name} | gzip > {output}")
    
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