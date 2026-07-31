import copy
import os
import shutil
import signal
import socket
import sys
import time
import traceback
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any, Dict, List, Optional
from humanfriendly import format_size, format_timespan
from rich import print
from classes.config import Config
from classes.database import Database, DatabaseCorruptException
from classes.file import File
from classes.master import Master
from classes.progress import ProgressSpinner
from classes.rustic import Rustic, RusticCheckError, RusticCleanError, RusticConfigError
from classes.s3 import s3
from classes.storage import Storage
from classes.tar import Tar
from classes.yml_checker import Yml_Checker
from classes.yml_parser import Yml_Parser
from constant import (
    BACKOFF,
    BQ_PATH,
    MAX_RETRIES,
    SITE_CONFIG_PATH,
    STORAGE_CONFIG_PATH,
    VERSION,
)
from helpers.datetime import (
    difference_in_days,
    get_today,
    interval_in_number,
    time_since,
)
from classes.s3 import s3
from helpers.hook import send_backup_summary, StorageCredentialError
from helpers.utility import is_debug
from models.log import Log
from models.notification_log import NotificationLog
from classes.master import Master
from helpers.file import remove_folder
from hashlib import sha256
from pathlib import Path
from lib.notifications.webhook import send_report_to_webhook
from lib.notifications.email import send_notification as send_email_notification
from lib.notifications.discord import send_notification as send_discord_notification
from helpers.datetime import time_since, get_today, difference_in_days, interval_in_number
from helpers.network import get_server_ip
from rich import print
from humanfriendly import format_size, format_timespan

class ConfigExceptions(Exception):
    pass


def signal_handler(sig, frame):
    Log().delete().where(Log.status == Log.__ON_PROGRESS__).execute()

    print("\n[red]Aborted.[/red]")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


