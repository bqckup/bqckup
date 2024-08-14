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

bq_cli = typer.Typer()


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
    from humanfriendly import format_timespan
    from helpers import generate_short_link

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
def download_latest(name: str, target: str = typer.Option(),):
    from humanfriendly import format_size

    try:
        node = Bqckup().detail(name)

        if not node:
            print(f"[red]Backup for {name} not found[/red]")
            return 
        
        if not target:
            target = Path().absolute()
        else:
            target = Path(target)

        _s3 = s3(node['options']['storage'])
        backups = _s3.list(f"{_s3.root_folder_name}/{node['name']}")
        config = _s3.list(f"{_s3.root_folder_name}/config/")

        config_file = [item for item in config.get('Contents', []) if item['Key'].endswith('.yml') and name in item['Key']][0]
        
        backup_contents = backups.get('Contents')   
        sorted_backups = sorted(backup_contents, key=lambda x: x['LastModified'], reverse=True)[:2]

        sorted_backups.append(config_file)

        table = Table("#", "Data", "Created at", "Size")
        total_size = 0      

        for i, backup in enumerate(sorted_backups):
            table.add_row(str(i+1), backup['Key'], backup['LastModified'].strftime("%d %b %Y %H:%M:%S"), format_size(backup['Size']))    
            total_size += backup['Size']  
        
        Console().print(table)
        
        if not typer.confirm(f"Do you really want to download these files with a total size of {format_size(total_size)}?"):
            print("[red]Download cancelled[/red]")
            return

        if target.is_dir():
            print(f"[green]\nTarget directory: {target}\n[/green]")
        else:
            target.mkdir(parents=True, exist_ok=True)
            print("[yellow]\nTarget directory not exist[/yellow]")
            print(f"[green]Created directory: {target}\n[/green]")

        for i, backup in enumerate(sorted_backups):
            backup_file_path = Path(backup['Key']).name
            file_path = target / backup_file_path

            if file_path.exists():
                print(f"[yellow]File {file_path} already exists[/yellow]")
                continue
            
            total_size = backup['Size']
            with Progress() as progress:
                task = progress.add_task(f"{backup_file_path}", total=total_size)
                
                def progress_callback(bytes_transferred):
                    progress.update(task, advance=bytes_transferred)
                
                _s3.client.download_file(_s3.bucket_name, backup['Key'], str(file_path), Callback=progress_callback)
            
        print("[green]\nDownloaded successfully[/green]")
    except Exception as e:
        print(f"[red]An error occurred: {e}[/red]")


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
