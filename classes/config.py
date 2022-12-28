import os, configparser
from constant import BQ_PATH

class Config:
    def __init__(self):
        self.config_path = os.path.join(BQ_PATH, 'bqckup.cnf')
        self.config_parser = configparser.ConfigParser()
        self.config_parser.read(self.config_path)
    
    def read(self, section, key):
        try:
            return self.config_parser[section][key]
        except Exception as e:
            print(f"Failed to read config, {str(e)}")
            print(f"Check if {self.config_path} exists and has the correct format")
            return None