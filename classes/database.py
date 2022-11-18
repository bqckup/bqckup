import logging

# Database Exceptions
class DatabaseException(Exception):
    pass


"""
should be compatible with to other database type
"""
class Database:
    # mysqli is temporary
    def __init__(self, type = "mysql"):
        self.type = type.lower()
        
    def test_connection(self, credentials: dict) -> bool:
        import mysql.connector
        try:
            c = mysql.connector.connect(**credentials)
        except mysql.connector.Error as e:
            logging.error(e)
            raise DatabaseException("Failed to connect database, see log for details")
        else:
            c.close()