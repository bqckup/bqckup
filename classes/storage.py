import os
from classes.yml_parser import Yml_Parser
from config import BQ_PATH

class Storage:
    def __init__(self):
        self.config_path = os.path.join(BQ_PATH, '.config', 'storages.yml')
    
    def get_primary_storage(self):
        parsed_config = Yml_Parser().parse(self.config_path)
        for storage in parsed_config['storages']:
            pass