import configparser
from constant import CONFIG_PATH

class Config:
    def __init__(self):
        self.config_parser = configparser.ConfigParser()
        self.config_parser.read(CONFIG_PATH)
    
    def read(self, section, key, default=None, print_error: bool = True):
        try:
            return self.config_parser[section][key]
        except Exception as e:
            if not print_error:
                return False

            print(f"Failed to read config, {str(e)}")
            print(f"Check if {CONFIG_PATH} exists and has the correct format")
            return default
