import os, typer, signal, re
from pathlib import Path
from rich.console import Console
from humanfriendly import format_size
from rich.table import Table
from rich import print
import time

def get_os_version():
    # get ubuntu version
    name = ''
    if os.path.isfile('/etc/lsb-release'):
        lines = open('/etc/lsb-release').read().split('\n')
        for line in lines:
            if line.startswith('DISTRIB_DESCRIPTION='):
                name = line.split('=')[1]
                if name[0]=='"' and name[-1]=='"':
                    return name[1:-1].split(' ')[1]
    print ("[red] Failed to get your OS version [/red]")
    return name

# remove protocol and slash
def clearDomain(domain):
    import re

    regex = re.compile(r"https?://(www\.)?")
    return regex.sub("", domain).strip().strip("/")

def isNone(s):
    return "-" if s is None or not s else s

def getInt(s):
    import re

    if isinstance(s, int):
        return s

    if not s:
        return 0

    arr = re.findall(r"\d+", s)
    return int(arr[0])

"""
convert bytes to megabytes, etc.
       sample code:
           print('mb= ' + str(bytesto(314575262000000, 'm')))
       sample output: 
           mb= 300002347.946
"""
def bytes_to(to, bytes, bsize=1024):
    a = {'k' : 1, 'm': 2, 'g' : 3, 't' : 4, 'p' : 5, 'e' : 6 }
    r = float(bytes)
    
    for i in range(a[to]):
        r = r / bsize

    return round(r)

# generate random string
def generate_token(length=20):
    import random, string

    # Random string with the combination of lower and upper case
    letters = string.ascii_letters
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str

def get_disk_size():
    statvfs = os.statvfs('/')
    total = statvfs.f_frsize * statvfs.f_blocks
    free = statvfs.f_frsize * statvfs.f_bfree
    used = total - free
    return {
        "total": total,
        "free": free,
        "used": used
    }

def display_disk_table(disk_size):
    disk_table = Table("#", "Description", "Size")
    disk_info = [
        ("Total Disk Size", "total"),
        ("Free Disk Size", "free"),
        ("Used Disk Size", "used")
    ]

    for index, (description, key) in enumerate(disk_info, start=1):
        disk_table.add_row(str(index), description, format_size(disk_size[key]))

    Console().print(disk_table)

def timeout_handler(signum, frame):
    raise TimeoutError

def confirm_with_timeout(prompt: str, timeout: int = 10) -> bool:
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)
    
    try:
        result = typer.confirm(prompt, default=True)
        signal.alarm(0) 
        return result
    except TimeoutError:
        print("\n[yellow]No input received. Defaulting to [bold]Yes[/bold][/yellow]")
        return True
    
        
def validate_path(directory_name: str) -> Path:
    try:
        # regex pattern to allow alphanumeric characters, underscores, hyphens, dot, and spaces
        pattern = re.compile(r'^[\w\- .@/]+$')
        if not pattern.match(directory_name):
            raise ValueError("Invalid characters in directory name")
        return Path(directory_name)
    except Exception as e:
        raise typer.BadParameter(f"\nThe path '{directory_name}' is not valid: {e}")


def split_list(lst, chunk_size):
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def isset(key, array = None):
    if array is not None:
        try:
            array[key]
            return True
        except:
            return False
    else:
        return key in globals()

def is_debug() -> bool:
    return os.environ.get('BQCKUP_DEBUG', "0") == "1"

def is_verbose() -> bool:
    return os.environ.get('BQCKUP_VERBOSE', "0") == "1"

def should_keep_rustic_secrets() -> bool:
    return os.environ.get('BQCKUP_KEEP_RUSTIC_SECRETS', "0") == "1"

def now() -> int:
    """Returns the current time in seconds since the epoch."""
    return int(time.time())