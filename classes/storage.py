from classes.yml_parser import Yml_Parser
from helpers.hook import get_credential
from constant import STORAGE_CONFIG_PATH
from typing import Dict, List, Union

class StorageException(Exception): ...

class Storage:
    def __init__(self):
        self.parsed_storage = Yml_Parser.parse(STORAGE_CONFIG_PATH)

    def get_all_storage(self) -> List[Dict]:
        return [self.get_storage_detail(storage_name) for storage_name in self.list()]

    def get_storage_detail(self, name: str) -> Dict:
        try:
            storage: dict = self.parsed_storage["storages"][name]

            if remote_url := storage.get("remote_url"):
                return {
                    **storage,
                    **get_credential(remote_url),
                }  # Merge config from file and remote

            return storage

        except KeyError:
            raise StorageException(f"Storage {name} doesn't exists")

    def get_parsed_storage(self):
        return self.parsed_storage

    def get_primary_storage(self) -> Union[Dict, None]:
        storages = self.list()

        if len(storages) >= 1:
            return storages[0]

        parsed_config = self.parsed_storage

        for storage in storages:
            if "primary" not in parsed_config["storages"][storage]:
                continue
            if parsed_config["storages"][storage]["primary"].lower() == "yes":
                return parsed_config["storages"][storage]

        return None

    def list(self) -> List[str]:
        try:
            return list(self.parsed_storage["storages"].keys())
        except Exception:
            return []
