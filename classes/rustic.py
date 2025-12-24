from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Union, Generator
from subprocess import CalledProcessError, CompletedProcess
from functools import cached_property
import json
import toml
import traceback
import subprocess
import re

from constant import RUSTIC_CONFIG_PATH
from classes.config import Config as bqckup_config
from helpers.utility import is_debug

from rich import print  # pyright: ignore[reportMissingImports]


class RusticError(Exception): ...


class RusticConfigError(RusticError): ...


class RusticCleanError(RusticError): ...


class RusticCommandError(CalledProcessError, RusticError): ...


class RusticCheckError(RusticCommandError): ...


class RusticBackupError(RusticCommandError): ...


class RusticRestoreError(RusticCommandError): ...


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

    @cached_property
    def version(self) -> str:
        """Get rustic version"""
        try:
            output: CompletedProcess = subprocess.run(
                ["rustic", "--version"],
                **self.__subprocess_args,  # type: ignore
            )

            # Example outputs:
            # NixOS package: `rustic 0.10.2`
            # Manual install (release/build): `rustic v0.10.2-1-g189b17c`

            full_version_string = output.stdout.strip().split(" ")[1]
            match = re.search(r'v?(\d+\.\d+\.\d+)', full_version_string)
            if not match:
                raise RusticError(f"Could not parse rustic version from: {full_version_string}")

            return match.group(1)

        except (CalledProcessError, FileNotFoundError, IndexError) as e:
            if is_debug:
                traceback.print_exc()
            raise RusticError(f"Could not determine rustic version. Error: {e}") from e

    @cached_property
    def version_tuple(self) -> tuple[int, ...]:
        """Get rustic version as a tuple of ints"""
        return tuple(map(int, self.version.split(".")))

    @property
    def root_folder_name(self):
        return bqckup_config().read("bqckup", "root_folder_name")

    @staticmethod
    def is_enabled(config: dict) -> bool:
        incremental = config.get("incremental", {})
        return incremental and (incremental.get("enabled") or incremental.get("enable"))

    def _parse_json_stream(self, stream: str) -> List[Any]:
        """Parses a string that may contain multiple concatenated JSON objects."""
        decoder = json.JSONDecoder()
        results = []
        pos = 0
        stream = stream.strip()
        if not stream:
            return []
        while pos < len(stream):
            try:
                obj, end = decoder.raw_decode(stream, pos)
                results.append(obj)
                pos = end
                # skip whitespace until the next object
                next_char_match = re.search(r'\S', stream[pos:])
                if next_char_match:
                    pos += next_char_match.start()
                else:
                    break
            except json.JSONDecodeError:
                break # stop if there's non-JSON trailing data
        return results

    def _iter_snapshots(
        self, parsed_output: List[Any]
    ) -> Generator[Dict[str, Any], None, None]:
        """Iterates over snapshots from a parsed rustic output, handling different versions.

        Example yielded output (a single raw snapshot dictionary):
        ```json
        {
            "snapshot": {
                "time": "2025-12-17T15:45:33.834905424+08:00",
                "program_version": "rustic 0.9.0",
                "parent": "c8c72cad57d59dee5d525446459e0f7b46bd6fa60d7e7274a094bab949a117de",
                "tree": "ba0f6d2d228c46da98ea9c17c09e0e1c3419316cdb0b3e99343d07c504feb6c4",
                "paths": ["Downloads"],
                "hostname": "aira",
                "username": "",
                "uid": 0,
                "gid": 0,
                "tags": [],
                "original": "fcebc56c2e5f9f52524976642491a97c48dda736e3ba737556b7e108fcefde6b",
                "summary": {},
                "id": "fcebc56c2e5f9f52524976642491a97c48dda736e3ba737556b7e108fcefde6b"
            },
            "keep": true,
            "reasons": ["last", "hourly", "daily", "weekly", "monthly", "yearly"]
        }
        ```
        """

        for group in parsed_output:
            if self.version_tuple >= (0, 10, 0):
                if isinstance(group, dict):
                    yield from group.get("snapshots", [])
            elif self.version_tuple >= (0, 9, 5):
                # old format is a list inside a list `[[{}, [{}, {}]]]`
                if isinstance(group, list) and len(group) > 1 and isinstance(group[1], list):
                    yield from group[1]

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

        try:
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
        except CalledProcessError as e:
            raise RusticCommandError(e.returncode, e.cmd, e.stdout, e.stderr) from e

        parsed_output = json.loads(output.stdout)
        results: List[Dict[str, Any]] = []
        for snapshot in self._iter_snapshots(parsed_output):
            results.append(self.parse_snapshot(snapshot, full_id))

        return results

    def parse_snapshot(
        self, snapshot: Dict[str, Any], full_id: bool = False
    ) -> Dict[str, Any]:
        summary = snapshot.get("summary", {})

        raw_id = snapshot.get("id", "")
        id = raw_id if full_id else raw_id[:8]
        files_new = summary.get("files_new", 0)
        files_changed = summary.get("files_changed", 0)
        time = datetime.fromisoformat(
            snapshot.get("time", "")[:26]
            .replace("Z", "+00:00")
        ).strftime("%d %b %Y %H:%M:%S")

        return {
            "id": id,
            "paths": snapshot.get("paths", []),
            "changed": files_new + files_changed,
            "data_added": summary.get("data_added_packed"),
            "backup_duration": summary.get("backup_duration"),
            "time": time,
        }

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
            raise RusticCheckError(e.returncode, e.cmd, e.output, e.stderr) from e

    def backup(self) -> Dict[str, Union[int, str]]:
        """Running Backup

        Raises:
            RusticError: rustic return code not 0

        Returns:
            dict: detail information about backup action
        """

        try:
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
        except subprocess.CalledProcessError as e:
            raise RusticBackupError(e.returncode, e.cmd, e.output, e.stderr) from e

        parsed_output: dict = json.loads(output.stdout)
        summary = parsed_output["summary"]

        # if skip-if-unchanged is true and no snapshot changes, the key id does not exist; use the last snapshot id instead
        id = parsed_output.get("id", parsed_output.get("parent", ""))

        return {
            "id": id,
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
                "--filter-paths",  # filter-paths ensures the correct snapshot are selected during restore
                path,
                "restore",
                f"{snapshot}:{path}",
                destination,
            ]  # command: rustic -P domain.com --filter-paths /var/www/html restore latest:/var/www/html /var/www/html

            try:
                subprocess.run(command, **self.__subprocess_args)  # type: ignore
                print(f"[OK] {path}")
            except subprocess.CalledProcessError as e:
                raise RusticRestoreError(e.returncode, e.cmd, e.output, e.stderr) from e
            except Exception as e:
                if is_debug():
                    traceback.print_exc()
                raise RusticError(f"Unexpected error while restoring backups for {path}: {e}") from e

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
                } if with_credentials or is_debug() else None,
            },
            "backup": {
                # "init": True,  # Create repository if not exists ### not work
                "json": True,  # Output in json
                "no-scan": True,
                "git-ignore": True,
                "one-file-system": True,
                "tags": [self.site_config["name"]],
                "snapshots": [{"sources": self.site_config["path"]}],
                "globs": [
                    f"!{i}" for i in self.site_config.get("exclude_path", [])
                ],  # !/tmp/dir1 # see https://github.com/rustic-rs/rustic/discussions/1194#discussioncomment-10298116
            },
            "forget": {
                "keep-last": int(
                    self.site_config.get("options", {}).get("retention", 7)
                )
            },
        }

        # skip saving of the snapshot if it is identical to the parent (unchanged)
        if self.version_tuple <= (0, 9, 5):
            config["backup"]["skip-identical-parent"] = True
        elif self.version_tuple >= (0, 10, 0):
            config["backup"]["skip-if-unchanged"] = True

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

    def clean(self):
        """Forget old snapshots according to the policy and prune the repository"""

        command = [
            "rustic",
            "forget",
            "--json",
            "--prune",
            "--use-profile",
            self.site_config["name"],
        ]

        removed_count = 0
        try:
            print(f"Cleaning repository for '{self.site_config['name']}'...")

            output: CompletedProcess = subprocess.run(
                command,
                **self.__subprocess_args,  # type: ignore
            )

            if output.stdout.strip():
                all_outputs = self._parse_json_stream(output.stdout)

                for data in all_outputs:
                    if not isinstance(data, list):
                        continue  # skip non-list objects from stream (e.g. prune summary)

                    for snapshot_details in self._iter_snapshots(data):
                        if isinstance(snapshot_details, dict) and not snapshot_details.get("keep", True):
                            removed_count += 1

            if removed_count > 0:
                print(f"Successfully removed {removed_count} snapshots.")
            else:
                print("No old incremental snapshots to remove")
        except json.JSONDecodeError as e:
            raise RusticCleanError(f"Failed to parse JSON output:\n{output.stdout}") from e
        except Exception as e:
            raise RusticCleanError from e
