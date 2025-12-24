from pathlib import Path
import boto3
import re
import os
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from botocore.exceptions import ClientError
from classes.config import Config as bqckup_config
from classes.progress import ProgressPercentage
from classes.storage import Storage
from datetime import datetime
from helpers.utility import is_debug, is_verbose
from typing import Dict, List, Optional

# Rustic repository pattern: root_folder_name/site_name/incremental/
def get_rustic_repo_pattern():
    root_folder = bqckup_config().read('bqckup', 'root_folder_name')
    if root_folder is None:
        root_folder = 'bqckup'  # default fallback
    return re.compile(f"^{re.escape(root_folder)}/[^/]+/incremental/")

BACKUP_DATE_REGEX = re.compile(r"^\d{2}-[A-Za-z]+-\d{4}$")


class s3(object):
    _instances = {}
    config = Config(
        retries={
            "max_attempts": 10,
            "mode": "adaptive",
        }
    )

    def __new__(cls, storage_name: str):
        if storage_name not in cls._instances:
            instance = super(s3, cls).__new__(cls)
            cls._instances[storage_name] = instance
        return cls._instances[storage_name]

    def __init__(self, storage_name: str):
        if hasattr(self, '_initialized'):
            return

        self.storage = Storage().get_storage_detail(storage_name)
        self.root_folder_name: str = bqckup_config().read("bqckup", "root_folder_name") or "bqckup"
        self.clientInit()
        self.bucket_name = self.storage["bucket"]
        self._initialized = True

    def clientInit(self):
        session = boto3.session.Session()
        try:
            self.client = session.client(
                "s3",
                region_name=self.storage["region"],
                endpoint_url=self.storage["endpoint"],
                aws_access_key_id=self.storage["access_key_id"],
                aws_secret_access_key=self.storage["secret_access_key"],
                config=self.config,
            )
        except Exception as e:
            print(f"Failed to connect because : {e}")
            self.client = False

    def isAuthorized(self):
        return True if self.client else False

    def get_total_used(self, prefix=""):
        files = self.list(prefix)

        if not files.get("Contents"):
            return 0

        return sum([int(f["Size"]) for f in files["Contents"]])

    def get_backup_dates(self, site_name: str, sort_by_date: bool = True) -> List[str]:
        """
        Lists valid backup directories for a given site.

        This performs a non-recursive listing and filters for directories
        that match the backup naming convention (e.g., DD-Month-YYYY).
        This method is safe against accidentally listing rustic repositories.

        Args:
            site_name: The name of the backup site.

        Returns:
            A list of S3 prefixes for valid backup directories.

        Example Output:
        [
            "bqckups/my-site/01-January-2025/",
            "bqckups/my-site/02-January-2025/"
        ]
        """

        base_prefix = f"{self.root_folder_name}/{site_name}/"
        delimiter = "/"

        objects = self.list(prefix=base_prefix, delimiter=delimiter)
        top_level_prefixes = [p.get("Prefix", "") for p in objects.get("CommonPrefixes", [])]

        backup_prefixes = []
        for prefix in top_level_prefixes:
            if not prefix:
                continue

            dir_name = os.path.basename(prefix.rstrip(delimiter))
            if BACKUP_DATE_REGEX.match(dir_name):
                backup_prefixes.append(prefix)

        if sort_by_date:
            backup_prefixes.sort(
                key=lambda dir: datetime.strptime(
                    dir.strip("/").split("/")[-1], "%d-%B-%Y"
                )
            )

        return backup_prefixes

    def list(self, prefix: str, delimiter: str = "") -> Dict:
        """
        Lists all objects under a given prefix.

        WARNING: Use with extreme caution. This method can list objects within a rustic
        repository if the 'prefix' leads to it. Directly interacting with rustic
        repository contents via this method can lead to data corruption.
        """

        objects = self.client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=prefix,
            Delimiter=delimiter,
        )

        return objects

    def delete_objects(self, objects: List[str]):
        """
        Deletes a list of objects from the bucket.

        Warning: Ensure that no operations are performed on the rustic repository (e.g. the prefix:
            /{root_folder_name}/site_name/incremental).

        Raises:
            Exception: too many object to delete
            Exception: if the deletion request fails.
        """

        if not objects:
            return

        if len(objects) >= 1000:
            raise Exception("too many object to delete")

        try:
            self.client.delete_objects(
                Bucket=self.bucket_name, Delete={"Objects": [{"Key": k} for k in objects]}
            )

            if is_verbose():
                for k in objects:
                    print(f"Removed {k}")

            print(f"Deleted {len(objects)} objects")

        except Exception as e:
            raise Exception(f"failed to delete objects in bucket: {e}") from e

    def upload(self, file_path, new_file_name, show_progress=True):
        new_file_name = os.path.join(self.root_folder_name, new_file_name)
        file_size = os.path.getsize(file_path)

        MB = 1024 * 1024
        GB = 1024 * MB

        chunk = 8 * MB

        if file_size >= 20 * GB:
            chunk = 64 * MB
        elif file_size >= 1 * GB:
            chunk = 32 * MB
        elif file_size >= 100 * MB:
            chunk = 16 * MB

        config = TransferConfig(
            multipart_threshold=chunk,
            max_concurrency=5,
            multipart_chunksize=chunk,
            use_threads=True,
        )

        try:
            self.client.upload_file(
                file_path,
                self.bucket_name,
                new_file_name,
                Config=config,
                Callback=(
                    ProgressPercentage(file_path, label="Uploading")
                    if show_progress
                    else None
                ),
            )
        except Exception as errorMsg:
            print("File: {} , Upload error, reason: {}\n".format(file_path, errorMsg))
            raise Exception("Msg : {}\n".format(errorMsg))

    def delete(self, key: str):
        """
        Deletes a single object from the bucket.

        Warning: Ensure that no operations are performed on the rustic repository (e.g. the prefix:
            /{root_folder_name}/site_name/incremental).

        Args:
            key: The full key of the object to delete (e.g., "{root_folder_name}/my-site/backup.tar.gz").
        """
        try:
            # skip rustic repository
            if get_rustic_repo_pattern().match(key):
                if is_debug:
                    print(f"Skipping deletion of rustic repository object: {key}")
                return

            self.client.delete_object(Bucket=self.bucket_name, Key=key)
        except Exception as errorMsg:
            print("File: {} Delete failed, reason: {}\n".format(key, errorMsg))
            raise Exception("Msg : {}\n".format(errorMsg))

    def check_if_object_exists(self, bucket_name, key):
        try:
            self.client.head_object(Bucket=bucket_name, Key=key)
            return True
        except ClientError as e:
            return False

    def generate_link(self, file_name=False, time_to_expire=86400):
        key = f"{self.root_folder_name}/{file_name}"

        try:
            if not self.check_if_object_exists(self.bucket_name, key):
                raise Exception(f"File {file_name} not found in storage")

            link = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "ResponseContentDisposition": f"attachment; filename={file_name}",
                },
                ExpiresIn=time_to_expire,  # One Day
            )
            return link
        except Exception as e:
            raise Exception(f"Failed to generate link, Msg: {e}")

    @classmethod
    def check_connection(cls, storage: Optional[str] = None):
        """Check storage connection

        Args:
            storage (Optional[str]): name of storage. Defaults to None. If None, check all storages

        Raises:
            Exception: raise error while check failed for any reason
        """

        storages: List[str] = []

        if storage:
            storages.append(storage)
        else:
            storages = Storage().get_parsed_storage()["storages"]

        for storage_name in storages:
            try:
                obj = cls(storage_name)
                obj.client.head_bucket(Bucket=obj.bucket_name)
            except Exception as e:
                raise Exception(f"{e.__class__.__name__}: Failed connection check for {storage_name} -> {e}") from e
