import getpass
import traceback
from typing_extensions import Annotated
import typer
import os
import requests
import re
import ruamel.yaml as yaml
from classes.bqckup import Bqckup
from classes.database import Database
from classes.config import Config
from classes.progress import ProgressSpinner
from classes.rustic import Rustic
from classes.storage import Storage
from classes.s3 import s3
from pathlib import Path
from typing import List
from constant import STORAGE_CONFIG_PATH, VERSION, SITE_CONFIG_PATH, BQ_PATH
from rich import print
from rich.console import Group, Console
from rich.table import Table
from rich.panel import Panel
from helpers.utility import (
    get_disk_size,
    display_disk_table,
    confirm_with_timeout,
    is_debug,
    validate_path,
)
from helpers.network import download_files, generate_short_link
from humanfriendly import format_size, format_timespan


bq_cli = typer.Typer()

# @ bq_cli.command()
# def report():
#     from classes.report import Report
#     Report().send()


@bq_cli.command()
def migrate():
    from models import database
    from playhouse.migrate import SqliteMigrator, migrate, IntegerField, FloatField

    try:
        # check if log table already migrated
        cursor = database.execute_sql("PRAGMA table_info(log);")
        columns = [column[1] for column in cursor.fetchall()]
        if "time_consume" in columns:
            print("[yellow] Log already migrated [/yellow]")
            return False

        # migrate log table
        migrator = SqliteMigrator(database)
        migrate(
            migrator.add_column("log", "time_consume", FloatField(default=0)),
        )
        print("[green] Log migration success [/green]")
    except Exception as e:
        print(f"Failed to migrate log, {str(e)}")


@bq_cli.command()
def summary(site=None):
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from helpers.datetime import interval_in_number
    from datetime import datetime

    bqckups = Bqckup().list()

    # search the site
    if site is not None:
        for i in list(bqckups):
            if bqckups[i]["name"] != site:
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
            _s3 = s3(backup["options"]["storage"])
            backups = _s3.list(f"{_s3.root_folder_name}/{backup['name']}")
            progress.update(task, completed=True)

        # check if backup exists
        if not backups or not backups.get("Contents"):
            print(f"[red] No backup found for {site} [/red]")
            return None

        contents = backups["Contents"]
        last_content = max(contents, key=lambda x: x["LastModified"].timestamp())
        last_folder = last_content["Key"].split("/")[2]
        last_size = 0
        total_size = 0

        # calculate the size
        for content in contents:
            total_size += content["Size"]
            if content["Key"].split("/")[2] == last_folder:
                last_size += content["Size"]

        interval = backup["options"]["interval"]
        last_modified = last_content["LastModified"]
        to_compare = interval_in_number(interval)

        print("\n================================================================\n")
        print(f"Backup Name                     : {backup['name']}")
        print(
            f"Last Backup                     : {last_modified.strftime('%d/%m/%Y %H:%M:%S')}"
        )
        print(
            f"Last backup file size and name  : {format_size( last_size)} ({last_folder}) "
        )
        print(f"Total size of a bqckup          : {format_size( total_size)}")
        print(f"Total files                     : {backups['KeyCount']}")
        print(f"Storage Name                    : {backup['options']['storage']}")
        print(f"Schedule                        : {interval}")
        print(
            f"Next bqckup                     : {datetime.fromtimestamp(last_modified.timestamp() + (to_compare * 86400)).strftime('%d/%m/%Y 00:00:00')}"
        )
        print(
            f"Local Backup                    : {'yes' if backup['options']['save_locally'] else 'no'} "
        )
    print("\n================================================================\n")
    print(f"Visit: https://bqckup.com\n")


