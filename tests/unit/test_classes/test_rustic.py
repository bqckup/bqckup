"""Unit tests for incremental backup (rustic) provider handling.

These tests focus on the local-provider support added to incremental backups,
so they avoid invoking the real `rustic` binary or touching S3. The pure
configuration logic in ``Rustic.dump_config`` is exercised directly, and the
provider gating in ``Bqckup.incremental_backup`` is verified with mocks.
"""

import os
from unittest.mock import patch

import pytest
import toml

from classes.rustic import Rustic
from constant import BQ_PATH


def make_site_config(provider="s3", save_locally_path=None, name="example.com"):
    options = {
        "provider": provider,
        "storage": "dummy",
        "interval": "daily",
        "retention": "7",
        "follow_symlink": False,
        "save_locally": False,
    }
    if save_locally_path is not None:
        options["save_locally_path"] = save_locally_path

    return {
        "name": name,
        "enabled": True,
        "incremental": {"enabled": True, "password": "secret-pass"},
        "path": ["/var/www/html"],
        "exclude_path": ["cache"],
        "options": options,
    }


S3_STORAGE = {
    "access_key_id": "AKIA_TEST",
    "secret_access_key": "SECRET_TEST",
    "region": "us-east-1",
    "bucket": "test-bucket",
    "endpoint": "https://s3.amazonaws.com",
}


@pytest.fixture(autouse=True)
def _stub_rustic_env():
    """Avoid the real `rustic` binary (version) and real bqckup config reads."""
    with patch.object(Rustic, "version", return_value="0.9.0"), \
         patch("classes.rustic.bqckup_config") as mock_cfg:
        mock_cfg.return_value.read.return_value = "bqckup"
        yield


class TestRusticProvider:
    def test_provider_defaults_to_s3_when_missing(self):
        cfg = make_site_config()
        cfg["options"].pop("provider")
        assert Rustic(cfg, {}).provider == "s3"

    def test_provider_reads_local(self):
        assert Rustic(make_site_config(provider="local"), {}).provider == "local"

    def test_local_repository_path_uses_save_locally_path(self, tmp_path):
        cfg = make_site_config(provider="local", save_locally_path=str(tmp_path))
        rustic = Rustic(cfg, {})

        assert rustic.local_repository_path == os.path.join(
            str(tmp_path), "example.com", "incremental"
        )

    def test_local_repository_path_falls_back_to_bq_tmp(self):
        cfg = make_site_config(provider="local")  # no save_locally_path configured
        rustic = Rustic(cfg, {})

        assert rustic.local_repository_path == os.path.join(
            BQ_PATH, "tmp", "example.com", "incremental"
        )


class TestDumpConfigLocal:
    def test_repository_is_written_as_filesystem_path(self, tmp_path):
        dest = tmp_path / "backups"
        cfg = make_site_config(provider="local", save_locally_path=str(dest))

        with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(tmp_path / "rustic")):
            config_path = Rustic(cfg, {}).dump_config()

        data = toml.load(config_path)
        expected_repo = str(dest / "example.com" / "incremental")

        assert data["repository"]["repository"] == expected_repo
        assert data["repository"]["password"] == "secret-pass"
        # Local repositories must not carry any S3 options/credentials block.
        assert "options" not in data["repository"]

    def test_creates_repository_directory(self, tmp_path):
        dest = tmp_path / "backups"
        cfg = make_site_config(provider="local", save_locally_path=str(dest))

        with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(tmp_path / "rustic")):
            Rustic(cfg, {}).dump_config()

        assert (dest / "example.com" / "incremental").is_dir()

    def test_works_with_empty_storage_config(self, tmp_path):
        # For the local provider the caller passes storage_config={}; dump_config
        # must never try to read S3 keys from it.
        cfg = make_site_config(provider="local", save_locally_path=str(tmp_path / "b"))

        with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(tmp_path / "rustic")):
            config_path = Rustic(cfg, {}).dump_config()  # must not raise KeyError

        assert os.path.exists(config_path)

    def test_scrubbed_config_has_no_secrets_and_stays_valid(self, tmp_path):
        cfg = make_site_config(provider="local", save_locally_path=str(tmp_path / "b"))

        with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(tmp_path / "rustic")):
            config_path = Rustic(cfg, {}).dump_config(with_credentials=False)

        data = toml.load(config_path)
        assert data["repository"]["repository"].endswith("incremental")
        assert "options" not in data["repository"]


class TestDumpConfigS3:
    def test_repository_uses_opendal_s3_with_credentials(self, tmp_path):
        cfg = make_site_config(provider="s3")

        with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(tmp_path / "rustic")):
            config_path = Rustic(cfg, S3_STORAGE).dump_config(with_credentials=True)

        data = toml.load(config_path)
        options = data["repository"]["options"]

        assert data["repository"]["repository"] == "opendal:s3"
        assert options["bucket"] == "test-bucket"
        assert options["access_key_id"] == "AKIA_TEST"
        assert options["root"] == "/bqckup/example.com/incremental"


class TestIncrementalBackupProviderGating:
    def _bqckup(self):
        from classes.bqckup import Bqckup

        # Bypass the heavy __init__ (storage connection checks / sys.exit).
        return Bqckup.__new__(Bqckup)

    def test_unsupported_provider_raises(self):
        bq = self._bqckup()
        cfg = make_site_config(provider="ftp")

        with pytest.raises(Exception, match="does not support provider 'ftp'"):
            bq.incremental_backup(cfg)

    def test_local_provider_does_not_query_storage(self, tmp_path):
        bq = self._bqckup()
        cfg = make_site_config(provider="local", save_locally_path=str(tmp_path / "b"))

        rustic_result = {
            "id": "abc123",
            "new": 1,
            "changed": 0,
            "unchanged": 5,
            "total_duration": 2,
            "uploaded": 10,
            "total_size": 100,
        }

        with patch("classes.bqckup.ProgressSpinner"), \
             patch("classes.bqckup.Storage") as mock_storage, \
             patch("classes.bqckup.Rustic") as MockRustic:
            inst = MockRustic.return_value
            inst.backup.return_value = rustic_result

            result = bq.incremental_backup(cfg)

        # The local provider must never look up S3 storage credentials.
        mock_storage.return_value.get_storage_detail.assert_not_called()

        # Rustic is constructed with an empty storage_config for local.
        args, _ = MockRustic.call_args
        assert args[0] is cfg
        assert args[1] == {}

        assert result["success"] is True

    def test_s3_provider_queries_storage(self, tmp_path):
        bq = self._bqckup()
        cfg = make_site_config(provider="s3")

        rustic_result = {
            "id": "abc123",
            "new": 1,
            "changed": 0,
            "unchanged": 5,
            "total_duration": 2,
            "uploaded": 10,
            "total_size": 100,
        }

        with patch("classes.bqckup.ProgressSpinner"), \
             patch("classes.bqckup.Storage") as mock_storage, \
             patch("classes.bqckup.Rustic") as MockRustic, \
             patch.object(bq, "_clean_old_backups") as mock_clean:
            mock_storage.return_value.get_storage_detail.return_value = S3_STORAGE
            MockRustic.return_value.backup.return_value = rustic_result

            result = bq.incremental_backup(cfg)

        mock_storage.return_value.get_storage_detail.assert_called_once_with("dummy")
        # S3 archive cleanup runs only for the s3 provider.
        mock_clean.assert_called_once_with(cfg)
        assert result["success"] is True
