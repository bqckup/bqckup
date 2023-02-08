import logging, os
from classes.has_yml import HasYML
from constant import DATABASE_PATH

# Database Exceptions
class DatabaseException(Exception):
    pass


class Database(HasYML):
    # mysqli is temporary
    SUPPORTED_DATABASE = ("mysql", "postgresql")
    
    def __init__(self):
        pass

    def get_config_path(self):
        return DATABASE_PATH

    def add(self, **kwargs):
        name = kwargs['name']
        del kwargs['name']
        self.save_config(name, dict(kwargs.items()))        

    def list(self):
        return self._parse_all_config()
        
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