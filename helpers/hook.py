from socket import gethostname
from requests.exceptions import RequestException, MissingSchema, JSONDecodeError
import requests
import sys
from typing import Dict

from classes.config import Config
from constant import CONFIG_PATH, DEFAULT_HEADER


class StorageCredentialError(Exception):
    """Raised when remote credential fetch fails."""

_credential_cache: Dict[str, Dict[str, str]] = {}
_credential_failure_cache: Dict[str, StorageCredentialError] = {}


def clear_credential_cache() -> None:
    """Reset cached credential lookups (used by tests)."""
    _credential_cache.clear()
    _credential_failure_cache.clear()


def get_credential(base_url: str) -> Dict[str, str]:
    # Cache both results and failures: a failed fetch must not be retried
    # (lru_cache would not cache the exception, causing a second network call).
    if base_url in _credential_cache:
        return _credential_cache[base_url]
    if base_url in _credential_failure_cache:
        raise _credential_failure_cache[base_url]

    try:
        r = requests.get(base_url, headers=DEFAULT_HEADER, timeout=(5, 30))
        json: dict = r.json()
    except JSONDecodeError:
        error = StorageCredentialError(f"Error while decode json from {base_url}")
        _credential_failure_cache[base_url] = error
        raise error
    except Exception as e:
        error = StorageCredentialError(f"Error while request to {base_url}: {e}")
        _credential_failure_cache[base_url] = error
        raise error

    if r.status_code != 200:
        error = StorageCredentialError(
            f"{json.get('error', 'Error')} {base_url}: {json.get('message') or str(json)}"
        )
        _credential_failure_cache[base_url] = error
        raise error

    _credential_cache[base_url] = r.json()
    return _credential_cache[base_url]


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

    if new_data == 0:
        message = f"Backup {status}: no new data uploaded (no changes detected)"
    else:
        message = f"Backup {status}: {new_data} bytes uploaded"

    payload = {
        "hostname": gethostname(),
        "domain": domain,
        "total_size": total_size,
        "size": new_data,
        "start_at": start_at,
        "finish_at": finish_at,
        "status": status,
        "backup_method": backup_method,
        "message": message,
    }

    # Discord webhook requires JSON with a "content" field
    is_discord = "discordapp.com" in url or "discord.com" in url
    if is_discord:
        discord_payload = {"content": f"**[{domain}]** {message} | size: {total_size} bytes | method: {backup_method}"}
        try:
            r = requests.post(url, json=discord_payload)
            if r.status_code not in (200, 204):
                print("Error while sending summary data.")
        except Exception as e:
            print(f"Error sending summary to Discord: {e}")
        return

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
