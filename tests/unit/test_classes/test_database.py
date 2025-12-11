import pytest
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
    
    @patch('subprocess.run')
    @patch('builtins.open')
    def test_export_success(self, mock_open, mock_subprocess):
        db = Database("mysql")
        mock_devnull = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_devnull
        
        db.export("/tmp/backup.sql.gz", "testuser", "testpass", "testdb")
        
        expected_command = "mysqldump --user=testuser --password=testpass testdb --no-tablespaces  --skip-dump-date | gzip > /tmp/backup.sql.gz"
        mock_subprocess.assert_called_once_with(
            expected_command,
            shell=True,
            stdout=mock_devnull,
            stderr=mock_devnull
        )
    
    @patch('mysql.connector.connect')
    def test_connection_success(self, mock_connect):
        mock_connection = Mock()
        mock_connect.return_value = mock_connection
        
        db = Database("mysql")
        credentials = {
            'user': 'testuser',
            'host': 'localhost',
            'password': 'testpass',
            'name': 'testdb'
        }
        
        result = db.test_connection(credentials)
        
        mock_connect.assert_called_once_with(
            user='testuser',
            host='localhost',
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
            'password': 'testpass',
            'name': 'testdb'
        }
        
        with pytest.raises(DatabaseException, match="Failed to connect database"):
            db.test_connection(credentials)
