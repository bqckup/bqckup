import os, time, tarfile
from classes.database import Database
from classes.file import File
from classes.yml_parser import Yml_Parser
from classes.log import Log
from config import BQ_PATH
from classes.s3 import s3
from helpers import difference_in_days, get_today
from datetime import datetime

class Bqckup:
    def __init__(self):
        self.backup_config_path = os.path.join(BQ_PATH, ".config", "bqckups")
        
        if not os.path.exists(self.backup_config_path):
            os.makedirs(self.backup_config_path)
            
    def detail(self, name: str):
        backups = self.list()
        
        for i in backups:
            if backups[i]['name'] == name:
                return backups[i]
            
        return None
    
    def list(self):
        files = File().get_file_list(self.backup_config_path)
        results = {}
        
        for index, file in enumerate(files):
            file_name = os.path.basename(file)
            parsed_content = Yml_Parser.parse(file)
            bqckup = parsed_content['bqckup']
            log = self.get_last_log(bqckup['name'])
            results[index] = {}
            results[index] = bqckup
            results[index]['file_name'] = file_name
            results[index]['last_backup'] = log[5] if log else 0
            results[index]['next_backup'] = False
            
        return results
    
    def get_next_backup(self, name: str):
        detail = self.detail(name)
        
        if detail['options']['interval'] == 'weekly':
            intervalNumber = 7
        elif detail['options']['interval'] == 'monthly':
            intervalNumber = 30
        else:
            intervalNumber = 1
            
    def get_last_log(self, name:str):
        logs = self.get_logs(name)
        return logs[0] if logs else None
        
    def get_logs(self, name: str):
        return Log().list(name)
    
    def backup(self):
        backups = self.list()
        for i in backups:
            backup = backups[i]
            last_log = self.get_last_log(backup['name'])
            if last_log:
                interval = backup['options']['interval']
                last_backup = last_log[5] # 5 is Last Backup
                last_backup = difference_in_days(last_backup, time.time())
                
                if interval == 'daily':
                    to_compare = 1
                elif interval == 'weekly':
                    to_compare = 7
                else:
                    to_compare = 30 # monthly
              
                
                # Not enough time has passed
                if last_backup <= to_compare:
                    print(f"\nBackup for {backup['name']} is not needed yet...")
                    print(f"Current Date: {time.strftime('%d/%m/%Y', time.localtime())}")
                    print(f"Last Backup: {datetime.fromtimestamp(last_log[5]).strftime('%d/%m/%Y')}")
                    print(f"Day passed: { 0 if last_backup < 0 else last_backup }")
                    print(f"Interval: {interval}\n")
                    return False
                
            self.do_backup(backup['file_name'])
            
    def do_backup(self, backup_config: str):
        backup = Yml_Parser.parse(
            os.path.join(BQ_PATH,'.config','bqckups', backup_config)
        )['bqckup']
        
        tmp_path = os.path.join(BQ_PATH, "tmp", f"{backup['name']}")
        
        if not File().is_exists(tmp_path):
            os.makedirs(tmp_path)
         
        print("Compressing files ... ")    
        file_path = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
        with tarfile.open(file_path, "w:gz") as tar:
            for path in backup['path']:
                if not File().is_exists(path):
                    print(f"Skipped, {path} not found")
                    continue
                tar.add(path, arcname=os.path.basename(path))
            tar.close()
        
        db_backup_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
        log = Log()
        
        print("Exporting Database ...\n")
        Database().export(
            db_backup_path,
            db_user=backup['database']['user'],
            db_password=backup['database']['password'],
            db_name=backup['database']['name']
        )
        
        _s3 = s3(storage_name=backup['options']['storage'])
        
        list_folder = _s3.list(f"{_s3.root_folder_name}/{backup['name']}/", '/')
        
        if list_folder.get('KeyCount') >=  int(backup['options']['retention']):
            last_folder_prefix = list_folder.get("CommonPrefixes")[0].get("Prefix")
            last_folder = _s3.list(last_folder_prefix)
            for obj in last_folder.get("Contents"):
                _s3.delete(obj.get("Key"))
                        
        backupFolder = f"{backup['name']}/{get_today()}"
        try:
            _s3.upload(
                file_path,
                f"{backupFolder}/{os.path.basename(file_path)}"
            )
            _s3.upload(
                db_backup_path,
                f"{backupFolder}/{os.path.basename(db_backup_path)}"
            )
        except Exception as e:
            print(f"Bqckup failed, {e}")
        else:
            log.write({
                "name": backup['name'],
                "file_size": os.stat(file_path).st_size,
                "file_path": file_path,
                "description": "File Backup Success",
                "type": log.FILES_BACKUP,
                "object_name": f"{_s3.root_folder_name}/{backupFolder}/{os.path.basename(file_path)}",
                "storage": backup['options']['storage']
            })
            
            log.write({
                "name": backup['name'],
                "file_size": os.stat(db_backup_path).st_size,
                "file_path": db_backup_path,
                "description": "Database Backup Success",
                "type": log.DB_BACKUP,
                "object_name": f"{_s3.root_folder_name}/{backupFolder}/{os.path.basename(db_backup_path)}",
                "storage": backup['options']['storage']
            })
        
            if not backup['options']['save_locally']:
                os.unlink(db_backup_path)
                os.unlink(file_path)
        
    def remove(self):
        pass