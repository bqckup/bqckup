import os

class File:
    def __init__(self):
        pass
    
    def is_exists(self, path: str):
        return os.path.exists(path)
    
    def create_file(self, path: str):
        with open(path, 'w+').close()