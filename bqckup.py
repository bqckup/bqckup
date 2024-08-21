import getpass
import typer
import os
import requests
import re
import ruamel.yaml as yaml
from classes.bqckup import Bqckup
from classes.database import Database
from classes.config import Config
from classes.storage import Storage
from classes.s3 import s3
from pathlib import Path
from typing import List
from constant import VERSION, SITE_CONFIG_PATH, BQ_PATH
from rich import print
from rich.console import Group, Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress
from helpers.utility import get_disk_size, display_disk_table, confirm_with_timeout, validate_path
from helpers.network import download_files, generate_short_link, get_server_ip
from humanfriendly import format_size, format_timespan


bq_cli = typer.Typer()


@ bq_cli.command()
def report():
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from lib.notifications.discord import send_notification
    from datetime import datetime
    from helpers import bytes_to
    from helpers.datetime import difference_in_days
    from helpers.utility import split_list
    from models.log import Log

    def check_site_need_to_check(contents, interval, site, type):
        contents.reverse()
        reason = dict()
        reason['error'] = []
        for i, content in enumerate(contents):
            if i+1 < len(contents) and contents[i+1]:
                prev_content = contents[i+1]
                difference_with_prev_content = abs(difference_in_days(content.get('LastModified').timestamp(), prev_content.get('LastModified').timestamp()))

                # check the interval is correct with backup
                if difference_with_prev_content > interval :
                    if 'interval' not in reason:
                        reason['error'].append(f"backup interval is not same as set in site configuration ({site['options']['interval']}) type {type}")
                    reason['interval'] = True

                # check the size is not same with next content
                if content.get('Size') == prev_content.get('Size'):
                    if "size" not in reason:
                        reason['error'].append(f"backup size is same at {content.get('Key')}")
                    reason["size"] = True
        
        return reason['error']
    
    first_day_of_month = datetime.now().replace(day=1).timestamp()
    first_day_of_two_month_ago = datetime.now().replace(day=1, month=datetime.now().month - 1).timestamp()

    storages = Storage().list()
    sites = Bqckup().list()

    for storage in storages:
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

                # count the failed logs
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

                # check site
                list_error_site_need_to_check = dict()
                for site in sites.values():
                    filter_two_month_ago_and_by_same_site = lambda content: ((content.get('LastModified').timestamp() >= first_day_of_two_month_ago) and (content.get('Key').split('/')[1] == site['name']))
                    contents_from_two_month_ago = list(filter(filter_two_month_ago_and_by_same_site, backups.get('Contents')))
                    interval = Bqckup()._interval_in_number(site['options']['interval'])

                    if not contents_from_two_month_ago: 
                        continue
                        
                    filter_get_database = lambda x: x.get('Key').split('.')[-2] == 'sql'
                    filter_get_files = lambda x: x.get('Key').split('.')[-2] != 'sql'
                    contents_database = list(filter(filter_get_database, contents_from_two_month_ago))
                    contents_files = list(filter(filter_get_files, contents_from_two_month_ago))
                                    
                    error_database = check_site_need_to_check(contents_database, interval, site, 'sql')
                    error_files = check_site_need_to_check(contents_files, interval, site, 'files')
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
                        {"name": "Total Site", "value": len(Bqckup().list()), "inline": True},
                        {"name": "Total Size", "value": f"{bytes_to('m',total_size)} MB", "inline": True},
                        {"name": "Largest Site Files", "value": f"{largest_content.get('Key').split('/')[1]} ({bytes_to('m', largest_content.get('Size'))} MB)", "inline": True},
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

                progress.update(task, completed=True)
                print ('[green]success send data to discord[/green]')
        except Exception as e:
            print(f"[red]Failed to send report to discord, {str(e)}[/red]")
    return True

