import os, shutil

def remove_folder(path):
    if os.path.exists(path):
        shutil.rmtree(path)
