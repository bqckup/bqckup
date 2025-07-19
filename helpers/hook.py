from socket import gethostname
import requests
import sys

from classes.config import Config


def get_credential(bucket_name: str) -> dict[str, str]:
    base_url = Config().read("storage", "remote_storage_endpoint")

    r = requests.get(f"{base_url}/{bucket_name}")

    try:
        json: dict = r.json()
    except requests.JSONDecodeError:
        print("Error while decode json.")
        sys.exit(1)

    if r.status_code != 200:
        raise requests.RequestException(
            f"{json.get('error', 'Error')}: {json.get('message') or str(json)}",
            response=r,
        )

    return r.json()


def send_backup_summary(
    domain: str,
    total_size: str,
    new_data: str,
    start_at: int,
    finish_at: int,
    status: str,
    backup_method: str, # can be `tar` or `incremental`
) -> None:
    url = Config().read("webhooks", "after_backup_completed")
    r = requests.post(
        url,
        data={
            "hostname": gethostname(),
            "domain": domain,
            "total_size": total_size,
            "size": new_data,
            "start_at": start_at,
            "finish_at": finish_at,
            "status": status,
            "backup_method": backup_method
        },
    )
    if r.status_code != 201:
        try:
            print("Error while sending summary data.")
            json: dict = r.json()
            raise requests.RequestException(
                f"{json.get('error', 'Error')}: {json.get('message', r.json())}",
                response=r,
            )
        except requests.JSONDecodeError:
            print("Error while decode json.", r.status_code)