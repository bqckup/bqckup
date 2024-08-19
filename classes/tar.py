import tarfile, os
from typing import Union

class Tar:
    def __init__(self):
        pass
    
    def compress(self, source: Union[str, list, dict], output: str, exclude_paths = []) -> str:

        def exclude_path(tarinfo, folder_name):
            file_name = tarinfo.name.replace(folder_name, "")
            for exclude_path in exclude_paths:
                if file_name.startswith(exclude_path):
                    print(f"Excluding {tarinfo.name}")
                    return None
            return tarinfo
    
        with tarfile.open(output, "w:gz") as tar:
            if type(source) != str:
                for path in source:
                    # remove last folder to get base path
                    folder_name = path.split("/")[-1] + "/"

                    if not os.path.exists(path):
                        print(f"Skipped, {path} not found")
                        continue
                    tar.add(path, arcname=os.path.basename(path), filter=lambda tarinfo: exclude_path(tarinfo, folder_name))
            else:
                tar.add(path, arcname=os.path.basename(path))
            tar.close()
        return output