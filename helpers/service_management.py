from socket import gethostname
import requests

from classes.config import Config
from helpers.network import get_server_ip

base_url = Config().read("notification", "service_management_url")


def get_credential(bucket_name: str):
    r = requests.get(f"{base_url}/bqckup/get/{bucket_name}")
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
    r = requests.post(
        f"{base_url}/bqckup/store",
        data={
            "ip_address": get_server_ip(),  # TODO: delete this
            "domain": domain,
            "hostname": gethostname(),
            "data_added": new_data,
            "start_at": start_at,
            "finish_at": finish_at,
            "status": status,
        },
    )

    if r.status_code != 201:
        raise requests.RequestException("Error while sending summary data.")
