import tarfile, os

class Tar:
    def __init__(self):
        pass
    
    def compress(output: str, target: str):
        with tarfile.open(output, "w:gz") as tar:
            tar.add(target, arcname=os.path.basename(target))
        return output