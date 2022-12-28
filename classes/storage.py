import os
from classes.yml_parser import Yml_Parser
from constant import BQ_PATH

class StorageException(Exception): pass
class Storage:
    def __init__(self):
        self.config_path = os.path.join(BQ_PATH, 'config', 'storages.yml')
        self.parsed_storage = Yml_Parser.parse(self.config_path)

    def validate_config(self):
        pass

    def get_parsed_storage(self):
        return self.parsed_storage

    def list(self) -> list:
        return list(self.parsed_storage['storages'].keys())

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