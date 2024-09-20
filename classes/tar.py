import tarfile
import os
from typing import Union, List, Dict

class Tar:
    def __init__(self):
        pass

    def compress(self, source: Union[str, List[str], Dict], output: str, symlink: bool, exclude_paths: List[str] = []) -> str:
        
        def exclude_path(tarinfo, folder_name):
            file_name = tarinfo.name.replace(folder_name, "")
            for exclude_path in exclude_paths:
                if file_name.startswith(exclude_path):
                    print(f"Excluding: {tarinfo.name}")
                    return None
            return tarinfo

        if isinstance(source, list):
            base_name = os.path.basename(source[0])
        else:
            base_name = os.path.basename(source)

        if os.path.isdir(output):
            output_path = os.path.join(output, f"{base_name}.tar.gz")
        else:
            output_path = output

        with tarfile.open(output_path, "w:gz", dereference=symlink) as tar:
            if isinstance(source, list):
                for path in source:
                    if not os.path.exists(path):
                        print(f"Skipped: {path} not found")
                        continue

                    tar.add(path, arcname=base_name, filter=lambda tarinfo: exclude_path(tarinfo, base_name))
            else:
                if not os.path.exists(source):
                    print(f"Skipped: {source} not found")
                    return output_path

                tar.add(source, arcname=base_name, filter=lambda tarinfo: exclude_path(tarinfo, base_name))

        return output_path