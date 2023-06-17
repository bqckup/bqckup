import shutil, requests
class Server:
    def __init__(self):
        pass
    
    def get_storage_information(self):
        return shutil.disk_usage('/')
    
    def ip(self):
        try:
            return requests.get('https://ifconfig.me').text
        except Exception:
            print("Failed to get IP address, using socket instead")
            return "0.0.0.0"
