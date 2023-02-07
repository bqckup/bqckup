from classes.yml_parser import Yml_Parser
from constant import STORAGE_PATH

class StorageException(Exception): pass
class Storage:
    def __init__(self):
        self.parsed_storage = Yml_Parser.parse(STORAGE_PATH)

    def get_parsed_storage(self):
        return self.parsed_storage
    
    def list(self):
        try:
            return list(self.parsed_storage['storages'].keys())
        except:
            return list()

    def get_storage_detail(self, name: str) -> dict:
        try:
            return self.parsed_storage['storages'][name]
        except:
            raise StorageException(f"Storage {name} doesn't exists")
        
    def get_primary_storage(self):
        storages = self.list()
        
        if len(storages) >= 1:
            return storages[0]
        
        parsed_config = self.parsed_storage
        
        for storage in storages:
            if 'primary' not in parsed_config['storages'][storage]:
                continue
            if parsed_config['storages'][storage]['primary'].lower() == 'yes':
                return parsed_config['storages'][storage]
            
        return None