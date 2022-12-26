from peewee import *
import os, time, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from constant import BQ_PATH

database = SqliteDatabase(
    os.path.join(BQ_PATH, 'database', 'bqckup.db'),
    pragmas={ 'journal_mode': 'wal', 'cache_size': -1024 * 64}
)

class BaseModel(Model):
    class Meta:
        database = database  
        
class Log(BaseModel):
    # constants
    __SUCCESS__ = 1
    __FAILED__ = 2
    __ON_PROGRESS__ = 3
    __DATABASE__ = 'database'
    __FILES__ = 'files'
    
    id = AutoField()
    name = CharField()
    file_path = CharField()
    file_size = IntegerField()
    description = TextField()
    created_at = IntegerField()
    type = TextField()
    storage = CharField()
    object_name = TextField()
    status = IntegerField()
    
    # TODO: Fix this duplicate query
    def update_status(self, id: int, status: int, description=False):
        self.update(status=status).where(self.id == id).execute()
        if description:
            self.update(description=description).where(self.id == id).execute()    
            
    def write(self, data: dict):
        return self.create( name=data['name'], file_path=data['file_path'], file_size=data['file_size'], description=data['description'], created_at=int(time.time()), type=data['type'], storage=data['storage'], object_name=data['object_name'], status=self.__ON_PROGRESS__ )    

# if __name__ == '__main__':
#     xx = Log().write({
#         "name":"test",
#         "file_path":"test",
#         "file_size":123,
#         "description":"test",
#         "type":"test",
#         "storage":"test",
#         "object_name":"test"
#     })
#     Log().update_status(xx, Log.__SUCCESS__)
