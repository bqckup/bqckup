"""End-to-end tests for local-provider incremental backups.

Unlike the unit tests in ``tests/unit/test_classes/test_rustic.py`` (which mock
out the binary), these run the real ``rustic`` executable against a local
repository. Everything is self-contained in a generated temp directory; no S3
is involved (the local provider passes an empty/dummy storage config).

The whole module is skipped automatically when ``rustic`` is not installed.
"""

import shutil
from unittest.mock import patch

import pytest

from classes.rustic import Rustic

pytestmark = pytest.mark.skipif(
    shutil.which("rustic") is None,
    reason="requires the rustic binary to be installed",
)


def _local_site_config(name, source_dir, save_locally_path):
    """Build a local-provider site config (S3 storage stays a dummy name)."""
    return {
        "name": name,
        "enabled": True,
        "incremental": {"enabled": True, "password": "test-pass"},
        "path": [str(source_dir)],
        "exclude_path": [],
        "options": {
            "provider": "local",
            "storage": "dummy",  # ignored for local, kept as a dummy
            "interval": "daily",
            "retention": "7",
            "follow_symlink": False,
            "save_locally": False,
            "save_locally_path": str(save_locally_path),
        },
    }


@pytest.fixture
def rustic_workspace(tmp_path, monkeypatch):
    """Generate an isolated workspace and make rustic discover profiles there.

    ``dump_config`` writes ``<name>.toml`` into ``RUSTIC_CONFIG_PATH``; rustic
    discovers profiles in ``$XDG_CONFIG_HOME/rustic``. We point both at the same
    generated temp directory so the real binary can find the profile without
    touching the system-wide ``/etc/rustic``.
    """
    config_home = tmp_path / "config"
    profile_dir = config_home / "rustic"
    profile_dir.mkdir(parents=True)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    with patch("classes.rustic.RUSTIC_CONFIG_PATH", str(profile_dir)):
        yield tmp_path


def test_local_backup_creates_repository_and_snapshot(rustic_workspace):
    tmp = rustic_workspace
    source = tmp / "source"
    (source / "nested").mkdir(parents=True)
    (source / "hello.txt").write_text("hello world")
    (source / "nested" / "data.bin").write_bytes(b"\x00\x01\x02\x03" * 256)

    destination = tmp / "backups"
    cfg = _local_site_config("local-site", source, destination)

    rustic = Rustic(cfg, {}).check_and_dump()
    result = rustic.backup()
    snapshots = rustic.get_snapshots()

    # The repository is materialised on the local filesystem.
    repo = destination / "local-site" / "incremental"
    assert repo.is_dir()
    assert (repo / "config").exists()  # rustic repo config marker

    assert result["new"] >= 2  # both files counted as new
    assert result["total_size"] > 0
    assert len(snapshots) == 1
    assert snapshots[0]["paths"] == [str(source)]


def test_local_backup_restore_roundtrip(rustic_workspace):
    tmp = rustic_workspace
    source = tmp / "source"
    source.mkdir()
    (source / "hello.txt").write_text("restore me please")

    destination = tmp / "backups"
    cfg = _local_site_config("restore-site", source, destination)

    rustic = Rustic(cfg, {}).check_and_dump()
    rustic.backup()

    target = tmp / "restored"
    rustic.restore(snapshot="latest", target=str(target))

    restored_file = target / source.name / "hello.txt"
    assert restored_file.exists()
    assert restored_file.read_text() == "restore me please"


def test_local_backup_detects_changes_in_new_snapshot(rustic_workspace):
    tmp = rustic_workspace
    source = tmp / "source"
    source.mkdir()
    (source / "a.txt").write_text("one")

    destination = tmp / "backups"
    cfg = _local_site_config("incr-site", source, destination)

    rustic = Rustic(cfg, {}).check_and_dump()
    rustic.backup()
    assert len(rustic.get_snapshots()) == 1

    # Add a new file and back up again -> a second snapshot with new data.
    (source / "b.txt").write_text("two")
    second = rustic.backup()

    assert len(rustic.get_snapshots()) == 2
    assert second["new"] >= 1


def test_local_backup_skipped_when_unchanged(rustic_workspace):
    tmp = rustic_workspace
    source = tmp / "source"
    source.mkdir()
    (source / "a.txt").write_text("unchanged")

    destination = tmp / "backups"
    cfg = _local_site_config("skip-site", source, destination)

    rustic = Rustic(cfg, {}).check_and_dump()
    rustic.backup()
    assert len(rustic.get_snapshots()) == 1

    # Nothing changed: skip-identical-parent must not create a new snapshot.
    second = rustic.backup()
    assert second["new"] == 0
    assert second["changed"] == 0
    assert len(rustic.get_snapshots()) == 1
