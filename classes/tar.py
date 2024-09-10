import tarfile, os
from typing import Union

class Tar:
    def __init__(self):
        pass

    def compress(self, source: Union[str, list, dict], output: str, exclude_paths=[]) -> str:
        
        def exclude_path(tarinfo, folder_name):
            file_name = tarinfo.name.replace(folder_name, "")
            for exclude_path in exclude_paths:
                if file_name.startswith(exclude_path):
                    print(f"Excluding {tarinfo.name}")
                    return None
            return tarinfo

        with tarfile.open(output, "w:gz", dereference=True) as tar:
            if isinstance(source, list):
                for path in source:
                    folder_name = path.split("/")[-1] + "/"

                    if not os.path.exists(path):
                        print(f"Skipped, {path} not found")
                        continue
                    
                    tar.add(path, arcname=os.path.basename(path), filter=lambda tarinfo: exclude_path(tarinfo, folder_name), recursive=True)
            else:
                tar.add(source, arcname=os.path.basename(source), recursive=True)
        return output