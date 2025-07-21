from socket import gethostname
from functools import cache
from requests.exceptions import RequestException, MissingSchema, JSONDecodeError
import requests
import sys

from classes.config import Config
from constant import CONFIG_PATH


@cache
def get_credential(base_url: str) -> dict[str, str]:
    try:
        r = requests.get(base_url)
        json: dict = r.json()
    except JSONDecodeError:
        print("Error while decode json.")
        sys.exit(1)
    except Exception:
        print(f"Error while request to {base_url}.")
        sys.exit(1)

    if r.status_code != 200:
        raise RequestException(
            f"{json.get('error', 'Error')} {base_url}: {json.get('message') or str(json)}",
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
