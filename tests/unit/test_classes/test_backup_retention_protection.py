"""Unit tests for the last-known-good database backup retention protection.

Covers the requirement that when a database is stuck in a corrupt/unrepaired
state, its last successful backup must never be deleted by the normal
date-based retention cleanup (`Bqckup._clean_old_backups`), even if that
backup falls outside the configured retention window.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from peewee import SqliteDatabase

from classes.bqckup import Bqckup
from models.log import Log

SITE_CONFIG = {
    "name": "example.com",
    "database": {
        "type": "mysql",
        "user": "root",
        "password": "secret",
        "host": "localhost",
        "port": 3306,
        "name": "example_db",
    },
    "options": {"storage": "dummy", "retention": "1"},
}


def _bq():
    # Bypass the heavy __init__ (storage connection checks).
    return Bqckup.__new__(Bqckup)


@pytest.fixture
def test_db():
    db = SqliteDatabase(":memory:")
    with patch("models.database", db):
        db.bind([Log])
        db.create_tables([Log])
        yield db
        db.drop_tables([Log])


class TestGetProtectedDbBackupKeys:
    def test_no_successful_backup_means_nothing_is_protected(self, test_db):
        bq = _bq()
        assert bq._get_protected_db_backup_keys(SITE_CONFIG) == set()

    def test_last_successful_backup_key_is_protected(self, test_db):
        created_at = int(time.time()) - 30 * 86400  # well outside any retention
        Log.create(
            name="example.com",
            file_path="1700000000-example_db.sql.gz",
            description="Database Backup for 'root@localhost:3306/example_db' Success",
            created_at=created_at,
            type=Log.__DATABASE__,
            storage="dummy",
            status=Log.__SUCCESS__,
        )

        bq = _bq()
        with patch("classes.bqckup.Config") as mock_config:
            mock_config.return_value.read.return_value = "bqckup"
            protected = bq._get_protected_db_backup_keys(SITE_CONFIG)

        expected_date = datetime.fromtimestamp(created_at).strftime("%d-%B-%Y")
        assert protected == {
            f"bqckup/example.com/{expected_date}/1700000000-example_db.sql.gz"
        }

    def test_failed_attempts_do_not_shift_the_protected_key(self, test_db):
        """A later FAILED attempt (e.g. corrupt table) must not override the
        last known-good backup used for protection."""
        success_created_at = int(time.time()) - 10 * 86400
        Log.create(
            name="example.com",
            file_path="1000-example_db.sql.gz",
            description="Database Backup for 'root@localhost:3306/example_db' Success",
            created_at=success_created_at,
            type=Log.__DATABASE__,
            storage="dummy",
            status=Log.__SUCCESS__,
        )
        Log.create(
            name="example.com",
            file_path="2000-example_db.sql.gz",
            description="Database Backup Failed for 'root@localhost:3306/example_db': corrupt",
            created_at=int(time.time()),
            type=Log.__DATABASE__,
            storage="dummy",
            status=Log.__FAILED__,
        )

        bq = _bq()
        with patch("classes.bqckup.Config") as mock_config:
            mock_config.return_value.read.return_value = "bqckup"
            protected = bq._get_protected_db_backup_keys(SITE_CONFIG)

        expected_date = datetime.fromtimestamp(success_created_at).strftime("%d-%B-%Y")
        assert protected == {
            f"bqckup/example.com/{expected_date}/1000-example_db.sql.gz"
        }


class TestCleanOldBackupsPreservesLastGoodDbBackup:
    def test_protected_key_is_excluded_from_deletion(self, test_db):
        old_date = "01-January-2020"
        recent_date = "01-January-2026"

        old_db_key = f"bqckup/example.com/{old_date}/1000-example_db.sql.gz"
        old_file_key = f"bqckup/example.com/{old_date}/1000.tar.gz"

        created_at = int(datetime.strptime(old_date, "%d-%B-%Y").timestamp())
        Log.create(
            name="example.com",
            file_path="1000-example_db.sql.gz",
            description="Database Backup for 'root@localhost:3306/example_db' Success",
            created_at=created_at,
            type=Log.__DATABASE__,
            storage="dummy",
            status=Log.__SUCCESS__,
        )

        mock_s3 = MagicMock()
        mock_s3.get_backup_dates.return_value = [
            f"bqckup/example.com/{old_date}/",
            f"bqckup/example.com/{recent_date}/",
        ]
        mock_s3.list.return_value = {
            "Contents": [{"Key": old_db_key}, {"Key": old_file_key}]
        }

        bq = _bq()
        with (
            patch("classes.bqckup.s3", return_value=mock_s3),
            patch("classes.bqckup.Config") as mock_config,
        ):
            mock_config.return_value.read.return_value = "bqckup"
            bq._clean_old_backups(SITE_CONFIG)

        mock_s3.delete_objects.assert_called_once()
        deleted = mock_s3.delete_objects.call_args.kwargs["objects"]
        assert old_db_key not in deleted
        assert old_file_key in deleted

    def test_no_deletion_call_when_only_protected_objects_remain(self, test_db):
        old_date = "01-January-2020"
        recent_date = "01-January-2026"
        old_db_key = f"bqckup/example.com/{old_date}/1000-example_db.sql.gz"

        created_at = int(datetime.strptime(old_date, "%d-%B-%Y").timestamp())
        Log.create(
            name="example.com",
            file_path="1000-example_db.sql.gz",
            description="Database Backup for 'root@localhost:3306/example_db' Success",
            created_at=created_at,
            type=Log.__DATABASE__,
            storage="dummy",
            status=Log.__SUCCESS__,
        )

        mock_s3 = MagicMock()
        mock_s3.get_backup_dates.return_value = [
            f"bqckup/example.com/{old_date}/",
            f"bqckup/example.com/{recent_date}/",
        ]
        mock_s3.list.return_value = {"Contents": [{"Key": old_db_key}]}

        bq = _bq()
        with (
            patch("classes.bqckup.s3", return_value=mock_s3),
            patch("classes.bqckup.Config") as mock_config,
        ):
            mock_config.return_value.read.return_value = "bqckup"
            bq._clean_old_backups(SITE_CONFIG)

        mock_s3.delete_objects.assert_not_called()
