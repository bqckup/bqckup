import yaml

class Yml_Parser:
    def __init__(self):
        pass

    @staticmethod
    def parse(path: str) -> dict:
        with open(path, "r") as stream:
            try:
                parsed_yml = yaml.safe_load(stream)
                if 'site' in path:
                    parsed_yml = Yml_Parser.set_default_site(parsed_yml)
            except yaml.YAMLError as exc:
                raise Exception(exc)
            finally:
                stream.close()
                
            return parsed_yml
        
    @staticmethod
    def set_default_site(parsed_yml: dict) -> dict:
        defaults = {
            "bqckup": {
                "enabled": True,
                "options": {
                    "follow_symlink": False
                }
            }
        }
        return Yml_Parser._merge_dicts(defaults, parsed_yml)

    @staticmethod
    def _merge_dicts(default: dict, custom: dict) -> dict:
        for key, value in default.items():
            if key not in custom:
                custom[key] = value
            elif isinstance(value, dict):
                custom[key] = Yml_Parser._merge_dicts(value, custom[key])
        return custom