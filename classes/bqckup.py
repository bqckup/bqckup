import os, time
from classes.database import Database
from classes.tar import Tar
from classes.file import File
from classes.yml_parser import Yml_Parser
from models.log import Log
from config import BQ_PATH
from classes.s3 import s3
from helpers import difference_in_days, get_today, time_since
from datetime import datetime

class Bqckup:
    def __init__(self):
        self.backup_config_path = os.path.join(BQ_PATH, ".config", "bqckups")
        
        if not os.path.exists(self.backup_config_path):
            os.makedirs(self.backup_config_path)
            
    def validate_config(self):
        pass
            
    def detail(self, name: str):
        backups = self.list()
        
        for i in backups:
            if backups[i]['name'] == name:
                return backups[i]
            
        return None
    
    def _interval_in_number(self, interval: str) -> int:
        if interval == 'weekly':
            return 7
        elif interval == 'monthly':
            return 30
        return 1
    
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
            results[index]['last_backup'] = log.created_at if log else None
            
            # Next Backup
            results[index]['next_backup'] = False
            if results[index]['last_backup']:
                next_backup_in_date = datetime.fromtimestamp(results[index]['last_backup'] + (self._interval_in_number(bqckup['options']['interval']) * 86400)).strftime('%d/%m/%Y 00:00:00')
                results[index]['next_backup'] = time_since(datetime.strptime(next_backup_in_date, '%d/%m/%Y %H:%M:%S').timestamp(), time.time(), reverse=True)
            
        return results
            
    def get_last_log(self, name:str):
        return Log().select().where(Log.name == name).order_by(Log.id.desc()).first()
        
    def get_logs(self, name: str):
        return list(Log().select().where(Log.name == name))
    
    def self_backup(self):
        from config import SELF_BACKUP
        from classes.storage import Storage
        
        if not SELF_BACKUP:
            return False
        
        folder_to_backup= {'.config', 'database'}
        primary_storage = Storage().get_primary_storage()
        
        if not primary_storage:
            return False
        
        for folder in folder_to_backup:
            pass        
        
    def backup(self):
        backups = self.list()
        for i in backups:
            backup = backups[i]
            last_log = self.get_last_log(backup['name'])
            if last_log:
                interval = backup['options']['interval']
                last_backup = last_log.created_at # 5 is Last Backup
                last_backup = difference_in_days(time.time(), last_backup)
                to_compare = self._interval_in_number(interval)
                
                # Not enough time has passed
                if last_backup < to_compare:
                    print(f"\nBackup for {backup['name']} is not needed yet...")
                    print(f"Current Date: {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())}")
                    print(f"Last Backup: {datetime.fromtimestamp(last_log.created_at).strftime('%d/%m/%Y %H:%M:%S')}")
                    print(f"Next bqckup: {datetime.fromtimestamp(last_log.created_at + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}")
                    print(f"Day passed: {last_backup}")
                    print(f"Interval: {interval}\n")
                    return False
                
            self.do_backup(backup['file_name'])
    
    # Upload
    def do_backup(self, backup_config):
        backup = Yml_Parser.parse(
            os.path.join(BQ_PATH,'.config','bqckups', backup_config)
        )['bqckup']
        
        tmp_path = os.path.join(BQ_PATH, 'tmp', f"{backup['name']}")
        
        os.system(f"touch {tmp_path}/.running")
        
        if not File().is_exists(tmp_path):
            os.makedirs(tmp_path)
            
        compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
        
        print("\nCompressing files...\n")
        compressed_file = Tar().compress(backup.get('path'), compressed_file)
        
        # Database export
        sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
        if backup.get('database'):
            print("Exporting database...\n")
            Database().export(
                sql_path,
                db_user=backup.get('database').get('user'),
                db_password=backup.get('database').get('password'),
                db_name=backup.get('database').get('name'),
            )
        
        try:
            _s3 = s3(storage_name=backup.get('options').get('storage'))
            
            # Cleaning Old Folder
            list_folder = _s3.list(
                f"{_s3.root_folder_name}/{backup.get('name')}/",
                '/'
            )
            
            if list_folder.get('KeyCount') >= backup.get('options').get('retention'):
                last_folder_prefix = list_folder.get('CommonPrefixes')[0].get('Prefix')
                last_folder = _s3.list(last_folder_prefix)
                for obj in last_folder.get("Contents"):
                    _s3.delete(obj.get("Key"))
            
            backup_folder = f"{backup.get('name')}/{get_today()}"

            if os.path.exists(compressed_file):
                _s3.upload(
                    compressed_file,
                    f"{backup_folder}/{os.path.basename(compressed_file)}"
                )
                
                Log().write({
                    "name": backup['name'],
                    "file_size": os.stat(compressed_file).st_size,
                    "file_path": compressed_file,
                    "description": "File Backup Success",
                    "type": Log.__FILES__,
                    "object_name": f"{_s3.root_folder_name}/{backup_folder}/{os.path.basename(compressed_file)}",
                    "storage": backup['options']['storage']
                })
            
            if os.path.exists(sql_path):
                _s3.upload(
                    sql_path,
                    f"{backup_folder}/{os.path.basename(sql_path)}"
                )
                Log().write({
                    "name": backup['name'],
                    "file_size": os.stat(sql_path).st_size,
                    "file_path": sql_path,
                    "description": "Database Backup Success",
                    "type": Log.__DATABASE__,
                    "object_name": f"{_s3.root_folder_name}/{backup_folder}/{os.path.basename(sql_path)}",
                    "storage": backup['options']['storage']
                })
                if not backup.get('options').get('save_locally'):
                    os.unlink(compressed_file)
                    os.unlink(sql_path)
                
                os.system(f"rm {tmp_path}/.running")
                
                print(f"\nBackup for {backup.get('name')} is done!\n")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[{backup.get('name')}] Error: {e}.")
    
    def remove(self):
        pass