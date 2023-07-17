import shutil, requests
class Server:
    def __init__(self):
        pass
    
    def get_storage_information(self):
        return shutil.disk_usage('/')