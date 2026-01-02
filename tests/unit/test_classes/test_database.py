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
    
    def test_init_case_insensitive(self):
        db = Database("MYSQL")
        assert db.type == "mysql"
    
    def test_supported_databases(self):
        assert "mysql" in Database.SUPPORTED_DATABASE
        assert "postgresql" in Database.SUPPORTED_DATABASE
        assert "sqlite" in Database.SUPPORTED_DATABASE
    
    @patch('gzip.open')
    @patch('subprocess.Popen')
    def test_export_success(self, mock_popen, mock_gzip_open):
        db = Database("mysql")

        mock_file = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_file

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout.read.side_effect = [b'test data', b'']
        mock_popen.return_value = mock_process
        
        db.export("/tmp/backup.sql.gz", "testuser", "testpass", "testdb", "localhost")
        
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
        assert kwargs['stdout'] == subprocess.PIPE
        assert 'stderr' in kwargs
        assert hasattr(kwargs['stderr'], 'fileno')

        mock_process.stdout.read.assert_called()
        mock_file.write.assert_called_once_with(b'test data')
        mock_process.wait.assert_called_once()
    
    @patch('mysql.connector.connect')
    def test_connection_success(self, mock_connect):
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        db = Database("mysql")
        credentials = {
            'user': 'testuser',
            'host': 'localhost',
            'password': 'testpass',
            'port': 3306,
            'name': 'testdb'
        }
        
        db.test_connection(credentials)
        
        mock_connect.assert_called_once_with(
            user='testuser',
            host='localhost',
            port=3306,
            password='testpass',
            database='testdb'
        )
        mock_connection.close.assert_called_once()
    
    @patch('mysql.connector.connect')
    def test_connection_failure(self, mock_connect):
        import mysql.connector
        mock_connect.side_effect = mysql.connector.Error("Connection failed")
        
        db = Database("mysql")
        credentials = {
            'user': 'testuser',
            'host': 'localhost',
            'port': 3306,
            'password': 'testpass',
            'name': 'testdb'
        }
        
        with pytest.raises(DatabaseException, match="Failed to connect database"):
            db.test_connection(credentials)
