from rich.progress import Progress, SpinnerColumn, TextColumn
from lib.notifications.discord import send_notification
from datetime import datetime
from helpers import bytes_to
from helpers.datetime import difference_in_days, interval_in_number
from helpers.utility import split_list
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
        if Config().read('notification', 'monthly_report_enabled') != '1':
            return
        
        last_day_of_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
        if datetime.now().day != last_day_of_month:
            return
        
        storages = Storage().list()
        sites = Bqckup().list()

        first_day_of_month = datetime.now().replace(day=1).timestamp()
        first_day_of_two_month_ago = datetime.now().replace(day=1, month=datetime.now().month - 1).timestamp()

        for storage in storages:
            hash_value_notification = sha256(storage.encode()).hexdigest()
            if NotificationLog().select().where(NotificationLog.hash == hash_value_notification).exists():
                continue
            print ('make report for this month')
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
                    for failed_log in failed_logs:
                        if failed_log.name in logs:
                            logs[failed_log.name] += 1
                        else:
                            logs[failed_log.name] = 1
                    failed_site = ''
                    for log in logs:
                        failed_site += f"{log} ({logs[log]} fail)\n"
                    
                    # get content for this month from backups s3
                    filter_this_month = lambda content: content.get('LastModified').month == datetime.now().month
                    contents = list(filter(filter_this_month, backups.get('Contents')))

                    # list site in storage
                    list_site_in_storage = []
                    for content in contents:
                        site_name = content.get('Key').split('/')[1]
                        ignore = ['config', 'storages.yml']
                        if site_name not in list_site_in_storage and site_name not in ignore:
                            list_site_in_storage.append(site_name)

                    # check site
                    list_error_site_need_to_check = dict()
                    for site in sites.values():
                        filter_two_month_ago_and_by_same_site = lambda content: ((content.get('LastModified').timestamp() >= first_day_of_two_month_ago) and (content.get('Key').split('/')[1] == site['name']))
                        contents_from_two_month_ago = list(filter(filter_two_month_ago_and_by_same_site, backups.get('Contents')))
                        interval = interval_in_number(site['options']['interval'])

                        if not contents_from_two_month_ago: 
                            continue

                        contents_database = list(filter(lambda x: x.get('Key').split('.')[-2] == 'sql', contents_from_two_month_ago))
                        contents_files = list(filter(lambda x: x.get('Key').split('.')[-2] != 'sql', contents_from_two_month_ago))
                
                        error_database = self._check_site(contents_database, interval, site, 'sql')
                        error_files = self._check_site(contents_files, interval, site, 'files')
                        error = error_database + error_files
                        if len(error) > 0:
                            list_error_site_need_to_check[site['name']] = error

                    # calculate size
                    largest_content = max(contents, key=lambda x: x['Size'])
                    total_size = 0
                    for content in contents:
                        total_size += content['Size']

                    # list message site need to check
                    site_need_to_check = []
                    for site_name in list_error_site_need_to_check:
                        embeds = {
                                'title': f'need to check at site {site_name}',
                                'description' : '\n'.join(list_error_site_need_to_check[site_name]),
                                'color' : 15548997,
                                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                            }
                        
                        site_need_to_check.append(embeds)

                    # list all backups for this month
                    fields = [
                            {"name": "Server IP", "value": get_server_ip(), "inline": True},
                            {"name": "Bqckup Version", "value": VERSION, "inline": True},
                            {"name": "Storage", "value": storage, "inline": True},
                            {"name": "Total Site on config", "value": len(Bqckup().list()), "inline": True},
                            {"name": "Total Size", "value": f"{bytes_to('m',total_size)} MB", "inline": True},
                            {"name": "Largest Site Files", "value": f"{largest_content.get('Key').split('/')[1]} ({bytes_to('m', largest_content.get('Size'))} MB)", "inline": True},
                            {"name": "List site in storage", "value": '\n'.join(list_site_in_storage), "inline": True},
                            {"name": "Failed Site", "value": failed_site, "inline": True},
                        ]
                    payload = {
                            "embeds": [{
                                "title": f"Report this {datetime.now().strftime('%B %Y')}",
                                "description": f"This is an automated notification to inform you that the bqckup information.",
                                "color": 30646,
                                "fields": fields,
                                "footer": {"text": "If this was a mistake, please create issue here: https://github.com/bqckup/bqckup"}
                            }, ]
                        }
                    
                    # send to discord
                    send_notification(payload)

                    site_need_to_check = split_list(site_need_to_check, 10)
                    for embeds in site_need_to_check:
                        payload = {"embeds" : embeds}
                        send_notification(payload)

                    NotificationLog().create(hash=hash_value_notification, sent_at=int(datetime.now().timestamp()))  
                    progress.update(task, completed=True)
                    print ('[green]success send report to discord[/green]')
            except Exception as e:
                print(f"[red]Failed to send data to discord, {str(e)}[/red]")
        return True
    
    def _check_site(self, contents, interval, site, type):
        contents.reverse()
        reason = dict()
        reason['error'] = []
        for i, content in enumerate(contents):
            if i+1 < len(contents) and contents[i+1]:
                prev_content = contents[i+1]
                difference_with_prev_content = abs(difference_in_days(content.get('LastModified').timestamp(), prev_content.get('LastModified').timestamp()))

                # check the interval is correct with backup
                if difference_with_prev_content != interval :
                    if 'interval' not in reason:
                        reason['error'].append(f"backup interval is not same as set in site configuration ({site['options']['interval']}) type {type}")
                    reason['interval'] = True

                # check the size is not same with next content
                if content.get('Size') == prev_content.get('Size'):
                    if "size" not in reason:
                        reason['error'].append(f"backup size is same at {content.get('Key')}")
                    reason["size"] = True
        
        return reason['error']