import os
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

    def list(self):
        return self._parse_all_config()