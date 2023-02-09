from abc import ABC, abstractmethod
from classes.file import File
from classes.yml_parser import Yml_Parser
import os

class HasYML(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def get_config_path(self):
        pass

    def remove(self, name: str):
        config = os.path.join(self.get_config_path(), f"{name}.yml")

        if not os.path.exists(config):
            raise Exception(f"{config} doesn't exists")
        
        os.unlink(config)

    def save_config(self, name: str, data: dict):
        import ruamel.yaml as yaml
        config_path = os.path.join(self.get_config_path(), f"{name}.yml")
        with open(config_path, "w+") as stream:
            yaml = yaml.YAML()
            yaml.indent(sequence=4, offset=2)
            yaml.dump(data, stream)

    def get_list_file_config(self):
        return [f for f in File().get_file_list(self.get_config_path()) if f.endswith('.yml')]

    def _parse_config(self, name: str):
        return Yml_Parser.parse(os.path.join(self.get_config_path(), f"{name}.yml"))
    
    def _parse_all_config(self):
        results = []
        for config in self.get_list_file_config():
            parsed_config = Yml_Parser.parse(config)
            parsed_config['name'] = os.path.basename(config).replace('.yml', '')
            results.append(parsed_config)

        return list(results)