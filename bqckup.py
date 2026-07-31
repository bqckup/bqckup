import getpass
import time
from subprocess import CalledProcessError
import traceback
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
from typing import Dict, List, Optional
from constant import VERSION, SITE_CONFIG_PATH, BQ_PATH
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
from helpers.hook import StorageCredentialError
from humanfriendly import format_size, format_timespan


bq_cli = typer.Typer()

@bq_cli.command()
def report(force: bool = typer.Option(False, "--force", "-f", help="force generate monthly report")):
    from classes.report import Report
    Report().send(force=force)


@bq_cli.command()
def migrate():
    from models import database
    # pyrefly: ignore [missing-import]
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
def summary(site: Optional[str] = None, watch: bool = typer.Option(False, "--watch", help="Refresh summary until running backups finish")):
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from helpers.datetime import interval_in_number
    from datetime import datetime
    from models.log import Log

    bqckup = Bqckup()

    all_backups: List[Dict] = (
        [bqckup.detail(site)] if site else list(bqckup.list().values())
    )  # pyright: ignore[reportAssignmentType]

    if not all_backups:
        print("[yellow]No sites found.[/yellow]")
        return

    def render_once() -> bool:
        """Render summary for all sites once. Return True if any backup is running."""
        any_running = False

        for site_config in all_backups:
            storage_name = site_config["options"]["storage"]
            backup_name = site_config["name"]
            is_incremental = Rustic.is_enabled(site_config) and Rustic.is_installed()
            is_local = site_config.get("options", {}).get("provider") == "local"
            rustic_stats = None

            last_log = (
                Log.select()
                .where(Log.name == backup_name)
                .order_by(Log.id.desc())
                .get_or_none()
            )

            last_successful_log = (
                Log.select()
                .where((Log.name == backup_name) & (Log.status == Log.__SUCCESS__))
                .order_by(Log.id.desc())
                .get_or_none()
            )

            last_backup_status = "[yellow]N/A[/yellow]"
            is_running = False

            if last_log:
                is_running = last_log.status == Log.__ON_PROGRESS__
                last_backup_status = {
                    Log.__ON_PROGRESS__: "[yellow]On Progress[/yellow]",
                    Log.__SUCCESS__: "[green]Success[/green]",
                    Log.__FAILED__: "[red]Failed[/red]",
                }.get(last_log.status, "[red]Unknown[/red]")

            next_backup_date = "[yellow]N/A[/yellow]"
            if last_successful_log:
                interval = site_config["options"]["interval"]
                interval_days = interval_in_number(interval)
                next_backup_date = datetime.fromtimestamp(
                    last_successful_log.created_at + (interval_days * 86400)
                ).strftime("%d/%m/%Y 00:00:00")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task(
                    description=f"fetching details for {backup_name}...", total=None
                )

                dates = []
                objects = {}
                if not is_local:
                    _s3 = s3(storage_name)
                    dates = _s3.get_backup_dates(backup_name, sort_by_date=True)
                    objects = {
                        prefix: obj
                        for prefix in dates
                        for obj in _s3.list(prefix=prefix).get("Contents", [])
                    }

                if is_incremental:
                    try:
                        rustic = Rustic(
                            site_config=site_config,
                            storage_config={} if is_local else Storage().get_storage_detail(storage_name),
                        ).check_and_dump()
                        rustic_stats = rustic.get_stats()
                        rustic.dump_config(with_credentials=False)
                    except Exception as e:
                        if is_debug() and isinstance(e, CalledProcessError):
                            print(e.stderr)
                        print(f"[red] Failed to get rustic stats, {e} [/red]")

                progress.update(task, completed=True)

            rows = {
                "Status": "[yellow]Running[/yellow]" if is_running else "[green]Idle[/green]",
                "Last Backup Status": last_backup_status,
                "Storage Name": storage_name,
                "Schedule": site_config["options"]["interval"],
                "Local Backup": "yes" if site_config["options"]["save_locally"] else "no",
                "Next Backup": next_backup_date,
            }

            if objects:
                total_size = sum([i.get("Size") for i in objects.values()])
                last_content = dates[-1]
                last_backup_size = objects[last_content].get("Size")
                last_modified = objects[last_content]["LastModified"]

                rows.update(
                    {
                        "Last Backup": last_modified.strftime("%d/%m/%Y %H:%M:%S"),
                        "Last Backup Size": format_size(last_backup_size),
                        "Total Backups Size": format_size(total_size),
                        "Total Files": len(objects),
                    }
                )

            if is_incremental and rustic_stats:
                rows["Incremental Snapshots"] = rustic_stats.get("snapshots_count", "N/A")
                rows["Repository Size"] = format_size(
                    rustic_stats.get("compressed_repo_size", 0)
                )

            orders = [
                "Status",
                "Last Backup",
                "Last Backup Status",
                "Last Backup Size",
                "Total Backups Size",
                "Total Files",
                "Repository Size",
                "Incremental Snapshots",
                "Storage Name",
                "Schedule",
                "Next Backup",
                "Local Backup",
            ]

            table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
            table.add_column(style="cyan")
            table.add_column(style="white")

            for key in orders:
                if not rows.get(key):
                    continue

                table.add_row(key, f": {rows[key]}")

            # If running, compute elapsed time from log.created_at
            if last_log and last_log.status == Log.__ON_PROGRESS__:
                any_running = True
                elapsed_seconds = int(time.time()) - int(last_log.created_at)
                table.add_row("Elapsed", f": {format_timespan(elapsed_seconds)}")

            print(
                Panel(
                    table,
                    title=f"Backup Summary for [bold]{backup_name}[/bold]",
                    border_style="green",
                    expand=False,
                    title_align="left",
                )
            )

        return any_running

    if watch:
        try:
            while True:
                Console().clear()
                running = render_once()
                if not running:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped watching.")
        return

    # default single render
    render_once()

    print("\nVisit: https://bqckup.com\n")


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
            status = {
                Log.__SUCCESS__: "[green]Success[/green]",
                Log.__ON_PROGRESS__: "[yellow]On Progress[/yellow]",
                Log.__FAILED__: "[red]Failed[/red]",
            }.get(log.status, "[red]Unknown[/red]")
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
            if log_files:
                print("\nFile Backup")
                print_table(log_files, table_files)
            else:
                print("\nNo file backup history found")

            if log_database:
                print("\n Database Backup")
                print_table(log_database, table_database)
            else:
                print("\nNo database backup history found")

            print("\nVisit: https://bqckup.com\n")
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
    site: Optional[str] = None,
    incremental: Optional[bool] = typer.Option(
        None,
        "--incremental/--full",
        help="use incremental backup or create a full tar.gz archive",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="force trigger monthly report generation",
    ),
):
    from classes.report import Report

    Bqckup().backup(
        force=force,
        site=site,
        incremental=incremental
    )

    Report().send(force=report)


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
        print(f"[red]Backup for {name} not found[/red]")
        return

    show_snapshots = show_snapshots and Rustic.is_enabled(node) and Rustic.is_installed()
    is_local = node.get("options", {}).get("provider") == "local"

    objects = []
    if not is_local:
        _s3 = s3(node["options"]["storage"])
        backup_dates = _s3.get_backup_dates(site_name=name, sort_by_date=True)

        with ProgressSpinner("getting backup list..."):
            for prefix in backup_dates:
                objects_in_prefix = _s3.list(prefix=prefix).get("Contents", [])
                objects.extend(objects_in_prefix)

    table = Table("#", "Key", "Size", "Created at")
    snapshots_table = Table("No", "Snapshot IDs", "Paths", "Size", "Created At", title="Incremental Backups")

    if show_snapshots:
        storage = {} if is_local else Storage().get_storage_detail(node["options"]["storage"])
        r = Rustic(node, storage).check_and_dump()

        with ProgressSpinner("getting snapshots..."):
            incremental_snapshots = sorted(r.get_snapshots(full_id=full_id), key=lambda x: x["time"])
            r.dump_config(with_credentials=False)

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

        if show_snapshots and incremental_snapshots:
            print(incremental_snapshots)
    else:
        if objects:
            for i, backup in enumerate(objects):
                table.add_row(
                    str(i + 1),
                    backup["Key"],
                    format_size(backup["Size"]),
                    backup["LastModified"].strftime("%d %b %Y %H:%M:%S"),
                )

            Console().print(table)
        else:
            print(f"[red] No archive backup found for {name} [/red]")

        if show_snapshots:
            if incremental_snapshots:
                for i, row in enumerate(incremental_snapshots, start=1):
                    snapshots_table.add_row(
                        str(i),
                        row["id"],
                        "\n".join(row["paths"]),
                        format_size(row["size"]),
                        row["time"],
                    )
                Console().print(snapshots_table)
            else:
                print(f"[red] No incremental backups found for {name} [/red]")

        print("\n[yellow]Tips: [/yellow]")
        print("You can generate a download link by running this command:\n")
        print(f"bqckup generate-link {node['options']['storage']} <Key>\n")

        if objects:
            print("Example:")
            print(f"bqckup generate-link {node['options']['storage']} '{objects[0].get('Key')}'\n")


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

        if node.get("options", {}).get("provider") == "local":
            print("[yellow]This site uses the local provider; its archives already live on disk and there is nothing to download.[/yellow]")
            print("[yellow]For incremental backups, restore with 'bqckup restore <site>'.[/yellow]")
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
    target: Optional[str] = None,
    force: bool = typer.Option(
        False,
        "--force",
        help="Skip the confirmation prompt when restoring over the original paths.",
    ),
):
    """Restore for incremental backup"""

    bqckup = Bqckup()
    site_config = bqckup.detail(site)

    if not site_config:
        print(f"[red]Site [bold]{site}[/bold] not found![/red]")
        return

    # No target means restoring in place over the original paths: warn and confirm.
    if not target:
        paths = site_config.get("path") or []
        print("[bold red]WARNING:[/bold red] Restoring without --target will [bold]REPLACE[/bold] the current files at:")
        for p in paths:
            print(f"   [yellow]{p}[/yellow]")
        print("Existing data at these paths will be overwritten with the backup contents.")
        print("[dim]Tip: use --target <dir> to restore to a separate folder instead.[/dim]")

        if not force and not typer.confirm("Continue and overwrite the original paths?"):
            print("[yellow]Restore cancelled.[/yellow]")
            return

    # Only pre-create the original paths when restoring in place; rustic creates a custom target itself.
    if not target and (paths := site_config.get("path")) and isinstance(paths, list):
        for p in paths:
            Path(p).mkdir(parents=True, exist_ok=True)

    if not bqckup.validate_config(site):
        print(f"Invalid configuration for {site}")
        return

    if site_config.get("options", {}).get("provider") == "local":
        storage_config = {}
    else:
        try:
            with ProgressSpinner("getting credentials..."):
                storage_config = Storage().get_storage_detail(
                    site_config.get("options").get("storage")
                )
        except StorageCredentialError as e:
            if is_debug():
                traceback.print_exc()

            print(f"Error while getting credential: {e}")

            from helpers.network import get_server_ip
            from lib.notifications.webhook import send_report_to_webhook
            from lib.notifications.email import send_notification as send_email

            payload = {
                "report_type": "daily",
                "site": site,
                "status": "failed",
                "event": "credential_failed",
                "title": f"Storage Credential Failed for {site}",
                "message": str(e),
                "timestamp": int(__import__("time").time()),
                "server_ip": get_server_ip(),
            }
            send_report_to_webhook(payload)
            send_email(payload)
            raise
        except Exception as e:
            if is_debug():
                traceback.print_exc()

            print(f"Error while getting credential: {e}")
            raise

    try:
        rustic = Rustic(site_config, storage_config).check_and_dump()
    except Exception as e:
        if is_debug():
            traceback.print_exc()

        print(f"Failed to setup rustic: {e}")
        raise

    with ProgressSpinner("Restoring backups..."):
        try:
            rustic.restore(snapshot=snapshot, target=target)
        finally:
            rustic.dump_config(with_credentials=False)

    location = target if target else "their original paths"
    print(f"[bold green]Restore complete![/bold green] Files restored to {location}.")


