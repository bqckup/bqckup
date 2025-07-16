from os.path import join as path_join
from pathlib import Path
from typing import Any
from subprocess import CompletedProcess
import json
import toml
import subprocess

from constant import RUSTIC_CONFIG_PATH, STORAGE_CONFIG_PATH, SITE_CONFIG_PATH
from classes.config import Config as bqckup_config


class RusticConfigError(Exception): ...


class RusticIndexError(Exception): ...


class RusticError(Exception): ...


class Rustic:
    def __init__(
        self,
        site_config: dict[str, Any],
        storage_config: dict[str, Any],
        include_config: bool = True,
    ):
        # Site Config:
        #     name: domain
        #     enabled: no
        #     path:
        #         - /var/www/html
        #     exclude_path:
        #         - cache
        #     database:
        #         type: mysql
        #         host: localhost
        #         port: 3306
        #         user: root
        #         password: root
        #         name: database
        #     options:
        #         storage: dummy
        #         interval: daily # can be daily, weekly, monthly
        #         retention: '7'
        #         follow_symlink: no
        #         save_locally: no
        #         save_locally_path: /etc/bqckup/tmp
        #         notification_email: email@example.com
        #         provider: s3
        # # Selected by options on Site Config
        # Storage Config:
        #     bucket: dummy
        #     access_key_id: dummy
        #     secret_access_key: dummy
        #     region: dummy
        #     endpoint: dummy
        #     primary: no

        # Include config file
        if include_config and bqckup_config().read("bqckup", "config_backup"):
            site_config["path"] += (STORAGE_CONFIG_PATH, site_config["config_path"])

        self.site_config = site_config
        self.storage_config = storage_config[site_config["options"]["storage"]]
        self.__subprocess_args = {
            "capture_output": True,
            "text": True,
            "check": True,
        }

        self.check_config()
        self.dump_config()

    @property
    def root_folder_name(self):
        return bqckup_config().read("bqckup", "root_folder_name")

    @property
    def snapshots(self) -> list[dict[str, Any]]:
        output: CompletedProcess = subprocess.run(
            [
                "rustic",
                "snapshots",
                "--use-profile",
                self.site_config["name"],
                "--json",
            ],
            **self.__subprocess_args,
        )

        parsed_output = json.loads(output.stdout)

        try:
            return parsed_output[0][1]
        except IndexError:
            return []
        except Exception as e:
            raise RusticError("Error while getting snapshots:", e)

    def check_repository(self):
        subprocess.run(
            [
                "rustic",
                "check",
                "--use-profile",
                self.site_config["name"],
            ],
            **self.__subprocess_args,
        )

    def backup(self) -> dict[str, int | str]:
        """Running Backup

        Raises:
            RusticError: rustic return code not 0

        Returns:
            dict: detail information about backup action
        """

        output: CompletedProcess = subprocess.run(
            [
                "rustic",
                "backup",
                "--init",
                "--use-profile",
                self.site_config["name"],
            ],
            **self.__subprocess_args,
        )

        if output.returncode != 0:
            raise RusticError(output.stderr)

        parsed_output: dict = json.loads(output.stdout)
        summary = parsed_output["summary"]

        return {
            "id": parsed_output["id"][:8],  # get only 8 characters from start
            "new": summary["files_new"],
            "changed": summary["files_changed"],
            "unchanged": summary["files_unmodified"],
            "total_duration": int(summary["total_duration"]),  # in seconds
            "uploaded": summary[
                "data_added_packed"
            ],  # data added to repository (compressed); in byte
            "total_size": summary["total_bytes_processed"],
        }

    def restore(self, snapshot: str, target: str = None):
        """Restore backup

        Args:
            snapshot (str): snapshot id or latest

        Raises:
            RusticError: No snapshots available
        """

        if len(self.snapshots) < 1:
            raise RusticError("No snapshots found.")

        for path in self.site_config["path"]:
            destination = str(Path(target) / Path(path).name) if target else path
            command = [
                "rustic",
                "--use-profile",
                self.site_config["name"],
                "restore",
                f"{snapshot}:{path}",
                destination,
            ]  # command: rustic -P domain.com restore latest:/var/www/html /var/www/html

            subprocess.run(command, **self.__subprocess_args)
            print(f"[OK] {path}")

    def check_config(self):
        """Check rustic configuration from sites

        Raises:
            RusticConfigError: rustic not configured
            RusticConfigError: password empty
        """

        rustic_config: dict | None = self.site_config.get("incremental")

        if rustic_config is None:
            raise RusticConfigError("Rustic not configured")

        if rustic_config.get("password") is None:
            raise RusticConfigError("Password can't be empty")

    def dump_config(self) -> Path:
        """Generate rustic config parsed from storage and site config

        Returns:
            Path: path to config file
        """

        config = {
            "global": {
                "no-progress": True,
                "check-index": True,
                "log-level": "info",
            },
            "repository": {
                "repository": "opendal:s3",
                "password": str(self.site_config["incremental"]["password"]),
                "options": {
                    "access_key_id": self.storage_config["access_key_id"],
                    "secret_access_key": self.storage_config["secret_access_key"],
                    "region": self.storage_config["region"],
                    "bucket": self.storage_config["bucket"],
                    "endpoint": self.storage_config["endpoint"],
                    "root": f"/{self.root_folder_name}/{self.site_config['name']}/incremental",
                },
            },
            "backup": {
                # "init": True,  # Create repository if not exists ### not work
                "json": True,  # Output in json
                "no-scan": True,
                "git-ignore": True,
                "one-file-system": True,
                "snapshots": [{"sources": self.site_config["path"]}],
                "globs": [
                    f"!{i}" for i in self.site_config.get("exclude_path", [])
                ],  # !/tmp/dir1 # see https://github.com/rustic-rs/rustic/discussions/1194#discussioncomment-10298116
            },
            "forget": {"keep-daily": int(self.site_config["options"]["retention"])},
        }

        config_dir: Path = Path(RUSTIC_CONFIG_PATH)
        config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        config_path: Path = config_dir / (self.site_config["name"] + ".toml")

        with config_path.open("w") as f:
            toml.dump(config, f)

        # Change permission to `.rw-------` for better security
        config_path.chmod(0o600)

        return config_path
