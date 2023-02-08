from classes.has_yml import HasYML
from constant import STORAGE_PATH

class StorageException(Exception): pass
class Storage(HasYML):

    def __init__(self):
        pass

    def get_config_path(self):
        return STORAGE_PATH

    def add(self, **kwargs):
        name = kwargs['name']
        del kwargs['name']
        self.save_config(name, dict(kwargs.items()))


    # Delete Storage YML file
    def remove(self, name: str):
        import os
        storage_path = os.path.join(STORAGE_PATH, f"{name}.yml")

        if not os.path.exists(storage_path):
            raise StorageException(f"Storage [{name}] doesn't exists")
        
        os.unlink(storage_path)
    
    def list(self):
        return self._parse_all_config()