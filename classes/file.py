import os
from config import BQ_PATH
from pathlib import Path

class File:
    def __init__(self):
        pass
    
    def is_exists(self, path: str):
        return os.path.exists(path)
    
    def create_file(self, path: str, content=False):
        f = open(path, "w")
        if content:
            f.write(content)
        f.close()
        
    def get_content(self, path: str):
        return Path(path).read_text()
    
    def get_file_list(self, path: str):
        return [os.path.join(path, f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    
    def get_list(self, path: str):
        pass