@ bq_cli.command()
def migrate():
    from models import database
    from playhouse.migrate import SqliteMigrator, migrate, IntegerField, FloatField

    try:
        # check if log table already migrated
        cursor = database.execute_sql("PRAGMA table_info(log);")
        columns = [column[1] for column in cursor.fetchall()]
        if 'time_consume' in columns:
            print ("[yellow] Log already migrated [/yellow]")
            return False

        # migrate log table
        migrator = SqliteMigrator(database)
        migrate(
            migrator.add_column('log', 'time_consume', FloatField(default=0)),
        )
        print ("[green] Log migration success [/green]")
    except Exception as e:
        print(f"Failed to migrate log, {str(e)}")

@ bq_cli.command()
def summary(site = None):
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from helpers import bytes_to
    from datetime import datetime

    bqckups = Bqckup().list()

    # search the site
    if site is not None: 
        for i in list(bqckups):
            if bqckups[i]['name'] != site:
                del bqckups[i]
        if not bqckups:
            print(f"\nSite '{site}' not found\n")
            return

    for i in bqckups:
        backup = bqckups[i]
        # get backups from s3
        backups = None
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task(description="Fetching details...", total=None)
            _s3 = s3(backup['options']['storage'])
            backups = _s3.list(f"{_s3.root_folder_name}/{backup['name']}")
            progress.update(task, completed=True)

        # check if backup exists
        if not backups or not backups.get('Contents'):
            print(f"[red] No backup found for {site} [/red]")
            return None

        contents = backups['Contents']
        last_content = max(contents, key=lambda x: x['LastModified'].timestamp())
        last_folder = last_content['Key'].split('/')[2]
        last_size = 0
        total_size = 0

        # calculate the size
        for content in contents:
            total_size += content['Size']
            if content['Key'].split('/')[2] == last_folder:
                last_size += content['Size']
        
        interval = backup['options']['interval']
        last_modified = last_content['LastModified']
        to_compare = Bqckup()._interval_in_number(interval)

        print("\n================================================================\n")
        print(f"Backup Name                     : {backup['name']}")
        print(f"Last Backup                     : {last_modified.strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"Last backup file size and name  : {bytes_to('m', last_size)} mb ({last_folder}) ")
        print(f"Total size of a bqckup          : {bytes_to('m', total_size)} mb")
        print(f"Total files                     : {backups['KeyCount']}")
        print(f"Storage Name                    : {backup['options']['storage']}")
        print(f"Schedule                        : {interval}")
        print(f"Next bqckup                     : {datetime.fromtimestamp(last_modified.timestamp() + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}")
        print(f"Local Backup                    : {'yes' if backup['options']['save_locally'] else 'no'} ")
    print("\n================================================================\n")
    print(f"Visit: https://bqckup.com\n")


@ bq_cli.command()
def history(site = None, filter_latest_days : int = 7):
    from models.log import Log
    from datetime import datetime
    from helpers import bytes_to

    # check if site is empty
    if site is None :
        print("\nPlease specify the site ([blue] bqckup history --site site_name [/blue])\n")
        return False

    def print_table(logs, table):
        for log in logs:
            # format sytle for status
            if log.status == Log.__SUCCESS__:
                status = "[green]Success[/green]"
            else:
                status = "[red]Failed[/red]"

            last_backup = datetime.fromtimestamp(log.created_at).strftime('%d/%m/%Y %H:%M:%S')
            if log.file_size >= 1e+9:
                # if size is greater than 1 gb
                size = f"{bytes_to('g', log.file_size)} GB"
            elif log.file_size >= 1000000:
                # if size is greater than 1 mb
                size = f"{bytes_to('m', log.file_size)} MB"
            else:
                size = f"{bytes_to('k', log.file_size)} KB"
            time_consume = log.time_consume
            file_name = log.file_path.split('/')[-1]

            table.add_row(last_backup, file_name, size, status, f"{time_consume:.2f}")

        Console().print(table)
    
    backup = Bqckup().detail(site)

    if backup is not None :
        logs = Log().select().where((Log.name == site) & (Log.created_at >= (datetime.now().timestamp() - (filter_latest_days * 86400)))).execute()
        
        if logs:
            schedule = backup['options']['interval']

            # split the logs into database and files
            log_database = []
            log_files = []
            for log in logs:
                if log.type == Log.__DATABASE__:
                    log_database.append(log)
                else:
                    log_files.append(log)

            table_files = Table("last backup date", 'file name' , "size", "status", 'time consume (s)')
            table_database = Table("last backup date", 'file name' , "size", "status", 'time consume (s)')

            print(f"\nBackup Name: {backup['name']} ([green]{schedule}[/green])")
            print("\nFile Backup")
            print_table(log_files, table_files)
            print ("\n Database Backup")
            print_table(log_database, table_database)
            print(f"\nVisit: https://bqckup.com\n")
        else:
            print(f"\nNo history found for site '{site}'\n")
    else:
        print(f"\nSite '{site}' not found\n")

@bq_cli.command()
def add_site(
        name: str = typer.Option(),
        path: List[str] = typer.Option(),
        storage: str = typer.Option(),
        db_name: str = typer.Option(),
        db_user: str = typer.Option(),
        db_pass: str = typer.Option(),
        db_host: str = typer.Option(default="localhost"),
        db_port: int = typer.Option(default=3306),
        interval: str = typer.Option(default='daily'),
        retention: int = typer.Option(default=7),
        save_locally: bool = typer.Option(default=False),
        save_locally_path: str = typer.Option(default=os.path.join(BQ_PATH, 'tmp'))
):
    # Check if path is empty
    if save_locally_path != os.path.join(BQ_PATH, 'tmp') and not os.path.exists(save_locally_path):
        print(f"Path '{save_locally_path}' not found")
        raise typer.Exit(code=1)
    
    # Check if name contain space or any symbol except dot and underscore
    if not re.match("^[a-zA-Z0-9_.-]*$", name):
        print("Name should not contain any space or special character except dot and underscore")
        raise typer.Exit(code=1)

    # Check paths
    for p in path:
        if not os.path.exists(p):
            print(f"Path '{p}' not found")
            raise typer.Exit(code=1)

    # Check Database Connection
    Database().test_connection({
        "user": db_user,
        "password": db_pass,
        "host": db_host,
        "name": db_name
    })

    # Interval only daily, weekly, monthly
    if interval not in ['daily', 'weekly', 'monthly']:
        print("Interval should be daily, weekly or monthly")
        raise typer.Exit(code=1)

    config = {
        'bqckup': {
            'name': name,
            'path': path,
            'database': {
                'type': 'mysql',  # Currently only support mysql
                'host': db_host,
                'port': db_port,
                'user': db_user,
                'password': db_pass,
                'name': db_name
            },
            'options': {
                'storage': storage,
                'interval': interval,
                'retention': retention,
                'save_locally': 'yes' if save_locally else 'no',
                'save_locally_path': save_locally_path,
                'notification_email': 'email@example.com',
                'provider': 's3'
            }
        }
    }

    try:
        with open(os.path.join(SITE_CONFIG_PATH, f"{name}.yml"), "w") as file:
            yml = yaml.YAML()
            yml.indent(sequence=4, offset=2)
            yml.dump(config, file)

        print(f"Backup configuration file '{name}.yaml' created successfully!")
    except Exception as e:
        print(f"Failed to create backup configuration file: {e}")
        raise typer.Exit(code=1)


@ bq_cli.command()
def get_information():
    content = Group(
        Panel("Version  : %s" % VERSION),
        Panel("Github   : https://github.com/bqckup/bqckup"),
    )
    print(
        Panel.fit(content, title="Bqckup information",
                  title_align="left", border_style="yellow"))


@ bq_cli.command()
def test_config():
    sites = Bqckup().list()
    if not sites:
        print("No site found")
        raise typer.Exit(code=1)
    else:
        # Storage config test

        # Site Config test
        table = Table(title="Bqckup sites config")
        table.add_column("Name", style="cyan")
        table.add_column("Config Path", style="cyan")
        table.add_column("Status", style="cyan")
        for i in sites:
            table.add_row(sites[i]['name'], os.path.join(
                SITE_CONFIG_PATH, sites[i]['file_name']), 'OK', style="red")

        Console().print(table)


@ bq_cli.command()
def run(force: bool = False, site : str = None):
    Bqckup().backup(force=force, site=site)


@ bq_cli.command()
def gui_active():
    print("[yellow] Currently not supported [/yellow]")
    return
    
    from gevent.pywsgi import WSGIServer

    try:
        port = int(Config().read('web', 'port'))
        http_server = WSGIServer(('0.0.0.0', port), app)
        print(f"\nListening on port {port}\n", flush=True)
        http_server.serve_forever()
    except Exception as e:
        print(f"Failed to start web server, {str(e)}")


@ bq_cli.command()
def upload_file(storage: str, file: str, save_as: str = None):
    if not os.path.exists(file):
        print(f"[red] File not found [/red]")
        return

    if os.path.isdir(file):
        print(f"[red] Cannot upload directory [/red]")
        return

    if not save_as:
        save_as = os.path.basename(file)

    try:
        # Check if storage exists
        Storage().get_storage_detail(storage)
        s3(storage).upload(file, save_as)
    except Exception as e:
        print(f"[red] Failed to upload file, {str(e)} [/red]")
    else:
        print(f"[green] File uploaded successfully [/green]")


@ bq_cli.command()
def generate_link(storage: str, key: str, expire: int = 86400):
    try:
        # Check if storage exists
        Storage().get_storage_detail(storage)
        link = s3(storage).generate_link(key, expire)
        shortlink = generate_short_link(link)

        print(f"[bold green]Link generated successfully [/bold green]\n")
        print(f"Original Link")
        print(f"[green]{link.strip()}[/green]\n")

        # Use Short link
        if shortlink:
            link = shortlink
            print(f"Shorrten Link")
            print(f"[green]{link.strip()}[/green]\n")

        print(f"[bold yellow]Information[/bold yellow]")
        print(f"This link will expire in {format_timespan(expire)}\n")
        print("-" * 30 + "Tips" + "-" * 30 + "\n")
        print(f"[bold purple]CURL[/bold purple]")
        print(f'curl {"" if not shortlink else "-L"} {os.path.basename(key)} "{link.strip()}" > "{os.path.basename(key)}"\n'.strip())
        print(f"\n[bold purple]WGET[/bold purple]")
        print(
            f'wget "{link.strip()}" -O "{os.path.basename(key)}" -q --show-progress'.strip())
    except Exception as e:
        print(f"[red] Failed to generate link, {str(e)} [/red]")


@ bq_cli.command()
def get_list(name: str, json: bool = False):
    node = Bqckup().detail(name)

    if not node:
        print(f"[red] Backup for {name} not found [/red]")
        return None

    _s3 = s3(node['options']['storage'])
    backups = _s3.list(f"{_s3.root_folder_name}/{node['name']}")

    if not backups or not backups.get('Contents'):
        print(f"[red] No backup found for {name} [/red]")
        return None

    table = Table("#", "Key", "Created at")

    if json:
        contents = backups.get('Contents')
        results = []
        for content in contents:
            result = {
                "key": content.get('Key').replace('bqckup/', ''),
                "date": content.get('LastModified').strftime("%d %b %Y %H:%M:%S"),
                "size": content.get('Size')
            }
            results.append(result)
        print(results)
    else:
        for i, backup in enumerate(backups.get('Contents')):
            backup['Key'] = backup['Key'].replace('bqckup/', '')
            table.add_row(
                str(i+1), backup['Key'], backup['LastModified'].strftime("%d %b %Y %H:%M:%S"))

        Console().print(table)

        print("\n[yellow]Tips: [/yellow]")
        print("You can generate a download link by running this command:\n")
        print(f"bqckup generate-link {node['options']['storage']} <Key>\n")
        print("Example:")
        print(
            f"bqckup generate-link {node['options']['storage']} '{backups.get('Contents')[0].get('Key')}'\n")


@ bq_cli.command()
def check_update(update: bool = False):
    import wget
    from packaging import version
    try:
        latest_version = requests.get(
            'https://download.bqckup.com/latest.txt').text.strip()
    except Exception as e:
        print(f"[red] Failed to check update, {str(e)} [/red]")
    else:
        need_update = version.parse(VERSION) < version.parse(latest_version)
        same_version = version.parse(VERSION) == version.parse(latest_version)

        if same_version:
            print(
                f"[bold green]You are using the latest version of Bqckup[/bold green]")
            return

        if need_update and update:
            import shutil
            tmp_file = "/tmp/bqckup.tar.gz"
            new_bqckup = "/tmp/bqckup"

            try:
                wget.download(
                    f"https://downloads.bqckup.com/{latest_version}/bqckup.tar.gz", tmp_file)
                os.system(f"tar xvf {tmp_file} -C /tmp")
            except Exception as e:
                print(f"[red] Failed to download update, {str(e)} [/red]")
                return
            else:
                if os.path.exist(new_bqckup):
                    shutil.move(new_bqckup, "/usr/bin/bqckup")
                    print(f"[green] Bqckup updated successfully [/green]")
                    os.system("/usr/bin/bqckup get-information")
                else:
                    print("[red] Failed to update [/red]")
                return

        print(f"Current Version : {VERSION}")
        print(f"Latest Version  : {latest_version}")

@ bq_cli.command()
def download_latest(name: str, target: str = None, silent: bool = False):

    try:
        node = Bqckup().detail(name)

        if not node:
            print(f"[red]Backup for {name} not found[/red]")
            return 

        _s3 = s3(node['options']['storage'])
        backups = _s3.list(f"{_s3.root_folder_name}/{node['name']}")
        config = _s3.list(f"{_s3.root_folder_name}/config/")

        config_file = [item for item in config.get('Contents', []) if item['Key'].endswith('.yml') and name in item['Key']][0]
        
        backup_contents = backups.get('Contents')   
        sorted_backups = sorted(backup_contents, key=lambda x: x['LastModified'], reverse=True)[:2]
        sorted_backups.append(config_file)

        table = Table("#", "Data", "Created at", "Size")
        total_size = 0      
        disk_size = get_disk_size()

        for i, backup in enumerate(sorted_backups):
            table.add_row(str(i+1), backup['Key'], backup['LastModified'].strftime("%d %b %Y %H:%M:%S"), format_size(backup['Size']))    
            total_size += backup['Size']  

        Console().print(table)

        print(f"[green]Total size of backup: [/green][bold green]{format_size(total_size)}[/bold green]\n")

        display_disk_table(disk_size) 

        if total_size > disk_size['free']:
            raise Exception("Not enough disk space to download the backup. Visit: https://bqckup.com")
        
        if not silent:
            if not target:
                prompt_message = typer.style(f"\nDo you want to make a download in this current directory {Path().absolute()}?", fg=typer.colors.YELLOW)
                if not confirm_with_timeout(prompt_message, timeout=10):
                    target = typer.prompt(typer.style("Please enter the target directory path", fg=typer.colors.YELLOW))
                else:
                    target =  os.getcwd()
            target = validate_path(target)
        else:
            target =  os.getcwd() if not target else validate_path(target)

        if target.is_dir():
            print(f"[green]\nTarget directory: {target}\n[/green]")
        else:
            target.mkdir(parents=True, exist_ok=True)
            
            print("[yellow]\nTarget directory did not exist[/yellow]")
            print(f"[green]Created directory:[/green] [green bold]{target}\n[/green bold]")
            
        download_files(sorted_backups, target, _s3)

        print("[green]\nDownloaded successfully[/green]")
        print(f"Visit: https://bqckup.com\n")    
    except Exception as e:
        print(f"[red]An error occurred: {e}[/red]")

def get_version(version: bool):
    if version:
        # print(f"Version: {VERSION}")
        print(
            Panel("Version  : %s" % VERSION, title="Bqckup Version",
                    title_align="left", border_style="yellow"))
        raise typer.Exit()
    
@bq_cli.callback()
def common(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-v", callback=get_version, help="Show version information"),
):
    pass

if __name__ == "__main__":
    if getpass.getuser() != 'root':
        print("Please run this script as root user")
    else:
        from app import initialization
        try:
            initialization()
        except Exception as e:
            print(f"Failed to initialize, {str(e)}")
        else:
            bq_cli()
