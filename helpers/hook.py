from socket import gethostname
from functools import cache
from requests.exceptions import RequestException, MissingSchema, JSONDecodeError
import requests
import sys

from classes.config import Config
from constant import CONFIG_PATH


@cache
def get_credential(bucket_name: str) -> dict[str, str]:
    base_url = Config().read("storage", "remote_storage_endpoint", print_error=False)

    try:
        r = requests.get(f"{base_url}/{bucket_name}")
        json: dict = r.json()
    except MissingSchema:
        print(
            f"Remote storage is enabled, but `remote_storage_endpoint` is missing or invalid in `{CONFIG_PATH}`."
        )
        sys.exit(1)

    except JSONDecodeError:
        print("Error while decode json.")
        sys.exit(1)

    if r.status_code != 200:
        raise RequestException(
            f"{json.get('error', 'Error')} {bucket_name}: {json.get('message') or str(json)}",
            response=r,
        )

    return r.json()


def send_backup_summary(
    domain: str,
    total_size: str,
    new_data: str,
    start_at: int,
    finish_at: int,
    status: str,  # can be `failed` or `completed`.
    backup_method: str,  # can be `tar` or `incremental`.
) -> None:
    url = Config().read("webhooks", "after_backup_completed", print_error=False)

    if not url:
        return

    payload = {
        "hostname": gethostname(),
        "domain": domain,
        "total_size": total_size,
        "size": new_data,
        "start_at": start_at,
        "finish_at": finish_at,
        "status": status,
        "backup_method": backup_method,
    }

    try:
        r = requests.post(url, data=payload)

        if r.status_code != 201:
            print("Error while sending summary data.")
            json: dict = r.json()
            raise RequestException(
                f"{json.get('error', 'Error')}: {json.get('message', r.json())}",
                response=r,
            )
    except MissingSchema:
        print(f"`after_backup_completed` url is invalid in `{CONFIG_PATH}`.")
        sys.exit(1)
    except JSONDecodeError:
        print("Error while decode json.", r.status_code)
