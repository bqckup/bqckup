import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from classes.database import Database, DatabaseException


class TestDatabase:
    def test_init_mysql(self):
        db = Database("mysql")
        assert db.type == "mysql"

    def test_init_postgresql(self):
        db = Database("postgresql")
        assert db.type == "postgresql"

    def test_init_sqlite(self):
        db = Database("sqlite")
        assert db.type == "sqlite"

    def test_init_case_insensitive(self):
        db = Database("MYSQL")
        assert db.type == "mysql"

    def test_supported_databases(self):
        assert "mysql" in Database.SUPPORTED_DATABASE
        assert "postgresql" in Database.SUPPORTED_DATABASE
        assert "sqlite" in Database.SUPPORTED_DATABASE

    # MySQL Tests
    @patch("gzip.open")
    @patch("subprocess.Popen")
    def test_export_mysql_success(self, mock_popen, mock_gzip_open):
        db = Database("mysql")

        mock_file = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.read.side_effect = [b"test data", b""]
        mock_popen.return_value = mock_process

        db.export(
            "/tmp/backup.sql.gz",
            "testuser",
            "testpass",
            "testdb",
            "localhost",
            log_dir="/tmp/bqckup",
        )

        expected_command = [
            "mysqldump",
            "--user=testuser",
            "--password=testpass",
            "--host=localhost",
            "--port=3306",
            "--no-tablespaces",
            "--skip-dump-date",
            "testdb",
        ]

        args, kwargs = mock_popen.call_args
        assert args[0] == expected_command
        assert kwargs["stdout"] == subprocess.PIPE
        assert "stderr" in kwargs

        mock_process.stdout.read.assert_called()
        mock_file.write.assert_called_once_with(b"test data")
        mock_process.wait.assert_called_once()

    @patch("mysql.connector.connect")
    def test_mysql_connection_success(self, mock_connect):
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        db = Database("mysql")
        credentials = {
            "user": "testuser",
            "host": "localhost",
            "password": "testpass",
            "port": 3306,
            "name": "testdb",
        }

        db.test_connection(credentials)

        mock_connect.assert_called_once_with(
            user="testuser",
            host="localhost",
            port=3306,
            password="testpass",
            database="testdb",
        )
        mock_connection.close.assert_called_once()

    @patch("mysql.connector.connect")
    def test_mysql_connection_failure(self, mock_connect):
        import mysql.connector

        mock_connect.side_effect = mysql.connector.Error("Connection failed")

        db = Database("mysql")
        credentials = {
            "user": "testuser",
            "host": "localhost",
            "port": 3306,
            "password": "testpass",
            "name": "testdb",
        }

        with pytest.raises(DatabaseException, match="Failed to connect database"):
            db.test_connection(credentials)

    # PostgreSQL Tests
    @patch("gzip.open")
    @patch("subprocess.Popen")
    def test_export_postgresql_success(self, mock_popen, mock_gzip_open):
        db = Database("postgresql")

        mock_file = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.read.side_effect = [b"test data", b""]
        mock_popen.return_value = mock_process

        db.export(
            "/tmp/backup.sql.gz",
            "testuser",
            "testpass",
            "testdb",
            "localhost",
            5432,
            log_dir="/tmp/bqckup",
        )

        expected_command = [
            "pg_dump",
            "-U",
            "testuser",
            "-h",
            "localhost",
            "-p",
            "5432",
            "testdb",
        ]

        args, kwargs = mock_popen.call_args
        assert args[0] == expected_command
        assert kwargs["stdout"] == subprocess.PIPE
        assert "stderr" in kwargs
        assert kwargs["env"]["PGPASSWORD"] == "testpass"

        mock_process.stdout.read.assert_called()
        mock_file.write.assert_called_once_with(b"test data")
        mock_process.wait.assert_called_once()

    @patch("gzip.open")
    @patch("subprocess.Popen")
    def test_export_postgresql_default_port(self, mock_popen, mock_gzip_open):
        db = Database("postgresql")

        mock_file = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.read.side_effect = [b"test data", b""]
        mock_popen.return_value = mock_process

        db.export("/tmp/backup.sql.gz", "testuser", "testpass", "testdb", "localhost")

        args, _ = mock_popen.call_args
        command = args[0]
        assert command[0] == "pg_dump"
        assert "-p" in command
        port_index = command.index("-p")
        assert command[port_index + 1] == "3306"

    @patch("psycopg2.connect")
    def test_postgresql_connection_success(self, mock_connect):
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        db = Database("postgresql")
        credentials = {
            "user": "pguser",
            "host": "localhost",
            "password": "pgpass",
            "port": 5432,
            "name": "pgdb",
        }

        db.test_connection(credentials)

        mock_connect.assert_called_once_with(
            user="pguser", host="localhost", port=5432, password="pgpass", dbname="pgdb"
        )
        mock_connection.close.assert_called_once()

    @patch("psycopg2.connect")
    def test_postgresql_connection_failure(self, mock_connect):
        import psycopg2

        mock_connect.side_effect = psycopg2.Error("Connection failed")

        db = Database("postgresql")
        credentials = {
            "user": "pguser",
            "host": "localhost",
            "port": 5432,
            "password": "pgpass",
            "name": "pgdb",
        }

        with pytest.raises(DatabaseException, match="Failed to connect database"):
            db.test_connection(credentials)

    # SQLite Tests
    @patch("gzip.open")
    @patch("subprocess.Popen")
    def test_export_sqlite_success(self, mock_popen, mock_gzip_open):
        db = Database("sqlite")

        mock_file = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.read.side_effect = [b"sqlite dump", b""]
        mock_popen.return_value = mock_process

        db.export(
            "/tmp/backup.sql.gz", "", "", "/path/to/db.sqlite", log_dir="/tmp/bqckup"
        )

        expected_command = ["sqlite3", "/path/to/db.sqlite", ".dump"]

        args, kwargs = mock_popen.call_args
        assert args[0] == expected_command
        assert kwargs["stdout"] == subprocess.PIPE
        assert "stderr" in kwargs

        mock_process.stdout.read.assert_called()
        mock_file.write.assert_called_once_with(b"sqlite dump")
        mock_process.wait.assert_called_once()

    @patch("sqlite3.connect")
    @patch("os.path.exists")
    def test_sqlite_connection_success(self, mock_exists, mock_connect):
        mock_exists.return_value = True
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        db = Database("sqlite")
        credentials = {"name": "/path/to/database.sqlite"}

        db.test_connection(credentials)

        mock_exists.assert_called_once_with("/path/to/database.sqlite")
        mock_connect.assert_called_once_with("/path/to/database.sqlite")
        mock_connection.close.assert_called_once()

    @patch("os.path.exists")
    def test_sqlite_connection_file_not_found(self, mock_exists):
        mock_exists.return_value = False

        db = Database("sqlite")
        credentials = {"name": "/path/to/nonexistent.sqlite"}

        with pytest.raises(DatabaseException, match="SQLite database file not found"):
            db.test_connection(credentials)

    def test_sqlite_connection_missing_path(self):
        db = Database("sqlite")
        credentials = {}

        with pytest.raises(DatabaseException, match="SQLite database path"):
            db.test_connection(credentials)

    # Unsupported database type tests
    def test_export_unsupported_type(self):
        db = Database("unsupported")

        with pytest.raises(DatabaseException, match="Unsupported database type"):
            db.export("/tmp/backup.sql.gz", "user", "pass", "db")

    def test_connection_unsupported_type(self):
        db = Database("unsupported")
        db.type = "unsupported"

        with pytest.raises(DatabaseException, match="Unsupported database type"):
            db.test_connection({})
