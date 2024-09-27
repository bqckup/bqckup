import tarfile
import os
from typing import Union, List, Dict
from rich.progress import Progress, SpinnerColumn, TextColumn
from classes.progress import ProgressSpinner

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

        with ProgressSpinner("Compressing files..."):
            with tarfile.open(output, "w:gz", dereference=symlink) as tar:
                if isinstance(source, list):
                    for path in source:
                        folder_name = path.split("/")[-1] + "/"

                        if not os.path.exists(path):
                            print(f"Skipped, {path} not found")
                            continue

                        if not symlink and os.path.islink(path):
                            print(f"Skipped, {path} is a symlink")
                            continue

                        tar.add(path, arcname=os.path.basename(path), filter=lambda tarinfo: exclude_path(tarinfo, folder_name), recursive=True)
                else:
                    if not symlink and os.path.islink(source):
                        print(f"Skipped, {source} is a symlink")
                    else:
                        tar.add(source, arcname=os.path.basename(source), recursive=True)
        return output