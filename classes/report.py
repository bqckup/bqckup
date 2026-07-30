from rich.progress import Progress, SpinnerColumn, TextColumn
from lib.notifications.webhook import send_report_to_webhook
from datetime import datetime
from helpers.datetime import difference_in_days, interval_in_number, get_today
from helpers.utility import isset, is_debug
from models.log import Log
from classes.bqckup import Bqckup
from classes.storage import Storage
from classes.s3 import s3
from helpers.network import get_server_ip
from bqckup import VERSION
from rich import print
from classes.config import Config
import calendar
from hashlib import sha256
from models.notification_log import NotificationLog

class Report:

    def send(self, force: bool = False):
        if Config().read('notification', 'enabled') != '1' and Config().read('notification', 'monthly_report_enabled') != '1':
            return
        
        last_day_of_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        if not force and not is_debug() and datetime.now().day != last_day_of_month:
            return
        
        storages = Storage().list()
        sites = Bqckup().list()

        now = datetime.now()
        first_day_of_month = now.replace(day=1).timestamp()
        if now.month == 1:
            first_day_of_two_month_ago = now.replace(year=now.year - 1, month=12, day=1).timestamp()
        else:
            first_day_of_two_month_ago = now.replace(day=1, month=now.month - 1).timestamp()

        for storage in storages:
            hash_value_notification = sha256(f"{storage}_{get_today('%B_%Y')}".encode()).hexdigest()
            if not force and not is_debug() and NotificationLog().select().where(NotificationLog.hash == hash_value_notification).exists():
                continue
            
            print (f"make report this month for '{storage}'")
            try:
                with Progress(SpinnerColumn(),TextColumn("[progress.description]{task.description}"),transient=True,) as progress:
                    task = progress.add_task(description=f"Fetching and calculate data for storage '{storage}'...", total=None)

                    _s3 = s3(storage)
                    sites_key = _s3.list(
                        prefix=f"{_s3.root_folder_name}/", delimiter="/"
                    )

                    site_prefixes = [
                        p.get("Prefix")
                        for p in sites_key.get("CommonPrefixes", [])
                        if p.get("Prefix")
                    ]

                    all_backups = []
                    for site_prefix in site_prefixes:
                        site_name = site_prefix.strip("/").split("/")[-1]

                        backup_date_prefixes = _s3.get_backup_dates(
                            site_name=site_name, sort_by_date=False
                        )

                        for backup_prefix in backup_date_prefixes:
                            objects = _s3.list(prefix=backup_prefix).get("Contents")
                            if objects:
                                all_backups.extend(objects)

                    backups = {"Contents": all_backups}

                    # get data from log
                    failed_logs = list(Log().select().where((Log.created_at >= first_day_of_month) & (Log.storage == storage) & (Log.status == Log.__FAILED__)).execute())

                    # check if backup exists
                    if not backups or not backups.get('Contents'):
                        print(f"[red] No backup found for {storage} [/red]")
                        continue

                    # count the failed site in logs
                    logs = {}
                    failed_logs_description = {}
                    for failed_log in failed_logs:
                        created_at = datetime.fromtimestamp(failed_log.created_at).strftime('%d-%B-%Y %H:%M:%S')
                        if failed_log.name in logs:
                            logs[failed_log.name] += 1
                            failed_logs_description[failed_log.name].append(f"{failed_log.description} ({created_at})")
                        else:
                            logs[failed_log.name] = 1
                            failed_logs_description[failed_log.name] = [f"{failed_log.description} ({created_at})"]
                    for log in logs:
                        failed_logs_description[log] = list(set(failed_logs_description[log]))
                    
                    # get content for this month from backups s3
                    filter_this_month = lambda content: content.get('LastModified').month == datetime.now().month
                    backups_this_month = list(filter(filter_this_month, backups.get('Contents')))

                    # list site in storage
                    list_site_in_storage = []
                    for backup in backups_this_month:
                        site_name = backup.get('Key').split('/')[1]
                        ignore = ['config', 'storages.yml']
                        if site_name not in list_site_in_storage and site_name not in ignore:
                            list_site_in_storage.append(site_name)

                    # check site
                    list_error_site_need_to_check = dict()
                    for site in sites.values():
                        filter_two_month_ago_and_by_same_site_name = lambda content: ((content.get('LastModified').timestamp() >= first_day_of_two_month_ago) and (content.get('Key').split('/')[1] == site['name']))
                        backups_from_two_month_ago = list(filter(filter_two_month_ago_and_by_same_site_name, backups.get('Contents')))
                        interval = interval_in_number(site['options']['interval'])

                        if not backups_from_two_month_ago: 
                            continue

                        # split backups to database and files
                        backups_database = list(filter(lambda x: x.get('Key').split('.')[-2] == 'sql', backups_from_two_month_ago))
                        backups_files = list(filter(lambda x: x.get('Key').split('.')[-2] != 'sql', backups_from_two_month_ago))

                        # check site
                        error_database = self._check_site(backups_database, interval, site, 'sql')
                        error_files = self._check_site(backups_files, interval, site, 'files')
                        
                        # merge error
                        error = error_database + error_files

                        # if error found add to list by site name
                        if len(error) > 0:
                            list_error_site_need_to_check[site['name']] = error

                    # calculate size
                    largest_backup = max(backups_this_month, key=lambda x: x['Size']) if backups_this_month else {}
                    total_size = 0
                    for backup in backups_this_month:
                        total_size += backup['Size']

                    list_site_name_in_config = [site['name'] for site in sites.values()]

                    data_payload = []
                    for site in list_site_in_storage:
                        errors = list_error_site_need_to_check.get(site, [])
                        failed_logs_list = failed_logs_description.get(site, [])
                        
                        status = self._classify_status(errors, failed_logs_list)

                        data_payload.append({
                            "site": site,
                            "status": status,
                            "in_config": site in list_site_name_in_config,
                            "errors": errors,
                            "fail_count": logs.get(site, 0),
                            "failed_logs": failed_logs_list
                        })

                    payload = {
                        "report_type": "monthly",
                        "storage": storage,
                        "month": get_today('%B_%Y'),
                        "server_ip": get_server_ip(),
                        "version": VERSION,
                        "total_size_bytes": total_size,
                        "largest_site": {
                            "name": largest_backup.get('Key', '').split('/')[1] if largest_backup else "",
                            "size_bytes": largest_backup.get('Size', 0)
                        },
                        "total_sites_in_config": len(sites),
                        "data": data_payload
                    }

                    # send to webhook
                    send_report_to_webhook(payload)
                    
                    NotificationLog().create(hash=hash_value_notification, sent_at=int(datetime.now().timestamp()))  
                    progress.update(task, completed=True)
                    print ('[green]success send report to webhook[/green]')
            except Exception as e:
                print(f"[red]Failed to send data to webhook, {str(e)}[/red]")
        return True
    
    def _classify_status(self, errors, failed_logs_list):
        INTERVAL_ERR = "backup interval is not same as set in site configuration"
        if failed_logs_list or any(INTERVAL_ERR in err for err in errors):
            return "failed"
        if errors:
            return "no_change"
        return "completed"

    def _check_site(self, backups, interval, site, type):
        # reverse content to check from the latest backup
        backups.reverse()

        # init
        reason = {'error': [], 'status':[]}

        for i, backup in enumerate(backups):
            if isset(i+1, backups):
                previous_backup = backups[i+1]
                difference_with_previous_backup = abs(difference_in_days(backup.get('LastModified').timestamp(), previous_backup.get('LastModified').timestamp()))

                # check the interval is correct with backup
                if difference_with_previous_backup != interval :
                    #check to make sure the error is write once
                    if 'interval' not in reason['status']:
                        reason['error'].append(f"backup interval is not same as set in site configuration")
                    reason['status'].append('interval')

                # check the size is not same with next backup
                if backup.get('Size') == previous_backup.get('Size'):
                    if "size" not in reason['status']:
                        reason['error'].append(f"backup size is same at {backup.get('Key')}")
                    reason['status'].append('size')
        
        # return only error message
        return reason['error']
