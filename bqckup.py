import typer, getpass, os, requests
from classes.bqckup import Bqckup
from classes.config import Config
from classes.storage import Storage
from classes.s3 import s3
from constant import VERSION, SITE_CONFIG_PATH
from rich import print
from rich.console import Group, Console
from rich.table import Table
from rich.panel import Panel

bq_cli = typer.Typer()

@bq_cli.command()
def get_information():
    content = Group(
        Panel("Version  : %s" % VERSION),
        Panel("Github   : https://github.com/bqckup/bqckup"),
    )
    print(Panel.fit(content, title="Bqckup information", title_align="left", border_style="yellow"))

@bq_cli.command()
def test_config():
    sites = Bqckup().list()
    if not sites:
        print("No site found")
    else:
        # Storage config test

        # Site Config test
        table = Table(title="Bqckup sites config")
        table.add_column("Name", style="cyan")
        table.add_column("Config Path", style="cyan")
        table.add_column("Status", style="cyan")
        for i in sites:
            table.add_row(sites[i]['name'], os.path.join(SITE_CONFIG_PATH, sites[i]['file_name']), 'OK', style="red")

        Console().print(table)
        
@bq_cli.command()
def run(force:bool = False):
    Bqckup().backup(force=force)
    
@bq_cli.command()
def gui_active():
    from gevent.pywsgi import WSGIServer
    
    try:
        port = int(Config().read('web', 'port'))
        http_server = WSGIServer(('0.0.0.0', port), app)
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

# Expire is in seconds
@bq_cli.command()
def generate_link(storage: str, key:str, expire:int = 86400):
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
        print(f'wget "{link.strip()}" -O "{os.path.basename(key)}" -q --show-progress'.strip())
    except Exception as e:
        print(f"[red] Failed to generate link, {str(e)} [/red]")

@bq_cli.command()
def get_list(name: str):
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
    
    for i, backup in enumerate(backups.get('Contents')):
        backup['Key'] = backup['Key'].replace('bqckup/', '')
        table.add_row(str(i+1), backup['Key'], backup['LastModified'].strftime("%d %b %Y %H:%M:%S"))
    
    Console().print(table)

    print("\n[yellow]Tips: [/yellow]")
    print("You can generate a download link by running this command:\n")
    print(f"bqckup generate-link {node['options']['storage']} <Key>\n")
    print("Example:")
    print(f"bqckup generate-link {node['options']['storage']} '{backups.get('Contents')[0].get('Key')}'\n")

@bq_cli.command()
def check_update(update:bool = False):
    import wget
    from packaging import version
    try:
        latest_version = requests.get('https://download.bqckup.com/latest.txt').text.strip()
    except Exception as e:
        print(f"[red] Failed to check update, {str(e)} [/red]")
    else:
        need_update = version.parse(VERSION) < version.parse(latest_version)
        same_version = version.parse(VERSION) == version.parse(latest_version)

        if same_version:
            print(f"[bold green]You are using the latest version of Bqckup[/bold green]")
            return

        if need_update and update:
            import shutil
            tmp_file = "/tmp/bqckup.tar.gz"
            new_bqckup = "/tmp/bqckup"

            try:
                wget.download(f"https://download.bqckup.com/{latest_version}/bqckup.tar.gz", tmp_file)
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

if __name__ == "__main__":
    if getpass.getuser() != 'root':
        print("Please run this script as root user")
    else:
        from app import app, initialization
        try:
            initialization()
        except Exception as e:
            print(f"Failed to initialize, {str(e)}")
        else:
            bq_cli()
