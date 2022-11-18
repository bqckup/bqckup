import sqlite3, os, logging
from config import BQ_PATH

class Log:
    __TABLE__ = 'logs' # Also DB name
    __DB_PATH__ = os.path.join(BQ_PATH, 'database', f"{__TABLE__}.db")
    
    def __init__(self):
        if not os.path.exists(self.__DB_PATH__):
            open(self.__DB_PATH__, "w").close()
            
        self._connection = sqlite3.connect(self.__DB_PATH__)
        self._cursor = self._connection.cursor()
        try:        
            self.query(f"SELECT * FROM {self.__TABLE__}")
        except sqlite3.OperationalError as e:
            logging.error(e)
            self.create_table()
    
    def write(self, data: dict) -> None:
        pass
    
    """
        type:
         - database
         - files
    """
    def create_table(self) -> None:
        self.query('CREATE TABLE "logs" ( "id" INTEGER PRIMARY KEY AUTOINCREMENT, "name" TEXT, "file_size" BIGINT, "file_path" TEXT, "description" TEXT, "created_at" INTEGER, type TEXT)')
    
    def query(self, q: str):
        return self._cursor.execute(q)