class Bqckup:
    def __init__(self):
        Yml_Checker.checker()

        try:
            with ProgressSpinner("checking storage connection..."):
                s3.check_connection()  # check all storage
        except Exception as e:
            print(f"[red]Storage connection check failed: {e}[/red]")

    def _send_notification(
        self,
        site,
        status,
        event,
        title,
        message="",
        description=None,
        additional_data=None,
        footer=None,
        color=None,
    ):
        payload = {
            "report_type": "daily",
            "site": site,
            "status": status,
            "event": event,
            "title": title,
            "message": message,
            "description": description,
            "additional_data": additional_data,
            "footer": footer,
            "color": color,
            "timestamp": int(time.time()),
            "server_ip": get_server_ip(),
        }

        hashed_payload = sha256(f"{site}_{event}".encode()).hexdigest()
        if (
            NotificationLog()
            .select()
            .where(NotificationLog.hash == hashed_payload)
            .exists()
            and not is_debug()
        ):
            return

        send_report_to_webhook(payload)
        send_email_notification(payload)
        send_discord_notification(payload)
        NotificationLog().create(hash=hashed_payload, sent_at=int(time.time()))

    def validate_config(self, name: str) -> bool:
        try:
            with ProgressSpinner("Validating config..."):
                config = self.detail(name)
                if not config:
                    raise ConfigExceptions(f"Backup {name} not found")
                for path in config.get("path"):
                    if not os.path.exists(path):
                        raise ConfigExceptions(f"Can't find {path}")

                if Rustic.is_enabled(config):
                    Rustic(config, {}).check_config()

                databases = Database.get_all(config)

                for database in databases:
                    db_type = database.get("type", "mysql")
                    if db_type not in Database().SUPPORTED_DATABASE:
                        raise ConfigExceptions(f"Database type {db_type} not supported")

                    if db_type == "sqlite":
                        Database(type=db_type).test_connection(
                            {
                                "name": database["name"],
                            }
                        )
                    else:
                        Database(type=db_type).test_connection(
                            {
                                "user": database["user"],
                                "password": database["password"],
                                "host": database["host"],
                                "port": database["port"],
                                "name": database["name"],
                            }
                        )

                if config.get("options").get("provider") == "s3":
                    Storage().get_storage_detail(config.get("options").get("storage"))
            return True
        except StorageCredentialError as e:
            print(f"[red]{e}[/red]")
            self._send_notification(
                site=config.get("name"),
                status="failed",
                event="credential_failed",
                title=f"Storage Credential Failed for {config.get('name')}",
                message=str(e),
            )
            return False
        except Exception as e:
            print(f"[red]Error: {e}[/red]")
            return False

    def detail(self, name: str):
        backups = self.list()

        for i in backups:
            if backups[i]["name"] == name:
                return backups[i]

        return None

    def list(self):
        files = File().get_file_list(SITE_CONFIG_PATH)
        files = [file for file in files if file.endswith(".yml")]
        results = {}

        for index, file in enumerate(files):
            file_name = os.path.basename(file)
            parsed_content = Yml_Parser.parse(file)
            bqckup = parsed_content["bqckup"]
            log = self.get_last_log(bqckup["name"])
            results[index] = {}
            results[index] = bqckup
            results[index]["config_path"] = file
            results[index]["file_name"] = file_name
            results[index]["last_backup"] = log.created_at if log else None

            # Next Backup
            results[index]["next_backup"] = False
            if results[index]["last_backup"]:
                next_backup_in_date = datetime.fromtimestamp(
                    results[index]["last_backup"]
                    + (interval_in_number(bqckup["options"]["interval"]) * 86400)
                ).strftime("%d/%m/%Y 00:00:00")
                results[index]["next_backup"] = time_since(
                    datetime.strptime(
                        next_backup_in_date, "%d/%m/%Y %H:%M:%S"
                    ).timestamp(),
                    time.time(),
                    reverse=True,
                )

        return results

    def get_last_log(self, name: str):
        return (
            Log()
            .select()
            .where((Log.name == name) & (Log.status != Log.__FAILED__))
            .order_by(Log.id.desc())
            .first()
        )

    def get_logs(self, name: str):
        return list(Log().select().where(Log.name == name))

    def _build_api_payload(
        self,
        site_config: Dict[str, Any],
        file_backup_result: Optional[Dict[str, Any]],
        database_results: List[Dict[str, Any]],
        backup_mode: str,
        backup_started_at: int,
        rustic_version: Optional[str],
    ) -> Dict[str, Any]:
        """
        Args:
            site_config: The backup configuration
            file_backup_result: Result from file backup (full_backup or incremental_backup)
            database_results: List of database backup results
            backup_mode: "archive" or "incremental"
            backup_started_at: Unix timestamp when backup started
            rustic_version: Version of rustic tool
        """

        # Clean up backup config for API
        config: dict = copy.deepcopy(site_config)
        removed_keys = ["config_path", "file_name", "last_backup", "next_backup"]
        for key in removed_keys:
            config.pop(key, None)

        # Sanitize sensitive data
        if "incremental" in config and isinstance(config["incremental"], dict):
            config["incremental"].pop("password", None)

        if "database" in config and isinstance(config["database"], dict):
            config["database"].pop("password", None)

        backups = {}

        if file_backup_result:
            backups["file"] = {
                "status": "completed"
                if file_backup_result.get("success")
                else "failed",
                "size": file_backup_result.get("file_size", 0),
                "errors": file_backup_result.get("errors", []),
                "metadata": {},
                "started_at": file_backup_result.get("started_at"),
                "ended_at": file_backup_result.get("ended_at", now()),
            }

        databases_payload = []
        for db_result in database_results:
            db_info = db_result.get("database", {})
            db_info.pop("password", None)

            databases_payload.append(
                {
                    "status": "completed" if db_result.get("success") else "failed",
                    "size": db_result.get("size", 0),
                    "errors": db_result.get("errors", []),
                    "database": db_info,
                    "metadata": {},
                    "started_at": db_result.get("started_at"),
                    "ended_at": db_result.get("ended_at"),
                }
            )

        if databases_payload:
            backups["databases"] = databases_payload

        payload = {
            "hostname": socket.gethostname(),
            "bqckup_version": VERSION,
            "rustic_version": rustic_version,
            "started_at": backup_started_at,
            "ended_at": now(),
            "site": {
                "name": site_config["name"],
                "config": config,
                "mode": backup_mode,
                "backups": backups,
            },
        }

        return payload

    def _get_protected_db_backup_keys(self, site_config: Dict[str, Any]) -> set:
        """S3 keys of the most recent successful backup for each database on
        this site. These must survive retention cleanup even if they fall
        outside the normal retention window, so that a database stuck in a
        corrupt/unrepaired state never loses its last known-good backup.
        Once a newer backup succeeds, this naturally points to that one
        instead, releasing the older copy back to normal retention.
        """
        protected_keys = set()
        site_name = site_config.get("name", "")
        root_folder = Config().read("bqckup", "root_folder_name") or "bqckup"

        for database in Database.get_all(site_config):
            db_label = f"{database['user']}@{database['host']}:{database['port']}/{database['name']}"
            last_success = (
                Log()
                .select()
                .where(
                    (Log.name == site_name)
                    & (Log.type == Log.__DATABASE__)
                    & (Log.status == Log.__SUCCESS__)
                    & (Log.description.contains(db_label))
                )
                .order_by(Log.id.desc())
                .first()
            )

            if not last_success or not last_success.file_path:
                continue

            date_str = datetime.fromtimestamp(last_success.created_at).strftime(
                "%d-%B-%Y"
            )
            file_name = os.path.basename(last_success.file_path)
            protected_keys.add(f"{root_folder}/{site_name}/{date_str}/{file_name}")

        return protected_keys

    def _clean_old_backups(self, site_config: Dict[str, Any]) -> None:
        print("Removing old backups...")

        try:
            _s3 = s3(storage_name=site_config.get("options", {}).get("storage"))
            site_name: str = site_config.get("name", "")
            keep_last = int(site_config.get("options", {}).get("retention", 3))

            backup_dates = _s3.get_backup_dates(site_name=site_name, sort_by_date=True)
            backup_to_delete = backup_dates[:-keep_last]

            if not backup_to_delete:
                print("No old backup to delete")
                return

            candidate_objects = [
                obj.get("Key")
                for prefix in backup_to_delete
                for obj in _s3.list(prefix=prefix).get("Contents", [])
                if obj.get("Key")
            ]

            protected_keys = self._get_protected_db_backup_keys(site_config)
            objects = [key for key in candidate_objects if key not in protected_keys]

            for key in candidate_objects:
                if key in protected_keys:
                    print(
                        f"[yellow]Preserving last known-good database backup (outside retention window): {key}[/yellow]"
                    )

            if not objects:
                print("No old backup to delete")
                return

            _s3.delete_objects(objects=objects)

        except Exception as e:
            if is_debug():
                traceback.print_exc()

            err_msg = f"Failed to Clean Old Backups for {site_config.get('name')}"
            print(f"[red]Error: {err_msg}.[/red]")
            self._send_notification(
                site=site_config.get("name"),
                status="failed",
                event="cleanup_failed",
                title=err_msg,
                message=f"An error occurred while trying to clean old backups.\nError: {e}",
            )

    def _should_skip_backup(self, backup: Dict[str, Any], force: bool) -> bool:
        """
        Determines whether a backup should be skipped based on configuration and status.

        Returns:
            True if the backup should be skipped, False otherwise.
        """

        backup_name: str = backup["name"]
        if not (backup.get("enabled") or backup.get("enable")):
            print(f"[red]Backup for {backup_name} is not enabled[/red]")
            return True

        last_any_log = (
            Log()
            .select()
            .where(Log.name == backup_name)
            .order_by(Log.id.desc())
            .first()
        )
        last_success_log = (
            Log()
            .select()
            .where((Log.name == backup_name) & (Log.status == Log.__SUCCESS__))
            .order_by(Log.id.desc())
            .first()
        )

        if last_any_log:
            last_log_status = {
                Log.__SUCCESS__: "success",
                Log.__ON_PROGRESS__: "on-progress",
                Log.__FAILED__: "failed",
            }.get(last_any_log.status, "unknown")

            if last_any_log.status != Log().__SUCCESS__:
                print(
                    f"[yellow]The previous backup for {backup_name} was not successful.[/yellow]"
                )
                print(
                    f"[yellow]Last Status: '{last_log_status}'. Attempted at: {datetime.fromtimestamp(last_any_log.created_at).strftime('%d/%m/%Y %H:%M:%S')}[/yellow]"
                )
                self._send_notification(
                    site=backup_name,
                    status="failed",
                    event="previous_backup_failed",
                    title=f"Previous Backup Not Successful for {backup_name}",
                    message=(
                        f"The last backup attempt on {datetime.fromtimestamp(last_any_log.created_at).strftime('%d/%m/%Y %H:%M:%S')} "
                        f"did not complete successfully. The last known status was '{last_log_status}'."
                    ),
                )

        failed_components = []
        last_file_log = (
            Log()
            .select()
            .where((Log.name == backup_name) & (Log.type == Log.__FILES__))
            .order_by(Log.id.desc())
            .first()
        )
        if last_file_log and last_file_log.status == Log.__FAILED__:
            failed_components.append("files")

        for database in Database.get_all(backup):
            db_label = f"{database['user']}@{database['host']}:{database['port']}/{database['name']}"
            last_db_log = (
                Log()
                .select()
                .where(
                    (Log.name == backup_name)
                    & (Log.type == Log.__DATABASE__)
                    & (Log.description.contains(db_label))
                )
                .order_by(Log.id.desc())
                .first()
            )
            if last_db_log and last_db_log.status == Log.__FAILED__:
                failed_components.append(f"database {db_label}")

        if failed_components:
            print(
                f"[yellow]Previous backup has failed components ({', '.join(failed_components)}). Running backup again.[/yellow]"
            )
            return False

        if last_success_log:
            interval = backup["options"]["interval"]
            last_backup_timestamp = last_success_log.created_at
            days_passed = abs(
                difference_in_days(last_backup_timestamp, int(time.time()))
            )
            to_compare = interval_in_number(interval)

            if not force and days_passed < to_compare:
                print("\n=========================================")
                print(f"Backup Name: {backup_name}")
                print(
                    f"Current Date: {time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())}"
                )
                print(
                    f"Last Backup: {datetime.fromtimestamp(last_backup_timestamp).strftime('%d/%m/%Y %H:%M:%S')}"
                )
                print(
                    f"Next bqckup: {datetime.fromtimestamp(last_backup_timestamp + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}"
                )
                print(f"Day passed: {days_passed}")
                print(f"Interval: {interval}")
                print(f"\nBackup for {backup_name} is not needed yet...")
                print("=========================================\n")
                print("Visit: https://bqckup.com\n")
                return True

        if (
            Log()
            .select()
            .where((Log.name == backup_name) & (Log.status == Log.__ON_PROGRESS__))
            .exists()
        ):
            print(f"Backup for {backup_name} is already running...")
            return True

        return False

    def backup(
        self,
        force: bool = False,
        site: Optional[str] = None,
        incremental: Optional[bool] = None,
    ):
        backups = {0: self.detail(site)} if site else self.list()

        if not backups:
            print("No backups found")
            return

        valid_backups = {}
        for k, v in backups.items():
            try:
                if self.validate_config(v["name"]):
                    valid_backups[k] = v
                else:
                    print(f"[red]Validation for {v['name']} failed[/red]\n")
            except Exception as e:
                print(f"[red]Error during validation for {v['name']}: {e}[/red]\n")

        for backup in valid_backups.values():
            log = None
            backup_result = None
            backup_started_at = now()
            rustic_version = Rustic.version()
            is_incremental = (
                Rustic.is_enabled(backup) if incremental is None else incremental
            )
            backup_mode = "incremental" if is_incremental else "archive"
            database_results = []

            try:
                if is_incremental and not Rustic.is_installed():
                    raise RuntimeError("Rustic is not installed.")

                if self._should_skip_backup(backup, force):
                    continue

                storage_name = backup.get("options", {}).get("storage")
                is_s3 = backup.get("options", {}).get("provider") == "s3"
                _s3 = s3(storage_name=storage_name) if is_s3 and storage_name else None

                self.backup_config(backup, _s3)
                database_results = self.backup_databases(backup, _s3)

                backup_method = (
                    self.incremental_backup if is_incremental else self.full_backup
                )

                log = Log().write(
                    {
                        "name": backup["name"],
                        "description": "File backup process starting...",
                        "type": Log.__FILES__,
                        "storage": backup["options"]["storage"],
                        "file_path": "/dev/null",
                    }
                )

                errors = []

                for attempt in range(MAX_RETRIES):
                    attempt_info = (
                        f"(Attempt {attempt + 1}/{MAX_RETRIES})" if attempt > 0 else ""
                    )
                    print(
                        f"[green]Starting file backup for {backup['name']}[/green] {attempt_info}..."
                    )

                    backup_result = backup_method(backup)

                    if backup_result["success"]:
                        print(
                            f"[green]File backup for {backup['name']} successful.[/green]"
                        )
                        break

                    error = backup_result.get("traceback") or backup_result.get("error")
                    if error:
                        errors.append(str(error))

                    error_message = backup_result.get("message", "Unknown error")
                    print(
                        f"[yellow]File backup for {backup['name']} failed: {error_message}[/yellow]"
                    )

                    if attempt < MAX_RETRIES - 1:
                        print(f"[yellow]Retrying in {BACKOFF} seconds...[/yellow]")
                        time.sleep(BACKOFF)
                else:
                    print(
                        f"[red]File backup for {backup['name']} failed after {MAX_RETRIES} attempts.[/red]"
                    )

                if backup_result:
                    backup_result["errors"] = errors

                    if not backup_result.get("summary_payload"):
                        # default payload
                        backup_result["summary_payload"] = {
                            "domain": backup.get("name"),
                            "total_size": 0,
                            "new_data": 0,
                            "start_at": backup_started_at,
                            "finish_at": now(),
                            "status": "failed",
                            "backup_method": "incremental" if is_incremental else "tar",
                        }

                    log_update_data = {
                        "status": Log.__SUCCESS__
                        if backup_result.get("success")
                        else Log.__FAILED__,
                        "description": backup_result["message"],
                        "time_consume": backup_result["time_consumed"],
                    }

                    if "file_size" in backup_result:
                        log_update_data["file_size"] = backup_result["file_size"]
                    if "file_path" in backup_result:
                        log_update_data["file_path"] = backup_result["file_path"]

                    Log.update(log_update_data).where(Log.id == log.id).execute()

                    if notification_payload := backup_result.get("notification"):
                        self._send_notification(
                            site=backup.get("name"),
                            **notification_payload
                        )

                    try:
                        with ProgressSpinner("sending summary data..."):
                            send_backup_summary(**backup_result["summary_payload"])
                    except Exception as e:
                        print(f"[red]Error sending summary: {e}[/red]")

                    try:
                        payload = self._build_api_payload(
                            site_config=backup,
                            file_backup_result=backup_result,
                            database_results=database_results,
                            backup_mode=backup_mode,
                            backup_started_at=backup_started_at,
                            rustic_version=rustic_version,
                        )

                        Master.get().send(payload)
                    except Exception as e:
                        print(
                            f"[red]Failed to send backup report for {backup['name']}: {e}[/red]"
                        )
                        if is_debug():
                            traceback.print_exc()

            except StorageCredentialError as e:
                print(f"[red]{e}[/red]")
                self._send_notification(
                    site=backup.get("name"),
                    status="failed",
                    event="credential_failed",
                    title=f"Storage Credential Failed for {backup.get('name')}",
                    message=str(e),
                )
                continue
            except Exception as e:
                if is_debug():
                    traceback.print_exc()

                error_msg = f"An unexpected error occurred during backup process for {backup['name']}: {e}"
                print(f"[red]{error_msg}[/red]")

                if log:
                    Log.update(
                        status=Log.__FAILED__,
                        description=f"Backup failed: {e}",
                    ).where(Log.id == log.id).execute()

                self._send_notification(
                    site=backup.get("name"),
                    status="failed",
                    event="backup_failed",
                    title=f"Backup failed for {backup.get('name')}",
                    message=error_msg,
                )

                try:
                    payload = self._build_api_payload(
                        site_config=backup,
                        file_backup_result=backup_result,
                        database_results=database_results,
                        backup_mode=backup_mode,
                        backup_started_at=backup_started_at,
                        rustic_version=rustic_version,
                    )

                    Master.get().send(payload)
                except Exception as e:
                    print(
                        f"[red]Failed to send backup report for {backup['name']}: {e}[/red]"
                    )
                    if is_debug():
                        traceback.print_exc()

    def backup_config(self, site_config: Dict[str, Any], _s3: Optional[s3]) -> None:
        """Backs up configuration files."""
        if not (_s3 and Config().read("bqckup", "config_backup")):
            return

        print("Backing up config files...")
        backup_config = Path(SITE_CONFIG_PATH) / site_config["file_name"]

        try:
            _s3.upload(backup_config, f"config/{site_config.get('name')}.yml", False)
            _s3.upload(STORAGE_CONFIG_PATH, "storages.yml", False)
        except Exception as e:
            print(f"[red]Failed to backup config: {e}[/red]")

    def full_backup(self, site_config) -> dict:
        summary_payload = {
            "domain": site_config.get("name"),
            "total_size": 0,
            "new_data": 0,
            "start_at": now(),
            "finish_at": None,
            "status": "failed",
            "backup_method": "tar",
        }

        result = {
            "success": False,
            "started_at": now(),
            "ended_at": None,
            "message": "",
            "error": None,
            "traceback": None,
            "time_consumed": 0,
            "backup_method": "tar",
            "summary_payload": summary_payload,
        }

        try:
            bqckup_config_location = os.path.join(
                SITE_CONFIG_PATH, site_config["file_name"]
            )
            backup = Yml_Parser.parse(bqckup_config_location)["bqckup"]
            backup_folder = f"{backup.get('name')}/{get_today()}"
            tmp_path = os.path.join(BQ_PATH, "tmp", f"{backup.get('name')}")

            if not File().is_exists(tmp_path):
                os.makedirs(tmp_path)

            compressed_file = os.path.join(tmp_path, f"{int(time.time())}.tar.gz")
            result["file_path"] = compressed_file

            compressed_file = Tar().compress(
                backup.get("path"),
                compressed_file,
                backup.get("options")["follow_symlink"],
                site_config.get("exclude_path", []),
            )

            last_compressed_file_backup = (
                Log()
                .select()
                .where(
                    (Log.name == backup.get("name"))
                    & (Log.type == Log.__FILES__)
                    & (Log.file_size != 0)
                )
                .order_by(Log.id.desc())
                .get_or_none()
            )

            compressed_file_size = os.stat(compressed_file).st_size
            result["file_size"] = compressed_file_size
            summary_payload["total_size"] = compressed_file_size
            summary_payload["new_data"] = compressed_file_size

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

            if (
                last_compressed_file_backup
                and os.stat(compressed_file).st_size
                == last_compressed_file_backup.file_size
            ):
                print(
                    f"[red]Based on file size, there is no changes detected for {compressed_file}[/red]\n"
                )

                result["notification"] = {
                    "status": "no_change",
                    "event": "no_change_detected",
                    "title": "No Changes Detected",
                    "description": (
                        "We have not detected any changes. There could be 2 reasons for this:\n"
                        "1. The application is rarely used.\n"
                        "2. There might be an issue with the database backup process.\n\n"
                        "We recommend the following steps:\n"
                        "1. Check the storage (S3) bucket. If the database size is less than 1 KB or seems unusual, it likely means the backup did not complete successfully.\n"
                        "2. Attempt to force a backup by running `bqckup --site {domain_name} --force` to ensure the backup process is functioning correctly."
                    ),
                    "message": "Based on file size, there is no changes detected",
                    "additional_data": {
                        "name": "File name",
                        "value": os.path.basename(compressed_file),
                        "inline": False,
                    },
                    "footer": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup",
                }

            if backup.get("options").get("provider") == "local":
                destination = backup.get("options").get("save_locally_path")
                if not destination:
                    destination = os.path.join(BQ_PATH, "tmp")
                    print(
                        "[yellow]save_locally_path is not configured for local provider[/yellow]"
                    )
                    print(f"[yellow]Using '{destination}' as backup location[/yellow]")

                backup_path = os.path.join(destination, backup_folder)

                if not os.path.exists(backup_path):
                    os.makedirs(backup_path, exist_ok=True)

                backup_path_without_date = os.path.join(destination, backup["name"])
                folders = [
                    folder
                    for folder in os.listdir(backup_path_without_date)
                    if os.path.isdir(os.path.join(backup_path_without_date, folder))
                ]
                folders.sort(
                    key=lambda x: os.path.getmtime(
                        os.path.join(backup_path_without_date, x)
                    )
                )

                if len(folders) > int(backup.get("options").get("retention")):
                    shutil.rmtree(os.path.join(backup_path_without_date, folders[0]))

                if os.path.exists(compressed_file):
                    shutil.move(
                        compressed_file,
                        os.path.join(backup_path, os.path.basename(compressed_file)),
                    )

            if backup.get("options").get("provider") == "s3":
                # Cleaning Old Folder
                self._clean_old_backups(site_config)

                _s3 = s3(storage_name=backup.get("options").get("storage"))

                if os.path.exists(compressed_file):
                    print(f"\nUploading {compressed_file}")
                    _s3.upload(
                        compressed_file,
                        f"{backup_folder}/{os.path.basename(compressed_file)}",
                    )

                    should_save_locally = backup.get("options").get("save_locally")
                    save_locally_path = backup.get("options").get(
                        "save_locally_path"
                    )  # If not set it will be at /etc/bqckup/tmp

                    if not should_save_locally:
                        os.unlink(compressed_file)
                    elif should_save_locally and save_locally_path:
                        print("Saving file backup locally ...")
                        if not os.path.isdir(save_locally_path):
                            raise Exception(
                                f"Save locally path {save_locally_path} is not a directory"
                            )
                        else:
                            try:
                                save_locally_path = os.path.join(
                                    save_locally_path, backup.get("name")
                                )
                                if not os.path.isdir(save_locally_path):
                                    os.makedirs(save_locally_path)
                                if (
                                    os.path.dirname(os.path.abspath(compressed_file))
                                    != save_locally_path
                                ):
                                    shutil.move(compressed_file, save_locally_path)
                            except Exception as e:
                                print(f"Failed to save file backup locally: {e}")

            print(f"\n[green]Backup for {backup.get('name')} is done![/green]")
            summary_payload["status"] = "completed"
            result["success"] = True
            result["message"] = "File Backup Success"

        except Exception as e:
            if is_debug():
                traceback.print_exc()

            # If backup failed remove the tmp folder
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                remove_folder(tmp_path)

            result["success"] = False
            result["message"] = f"File Backup Failed: {e}"
            result["error"] = e
            result["traceback"] = traceback.format_exc()
            print(f"[{site_config.get('name')}] Error: {e}.")

        result["ended_at"] = now()
        result["time_consumed"] = now() - result["started_at"]
        result["summary_payload"]["finish_at"] = now()

        return result

    def incremental_backup(
        self,
        site_config: Dict[str, Any],
    ) -> dict:
        time_start = time.time()
        summary_payload = {
            "domain": site_config.get("name"),
            "total_size": 0,
            "new_data": 0,
            "start_at": now(),
            "finish_at": None,
            "status": "failed",
            "backup_method": "incremental",
        }

        result = {
            "success": False,
            "started_at": now(),
            "ended_at": None,
            "message": "",
            "error": None,
            "traceback": None,
            "time_consumed": 0,
            "backup_method": "incremental",
            "summary_payload": summary_payload,
            "notification": {},
        }

        provider = site_config.get("options", {}).get("provider")

        if provider not in ("s3", "local"):
            raise Exception(
                f"Incremental backup does not support provider '{provider}'. Supported providers: s3, local."
            )

        if provider == "s3":
            bucket_name = site_config.get("options", {}).get("storage")
            try:
                storage_config = Storage().get_storage_detail(bucket_name)
            except StorageCredentialError as e:
                print(f"[red]{e}[/red]")
                result["notification"] = {
                    "status": "failed",
                    "event": "credential_failed",
                    "title": f"Storage Credential Failed for {site_config['name']}",
                    "message": str(e),
                }
                return result
        else:
            storage_config = {}

        rustic = Rustic(site_config, storage_config)

        try:
            rustic.check_and_dump()

            with ProgressSpinner("doing incremental backup..."):
                rustic_result = rustic.backup()

            try:
                stats = rustic.get_stats()
                summary_payload["total_size"] = stats.get(
                    "compressed_repo_size", rustic_result.get("total_size", 0)
                )
            except Exception:
                summary_payload["total_size"] = rustic_result.get("total_size", 0)
            summary_payload["new_data"] = rustic_result.get("uploaded", 0)
            summary_payload["status"] = "completed"

            result["success"] = True
            result["message"] = "File Backup Success"
            result["file_size"] = summary_payload["total_size"]
            result["file_path"] = rustic_result.get("id")

            print("=========================================")
            print("Backup complete")
            print("New Files\t:", rustic_result["new"])
            print("Changed Files\t:", rustic_result["changed"])
            print("Unchanged Files\t:", rustic_result["unchanged"])
            print("Data Uploaded\t:", format_size(rustic_result["uploaded"]))
            print("Total Size\t:", format_size(rustic_result["total_size"]))
            print("Time Consumed\t:", format_timespan(rustic_result["total_duration"]))
            print("=========================================")

            with ProgressSpinner("checking repository..."):
                rustic.check_repository()

            # Dated archive folders only exist on S3; for local the rustic repo
            # retention is handled entirely by rustic.clean() below.
            if provider == "s3":
                self._clean_old_backups(site_config)
            rustic.clean()

        except RusticCleanError as e:
            result["traceback"] = traceback.format_exc()
            result["success"] = True
            result["message"] = "File Backup Success, but repository cleanup failed."

            err_detail = str(e)
            if e.__cause__ and isinstance(e.__cause__, CalledProcessError):
                cause = e.__cause__
                err_detail = (
                    f"Command: '{cause.cmd}'\n"
                    f"Output: '{cause.stdout}'\n"
                    f"Error: '{cause.stderr}'\n"
                )

            result["notification"] = {
                "status": "completed_with_errors",
                "event": "cleanup_failed",
                "title": f"Rustic Repository Cleanup Failed for {site_config['name']}",
                "message": f"Backup completed successfully, but repository cleanup failed. {err_detail}",
            }
            print(f"({site_config['name']}) Error while cleaning rustic repository.")

        except RusticCheckError as e:
            result["traceback"] = traceback.format_exc()
            result["success"] = False
            result["message"] = "File Backup Success, but repository check failed."
            result["notification"] = {
                "status": "completed_with_errors",
                "event": "repo_check_failed",
                "title": f"Repository Check Failed for {site_config['name']}",
                "message": (
                    f"Backup completed successfully, but repository check failed. Error: {e}. "
                    "Visit https://docs.bqckup.com/bqckup-documentation/troubleshoots/fixing-a-corrupted-incremental-backup to fix it"
                ),
            }
            print(f"({site_config['name']}) Error while checking repository.")

        except Exception as e:
            if is_debug():
                traceback.print_exc()

            err_msg = "unexpected error"
            err_detail = str(e)

            if e.__cause__ and isinstance(e.__cause__, CalledProcessError):
                err_msg = "command error"
                cause = e.__cause__
                err_detail = (
                    f"Command: '{cause.cmd}'\n"
                    f"Output: '{cause.stdout}'\n"
                    f"Error: '{cause.stderr}'\n"
                )
            elif isinstance(e, FileNotFoundError):
                err_msg = "rustic is not installed"
            elif isinstance(e, RusticConfigError):
                err_msg = "invalid configuration"

            print(
                f"Error while backing up {site_config['name']}: {err_msg}: {err_detail}"
            )

            result["success"] = False
            result["message"] = f"File Backup Failed: {err_msg}"
            result["error"] = e
            result["traceback"] = traceback.format_exc()
            result["notification"] = {
                 "status": "failed",
                 "event": "incremental_backup_failed",
                 "title": f"Incremental Backup Failed for {site_config['name']}",
                 "message": (
                    f"An error occurred while backup. {err_msg}: {err_detail}. "
                    "Visit https://docs.bqckup.com/bqckup-documentation/troubleshoots/fixing-a-corrupted-incremental-backup to fix it"
                ),
            }

        finally:
            rustic.dump_config(with_credentials=False)

        result["time_consumed"] = now() - time_start
        result["ended_at"] = now()
        result["summary_payload"]["finish_at"] = now()

        return result

    def backup_databases(
        self, site_config: Dict[str, Any], s3: Optional[s3]
    ) -> List[Dict[str, Any]]:
        databases = Database.get_all(site_config)
        results = []

        if not databases:
            return results

        print(f"Backing up {len(databases)} databases...")

        should_save_locally: bool = site_config.get("options", {}).get(
            "save_locally", False
        )
        save_locally_path_str = site_config.get("options", {}).get(
            "save_locally_path", "/etc/bqckup/tmp"
        )
        save_locally_path = (
            Path(save_locally_path_str) if save_locally_path_str else None
        )

        if not s3:
            should_save_locally = True

        for database in databases:
            # root@localhost:3306/dbname
            db_label = f"{database['user']}@{database['host']}:{database['port']}/{database['name']}"
            tmp_path: Path = Path(BQ_PATH) / "tmp" / site_config["name"]
            backup_path = tmp_path / f"{int(time.time())}-{database['name']}.sql.gz"

            db_job_result = {
                "database": {
                    "name": database["name"],
                    "host": database["host"],
                    "port": int(database["port"]),
                    "user": database["user"],
                    "type": database["type"],
                },
                "success": False,
                "size": 0,
                "started_at": now(),
                "ended_at": None,
                "errors": [],
            }

            current_log = Log().write(
                {
                    "name": site_config["name"],
                    "description": f"Database Backup for '{db_label}' in Progress",
                    "type": Log.__DATABASE__,
                    "storage": site_config["options"]["storage"],
                    "file_path": str(backup_path),
                }
            )

            result = {}
            errors = []

            for attempt in range(MAX_RETRIES):
                attempt_info = (
                    f" (Attempt {attempt + 1}/{MAX_RETRIES})" if attempt > 0 else ""
                )
                print(
                    f"Starting database backup for {site_config['name']} {db_label}{attempt_info}"
                )

                result = self.backup_database(
                    site_config=site_config,
                    database=database,
                    s3=s3,
                    backup_path=backup_path,
                    db_label=db_label,
                )

                if result["success"]:
                    print(f"[green]Database backup for {db_label} successful.[/green]")
                    break

                error = result.get("traceback") or result.get("error")
                if error:
                    errors.append(str(error))

                error_message = result.get("error", "Unknown error")
                print(
                    f"[yellow]Database backup for {db_label} failed: {error_message}[/yellow]"
                )

                if result.get("corrupt"):
                    # Corrupt table + automatic repair already failed once; retrying the
                    # same dump won't help and would just waste time before we report it.
                    print(
                        f"[red]Skipping further retries for {db_label}: corrupt table repair failed and requires manual intervention.[/red]"
                    )
                    break

                if attempt < MAX_RETRIES - 1:
                    print(f"[yellow]Retrying in {BACKOFF} seconds...[/yellow]")
                    time.sleep(BACKOFF)
            else:
                print(
                    f"[red]Database backup for {db_label} failed after {MAX_RETRIES} attempts.[/red]"
                )

            db_job_result["success"] = result.get("success", False)
            db_job_result["size"] = result.get("file_size", 0)
            db_job_result["started_at"] = result.get("started_at", now())
            db_job_result["ended_at"] = result.get("ended_at", now())
            db_job_result["errors"] = errors

            log_update_data = {
                "time_consume": result.get("time_consumed", 0),
                "description": result.get("message", "No message"),
            }

            if result.get("success"):
                log_update_data["status"] = Log.__SUCCESS__
                if "file_size" in result:
                    log_update_data["file_size"] = result["file_size"]

                self._post_database_backup(
                    site_name=site_config["name"],
                    db_label=db_label,
                    backup_path=backup_path,
                    time_consumed=result.get("time_consumed", 0),
                    should_save_locally=should_save_locally,
                    save_locally_path=save_locally_path,
                )
            else:
                log_update_data["status"] = Log.__FAILED__
                self._send_notification(
                    site=site_config["name"],
                    status="failed",
                    event="database_backup_failed",
                    title=f"Database Backup Failed for {site_config['name']} {db_label}",
                    message=f"Error: {result.get('error')}",
                )

            Log.update(log_update_data).where(Log.id == current_log.id).execute()

            results.append(db_job_result)

        return results

    def backup_database(
        self,
        site_config: Dict[str, Any],
        database: Dict[str, Any],
        s3: Optional[s3],
        backup_path: Path,
        db_label: str,
    ) -> dict:
        tmp_path = backup_path.parent

        if not tmp_path.exists() or not tmp_path.is_dir():
            tmp_path.mkdir(parents=True, exist_ok=True)

        result = {
            "success": False,
            "started_at": now(),
            "ended_at": None,
            "message": "",
            "error": None,
            "traceback": None,
            "time_consumed": 0,
        }

        try:
            with ProgressSpinner(f"Exporting database {db_label}"):
                db_type = database.get("type", "mysql")
                if db_type == "sqlite":
                    db_user = ""
                    db_password = ""
                    db_host = ""
                    db_port = 0
                else:
                    db_user = database["user"]
                    db_password = database["password"]
                    db_host = database["host"]
                    db_port = database["port"]

                Database(type=db_type).export(
                    str(backup_path),
                    db_user=db_user,
                    db_password=db_password,
                    db_name=database["name"],
                    db_host=db_host,
                    db_port=db_port,
                )

            if s3:
                s3.upload(
                    backup_path,
                    Path(site_config["name"]) / get_today() / backup_path.name,
                )

            result["success"] = True
            result["message"] = f"Database Backup for '{db_label}' Success"
            result["file_size"] = backup_path.stat().st_size

        except DatabaseCorruptException as e:
            # Corrupt table detected and automatic repair could not resolve it.
            # The last known-good backup on storage is left untouched since we
            # never reach the upload step above.
            result["success"] = False
            result["corrupt"] = True
            result["repair_attempted"] = e.repair_attempted
            result["repair_succeeded"] = e.repair_succeeded
            result["table_name"] = getattr(e, "table_name", None)
            result["message"] = f"Database Backup Failed for '{db_label}': {e}"
            result["error"] = e
            result["traceback"] = traceback.format_exc()

        except Exception as e:
            result["success"] = False
            result["message"] = f"Database Backup Failed for '{db_label}': {e}"
            result["error"] = e
            result["traceback"] = traceback.format_exc()

        result["time_consumed"] = now() - result["started_at"]
        result["ended_at"] = now()
        return result

    def _post_database_backup(
        self,
        site_name: str,
        db_label: str,
        backup_path: Path,
        time_consumed: float,
        should_save_locally: bool = False,
        save_locally_path: Optional[Path] = None,
    ) -> None:
        last_log = (
            Log.select()
            .where(
                (Log.name == site_name)
                & (Log.type == Log.__DATABASE__)
                & (Log.status == Log.__SUCCESS__)
                & (Log.description.contains(db_label))
            )
            .order_by(Log.id.desc())
            .get_or_none()
        )

        try:
            if last_log:
                previous_size = format_size(last_log.file_size)
                formatted_time_consume = format_timespan(time_consumed)
                current_size = format_size(backup_path.stat().st_size)

                print("=========================================")
                print("Database Compressed")
                print(f"Database\t: {db_label}")
                print(f"Previous Size\t: {previous_size}")
                print(f"Current Size\t: {current_size}")
                print(f"Time Consumed\t: {formatted_time_consume}")
                print("=========================================")

                if previous_size == current_size:
                    print(
                        f"[yellow]Based on file size, there is no changes detected for {backup_path.name}[/yellow]"
                    )

            if not should_save_locally:
                backup_path.unlink(missing_ok=True)  # remove file
            elif should_save_locally and save_locally_path:
                print(f"Saving '{backup_path.name}' locally ...")
                final_dest_path: Path = save_locally_path / site_name
                if not final_dest_path.is_dir():
                    final_dest_path.mkdir(parents=True, exist_ok=True)

                if backup_path.parent.resolve() != final_dest_path.resolve():
                    print(f"Moving {backup_path} to {final_dest_path}...")
                    shutil.move(backup_path, final_dest_path)
                else:
                    print(f"Database backup located at {backup_path}")

            print()
        except Exception as e:
            print(
                f"Error while post-processing database backup for {site_name} '{db_label}': {e}"
            )
