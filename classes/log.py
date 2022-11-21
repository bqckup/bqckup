import sqlite3, os, logging, time
from config import BQ_PATH
from contextlib import closing

class Log:
    __TABLE__ = 'logs' # Also DB name
    __DB_PATH__ = os.path.join(BQ_PATH, 'database', f"{__TABLE__}.db")
    DB_BACKUP = "Database Backup"
    FILES_BACKUP = "Files Backup"
    
    def __init__(self):
        if not os.path.exists(self.__DB_PATH__):
            open(self.__DB_PATH__, "w").close()
            
        try:        
            self.query(f"SELECT * FROM {self.__TABLE__}")
        except sqlite3.OperationalError as e:
            logging.error(e)
            self.create_table()
            
    def create_connection(self):
        self._connection = sqlite3.connect(self.__DB_PATH__)
        self._cursor = self._connection.cursor()
    
    def write(self, data: dict) -> None:
        query = f"INSERT INTO {self.__TABLE__} (name, file_size, file_path, description, created_at, type) VALUES ('{data['name']}', '{data['file_size']}', '{data['file_path']}', '{data['description']}', '{int(time.time())}', '{data['type']}');"
        return self.query(query)

    """
        type:
         - database
         - files
    """
    def create_table(self) -> None:
        self.query('CREATE TABLE "logs" ( "id" INTEGER PRIMARY KEY AUTOINCREMENT, "name" TEXT, "file_size" BIGINT, "file_path" TEXT, "description" TEXT, "created_at" INTEGER, type TEXT)')
    
    def query(self, q: str):
        self.create_connection()
        result = self._cursor.execute(q)
        self._connection.commit()
        self._connection.close()
        return result
