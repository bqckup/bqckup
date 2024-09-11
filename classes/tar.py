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

        if not symlink:
            with tarfile.open(output_path, "w:gz") as tar:
                if isinstance(source, list):
                    for path in source:
                        if not os.path.exists(path):
                            print(f"Skipped: {path} not found")
                            continue

                        for root, dirs, files in os.walk(path):
                            if os.path.islink(root):
                                print(f"Excluding symlink directory: {root}")
                                continue
                            
                            for file in files:
                                full_path = os.path.join(root, file)
                                if os.path.islink(full_path):
                                    print(f"Excluding symlink file: {full_path}")
                                    continue
                                
                                arcname = os.path.join(base_name, os.path.relpath(full_path, path))
                                tar.add(full_path, arcname=arcname, filter=lambda tarinfo: exclude_path(tarinfo, base_name))
                else:
                    if not os.path.exists(source):
                        print(f"Skipped: {source} not found")
                        return output_path

                    symlink_list= []
                    for root, dirs, files in os.walk(source):
                        for dir in dirs:
                            dir_path = os.path.join(root, dir)
                            if os.path.islink(dir_path):
                                symlink_list.append(dir_path)
                                continue
                        
                        for file in files:
                            full_path = os.path.join(root, file)
                            if os.path.islink(full_path):
                                symlink_list.append(full_path)
                                continue
                            
                            arcname = os.path.join(base_name, os.path.relpath(full_path, source))
                            tar.add(full_path, arcname=arcname, filter=lambda tarinfo: exclude_path(tarinfo, base_name))

                    if symlink_list:
                        print("Symlinks excluded from compression:")
                        for symlink in symlink_list:
                            print(symlink)
        else:
            with tarfile.open(output_path, "w:gz", dereference=True) as tar:
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