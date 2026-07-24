import os
import subprocess
import time
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

    def test_myisam_incompatible_engine_skips_repair_attempt_outright(
        self, output_path, log_dir, mocker
    ):
        """`mysqlcheck --auto-repair` is documented to be a no-op for anything
        other than MyISAM/Aria tables - this is a certain, unambiguous case,
        so the strict upfront verdict must skip the repair attempt entirely
        instead of wasting time on it.
        """
        db = Database("mysql")

        mock_popen = mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(
                b"Error: crashed table, and it's not a MyISAM table so repair is skipped\n",
                2,
            ),
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

    def test_ambiguous_wording_still_gets_a_repair_attempt(
        self, output_path, log_dir, mocker
    ):
        """Vague/uncertain wording (that isn't a documented, certain engine
        limitation) must NOT short-circuit straight to "manual intervention
        required" - the repair should still be given a chance to succeed.
        """
        db = Database("mysql")

        popen_side_effects = [
            _make_popen_side_effect(
                b"Error: Table 'foo' is marked as crashed and cannot be repaired "
                b"using the quick method\n",
                2,
            ),
            _make_popen_side_effect(b"", 0),
        ]
        mocker.patch(
            "subprocess.Popen",
            side_effect=lambda *a, **kw: popen_side_effects.pop(0)(*a, **kw),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0

        # Should succeed: repair was attempted (and, per the mock, succeeded)
        # and the retried dump then goes through cleanly, instead of being
        # skipped based on the ambiguous "cannot be repaired" wording.
        db.export(
            output_path,
            "testuser",
            "testpass",
            "testdb",
            "localhost",
            log_dir=log_dir,
        )

        mock_run.assert_called_once()

    def test_repair_is_never_given_a_timeout(self, output_path, log_dir, mocker):
        """Large databases can legitimately take a long time to repair, so
        `mysqlcheck --repair` must never be invoked with a `timeout=` that
        could kill it mid-repair.
        """
        db = Database("mysql")

        popen_side_effects = [
            _make_popen_side_effect(b"Error: Table 'foo' is marked as crashed\n", 2),
            _make_popen_side_effect(b"", 0),
        ]
        mocker.patch(
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

        mock_run.assert_called_once()
        assert "timeout" not in mock_run.call_args.kwargs

    def test_table_name_is_extracted_from_error_message_when_available(
        self, output_path, log_dir, mocker
    ):
        db = Database("mysql")

        mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(
                b"Error: Table 'foo' is marked as crashed\n", 2
            ),
        )
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 1  # repair fails

        with pytest.raises(DatabaseCorruptException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert exc_info.value.table_name == "foo"

    def test_table_name_is_none_when_not_present_in_error_message(
        self, output_path, log_dir, mocker
    ):
        db = Database("postgresql")

        mocker.patch(
            "subprocess.Popen",
            side_effect=_make_popen_side_effect(b"ERROR: relation is corrupt\n", 1),
        )
        mocker.patch("subprocess.run")

        with pytest.raises(DatabaseCorruptException) as exc_info:
            db.export(
                output_path,
                "testuser",
                "testpass",
                "testdb",
                "localhost",
                log_dir=log_dir,
            )

        assert exc_info.value.table_name is None


class TestLongRunningRepairWarning:
    """A repair on a very large database can legitimately take a long time.
    It must never be aborted; instead, a one-time warning notification is
    sent once the repair has been running longer than the size-based
    threshold (see `_estimate_warning_threshold`), while the repair itself
    keeps running until it actually finishes.
    """

    @pytest.fixture
    def log_file(self, tmp_path):
        return tmp_path / "database.log"

    def test_fast_repair_does_not_trigger_a_warning(self, log_file, mocker):
        db = Database("mysql")

        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value.returncode = 0
        mocker.patch("classes.database.DB_REPAIR_POLL_INTERVAL", 5)
        mocker.patch.object(Database, "_estimate_warning_threshold", return_value=5)
        mock_notify = mocker.patch.object(Database, "_notify_long_running_repair")

        succeeded, started_at, duration = db._repair_mysql_database(
            "user", "pass", "testdb", "localhost", 3306, log_file
        )

        assert succeeded is True
        mock_notify.assert_not_called()

    def test_long_running_repair_warns_once_but_waits_for_completion(
        self, log_file, mocker
    ):
        def slow_repair(*args, **kwargs):
            time.sleep(0.15)
            completed = MagicMock()
            completed.returncode = 0
            return completed

        db = Database("mysql")

        mocker.patch("subprocess.run", side_effect=slow_repair)
        # Small poll interval/threshold so the test observes the "still
        # running" branch quickly instead of waiting on real production
        # values (30s / 1 hour+).
        mocker.patch("classes.database.DB_REPAIR_POLL_INTERVAL", 0.03)
        mocker.patch.object(Database, "_estimate_warning_threshold", return_value=0.05)
        mock_notify = mocker.patch.object(Database, "_notify_long_running_repair")

        succeeded, started_at, duration = db._repair_mysql_database(
            "user", "pass", "testdb", "localhost", 3306, log_file
        )

        # The repair was allowed to run to completion (not aborted) and still
        # reports its real outcome.
        assert succeeded is True
        assert duration >= 0.1
        # Exactly one warning must be sent, no matter how many poll cycles
        # observed the repair as still running.
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        assert call_args.args[0] == "testdb"
        assert call_args.args[2] == 0.05  # threshold_seconds passed through

    def test_warning_includes_partial_log_output_so_far(self, log_file, mocker):
        """If the repair tool has already written something to the log by the
        time we decide to warn (e.g. its own progress/warning output), that
        should be surfaced in the notification even though the repair hasn't
        finished/failed yet.
        """

        def slow_repair_with_partial_output(*args, **kwargs):
            log_file.write_text(
                log_file.read_text() + "mysqlcheck: still checking large_table...\n"
            )
            time.sleep(0.15)
            completed = MagicMock()
            completed.returncode = 0
            return completed

        db = Database("mysql")
        log_file.write_text("")

        mocker.patch("subprocess.run", side_effect=slow_repair_with_partial_output)
        mocker.patch("classes.database.DB_REPAIR_POLL_INTERVAL", 0.03)
        mocker.patch.object(Database, "_estimate_warning_threshold", return_value=0.05)
        mock_notify = mocker.patch.object(Database, "_notify_long_running_repair")

        db._repair_mysql_database("user", "pass", "testdb", "localhost", 3306, log_file)

        mock_notify.assert_called_once()
        log_snippet = mock_notify.call_args.args[3]
        assert log_snippet is not None
        assert "still checking large_table" in log_snippet


class TestEstimateWarningThreshold:
    """The "taking too long" threshold scales with the size of the data being
    repaired instead of being a single fixed number for every database - 1
    hour is nothing for a table with millions of rows, but excessive for a
    tiny one.
    """

    def test_falls_back_to_base_threshold_when_size_cannot_be_determined(self, mocker):
        db = Database("mysql")
        mocker.patch("mysql.connector.connect", side_effect=Exception("no connection"))

        threshold = db._estimate_warning_threshold(
            "user", "pass", "testdb", "localhost", 3306
        )

        assert threshold == 900

    def test_small_table_uses_the_base_threshold_floor(self, mocker):
        db = Database("mysql")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1024,)  # 1 KB, tiny
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mocker.patch("mysql.connector.connect", return_value=mock_conn)

        threshold = db._estimate_warning_threshold(
            "user", "pass", "testdb", "localhost", 3306
        )

        assert threshold == 900

    def test_large_table_scales_the_threshold_up(self, mocker):
        db = Database("mysql")

        ten_gb = 10 * 1024**3
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (ten_gb,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mocker.patch("mysql.connector.connect", return_value=mock_conn)

        threshold = db._estimate_warning_threshold(
            "user", "pass", "testdb", "localhost", 3306, table_name="big_table"
        )

        # 10 GiB = 10240 MB -> (10240 / 100) * 900s = 92160s, well above the
        # 15-minute floor.
        assert threshold == 92160

    @pytest.mark.parametrize(
        "size_mb, expected_minutes",
        [
            (100, 15),  # 100 MB -> 15 minutes
            (200, 30),  # 200 MB -> 30 minutes (linear: +15 min per +100 MB)
            (300, 45),
            (400, 60),
        ],
    )
    def test_threshold_scales_linearly_by_100mb_increments(
        self, mocker, size_mb, expected_minutes
    ):
        db = Database("mysql")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (size_mb * 1024**2,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mocker.patch("mysql.connector.connect", return_value=mock_conn)

        threshold = db._estimate_warning_threshold(
            "user", "pass", "testdb", "localhost", 3306, table_name="t"
        )

        assert threshold == expected_minutes * 60
