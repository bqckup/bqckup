import os, time, shutil, signal, sys
import traceback
from subprocess import CalledProcessError
from typing import Any, Dict
from classes.database import Database
from classes.rustic import Rustic, RusticCheckError, RusticConfigError
from classes.storage import Storage
from classes.tar import Tar
from classes.file import File
from classes.config import Config
from classes.yml_parser import Yml_Parser
from classes.progress import ProgressSpinner
from classes.yml_checker import Yml_Checker
from classes.s3 import s3
from helpers.hook import send_backup_summary
from helpers.utility import is_debug
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
            with ProgressSpinner("checking storage connection..."):
                s3.check_all_storage_connection()
        except Exception as e:
            print(f"[red]{e}[/red]")
            sys.exit()

    def _send_notification(
        self,
        backup_name,
        title,
        description=None,
        messages=None,
        additional_data=None,
        footer=None,
        color=15548997,
    ):
        fields = [
            {"name": "Server IP", "value": get_server_ip(), "inline": True},
            {"name": "Name", "value": backup_name, "inline": True},
            {"name": "Date", "value": get_today(format="%d-%B-%Y"), "inline": True},
        ]

        if additional_data:
            fields.append(additional_data)

        if messages:
            fields.append({"name": "Details", "value": messages, "inline": False})

        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                    "fields": fields,
                    "footer": {
                        "text": footer,
                    }
                }
            ]
        }

        hashed_payload = sha256(str(payload).encode()).hexdigest()
        if (
            not NotificationLog()
            .select()
            .where(NotificationLog.hash == hashed_payload)
            .exists()
        ):
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

                if Rustic.is_enabled(config) and config.get("incremental", {}).get("password") is None:
                    raise RusticConfigError("Password can't be empty")

                databases = config.get("databases", [])

                # For backward compatibility
                database = config.get("database", {})
                if database and (database.get("enabled") or database.get("enable")):
                    databases.append(database)

                for database in databases:
                    if not (database.get("enabled") or database.get("enable")):
                        continue
                    if database.get("type") not in Database().SUPPORTED_DATABASE:
                        raise ConfigExceptions(
                            f"Database type {database.get('type')} not supported"
                        )
                    Database(type=database["type"]).test_connection({
                        "user": database["user"],
                        "password": database["password"],
                        "host": database["host"],
                        "name": database["name"],
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
            results[index]['config_path'] = file
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

    def backup(
        self,
        force: bool = False,
        site: str = None,
        backup_method: str = None,
        keep_credential: bool = False,
    ):
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
                if not (backup.get("enabled") or backup.get("enable")):
                    print(f"[red]Backup for {backup.get('name')} is not enabled[/red]")
                    continue

                last_log = self.get_last_log(backup['name'])
                if last_log:
                    interval = backup['options']['interval']
                    last_backup_timestamp = last_log.created_at
                    days_passed = abs(difference_in_days(last_backup_timestamp, time.time()))
                    to_compare = interval_in_number(interval)

                    last_log_status = {
                        Log().__SUCCESS__: "success",
                        Log().__ON_PROGRESS__: "on-progress",
                        Log().__FAILED__: "failed",
                    }.get(last_log.status, "unknown")

                    if last_log.status != Log().__SUCCESS__:
                        print(f"[yellow]The previous backup for {backup['name']} was not successful.[/yellow]")
                        print(f"[yellow]Last Status: '{last_log_status}'. Attempted at: {datetime.fromtimestamp(last_backup_timestamp).strftime('%d/%m/%Y %H:%M:%S')}[/yellow]")
                        self._send_notification(
                            backup_name=backup.get("name"),
                            title=f"Previous Backup Not Successful for {backup.get('name')}",
                            description=(
                                f"The last backup attempt on {datetime.fromtimestamp(last_backup_timestamp).strftime('%d/%m/%Y %H:%M:%S')} "
                                f"did not complete successfully. The last known status was '{last_log_status}'.\n\n"
                            ),
                        )

                    if not force and days_passed < to_compare:
                        print("\n=========================================")
                        print(f"Backup Name: {backup['name']}")
                        print(f"Current Date: {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())}")
                        print(f"Last Backup: {datetime.fromtimestamp(last_backup_timestamp).strftime('%d/%m/%Y %H:%M:%S')}")
                        print(f"Next bqckup: {datetime.fromtimestamp(last_backup_timestamp + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}")
                        print(f"Day passed: {days_passed}")
                        print(f"Interval: {interval}")
                        print(f"\nBackup for {backup['name']} is not needed yet...")
                        print("=========================================\n")
                        print("Visit: https://bqckup.com\n")
                        continue

                last_running_log = Log().select().where(
                    Log.name == backup.get("name")
                    and Log.status == Log.__ON_PROGRESS__
                )

                if last_running_log.exists():
                    print(f"Backup for {backup.get('name')} is already running...")
                    continue

                if backup_method == "incremental":
                    self.incremental_backup(backup, keep_credential=keep_credential)
                    continue
                elif backup_method == "full":
                    self.do_backup(backup)
                    continue

                if Rustic.is_enabled(backup):
                    self.incremental_backup(backup, keep_credential=keep_credential)
                else:
                    self.do_backup(backup)
            except Exception as e:
                if is_debug():
                    traceback.print_exc()

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

            compressed_file_size = os.stat(compressed_file).st_size

            if last_compressed_file_backup:
                
                previous_size = format_size(last_compressed_file_backup.file_size)
                current_size = format_size(compressed_file_size)
                time_consume = format_timespan(last_compressed_file_backup.time_consume)
                print("=========================================")
                print("Backup File Compressed")
                print(f"Previous Size\t: {previous_size}")
                print(f"Current Size\t: {current_size}")
                print(f"Time Consumed\t: {time_consume}")
                print("=========================================")
                
            if last_compressed_file_backup and os.stat(compressed_file).st_size == last_compressed_file_backup.file_size:
                print(
                    f"[red]Based on file size, there is no changes detected for {compressed_file}[/red]\n"
                )

                self._send_notification(
                    backup_name=backup.get("name"),
                    title="No Changes Detected",
                    messages="Based on file size, there is no changes detected",
                    description=(
                        "We have not detected any changes. There could be 2 reasons for this:\n"
                        "1. The application is rarely used.\n"
                        "2. There might be an issue with the database backup process.\n\n"
                        "We recommend the following steps:\n"
                        "1. Check the storage (S3) bucket {bucket_name}. If the database size is less than 1 KB or seems unusual, it likely means the backup did not complete successfully.\n"
                        "2. Attempt to force a backup by running `bqckup --site {domain_name} --force` to ensure the backup process is functioning correctly."
                    ),
                    footer="If this was a mistake, please create issue here: https://github.com/bqckup/bqckup",
                    additional_data={
                        "name": "File name",
                        "value": os.path.basename(compressed_file),
                        "inline": False,
                    },
                )

            Log().update(file_size=os.stat(compressed_file).st_size).where(Log.id == log_compressed_files.id).execute()
            
            sql_path = os.path.join(tmp_path, f"{int(time.time())}.sql.gz")
            
            if backup.get("database") and (backup.get("database").get("enabled") or backup.get("database").get("enable")):
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
            backup_status = "completed"
        except Exception as e:
            backup_status = "failed"
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

            self._send_notification(
                backup.get("name"),
                title=f"Backup Failed for {backup.get('name')}",
                messages=f"Error: {e}",
            )

            print(f"[{backup.get('name')}] Error: {e}.")

        finally:
            try:
                with ProgressSpinner("sending data..."):
                    send_backup_summary(
                        domain=backup.get("name"),
                        total_size=compressed_file_size,
                        new_data=compressed_file_size,
                        start_at=int(time_start),
                        finish_at=int(time.time()),
                        status=backup_status,
                        backup_method="tar",
                    )
            except Exception as e:
                print(f"Error: {e}")

    def incremental_backup(
        self,
        site_config: Dict[str, Any],
        keep_credential: bool = False,
    ) -> None:
        time_start = time.time()

        if site_config.get("options", {}).get("provider") != "s3":
            raise RuntimeError("Currently, incremental backup only support S3 provider")

        print(f"[green]Starting backup for {site_config['name']}[/green]\n")

        bucket_name = site_config.get("options", {}).get("storage")
        storage_config = Storage().get_storage_detail(bucket_name)
        _s3 = s3(storage_name=bucket_name)

        if Config().read("bqckup", "config_backup"):
            _s3.upload(STORAGE_CONFIG_PATH, "storages.yml", False)
            _s3.upload(
                Path(SITE_CONFIG_PATH) / site_config["file_name"],
                f"config/{site_config.get('name')}.yml",
                False,
            )

        # Database backup
        self.backup_databases(site_config, _s3)

        result = {}
        rustic = Rustic(site_config, storage_config)

        # File backup
        try:
            logs: Log = Log().write(
                {
                    "name": site_config["name"],
                    "file_path": "/dev/null",  # replaced by snapshots id
                    "description": "File backup is in progress...",
                    "type": Log.__FILES__,
                    "storage": site_config["options"]["storage"],
                }
            )

            rustic.check_and_dump()

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

            backup_status = "completed"

            with ProgressSpinner("checking repository..."):
                rustic.check_repository()

        except RusticCheckError as e:
            if is_debug():
                traceback.print_exc()

            Log.update(
                status=Log.__SUCCESS__,
                time_consume=time.time() - time_start,
                description=f"File Backup Success, but repository check failed: {e}",
            ).where(Log.id == logs.id).execute()

            print(f"({site_config['name']}) Error while checking repository.")

            self._send_notification(
                site_config["name"],
                title=f"Repository Check Failed for {site_config['name']}",
                messages=f"Error: {e}",
                additional_data={
                    "name": "Command Output",
                    "value": e.stderr,
                    "inline": False,
                },
                description=(
                    "Backup completed successfully, but repository check failed.\n"
                    "Visit the [documentation](https://docs.bqckup.com/bqckup-documentation/troubleshoots/fixing-a-corrupted-incremental-backup) to fix it"
                ),
            )

        except Exception as e:
            backup_status = "failed"

            if is_debug():
                traceback.print_exc()

            Log.update(
                status=Log.__FAILED__,
                time_consume=time.time() - time_start,
                description=f"File Backup Failed: {e}",
            ).where(Log.id == logs.id).execute()

            print(f"Error while backing up {site_config['name']}: ", end="")
            err_msg = "unexpected error"
            err_detail = str(e)

            if isinstance(e, CalledProcessError):
                err_msg= "command error"
                err_detail = (
                    f"Command: '{e.cmd}'\n"
                    f"Output: '{e.stdout}'\n"
                    f"Error: '{e.stderr}'\n"
                )
            elif isinstance(e, FileNotFoundError):
                err_msg = "rustic is not installed"
            elif isinstance(e, RusticConfigError):
                err_msg = "invalid configuration"

            print(err_msg, err_detail, sep="\n" )

            self._send_notification(
                site_config["name"],
                title=f"Incremental Backup Failed for {site_config['name']}",
                messages=err_detail,
                additional_data={
                    "name": "Error Message",
                    "value": err_msg,
                    "inline": True,
                },
                description=(
                    "An error occurred while backup.\n"
                    "Visit the [documentation](https://docs.bqckup.com/bqckup-documentation/troubleshoots/fixing-a-corrupted-incremental-backup) to fix it"
                ),
            )

        finally:
            rustic.dump_config(with_credentials=keep_credential)
            try:
                with ProgressSpinner("sending data..."):
                    send_backup_summary(
                        domain=site_config["name"],
                        total_size=result.get("total_size", -1), # pyright: ignore[reportArgumentType]
                        new_data=result.get("uploaded", 0), # pyright: ignore[reportArgumentType]
                        start_at=int(time_start),
                        finish_at=int(time.time()),
                        status=backup_status,
                        backup_method="incremental",
                    )
            except Exception as e:
                print(f"Error while sending backup summary: {e}")

    def backup_databases(self, site_config: dict[str, Any], s3: s3):
        databases = site_config.get("databases", [])

        # For backward compatibility
        if site_config.get("database"):
            database = site_config.get("database", {})
            if database.get("enabled") or database.get("enable"):
                databases.append(database)

        if not databases:
            return

        should_save_locally: bool = site_config.get("options", {}).get("save_locally", False)
        save_locally_path_str = site_config.get("options", {}).get("save_locally_path", "/etc/bqckup/tmp")
        save_locally_path = Path(save_locally_path_str) if save_locally_path_str else None

        for database in databases:
            if not (database.get("enabled") or database.get("enable")):
                print(f"[yellow]Skipping disabled database: {database.get('name')}[/yellow]")
                continue

            self.backup_database(
                site_config=site_config,
                database=database,
                s3=s3,
                should_save_locally=should_save_locally,
                save_locally_path=save_locally_path,
            )

    def backup_database(
        self,
        site_config: dict[str, Any],
        database: dict[str, Any],
        s3: s3 | None = None,
        should_save_locally: bool = False,
        save_locally_path: Path | None = None,
    ):
        db_label = f"{database['user']}@{database['host']}:{database['port']}/{database['name']}"

        print(f"Starting database backup for {site_config['name']} {db_label}")

        time_start = time.time()
        tmp_path: Path = Path(BQ_PATH) / "tmp" / site_config["name"]
        backup_path = tmp_path / f"{int(time_start)}-{database['name']}.sql.gz"

        if not tmp_path.exists() or not tmp_path.is_dir():
            tmp_path.mkdir(parents=True, exist_ok=True)

        current_log = Log().write(
            {
                "name": site_config["name"],
                "description": f"Database Backup for '{db_label}' in Progress",
                "type": Log.__DATABASE__,
                "storage": site_config["options"]["storage"],
                "file_path": str(backup_path),
            }
        )

        try:
            with ProgressSpinner(f"Exporting database {db_label}"):
                Database().export(
                    str(backup_path),
                    db_user=database["user"],
                    db_password=database["password"],
                    db_name=database["name"],
                )

            if s3:
                s3.upload(
                    backup_path,
                    Path(site_config["name"]) / get_today() / backup_path.name,
                )

            Log.update(
                file_size=backup_path.stat().st_size,
                status=Log.__SUCCESS__,
                time_consume=time.time() - time_start,
                description=f"Database Backup for '{db_label}' Success",
            ).where(Log.id == current_log.id).execute()

            # Refresh the log object to get the updated time_consume
            current_log = Log.get_by_id(current_log.id)

            self._post_database_backup(
                site_name=site_config["name"],
                db_label=db_label,
                backup_path=backup_path,
                current_log=current_log,
                should_save_locally=should_save_locally,
                save_locally_path=save_locally_path,
            )
        except Exception as e:
            Log.update(
                status=Log.__FAILED__,
                time_consume=time.time() - time_start,
                description=f"Database Backup Failed for '{db_label}'",
            ).where(Log.id == current_log.id).execute()

            print(f"failed to backup database {db_label}: {e}")

            self._send_notification(
                backup_name=site_config["name"],
                title=f"Database Backup Failed for {site_config['name']} {db_label}",
                messages=f"Error: {e}",
            )

    def _post_database_backup(
        self,
        site_name: str,
        db_label: str,
        backup_path: Path,
        current_log: Log,
        should_save_locally: bool = False,
        save_locally_path: Path | None = None,
    ) -> None:
        last_log = Log.select().where(
            (Log.name == site_name)
            & (Log.type == Log.__DATABASE__)
            & (Log.status == Log.__SUCCESS__)
            & (Log.description.contains(db_label))
        ).order_by(Log.id.desc()).get_or_none()

        try:
            if last_log:
                previous_size = format_size(last_log.file_size)
                time_consume = format_timespan(current_log.time_consume)
                current_size = format_size(backup_path.stat().st_size)

                print("=========================================")
                print("Database Compressed")
                print(f"Database\t: {db_label}")
                print(f"Previous Size\t: {previous_size}")
                print(f"Current Size\t: {current_size}")
                print(f"Time Consumed\t: {time_consume}")
                print("=========================================")

                if previous_size == current_size:
                    print(
                        f"[yellow]Based on file size, there is no changes detected for {backup_path.name}[/yellow]\n"
                    )

            if not should_save_locally:
                backup_path.unlink(missing_ok=True) # remove file
            elif should_save_locally and save_locally_path:
                print(f"Saving '{backup_path.name}' locally ...")
                final_dest_path: Path = save_locally_path / site_name
                if not final_dest_path.is_dir():
                    final_dest_path.mkdir(parents=True, exist_ok=True)

                if backup_path.parent.resolve() != final_dest_path.resolve():
                    print(f"Moving {backup_path} to {final_dest_path}...")
                    shutil.move(backup_path, final_dest_path)
        except Exception as e:
            print(
                f"Error while post-processing database backup for {site_name} '{db_label}': {e}"
            )
