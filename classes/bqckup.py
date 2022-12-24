import os, time
from classes.database import Database
from classes.tar import Tar
from classes.file import File
from classes.yml_parser import Yml_Parser
from models.log import Log
from config import BQ_PATH, CONFIG_BACKUP
from classes.s3 import s3
from helpers import difference_in_days, get_today, time_since
from datetime import datetime

class Bqckup:
    def __init__(self):
        self.backup_config_path = os.path.join(BQ_PATH, "sites")
        
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
        return Log().select().where((Log.name == name) & (Log.status != Log.__FAILED__)).order_by(Log.id.desc()).first()
        
    def get_logs(self, name: str):
        return list(Log().select().where(Log.name == name))
    
    def backup(self, force:bool = False):
        backups = self.list()
        if not backups:
            print("No backups found")
            return
        for i in backups:
            backup = backups[i]
            last_log = self.get_last_log(backup['name'])
            if last_log:
                interval = backup['options']['interval']
                last_backup = last_log.created_at
                last_backup = difference_in_days(time.time(), last_backup)
                to_compare = self._interval_in_number(interval)
                
                # Not enough time has passed
                if not force and last_backup < to_compare:
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
        try:
            bqckup_config_location = os.path.join(self.backup_config_path, backup_config)
            backup = Yml_Parser.parse(bqckup_config_location)['bqckup']
            backup_folder = f"{backup.get('name')}/{get_today()}"
            
            tmp_path = os.path.join(BQ_PATH, 'tmp', f"{backup.get('name')}")

            if Log().select().where((Log.name == backup.get('name')) & (Log.status == Log.__ON_PROGRESS__)).exists():
                print(f"Backup for {backup.get('name')} is already running...")
                return False
            
            if not File().is_exists(tmp_path):
                os.makedirs(tmp_path)
                
            _s3 = s3(storage_name=backup.get('options').get('storage'))
            
            compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
            
            log_compressed_files = Log().write({
                "name": backup['name'],
                "file_size": 0,
                "file_path": compressed_file,
                "description": "File backup is in progress...",
                "type": Log.__FILES__,
                "object_name": f"{_s3.root_folder_name}/{backup_folder}/{os.path.basename(compressed_file)}",
                "storage": backup['options']['storage']
            })
            
            print("\nCompressing files...\n")
            
            compressed_file = Tar().compress(backup.get('path'), compressed_file)
            
            Log().update(file_size=os.stat(compressed_file).st_size).where(Log.id == log_compressed_files.id).execute()
            
            sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
            if backup.get('database'):
                print("Exporting database...\n")
                 # Database export
                
                log_database = Log().write({
                    "name": backup['name'],
                    "file_size": 0,
                    "file_path": sql_path,
                    "description": "Database Backup is in Progress",
                    "type": Log.__DATABASE__,
                    "object_name": f"{_s3.root_folder_name}/{backup_folder}/{os.path.basename(sql_path)}",
                    "storage": backup['options']['storage']
                })
                
                Database().export(
                    sql_path,
                    db_user=backup.get('database').get('user'),
                    db_password=backup.get('database').get('password'),
                    db_name=backup.get('database').get('name'),
                )
                
                Log().update(file_size=os.stat(sql_path).st_size).where(Log.id == log_database.id).execute()
            
                # Cleaning Old Folder
            list_folder = _s3.list(
                f"{_s3.root_folder_name}/{backup.get('name')}/",
                '/'
            )
            
            if list_folder.get('KeyCount') >= int(backup.get('options').get('retention')):
                last_folder_prefix = list_folder.get('CommonPrefixes')[0].get('Prefix')
                last_folder = _s3.list(last_folder_prefix)
                for obj in last_folder.get("Contents"):
                    _s3.delete(obj.get("Key"))
            
            # bqckup config
            if CONFIG_BACKUP:
                _s3.upload(bqckup_config_location, f"config/{backup.get('name')}.yml", False)
                _s3.upload(os.path.join(BQ_PATH, 'config', 'storages.yml'), 'config/storages.yml', False)

            if os.path.exists(compressed_file):
                print(f"\nUploading {compressed_file}\n")
                _s3.upload(
                    compressed_file,
                    f"{backup_folder}/{os.path.basename(compressed_file)}"
                )
                
            if os.path.exists(sql_path):
                print(f"\n\nUploading {sql_path}\n")
                _s3.upload(
                    sql_path,
                    f"{backup_folder}/{os.path.basename(sql_path)}"
                )
                
                if not backup.get('options').get('save_locally'):
                    os.unlink(compressed_file)
                    os.unlink(sql_path)
                
                Log().update_status(log_database.id, Log.__SUCCESS__, "Database Backup Success")
                
            Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success")
            print(f"\nBackup for {backup.get('name')} is done!\n")
        except Exception as e:
            import traceback
            traceback.print_exc()
            
            # Separate this two error by it's own exceptions
            if 'log_compressed_files' in locals():
                Log().update_status(log_compressed_files.id, Log.__FAILED__, f"File Backup Failed: {e}")
                
            if 'log_database' in locals():
                Log().update_status(log_database.id, Log.__FAILED__, f"Database Backup Failed: {e}")
                
            print(f"[{backup.get('name')}] Error: {e}.")
    
    def remove(self):
        pass