@bq_cli.command()
def test_notification():
    """Send a test notification to every configured channel (Discord + Email)."""
    from lib.notifications.webhook import send_report_to_webhook as send_webhook
    from lib.notifications.email import send_notification as send_email
    from helpers.network import get_server_ip
    from helpers.datetime import get_today

    enabled = Config().read("notification", "enabled") == "1"
    channel = Config().read("notification", "channel", default="", print_error=False) or ""
    channels = [c.strip().lower() for c in channel.split(",") if c.strip()]

    if not enabled:
        print("[yellow]Notifications are disabled. Set `enabled=1` under [notification] in bqckup.cnf to test.[/yellow]")
        return

    if not channels:
        print("[yellow]No notification channel configured. Set e.g. `channel=discord,email` in bqckup.cnf.[/yellow]")
        return

    payload = {
        "embeds": [
            {
                "title": "Bqckup Test Notification",
                "description": "This is a test notification. If you can read this, your notification settings are working.",
                "color": 3066993,  # green
                "fields": [
                    {"name": "Server IP", "value": get_server_ip(), "inline": True},
                    {"name": "Date", "value": get_today(format="%d-%B-%Y"), "inline": True},
                ],
                "footer": {"text": "Sent by `bqckup test-notification`"},
            }
        ]
    }

    print(f"Sending test notification to: [cyan]{', '.join(channels)}[/cyan] ...")
    send_webhook(payload)   # no-op unless 'discord' is in channels
    send_email(payload)     # no-op unless 'email' is in channels
    print("[green]Test notification dispatched. Check your channel(s).[/green]")

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
    keep_rustic_secret: bool = typer.Option(
        False, "--keep-rustic-secret",
    ),
):
    if verbose:
        os.environ["BQCKUP_VERBOSE"] = "1"
    if keep_rustic_secret:
        os.environ["BQCKUP_KEEP_RUSTIC_SECRETS"] = "1"

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
