import tarfile, os
from typing import Union

class Tar:
    def __init__(self):
        pass
    
    def compress(self, source: Union[str, list, dict], output: str, exclude_paths = []) -> str:
        with tarfile.open(output, "w:gz") as tar:
            if type(source) != str:
                for path in source:
                    # remove last folder to get base path
                    folder_name = path.split("/")[-1]
                    base_path = path.replace(folder_name, "")

                    if not os.path.exists(path):
                        print(f"Skipped, {path} not found")
                        continue
                    tar.add(path, arcname=os.path.basename(path), filter=lambda tarinfo: self.exclude_path(tarinfo, exclude_paths, base_path))
            else:
                tar.add(path, arcname=os.path.basename(path))
            tar.close()
        return output

    def exclude_path(self, tarinfo, exclude_paths, path):
        # Check if the path should be excluded
        nameFile = path + tarinfo.name
        for exclude_path in exclude_paths:
            if nameFile.startswith(exclude_path):
                print(f"Excluding {tarinfo.name}")
                return None
        return tarinfo