import requests
from pathlib import Path
from rich.progress import Progress

def get_server_ip():
    try:
        result = requests.get('http://ifconfig.me', verify=False)
        return result.text.strip()
    except Exception as e:
        import socket
        return socket.gethostbyname(socket.gethostname())

def generate_short_link(link):
    import uuid
    from constant import YOURLS_SECRET_KEY, YOURLS_HOST

    if not YOURLS_HOST or not YOURLS_HOST:
        return False

    r = requests.post(f"{YOURLS_HOST}/yourls-api.php?signature={YOURLS_SECRET_KEY}", {
       "format": "json",
        "action": "shorturl",
        "url": link,
    })

    if r.status_code != 200:
        return False
    
    return r.json()['shorturl']

def download_files(file, target, _s3):
    for i, backup in enumerate(file):
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

