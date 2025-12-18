from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union
from subprocess import CalledProcessError, CompletedProcess
import json
import toml
import traceback
import subprocess

from constant import RUSTIC_CONFIG_PATH
from classes.config import Config as bqckup_config
from helpers.utility import is_debug


class RusticConfigError(Exception): ...


class RusticCheckError(CalledProcessError): ...


class RusticError(Exception): ...


class Rustic:
    def __init__(
        self,
        site_config: Dict[str, Any],
        storage_config: Dict[str, Any],
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
        # Storage Config:
        #     bucket: dummy
        #     access_key_id: dummy
        #     secret_access_key: dummy
        #     region: dummy
        #     endpoint: dummy
        #     primary: no

        self.site_config = site_config
        self.storage_config = storage_config
        self.__subprocess_args = {
            "capture_output": True,
            "text": True,
            "check": True,
        }

    @property
    def root_folder_name(self):
        return bqckup_config().read("bqckup", "root_folder_name")

    def get_snapshots(self, full_id: bool = False) -> List[Dict[str, Any]]:        
        """Get snapshots from repository

        Example Outputs:
        `[
            {
                'id': '33e25d78ce3a86eda0d127c3689a8fb558338edec824141d8ef84e9d8856da4b',
                'paths': ['/var/www/html'],
                'changed': 1,
                'data_added': 789,
                'backup_duration': 1.44906424,
                'time': '2025-12-11T06:55:47.218649934Z'
            },
        ]`

        changed: new file or file change
        data_added: in byte
        """

        output: CompletedProcess = subprocess.run(
            [
                "rustic",
                "snapshots",
                "--use-profile",
                self.site_config["name"],
                "--json",
            ],
            **self.__subprocess_args,  # type: ignore
        )

        parsed_output = json.loads(output.stdout)

        results: List[Dict[str, Any]] = []

        for group in parsed_output:
            for snapshot in group.get("snapshots", []):
                results.append(self.parse_snapshot(snapshot, full_id))

        return results

    def parse_snapshot(self, snapshot: Dict[str, Any], full_id: bool = False) -> Dict[str, Any]:
        # only support rustic with version >= v0.10.0

        summary = snapshot.get("summary", {})

        raw_id = snapshot.get("id", "")
        id = raw_id if full_id else raw_id[:8]
        files_new = summary.get("files_new", 0)
        files_changed = summary.get("files_changed", 0)
        time = datetime.fromisoformat(
            snapshot.get("time", "")[:26]
            .replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "id": id,
            "paths": snapshot.get("paths", []),
            "changed": files_new + files_changed,
            "data_added": summary.get("data_added_packed"),
            "backup_duration": summary.get("backup_duration"),
            "time": time,
        }

    @staticmethod
    def is_enabled(config: dict) -> bool:
        incremental = config.get("incremental", {})
        return incremental and (incremental.get("enabled") or incremental.get("enable"))

    def check_repository(self):
        try:
            subprocess.run(
                [
                    "rustic",
                    "check",
                    "--use-profile",
                    self.site_config["name"],
                ],
                **self.__subprocess_args,  # type: ignore
            )
        except subprocess.CalledProcessError as e:
            raise RusticCheckError(e.returncode, e.cmd, e.output, e.stderr)

    def backup(self) -> Dict[str, Union[int, str]]:
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
            **self.__subprocess_args,  # type: ignore
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

    def restore(self, snapshot: str, target: str | None = None):
        """Restore backup

        Args:
            snapshot (str): snapshot id or latest

        Raises:
            RusticError: No snapshots available
        """

        for path in self.site_config["path"]:
            destination = str(Path(target) / Path(path).name) if target else path
            command = [
                "rustic",
                "--use-profile",
                self.site_config["name"],
                "--filter-paths", # filter-paths ensures the correct snapshot are selected during restore
                path,
                "restore",
                f"{snapshot}:{path}",
                destination,
            ]  # command: rustic -P domain.com --filter-paths /var/www/html restore latest:/var/www/html /var/www/html

            try:
                subprocess.run(command, **self.__subprocess_args)  # type: ignore
                print(f"[OK] {path}")
            except Exception as e:
                if is_debug():
                    traceback.print_exc()

                print(f"Failed restore {path}")

                if isinstance(e, CalledProcessError):
                    print(e.stderr)
                else:
                    print(e)

                raise e

    def check_config(self):
        """Check rustic configuration from sites

        Raises:
            RusticConfigError: password empty
        """

        if self.site_config.get("incremental", {}).get("password") is None:
            raise RusticConfigError("Password can't be empty")

    def dump_config(self, with_credentials: bool = True) -> Path:
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
                "password": self.site_config.get("incremental", {}).get("password"),
                "options": {
                    "access_key_id": self.storage_config["access_key_id"],
                    "secret_access_key": self.storage_config["secret_access_key"],
                    "region": self.storage_config["region"],
                    "bucket": self.storage_config["bucket"],
                    "endpoint": self.storage_config["endpoint"],
                    "root": f"/{self.root_folder_name}/{self.site_config['name']}/incremental",
                } if with_credentials else None,
            },
            "backup": {
                # "init": True,  # Create repository if not exists ### not work
                "json": True,  # Output in json
                "no-scan": True,
                "git-ignore": True,
                "one-file-system": True,
                "skip-if-unchanged": True, # skip saving of the snapshot if it is identical to the parent (unchanged)
                "tags": [self.site_config["name"]],
                "snapshots": [{"sources": self.site_config["path"]}],
                "globs": [
                    f"!{i}" for i in self.site_config.get("exclude_path", [])
                ],  # !/tmp/dir1 # see https://github.com/rustic-rs/rustic/discussions/1194#discussioncomment-10298116
            },
            "forget": {"keep-last": int(self.site_config.get("options", {}).get("retention", 7))},
        }

        config_dir: Path = Path(RUSTIC_CONFIG_PATH)
        config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        config_path: Path = config_dir / (self.site_config["name"] + ".toml")

        with config_path.open("w") as f:
            toml.dump(config, f)

        # Change permission to `.rw-------` for better security
        config_path.chmod(0o600)

        return config_path

    def check_and_dump(self):
        self.check_config()
        self.dump_config()