@bq_cli.command()
def history(site=None, filter_latest_days: int = 7):
    from models.log import Log
    from datetime import datetime

    # check if site is empty
    if site is None:
        print(
            "\nPlease specify the site ([blue] bqckup history --site site_name [/blue])\n"
        )
        return False

    def print_table(logs, table):
        for log in logs:
            # format sytle for status
            if log.status == Log.__SUCCESS__:
                status = "[green]Success[/green]"
            else:
                status = "[red]Failed[/red]"

            last_backup = datetime.fromtimestamp(log.created_at).strftime(
                "%d/%m/%Y %H:%M:%S"
            )
            size = format_size(log.file_size)
            time_consume = log.time_consume
            file_name = log.file_path.split("/")[-1]

            table.add_row(last_backup, file_name, size, status, f"{time_consume:.2f}")

        Console().print(table)

    backup = Bqckup().detail(site)

    if backup is not None:
        logs = (
            Log()
            .select()
            .where(
                (Log.name == site)
                & (
                    Log.created_at
                    >= (datetime.now().timestamp() - (filter_latest_days * 86400))
                )
            )
            .execute()
        )

        if logs:
            schedule = backup["options"]["interval"]

            # split the logs into database and files
            log_database = []
            log_files = []
            for log in logs:
                if log.type == Log.__DATABASE__:
                    log_database.append(log)
                else:
                    log_files.append(log)

            table_files = Table(
                "last backup date", "file name", "size", "status", "time consume (s)"
            )
            table_database = Table(
                "last backup date", "file name", "size", "status", "time consume (s)"
            )

            print(f"\nBackup Name: {backup['name']} ([green]{schedule}[/green])")
            print("\nFile Backup")
            print_table(log_files, table_files)
            print("\n Database Backup")
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
    interval: str = typer.Option(default="daily"),
    retention: int = typer.Option(default=7),
    save_locally: bool = typer.Option(default=False),
    save_locally_path: str = typer.Option(default=os.path.join(BQ_PATH, "tmp")),
):
    # Check if path is empty
    if save_locally_path != os.path.join(BQ_PATH, "tmp") and not os.path.exists(
        save_locally_path
    ):
        print(f"Path '{save_locally_path}' not found")
        raise typer.Exit(code=1)

    # Check if name contain space or any symbol except dot and underscore
    if not re.match("^[a-zA-Z0-9_.-]*$", name):
        print(
            "Name should not contain any space or special character except dot and underscore"
        )
        raise typer.Exit(code=1)

    # Check paths
    for p in path:
        if not os.path.exists(p):
            print(f"Path '{p}' not found")
            raise typer.Exit(code=1)

    # Check Database Connection
    Database().test_connection(
        {"user": db_user, "password": db_pass, "host": db_host, "name": db_name}
    )

    # Interval only daily, weekly, monthly
    if interval not in ["daily", "weekly", "monthly"]:
        print("Interval should be daily, weekly or monthly")
        raise typer.Exit(code=1)

    config = {
        "bqckup": {
            "name": name,
            "path": path,
            "database": {
                "type": "mysql",  # Currently only support mysql
                "host": db_host,
                "port": db_port,
                "user": db_user,
                "password": db_pass,
                "name": db_name,
            },
            "options": {
                "storage": storage,
                "interval": interval,
                "retention": retention,
                "save_locally": "yes" if save_locally else "no",
                "save_locally_path": save_locally_path,
                "notification_email": "email@example.com",
                "provider": "s3",
            },
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


@bq_cli.command()
def get_information():
    content = Group(
        Panel("Version  : %s" % VERSION),
        Panel("Github   : https://github.com/bqckup/bqckup"),
    )
    print(
        Panel.fit(
            content,
            title="Bqckup information",
            title_align="left",
            border_style="yellow",
        )
    )


@bq_cli.command()
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
            table.add_row(
                sites[i]["name"],
                os.path.join(SITE_CONFIG_PATH, sites[i]["file_name"]),
                "OK",
                style="red",
            )

        Console().print(table)


@bq_cli.command()
def run(
    force: bool = False,
    site: str = None,
    incremental: Annotated[bool, typer.Option("--incremental", "-i")] = None,
    full: Annotated[bool, typer.Option("--full", "-f")] = None,
    keep: Annotated[bool, typer.Option("--keep", "-k")] = False,
):
    from classes.report import Report

    backup_method = None
    if incremental and full:
        print("Can't running incremental and full backup at same time.")
        return
    elif incremental:
        backup_method = "incremental"
    elif full:
        backup_method = "full"

    Bqckup().backup(
        force=force,
        site=site,
        backup_method=backup_method,
        keep_credential=keep
    )
    Report().send()


@bq_cli.command()
def gui_active():
    print("[yellow] Currently not supported [/yellow]")
    return

    from gevent.pywsgi import WSGIServer

    try:
        port = int(Config().read("web", "port"))
        http_server = WSGIServer(("0.0.0.0", port), app)
        print(f"\nListening on port {port}\n", flush=True)
        http_server.serve_forever()
    except Exception as e:
        print(f"Failed to start web server, {str(e)}")


@bq_cli.command()
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


@bq_cli.command()
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
        print(
            f'curl {"" if not shortlink else "-L"} {os.path.basename(key)} "{link.strip()}" > "{os.path.basename(key)}"\n'.strip()
        )
        print(f"\n[bold purple]WGET[/bold purple]")
        print(
            f'wget "{link.strip()}" -O "{os.path.basename(key)}" -q --show-progress'.strip()
        )
    except Exception as e:
        print(f"[red] Failed to generate link, {str(e)} [/red]")


@bq_cli.command()
def get_list(
    name: str,
    show_snapshots: bool = typer.Option(
        True,
        "--show-snapshots/--no-snapshots",
        help="Show snapshot list fetched from Rustic.",
    ),
    full_id: bool = typer.Option(
        False,
        "--full-id",
        help=(
            "Display the full snapshot ID instead of the shortened version "
            "(default is the first 8 characters)."
        ),
    ),
    json: bool = False,
):
    node = Bqckup().detail(name)

    if not node:
        print(f"[red] Backup for {name} not found [/red]")
        return None

    _s3 = s3(node["options"]["storage"])

    backup_dates = _s3.get_backup_dates(site_name=name, sort_by_date=True)
    objects = []

    with ProgressSpinner("getting backup list..."):
        for prefix in backup_dates:
            objects_in_prefix = _s3.list(prefix=prefix).get("Contents", [])
            objects.extend(objects_in_prefix)

    if not objects:
        print(f"[red] No backup found for {name} [/red]")
        return None

    table = Table("#", "Key", "Created at")
    snapshots_table = Table("No", "Snapshot IDs", "Paths", "Created At", title="Incremental Backups")

    if show_snapshots:
        storage = Storage().get_storage_detail(node["options"]["storage"])
        r = Rustic(node, storage)
        r.check_and_dump()
        with ProgressSpinner("getting snapshots..."):
            rows = sorted(r.get_snapshots(full_id=full_id), key=lambda x: x["time"])

        for i, row in enumerate(rows, start=1):
            snapshots_table.add_row(
                str(i),
                row["id"],
                "\n".join(row["paths"]),
                row["time"],
            )

    if json:
        results = []
        for content in objects:
            result = {
                "key": content.get("Key").replace("bqckup/", ""),
                "date": content.get("LastModified").strftime("%d %b %Y %H:%M:%S"),
                "size": content.get("Size"),
            }
            results.append(result)
        print(results)

        if show_snapshots:
            print(rows)
    else:
        for i, backup in enumerate(objects):
            table.add_row(
                str(i + 1),
                backup["Key"],
                backup["LastModified"].strftime("%d %b %Y %H:%M:%S"),
            )

        Console().print(table)

        if show_snapshots:
            Console().print(snapshots_table)

        print("\n[yellow]Tips: [/yellow]")
        print("You can generate a download link by running this command:\n")
        print(f"bqckup generate-link {node['options']['storage']} <Key>\n")
        print("Example:")
        print(
            f"bqckup generate-link {node['options']['storage']} '{objects[0].get('Key')}'\n"
        )


@bq_cli.command()
def check_update(update: bool = False):
    import wget
    from packaging import version
    import json
    from helpers.utility import get_os_version

    try:
        # latest_version = requests.get(
        #     'https://download.bqckup.com/latest.txt').text.strip()
        release = requests.get(
            "https://api.github.com/repos/bqckup/bqckup/releases/latest"
        ).text.strip()
        release = json.loads(release)
        latest_version = release["tag_name"]
    except Exception as e:
        print(f"[red] Failed to check update, {str(e)} [/red]")
    else:
        need_update = version.parse(VERSION) < version.parse(latest_version)
        same_version = version.parse(VERSION) == version.parse(latest_version)

        if same_version:
            print(
                f"[bold green]You are using the latest version of Bqckup[/bold green]"
            )
            return

        # get asset for ubuntu from github
        asset_ubuntu = None
        for asset in release["assets"]:
            name = asset["name"].split("-")
            if "ubuntu" in name:
                ubuntu_index = name.index("ubuntu")
                ubuntu_version = name[ubuntu_index + 1].split(".tar.gz")[0]
                if ubuntu_version == ".".join(get_os_version().split(".")[:2]):
                    asset_ubuntu = asset

        if not asset_ubuntu:
            print(
                f"[red] your current ubuntu version ({get_os_version()}) is not match any available version [/red]"
            )
        else:
            print(
                f"[green] Found new version bqckup for ubuntu {get_os_version()} [/green]"
            )

        if need_update and update and asset_ubuntu:
            import shutil

            tmp_file = "/tmp/bqckup.tar.gz"
            new_bqckup = "/tmp/bqckup"

            try:
                wget.download(f"{asset_ubuntu['browser_download_url']}", tmp_file)
                os.system(f"tar xvf {tmp_file} -C /tmp")
                os.unlink(tmp_file)

            except Exception as e:
                print(f"[red] Failed to download update, {str(e)} [/red]")
                return
            else:
                if os.path.exists(new_bqckup):
                    shutil.move(new_bqckup, "/usr/bin/bqckup")
                    print(f"[green] Bqckup updated successfully [/green]")
                    os.system("/usr/bin/bqckup get-information")
                else:
                    print("[red] Failed to update [/red]")
                return

        print(f"Current Version : {VERSION}")
        print(f"Latest Version  : {latest_version}")


@bq_cli.command()
def download_latest(name: str, target: str = None, silent: bool = False):

    try:
        node = Bqckup().detail(name)

        if not node:
            print(f"[red]Backup for {name} not found[/red]")
            return

        _s3 = s3(node["options"]["storage"])
        
        backup_dates = _s3.get_backup_dates(site_name=name, sort_by_date=True)
        if not backup_dates:
            print(f"[red] No backup found for {name} [/red]")
            return

        latest_backup_prefix = backup_dates[-1]
        
        backup_contents = _s3.list(prefix=latest_backup_prefix).get("Contents", [])

        config_list = _s3.list(f"{_s3.root_folder_name}/config/")
        config_file = [
            item
            for item in config_list.get("Contents", [])
            if item["Key"].endswith(".yml") and name in item["Key"]
        ]

        files_to_download = backup_contents + config_file

        table = Table("#", "Data", "Created at", "Size")
        total_size = 0
        disk_size = get_disk_size()

        for i, backup in enumerate(files_to_download):
            table.add_row(
                str(i + 1),
                backup["Key"],
                backup["LastModified"].strftime("%d %b %Y %H:%M:%S"),
                format_size(backup["Size"]),
            )
            total_size += backup["Size"]

        Console().print(table)

        print(
            f"[green]Total size of backup: [/green][bold green]{format_size(total_size)}[/bold green]\n"
        )

        display_disk_table(disk_size)

        if total_size > disk_size["free"]:
            raise Exception(
                "Not enough disk space to download the backup. Visit: https://bqckup.com"
            )

        if not silent:
            if not target:
                prompt_message = typer.style(
                    f"\nDo you want to make a download in this current directory {Path().absolute()}?",
                    fg=typer.colors.YELLOW,
                )
                if not confirm_with_timeout(prompt_message, timeout=10):
                    target = typer.prompt(
                        typer.style(
                            "Please enter the target directory path",
                            fg=typer.colors.YELLOW,
                        )
                    )
                else:
                    target = os.getcwd()
            target = validate_path(target)
        else:
            target = os.getcwd() if not target else validate_path(target)

        if target.is_dir():
            print(f"[green]\nTarget directory: {target}\n[/green]")
        else:
            target.mkdir(parents=True, exist_ok=True)

            print("[yellow]\nTarget directory did not exist[/yellow]")
            print(
                f"[green]Created directory:[/green] [green bold]{target}\n[/green bold]"
            )

        download_files(files_to_download, target, _s3)

        print("[green]\nDownloaded successfully[/green]")
        print(f"Visit: https://bqckup.com\n")
    except Exception as e:
        print(f"[red]An error occurred: {e}[/red]")

@bq_cli.command()
def restore(
    site: str,
    snapshot: str = "latest",
    target: str | None = None,
):
    """Restore for incremental backup"""

    bqckup = Bqckup()
    site_config = bqckup.detail(site)

    if not site_config:
        print(f"[red]Site [bold]{site}[/bold] not found![/red]")
        return

    # Create directory if not exists
    if (paths := site_config.get("path")) and isinstance(paths, list):
        for p in paths:
            Path(p).mkdir(parents=True, exist_ok=True)

    if not bqckup.validate_config(site):
        print(f"Invalid configuration for {site}")
        return

    try:
        with ProgressSpinner("getting credentials..."):
            storage_config = Storage().get_storage_detail(
                site_config.get("options").get("storage")
            )
    except Exception as e:
        if is_debug():
            traceback.print_exc()

        print(f"Error while getting credential: {e}")
        return

    try:
        rustic = Rustic(site_config, storage_config)
        rustic.check_and_dump()
    except Exception as e:
        if is_debug():
            traceback.print_exc()

        print(f"Failed to setup rustic: {e}")
        return

    with ProgressSpinner("Restoring backups..."):
        rustic.restore(snapshot=snapshot, target=target)

    print("[bold green]Restore complete![/bold green]")

def get_version(version: bool):
    if version:
        # print(f"Version: {VERSION}")
        print(
            Panel(
                "Version  : %s" % VERSION,
                title="Bqckup Version",
                title_align="left",
                border_style="yellow",
            )
        )
        raise typer.Exit()


@bq_cli.callback()
def common(
    ctx: typer.Context,
    version: bool = typer.Option(
        None, "--version", "-v", callback=get_version, help="Show version information"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-V", help="Enable verbose output."
    ),
):
    if verbose:
        os.environ["BQCKUP_VERBOSE"] = "1"

if __name__ == "__main__":
    if getpass.getuser() != "root":
        print("Please run this script as root user")
    else:
        from app import initialization

        try:
            initialization()
        except Exception as e:
            print(f"Failed to initialize, {str(e)}")
        else:
            bq_cli()
