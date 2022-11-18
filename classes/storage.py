import os
from classes.yml_parser import Yml_Parser
from config import BQ_PATH

class Storage:
    def __init__(self):
        self.config_path = os.path.join(BQ_PATH, '.config', 'storages.yml')

    def _parse_storage_config(self):
        return Yml_Parser.parse(self.config_path)

    def list(self) -> list:
        parsed_config = self._parse_storage_config()
        return list(parsed_config['storages'].keys())
        
    def get_primary_storage(self) -> str:
        storages = self.list()
        
        if len(storages) >= 1:
            return storages[0]
        
        parsed_config = self._parse_storage_config()
        
        for storage in storages:
            if 'primary' not in parsed_config['storages'][storage]:
                continue
            if parsed_config['storages'][storage]['primary'].lower() == 'yes':
                return storage
            
        return None