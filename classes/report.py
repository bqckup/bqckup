from rich.progress import Progress, SpinnerColumn, TextColumn
from lib.notifications.discord import send_notification
from datetime import datetime
from helpers import bytes_to
from helpers.datetime import difference_in_days, interval_in_number, get_today
from helpers.utility import split_list, isset
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
    def send(self):
        if Config().read('notification', 'enabled') != '1' and Config().read('notification', 'monthly_report_enabled') != '1':
            return
        
        last_day_of_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        if datetime.now().day != last_day_of_month:
            return
        
        storages = Storage().list()
        sites = Bqckup().list()

        first_day_of_month = datetime.now().replace(day=1).timestamp()
        first_day_of_two_month_ago = datetime.now().replace(day=1, month=datetime.now().month - 1).timestamp()

        for storage in storages:
            hash_value_notification = sha256(f"{storage}_{get_today("%B_%Y")}".encode()).hexdigest()
            if NotificationLog().select().where(NotificationLog.hash == hash_value_notification).exists():
                continue
            
            print (f"make report this month for '{storage}'")
            try:
                with Progress(SpinnerColumn(),TextColumn("[progress.description]{task.description}"),transient=True,) as progress:
                    task = progress.add_task(description=f"Fetching and calculate data for storage '{storage}'...", total=None)

                    # get data from s3
                    backups = s3(storage).list()
                    # get data from log
                    failed_logs = list(Log().select().where((Log.created_at >= first_day_of_month) & (Log.storage == storage) & (Log.status == Log.__FAILED__)).execute())

                    # check if backup exists
                    if not backups or not backups.get('Contents'):
                        print(f"[red] No backup found for {storage} [/red]")
                        return None

                    # count the failed site in logs
                    logs = {}
                    failed_logs_description = {}
                    for failed_log in failed_logs:
                        created_at = datetime.fromtimestamp(failed_log.created_at).strftime('%Y-%B-%d %H:%M:%S')
                        if failed_log.name in logs:
                            logs[failed_log.name] += 1
                            failed_logs_description[failed_log.name].append(f"{failed_log.description} ({created_at})")
                        else:
                            logs[failed_log.name] = 1
                            failed_logs_description[failed_log.name] = [f"{failed_log.description} ({created_at})"]
                    failed_site = ''
                    for log in logs:
                        failed_logs_description[log] = list(set(failed_logs_description[log]))
                        failed_site += f"{log} ({logs[log]} fail)\n"
                    
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
                    largest_backup = max(backups_this_month, key=lambda x: x['Size'])
                    total_size = 0
                    for backup in backups_this_month:
                        total_size += backup['Size']

                    # format message list site in storage
                    list_failed_site_logs = logs.keys()
                    failed_site = logs
                    message_list_site_in_storage = ''
                    message_list_site_in_storage += '```ansi\n'
                    list_site_name_in_config = list(map(lambda x: x['name'], sites.values()))
                    for site in list_site_in_storage:
                        if site not in list_site_name_in_config:
                            message_list_site_in_storage += f"[2;33m{site}[0m"
                        else:
                            message_list_site_in_storage += site

                        if site in list_failed_site_logs:
                            message_list_site_in_storage += f" [2;31m({logs[site]} fail)[0m"
                        if site in list_error_site_need_to_check:
                            message_list_site_in_storage += ' [2;31m<-- need to check [0m'
                        message_list_site_in_storage += '\n'
                    message_list_site_in_storage += '```'

                    # list message site need to check
                    embeds_site_need_to_check = []
                    for site_name in list_error_site_need_to_check:
                        message_list_site_need_to_check = ''
                        unique_error = list(set(list_error_site_need_to_check[site_name]))
                        for i, error in enumerate(unique_error):
                            message_list_site_need_to_check += f"{i + 1}. {error} \n"

                        # merge with failed logs
                        if site_name in failed_logs_description:
                            message_list_site_need_to_check += f"\nFailed logs: \n"
                            for i, log in enumerate(failed_logs_description[site_name]):
                                message_list_site_need_to_check += f"{i + 1}. {log} \n"

                        embeds = {
                                'title': f"need to check at site '{site_name}' in storage '{storage}'",
                                'description' : message_list_site_need_to_check,
                                'color' : 16713736,
                                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                            }
                        
                        embeds_site_need_to_check.append(embeds)

                    # list all backups for this month
                    fields = [
                            {"name": "Server IP", "value": get_server_ip(), "inline": True},
                            {"name": "Bqckup Version", "value": VERSION, "inline": True},
                            {"name": "Storage", "value": storage, "inline": True},
                            {"name": "Total Site on config", "value": len(Bqckup().list()), "inline": True},
                            {"name": "Total Size", "value": f"{bytes_to('m',total_size)} MB", "inline": True},
                            {"name": "Largest Site Files", "value": f"{largest_backup.get('Key').split('/')[1]} ({bytes_to('m', largest_backup.get('Size'))} MB)", "inline": True},
                            {"name": "List site in storage", "value": message_list_site_in_storage, "inline": False},
                            {"name": "", "value": "```ansi\n[2;33myellow [0m: your site not in config\n```", "inline": False},
                            # {"name": "Failed Site", "value": failed_site, "inline": True},
                        ]
                    payload = {
                            "embeds": [{
                                "title": f"Report this {get_today("%B_%Y")}",
                                "description": f"This is an automated notification to inform you that the bqckup information.",
                                "color": 30646,
                                "fields": fields,
                                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                            }, ]
                        }
                    
                    # send to discord
                    send_notification(payload)

                    embeds_site_need_to_check = split_list(embeds_site_need_to_check, 10)
                    for embeds in embeds_site_need_to_check:
                        payload = {"embeds" : embeds}
                        send_notification(payload)

                    NotificationLog().create(hash=hash_value_notification, sent_at=int(datetime.now().timestamp()))  
                    progress.update(task, completed=True)
                    print ('[green]success send report to discord[/green]')
            except Exception as e:
                print(f"[red]Failed to send data to discord, {str(e)}[/red]")
        return True
    
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