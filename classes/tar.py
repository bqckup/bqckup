import tarfile, os
from typing import Union

class Tar:
    def __init__(self):
        pass
    
    def compress(self, source: Union[str, list, dict], output: str) -> str:
        with tarfile.open(output, "w:gz") as tar:
            if type(source) != str:
                for path in source:
                    if not os.path.exists(path):
                        print(f"Skipped, {path} not found")
                        continue
                    tar.add(path, arcname=os.path.basename(path))
            else:
                tar.add(path, arcname=os.path.basename(path))
            tar.close()
        return output