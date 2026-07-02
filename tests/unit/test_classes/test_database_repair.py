import os
import subprocess
from unittest.mock import MagicMock

import pytest

from classes.database import Database, DatabaseCorruptException, DatabaseException


def _make_popen_side_effect(stderr_bytes: bytes, returncode: int, stdout_chunks=None):
    """Build a subprocess.Popen replacement that writes `stderr_bytes` into the
    log file handle it receives (mimicking mysqldump writing errors to stderr)
    and returns a fake process object with the given returncode.
    """

    if stdout_chunks is None:
        stdout_chunks = [b"dummy data", b""]

    def _factory(*args, **kwargs):
        log_handle = kwargs["stderr"]
        log_handle.write(stderr_bytes)
        log_handle.flush()

        mock_process = MagicMock()
        mock_process.returncode = returncode
        mock_process.stdout.read.side_effect = list(stdout_chunks)
        return mock_process

    return _factory


class TestDatabaseCorruptRepairFlow:
    """Covers bqckup#163: detect corrupt-table failures, attempt repair,
    and report clearly when repair fails without touching the last good backup.
    """

    @pytest.fixture
    def output_path(self, tmp_path):
        return str(tmp_path / "backup.sql.gz")

    @pytest.fixture
    def log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        return str(log_dir)

    def test_repair_succeeds_and_retry_backup_succeeds(
        self, output_path, log_dir, mocker
    ):
        db = Database("mysql")

        popen_side_effects = [
            _make_popen_side_effect(b"Error: Table 'foo' is marked as crashed\n", 2),
            _make_popen_side_effect(b"", 0),
        ]

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=lambda *a, **kw: popen_side_effects.pop(0)(*a, **kw),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0

        db.export(
            output_path,
            "testuser",
            "testpass",
            "testdb",
            "localhost",
            log_dir=log_dir,
        )

        assert mock_popen.call_count == 2
        mock_run.assert_called_once()
        repair_command = mock_run.call_args.args[0]
        assert repair_command[0] == "mysqlcheck"
        assert "--auto-repair" in repair_command

    def test_repair_fails_raises_corrupt_exception_without_retrying_dump(
        self, output_path, log_dir, mocker
    ):
        db = Database("mysql")

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(
                b"Error: Table 'foo' is marked as crashed\n", 2
            ),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1  # mysqlcheck itself failed

        with pytest.raises(DatabaseCorruptException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert exc_info.value.repair_attempted is True
        assert exc_info.value.repair_succeeded is False
        assert "failed" in str(exc_info.value)
        # Dump should only be attempted once: repair failing should short-circuit
        # further retries against the still-corrupt table.
        assert mock_popen.call_count == 1
        # The failed/partial output file must never linger where it could be
        # mistaken for (or overwrite) a valid backup.
        assert not os.path.exists(output_path)

    def test_repair_reports_success_but_corruption_persists(
        self, output_path, log_dir, mocker
    ):
        """Real-world case: mysqlcheck --auto-repair returns 0 (e.g. for an
        InnoDB table with a missing tablespace) but the underlying issue is
        never actually fixed, so the retried dump fails again with the same
        corruption-like error.
        """
        db = Database("mysql")

        tablespace_error = (
            b'mysqldump: Got error: 1030: "Got error 194 '
            b'\\"Tablespace is missing for a table\\" from storage engine InnoDB" '
            b"when using LOCK TABLES\n"
        )

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(tablespace_error, 2),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0  # mysqlcheck reports "success"

        with pytest.raises(DatabaseCorruptException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert exc_info.value.repair_attempted is True
        assert exc_info.value.repair_succeeded is True
        assert "still failing" in str(exc_info.value)
        # Dump retried once after the "successful" repair, then gave up.
        assert mock_popen.call_count == 2
        assert not os.path.exists(output_path)

    @pytest.mark.parametrize(
        "error_message",
        [
            b"mysqldump: Got error: 130: \"Incorrect file format 'demo'\" when using LOCK TABLES\n",
            b"mysqldump: Got error: 145: \"Table './db/demo' is marked as crashed and last (automatic?) repair failed\"\n",
            b"mysqldump: Couldn't execute 'SELECT ...': Incorrect key file for table 'demo'; try to repair it (1034)\n",
        ],
    )
    def test_real_world_corruption_messages_are_detected(
        self, output_path, log_dir, mocker, error_message
    ):
        """Regression test for bqckup#163: real MySQL/MariaDB corruption errors
        use varied wording ("Incorrect file format", "try to repair", specific
        error codes) that must still be recognized as table corruption.
        """
        db = Database("mysql")

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(error_message, 2),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0

        with pytest.raises(DatabaseCorruptException):
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        # Repair must have been attempted for all of these real-world messages.
        mock_run.assert_called_once()

    def test_corruption_on_unsupported_engine_raises_without_repair_attempt(
        self, output_path, log_dir, mocker
    ):
        db = Database("postgresql")

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(b"ERROR: relation is corrupt\n", 1),
        )
        mock_run = mocker.patch("subprocess.run")

        with pytest.raises(DatabaseCorruptException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert exc_info.value.repair_attempted is False
        mock_run.assert_not_called()
        assert mock_popen.call_count == 1

    def test_generic_failure_raises_plain_database_exception(
        self, output_path, log_dir, mocker
    ):
        db = Database("mysql")

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(b"connection refused\n", 1),
        )
        mock_run = mocker.patch("subprocess.run")

        with pytest.raises(DatabaseException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert not isinstance(exc_info.value, DatabaseCorruptException)
        mock_run.assert_not_called()
        assert mock_popen.call_count == 1
