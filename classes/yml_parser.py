import yaml

class Yml_Parser:
    def __init__(self):
        pass

    def parse(path: str) -> dict:
        with open(path, "r") as stream:
            try:
                parsed_yml = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise Exception(exc)
            finally:
                stream.close()
                
            return parsed_yml