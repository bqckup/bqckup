import tarfile, os
from typing import Union

class Tar:
    def __init__(self):
        pass
    
    def compress(self, source: Union[str, list, dict], output: str, symlink: bool, exclude_paths = []) -> str:

        def exclude_path(tarinfo, folder_name):
            file_name = tarinfo.name.replace(folder_name, "")
            for exclude_path in exclude_paths:
                if file_name.startswith(exclude_path):
                    print(f"Excluding {tarinfo.name}")
                    return None
            return tarinfo

        def add_path(tar, path, arcname, added_files):
            if os.path.islink(path):
                if symlink:
                    real_path = os.path.realpath(path)
                    if real_path not in added_files:
                        tar.add(real_path, arcname=arcname, filter=lambda tarinfo: exclude_path(tarinfo, folder_name))
                        added_files.add(real_path)
                else:
                    print(f"Excluding symlink {path}")
            else:
                if path not in added_files:
                    tar.add(path, arcname=arcname, filter=lambda tarinfo: exclude_path(tarinfo, folder_name))
                    added_files.add(path)
    
        added_files = set()
        with tarfile.open(output, "w:gz") as tar:
            if type(source) != str:
                for path in source:
                    # remove last folder to get base path
                    folder_name = path.split("/")[-1] + "/"

                    if not os.path.exists(path):
                        print(f"Skipped, {path} not found")
                        continue
                    add_path(tar, path, arcname=os.path.basename(path), added_files=added_files)
            else:
                add_path(tar, source, arcname=os.path.basename(source), added_files=added_files)
            tar.close()
        return output