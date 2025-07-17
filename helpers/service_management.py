from socket import gethostname
import requests

from classes.config import Config
from helpers.network import get_server_ip


class UnauthorizedError(Exception): ...


def get_credential(bucket_name: str):
    url = Config().read("storage", "remote_storage_endpoint")
    payload = {
        "ip_address": get_server_ip(),
        "bucket_name": bucket_name
    }

    r = requests.post(url, data=payload)

    if r.status_code == 401:
        raise UnauthorizedError(f"Unauthorized: {r.json().get('message', '')}")

    if r.status_code != 200:
        raise requests.RequestException(r)

    return r.json()


def send_backup_summary(
    domain: str,
    new_data: str,
    start_at: int,
    finish_at: int,
    status: str,
):
    url = Config().read("webhooks", "after_backup_completed")
    r = requests.post(
        url,
        data={
            "ip_address": get_server_ip(),
            "domain": domain,
            "hostname": gethostname(),
            "data_added": new_data,
            "start_at": start_at,
            "finish_at": finish_at,
            "status": status,
        },
    )

    if r.status_code == 401:
        raise UnauthorizedError(f"Unauthorized: {r.json().get('message', '')}")

    if r.status_code != 201:
        raise requests.RequestException("Error while sending summary data.")
