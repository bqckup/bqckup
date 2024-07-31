import os, time, shutil
from classes.database import Database
from classes.storage import Storage
from classes.tar import Tar
from classes.file import File
from classes.config import Config
from classes.yml_parser import Yml_Parser
from models.log import Log
from models.notification_log import NotificationLog
from constant import BQ_PATH, STORAGE_CONFIG_PATH, SITE_CONFIG_PATH
from classes.s3 import s3
from helpers import difference_in_days, get_today, time_since, get_server_ip
from datetime import datetime
from helpers.file_management import remove_folder
from hashlib import sha256
from lib.notifications.discord import send_notification
from rich import print

class ConfigExceptions(Exception):
    pass

class Bqckup:
    def __init__(self):
        
        if not os.path.exists(SITE_CONFIG_PATH):
            os.makedirs(SITE_CONFIG_PATH)
            
    def _send_notification(self, backup_name, messages, additional_data):
        fields = [
            {"name": "Server IP", "value": get_server_ip(), "inline": True},
            {"name": "Name", "value": backup_name, "inline": True},
            {"name": "Date", "value": get_today(format="%d-%B-%Y"), "inline":True},
        ]
        
        if additional_data:
            fields.append(additional_data)
            
        fields.append({"name": "Details", "value": messages, "inline": False})
        
        payload = {
            "embeds": [{
                "title": f"No Changes Detected",
                "description": f"This is an automated notification to inform you that the bqckup information.",
                "color": 15548997,
                "fields": fields,
                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
            }]
        }

          
        hashed_payload = sha256(str(payload).encode()).hexdigest()                    
        if not NotificationLog().select().where(NotificationLog.hash == hashed_payload).exists():
            send_notification(payload)
            NotificationLog().create(hash=hashed_payload, sent_at=int(time.time()))
            
    def validate_config(self, name: str) -> None:
        print(f"\nChecking {name} config ...")
        config = self.detail(name)
        if not config:
            raise ConfigExceptions(f"Backup {name} not found")

        # validate files
        for path in config.get('path'):
            if not os.path.exists(path):
                raise ConfigExceptions(f"Can't find {path}")
            
        # validate database
        if config.get('database'):
            if config.get('database').get('type') not in Database().SUPPORTED_DATABASE:
                raise ConfigExceptions(f"Database type {config.get('database').get('type')} not supported")
            
            Database(type=config.get('database').get('type')).test_connection({
                "user": config.get('database').get('user'),
                "password": config.get('database').get('password'),
                "host": config.get('database').get('host'),
                "name": config.get('database').get('name')
            })
            
        if config.get('options').get('provider') == 's3':
            Storage().get_storage_detail(config.get('options').get('storage'))
            
        print("All OK !")
            
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
        files = File().get_file_list(SITE_CONFIG_PATH)
        files = [file for file in files if file.endswith('.yml')]
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
            # self.validate_config(backup['name'])
            last_log = self.get_last_log(backup['name'])
            
            if last_log:
                interval = backup['options']['interval']
                last_backup = last_log.created_at
                last_backup = abs(difference_in_days(last_backup, time.time()))
                to_compare = self._interval_in_number(interval)
                
                # Not enough time has passed
                if not force and last_backup < to_compare:
                    print("\n=========================================")
                    print(f"Backup Name: {backup['name']}")
                    print(f"Current Date: {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())}")
                    print(f"Last Backup: {datetime.fromtimestamp(last_log.created_at).strftime('%d/%m/%Y %H:%M:%S')}")
                    print(f"Next bqckup: {datetime.fromtimestamp(last_log.created_at + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}")
                    print(f"Day passed: {last_backup}")
                    print(f"Interval: {interval}")
                    print(f"\nBackup for {backup['name']} is not needed yet...")
                    print("=========================================\n")
                    print(f"Visit: https://bqckup.com\n")
                    continue
                
            self.do_backup(backup['file_name'])
    
    # Upload
    def do_backup(self, backup_config):
        try:
            bqckup_config_location = os.path.join(SITE_CONFIG_PATH, backup_config)
            backup = Yml_Parser.parse(bqckup_config_location)['bqckup']
            backup_folder = f"{backup.get('name')}/{get_today()}"
            
            tmp_path = os.path.join(BQ_PATH, 'tmp', f"{backup.get('name')}")

            if Log().select().where((Log.name == backup.get('name')) & (Log.status == Log.__ON_PROGRESS__)).exists():
                print(f"Backup for {backup.get('name')} is already running...")
                return False
            
            if not File().is_exists(tmp_path):
                os.makedirs(tmp_path)
                
            compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
            
            log_compressed_files = Log().write({
                "name": backup['name'],
                "file_path": compressed_file,
                "description": "File backup is in progress...",
                "type": Log.__FILES__,
                "storage": backup['options']['storage']
            })
            
            print(f"\nStarting backup for {backup.get('name')}\n")
                                    
            print("Compressing files ...")
            compressed_file = Tar().compress(backup.get('path'),compressed_file)
            last_compressed_file_backup = Log().select().where((Log.name == backup.get('name')) & (Log.type == Log.__FILES__) & (Log.file_size != 0)).order_by(Log.id.desc()).get_or_none()
            
            
            print(f"Previous: {last_compressed_file_backup.file_size}")
            print(f"Current: {os.stat(compressed_file).st_size}")
            
            if last_compressed_file_backup and os.stat(compressed_file).st_size == last_compressed_file_backup.file_size:
                print(f"[red]\nBased on file size, there is no changes detected for {compressed_file}[/red]\n")
                self._send_notification(backup.get('name'), "Based on file size, there is no changes detected", {"name": "File name", "value": os.path.basename(compressed_file), "inline": False})                    

            
            Log().update(file_size=os.stat(compressed_file).st_size).where(Log.id == log_compressed_files.id).execute()
            
            sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
            
            if backup.get('database'):
                print("Exporting database...")
                 # Database export
                
                log_database = Log().write({
                    "name": backup['name'],
                    "file_path": sql_path,
                    "description": "Database Backup is in Progress",
                    "type": Log.__DATABASE__,
                    "storage": backup['options']['storage']
                })
                
                Database().export(
                    sql_path,
                    db_user=backup.get('database').get('user'),
                    db_password=backup.get('database').get('password'),
                    db_name=backup.get('database').get('name'),
                )
                
                
            last_log_db_backup = Log().select().where((Log.name == backup.get('name')) & (Log.type == Log.__DATABASE__) & (Log.file_size != 0)).order_by(Log.id.desc()).get_or_none()
            
            print(f"Previous: {last_log_db_backup.file_size}")
            print(f"Current: {os.stat(sql_path).st_size}")

            if last_log_db_backup and os.stat(sql_path).st_size == last_log_db_backup.file_size:
                print(f"\n[red]Based on file size, there is no changes detected for {sql_path}[/red]\n")
                self._send_notification(backup.get('name'), "Based on file size, there is no changes detected", {"name": "File name", "value": os.path.basename(sql_path), "inline": False})
            
            Log().update(file_size=os.stat(sql_path).st_size).where(Log.id == log_database.id).execute()
            
            if backup.get('options').get('provider') == 'local':
                destination = backup.get('options').get('destination')
                backup_path = os.path.join(destination, backup_folder)
                
                if not os.path.exists(backup_path):
                    os.makedirs(backup_path, exist_ok=True)
                
                backup_path_without_date = os.path.join(destination, backup['name'])
                folders = [folder for folder in os.listdir(backup_path_without_date) if os.path.isdir(os.path.join(backup_path_without_date, folder))]
                folders.sort(key=lambda x: os.path.getmtime(os.path.join(backup_path_without_date, x)))
                
                if len(folders) > int(backup.get('options').get('retention')):
                    shutil.rmtree(os.path.join(backup_path_without_date, folders[0]))                    
                    
                if os.path.exists(compressed_file):
                    shutil.move(compressed_file, os.path.join(backup_path, os.path.basename(compressed_file)))
                    Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success")
                
                if os.path.exists(sql_path):
                    shutil.move(sql_path, os.path.join(backup_path, os.path.basename(sql_path)))
                    Log().update_status(log_database.id, Log.__SUCCESS__, "Database Backup Success")
                    
            if backup.get('options').get('provider') == 's3':
                _s3 = s3(storage_name=backup.get('options').get('storage'))
            
                # Cleaning Old Folder
                list_folder = _s3.list(
                    f"{_s3.root_folder_name}/{backup.get('name')}/"
                )

                last_modified_object  = lambda obj: int(obj['LastModified'].strftime('%s'))
                
                sorted_version = []
                if list_folder.get('Contents'):
                    for obj in sorted(list_folder.get('Contents'), key=last_modified_object):
                        folder_name = obj['Key'].replace(os.path.basename(obj['Key']), '')
                        if folder_name not in sorted_version:
                            sorted_version.append(folder_name)

                if sorted_version and len(sorted_version) > int(backup.get('options').get('retention')):
                    for obj in list_folder.get('Contents'):
                        if obj.get('Key').startswith(os.path.dirname(sorted_version[0])):
                            _s3.delete(obj.get('Key'))
            
                # bqckup config
                if Config().read('bqckup', 'config_backup'):
                    _s3.upload(bqckup_config_location, f"config/{backup.get('name')}.yml", False)
                    _s3.upload(STORAGE_CONFIG_PATH, 'storages.yml', False)

                if os.path.exists(compressed_file):
                    print(f"Uploading ...")
                    _s3.upload(
                        compressed_file,
                        f"{backup_folder}/{os.path.basename(compressed_file)}"
                    )
                    Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success")
                    
                
                if os.path.exists(sql_path):
                    print(f"\n\nUploading ...")
                    _s3.upload(
                        sql_path,
                        f"{backup_folder}/{os.path.basename(sql_path)}"
                    )
                    
                    should_save_locally = backup.get('options').get('save_locally')
                    save_locally_path = backup.get('options').get('save_locally_path') # If not set it will be at /etc/bqckup/tmp
                    
                    if not should_save_locally:
                        os.unlink(compressed_file)
                        os.unlink(sql_path)
                    elif should_save_locally and save_locally_path:
                        print("Saving locally ...")
                        if not os.path.isdir(save_locally_path):
                            raise Exception(f"Save locally path {save_locally_path} is not a directory")
                        else:
                            try:
                                save_locally_path = os.path.join(save_locally_path, backup.get('name'))
                                if not os.path.isdir(save_locally_path):
                                    os.makedirs(save_locally_path)
                                shutil.move(compressed_file, save_locally_path)
                                shutil.move(sql_path, save_locally_path)
                            except Exception as e:
                                print(f"Failed to save locally: {e}")
                        
                
                    Log().update_status(log_database.id, Log.__SUCCESS__, "Database Backup Success")
            
            print(f"\n\n[green]Backup for {backup.get('name')} is done![/green]\n")
        except Exception as e:
            import traceback
            traceback.print_exc()

            # If backup failed remove the tmp folder
            remove_folder(tmp_path)
            
            # Separate this two error by it's own exceptions
            if 'log_compressed_files' in locals():
                Log().update_status(log_compressed_files.id, Log.__FAILED__, f"File Backup Failed: {e}")
                
            if 'log_database' in locals():
                Log().update_status(log_database.id, Log.__FAILED__, f"Database Backup Failed: {e}")
                
            
            self._send_notification(backup.get('name'), f"Error: {e}", None)
                
            print(f"[{backup.get('name')}] Error: {e}.")
         
    
    def remove(self):
        pass
