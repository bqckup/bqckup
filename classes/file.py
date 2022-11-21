import os
from config import BQ_PATH
from pathlib import Path

class File:
    def __init__(self):
        pass
    
    def is_exists(self, path: str):
        return os.path.exists(path)
    
    def create_file(self, path: str):
        pass
        # return with open(path, 'w+').close()
        
    def get_content(self, path: str):
        return Path(path).read_text()
    
    def get_file_list(self, path: str):
        bqckups_dir = os.path.join(BQ_PATH, '.config', 'bqckups')
        return [os.path.join(bqckups_dir, f) for f in os.listdir(path) if os.path.isfile(os.path.join(bqckups_dir, f))]
    
    def get_list(self, path: str):
        pass