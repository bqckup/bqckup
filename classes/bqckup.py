import os
from classes.yml_parser import yaml
from config import BQ_PATH
class Bqckup:
    def __init__(self):
        self.backup_config_path = os.path.join(BQ_PATH, ".config", "bqckups")
        
        if not os.path.exists(self.backup_config_path):
            os.makedirs(self.backup_config_path)
    
    def list(self):
        pass
    