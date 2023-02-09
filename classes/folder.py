import os
from classes.has_yml import HasYML
from constant import FOLDER_PATH

class Folder(HasYML):
    def __init__(self):
        pass

    def get_config_path(self):
        return FOLDER_PATH

    def add(self, **kwargs):
        data = {
            "path": [str(p) for p in kwargs['path']],
            "storage": [str(s) for s in kwargs['storage']],
            "retention": kwargs['retention'],
            "interval": kwargs['interval'],
            "save_locally": 'yes' if kwargs['save_locally'] else 'no',
            "notification": 'yes' if kwargs['notification'] else 'no'
        }

        self.save_config(kwargs['name'], data)


    def list(self):
        return self._parse_all_config()