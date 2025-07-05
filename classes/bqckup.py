import os, time, shutil, signal, sys
from typing import Any
from classes.database import Database
from classes.rustic import Rustic, RusticError
from classes.storage import Storage
from classes.tar import Tar
from classes.file import File
from classes.config import Config
from classes.yml_parser import Yml_Parser
from classes.progress import ProgressSpinner
from classes.yml_checker import Yml_Checker
from classes.s3 import s3
from models.log import Log
from models.notification_log import NotificationLog
from constant import BQ_PATH, STORAGE_CONFIG_PATH, SITE_CONFIG_PATH
from datetime import datetime
from helpers.file import remove_folder
from hashlib import sha256
from pathlib import Path
from lib.notifications.discord import send_notification
from helpers.datetime import time_since, get_today, difference_in_days, interval_in_number
from helpers.network import get_server_ip
from rich import print
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from humanfriendly import format_size, format_timespan

class ConfigExceptions(Exception):
    pass

def signal_handler(sig, frame):
    Log().delete().where(Log.status == Log.__ON_PROGRESS__).execute()

    print ("\n[red]Aborted.[/red]")
    sys.exit(0)
    
signal.signal(signal.SIGINT, signal_handler)

class Bqckup:
    def __init__(self):
        Yml_Checker.checker()
        try:
            s3.check_connection()
        except Exception as e:
            print(f"[red]{e}[/red]")
            sys.exit()
            
    def _send_notification(self, backup_name, messages, additional_data = None):
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
                "title": "No Changes Detected",
                "description": (
                    "We have not detected any changes. There could be 2 reasons for this:\n"
                    "1. The application is rarely used.\n"
                    "2. There might be an issue with the database backup process.\n\n"
                    "We recommend the following steps:\n"
                    "1. Check the storage (S3) bucket {bucket_name}. If the database size is less than 1 KB or seems unusual, it likely means the backup did not complete successfully.\n"
                    "2. Attempt to force a backup by running `bqckup --site {domain_name} --force` to ensure the backup process is functioning correctly."
                ),
                "color": 15548997,
                "fields": fields,
                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
            }]
        }
        
        hashed_payload = sha256(str(payload).encode()).hexdigest()                    
        if not NotificationLog().select().where(NotificationLog.hash == hashed_payload).exists():
            send_notification(payload)
            NotificationLog().create(hash=hashed_payload, sent_at=int(time.time()))
            
    def validate_config(self, name: str) -> bool:
        try:
            with ProgressSpinner("Validating config..."):
                config = self.detail(name)
                if not config:
                    raise ConfigExceptions(f"Backup {name} not found")
                for path in config.get('path'):
                    if not os.path.exists(path):
                        raise ConfigExceptions(f"Can't find {path}")
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
            return True
        except Exception as e:
            print(f"[red]Error: {e}[/red]")
            return False
            
    def detail(self, name: str):
        backups = self.list()
        
        for i in backups:
            if backups[i]['name'] == name:
                return backups[i]
            
        return None
    
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
                next_backup_in_date = datetime.fromtimestamp(results[index]['last_backup'] + (interval_in_number(bqckup['options']['interval']) * 86400)).strftime('%d/%m/%Y 00:00:00')
                results[index]['next_backup'] = time_since(datetime.strptime(next_backup_in_date, '%d/%m/%Y %H:%M:%S').timestamp(), time.time(), reverse=True)
            
        return results
            
    def get_last_log(self, name:str):
        return Log().select().where((Log.name == name) & (Log.status != Log.__FAILED__)).order_by(Log.id.desc()).first()
        
    def get_logs(self, name: str):
        return list(Log().select().where(Log.name == name))
    
    def backup(self, force:bool = False, site:str = None):

        """
            Need to optimize this code
        """
        if site:
            backups = {0 : self.detail(site)}
        else:
            backups = self.list()
            
        if not backups:
            print("No backups found")
            return          

        valid_backups = {}
        for k, v in backups.items():
            try:
                if self.validate_config(v['name']):
                    valid_backups[k] = v
                else:
                    print(f"[red]Validation for {v['name']} failed[/red]\n")
            except Exception as e:
                print(f"[red]Error during validation for {v['name']}: {e}[/red]\n")

        backups = valid_backups      

        for backup in backups.values():
            try:
                last_log = self.get_last_log(backup['name'])
                if last_log:
                    interval = backup['options']['interval']
                    last_backup = last_log.created_at
                    last_backup = abs(difference_in_days(last_backup, time.time()))
                    to_compare = interval_in_number(interval)

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
                        print("Visit: https://bqckup.com\n")
                        continue

                if not backup.get("enabled"):
                    print(f"[red]Backup for {backup.get('name')} is not enabled[/red]")
                    continue

                if (
                    Log()
                    .select()
                    .where(
                        Log.name == backup.get("name")
                        and Log.status == Log.__ON_PROGRESS__
                    ).exists()
                ):
                    print(f"Backup for {backup.get('name')} is already running...")

                if backup.get("incremental"):
                    self.incremental_backup(backup)
                else:
                    self.do_backup(backup)
            except Exception as e:
                print(f"[red]Error during backup for {backup['name']}: {e}[/red]")
                continue
    
    # Upload
    def do_backup(self, backup_config):
        time_start = time.time()
        try:
            bqckup_config_location = os.path.join(SITE_CONFIG_PATH, backup_config['file_name'])
            backup = Yml_Parser.parse(bqckup_config_location)['bqckup']
            backup_folder = f"{backup.get('name')}/{get_today()}"
            
            tmp_path = os.path.join(BQ_PATH, 'tmp', f"{backup.get('name')}")
            
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
            
            print(f"[green]Starting backup for {backup.get('name')}[/green]\n")     

            compressed_file = Tar().compress(backup.get('path'), compressed_file, backup.get('options')['follow_symlink'],backup_config.get('exclude_path', []))
            last_compressed_file_backup = Log().select().where((Log.name == backup.get('name')) & (Log.type == Log.__FILES__) & (Log.file_size != 0)).order_by(Log.id.desc()).get_or_none()
            
            if last_compressed_file_backup:
                
                previous_size = format_size(last_compressed_file_backup.file_size)
                current_size = format_size(os.stat(compressed_file).st_size)
                time_consume = format_timespan(last_compressed_file_backup.time_consume)
                print("=========================================")
                print("Backup File Compressed")
                print(f"Previous Size\t: {previous_size}")
                print(f"Current Size\t: {current_size}")
                print(f"Time Consumed\t: {time_consume}")
                print("=========================================")
                
            if last_compressed_file_backup and os.stat(compressed_file).st_size == last_compressed_file_backup.file_size:
                    print(f"[red]Based on file size, there is no changes detected for {compressed_file}[/red]\n")

                    self._send_notification(backup.get('name'), "Based on file size, there is no changes detected", {"name": "File name", "value": os.path.basename(compressed_file), "inline": False})                    

            
            Log().update(file_size=os.stat(compressed_file).st_size).where(Log.id == log_compressed_files.id).execute()
            
            sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
            
            if backup.get('database'):
                with ProgressSpinner("Exporting database..."):
                    log_database = Log().write({
                        "name": backup['name'],
                        "file_path": sql_path,
                        "description": "Database Backup is in Progress",
                        "type": Log.__DATABASE__,
                        "storage": backup['options']['storage'],
                    })
                    Database().export(
                        sql_path,
                        db_user=backup.get('database').get('user'),
                        db_password=backup.get('database').get('password'),
                        db_name=backup.get('database').get('name'),
                    )
                    last_log_db_backup = Log().select().where((Log.name == backup.get('name')) & (Log.type == Log.__DATABASE__) & (Log.file_size != 0)).order_by(Log.id.desc()).get_or_none()
                    
                if last_log_db_backup:
                    
                    previous_size = format_size(last_log_db_backup.file_size)
                    current_size = format_size(os.stat(sql_path).st_size)
                    time_consume = format_timespan(last_log_db_backup.time_consume)
                    print("=========================================")
                    print("Database Compressed")
                    print(f"Previous Size\t: {previous_size}")
                    print(f"Current Size\t: {current_size}")
                    print(f"Time Consumed\t: {time_consume}")
                    print("=========================================")

                if last_log_db_backup and os.stat(sql_path).st_size == last_log_db_backup.file_size:
                    print(f"[red]Based on file size, there is no changes detected for {sql_path}[/red]\n")
                
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
                    
                time_consume = time.time() - time_start

                if os.path.exists(compressed_file):
                    shutil.move(compressed_file, os.path.join(backup_path, os.path.basename(compressed_file)))
                    Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success", time_consume)
                
                if os.path.exists(sql_path):
                    shutil.move(sql_path, os.path.join(backup_path, os.path.basename(sql_path)))
                    Log().update_status(log_database.id, Log.__SUCCESS__, "Database Backup Success", time_consume)
                    
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
                    print(f"\nUploading {compressed_file}")
                    _s3.upload(
                        compressed_file,
                        f"{backup_folder}/{os.path.basename(compressed_file)}"
                    )
                    time_consume = time.time() - time_start
                    Log().update_status(log_compressed_files.id, Log.__SUCCESS__, "File Backup Success", time_consume)
                    
                
                if os.path.exists(sql_path):
                    print(f"\nUploading {sql_path}")
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

                    time_consume = time.time() - time_start
                    Log().update_status(log_database.id, Log.__SUCCESS__, "Database Backup Success", time_consume)
            
            print(f"\n[green]Backup for {backup.get('name')} is done![/green]")
        except Exception as e:
            import traceback
            traceback.print_exc()

            # If backup failed remove the tmp folder
            remove_folder(tmp_path)
            
            # Separate this two error by it's own exceptions
            time_consume = time.time() - time_start
            if 'log_compressed_files' in locals():
                Log().update_status(log_compressed_files.id, Log.__FAILED__, f"File Backup Failed: {e}", time_consume)
                
            if 'log_database' in locals():
                Log().update_status(log_database.id, Log.__FAILED__, f"Database Backup Failed: {e}", time_consume)
                
            
            self._send_notification(backup.get('name'), f"Error: {e}", None)
                
            print(f"[{backup.get('name')}] Error: {e}.")

    def incremental_backup(
        self, config: dict[str, Any], include_database: bool = False
    ) -> None:
        time_start = time.time()

        if config.get("options").get("provider") != "s3":
            raise RuntimeError("Currently, incremental backup only support S3 provider")

        print(f"[green]Starting backup for {config['name']}[/green]\n")

        # Database backup
        db_dump_path = self.backup_database(config)
        if include_database:
            config["path"].append(db_dump_path)
        else:
            print(f"Uploading {db_dump_path}...")
            s3(storage_name=config.get("options").get("storage")).upload(
                db_dump_path, Path(config.get("name")) / get_today() / db_dump_path.name
            )

        # Save backup in local
        should_save_locally = config.get("options").get("save_locally")
        save_locally_path = Path(
            config.get("options").get("save_locally_path", "/etc/bqckup/tmp")
        )  # If not set it will be at /etc/bqckup/tmp

        if not should_save_locally:
            db_dump_path.unlink(missing_ok=True)
        elif should_save_locally and save_locally_path:
            print("Saving locally ...")

            if not save_locally_path.is_dir():
                raise Exception(
                    f"Save locally path {save_locally_path} is not a directory"
                )

            save_locally_path: Path = save_locally_path / config["name"]
            if not save_locally_path.is_dir():  # if directory not exists; create
                save_locally_path.mkdir(parents=True, exist_ok=True)

            shutil.move(db_dump_path, save_locally_path)

        # File backup
        try:
            logs: Log = Log().write(
                {
                    "name": config["name"],
                    "file_path": "/dev/null",  # replaced by snapshots id
                    "description": "File backup is in progress...",
                    "type": Log.__FILES__,
                    "storage": config["options"]["storage"],
                }
            )

            if Config().read("bqckup", "config_backup"):
                config["path"] += (
                    STORAGE_CONFIG_PATH,
                    os.path.join(SITE_CONFIG_PATH, config["name"]) + ".yml",
                )

            rustic: Rustic = Rustic(
                config, Yml_Parser.parse(STORAGE_CONFIG_PATH)["storages"]
            )

            result = None

            with ProgressSpinner("doing incremental backup..."):
                result = rustic.backup()

            Log.update(
                status=Log.__SUCCESS__,
                time_consume=time.time() - time_start,
                file_size=result["total_size"],
                file_path=result["id"],  # rustic snapshots id
                description="File Backup Success",
            ).where(Log.id == logs.id).execute()

            print("=========================================")
            print("Backup complete")
            print("New Files\t:", result["new"])
            print("Changed Files\t:", result["changed"])
            print("Unchanged Files\t:", result["unchanged"])
            print("Data Uploaded\t:", format_size(result["uploaded"]))
            print("Total Size\t:", format_size(result["total_size"]))
            print("Time Consumed\t:", format_timespan(result["total_duration"]))
            print("=========================================")

        except Exception as e:
            Log.update(
                status=Log.__FAILED__,
                time_consume=time.time() - time_start,
                description=f"File Backup Failed: {e}",
            ).where(Log.id == logs.id).execute()
            self._send_notification(config.get("name"), f"Error: {e}")
            print(f"[{config['name']}] Error: {e}")
            return

    def backup_database(self, config: dict) -> Path:
        """
        Returns:
            Path: return path to exported database
        """

        if not config.get("database"):
            return

        tmp_path: Path = Path(BQ_PATH) / "tmp" / config["name"]
        backup_path = tmp_path / f"{int(time.time())}.sql.gz"
        time_start = time.time()

        current_log: Log = Log().write(
            {
                "name": config["name"],
                "description": "Database Backup is in Progress",
                "type": Log.__DATABASE__,
                "storage": config["options"]["storage"],
                "file_path": backup_path,
            }
        )

        last_log = (
            Log()
            .select()
            .where(
                Log.name == config["name"]
                and Log.type == Log.__DATABASE__
                and Log.file_size != 0
            )
            .order_by(Log.id.desc())
            .get_or_none()
        )

        if not tmp_path.exists() or not tmp_path.is_dir():
            tmp_path.mkdir(parents=True, exist_ok=True)

        with ProgressSpinner("Exporting database"):
            Database().export(
                backup_path.__str__() if isinstance(backup_path, Path) else backup_path,
                db_user=config["database"]["user"],
                db_password=config["database"]["password"],
                db_name=config["database"]["name"],
            )

        current_size = backup_path.stat().st_size
        Log.update(
            file_size=current_size,
            status=Log.__SUCCESS__,
            time_consume=time.time() - time_start,
            description="Database Backup Success",
        ).where(Log.id == current_log.id).execute()

        if last_log:
            previous_size = format_size(last_log.file_size)
            time_consume = format_timespan(current_log.time_consume)
            current_size = format_size(current_size)

            print("=========================================")
            print("Database Compressed")
            print(f"Previous Size\t: {previous_size}")
            print(f"Current Size\t: {current_size}")
            print(f"Time Consumed\t: {time_consume}")
            print("=========================================")

            if previous_size == current_size:
                print(
                    f"[red]Based on file size, there is no changes detected for {backup_path}[/red]\n"
                )

        return backup_path

    def remove(self):
        pass
