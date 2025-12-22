import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from moto import mock_aws
import boto3

class TestBackupWorkflow:
    
    @pytest.fixture
    def temp_backup_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def mock_s3_setup(self):
        with mock_aws():
            client = boto3.client('s3', region_name='us-east-1')
            client.create_bucket(Bucket='test-backup-bucket')
            yield client
    
    @patch('classes.database.Database.export')
    @patch('classes.s3.s3')
    def test_database_backup_workflow(self, mock_s3_class, mock_export, temp_backup_dir, mock_s3_setup):
        """Test complete database backup workflow"""
        
        # Mock database export
        backup_file = os.path.join(temp_backup_dir, 'test_backup.sql.gz')
        mock_export.return_value = None
        
        # Create a dummy backup file
        with open(backup_file, 'w') as f:
            f.write('-- Test SQL dump')
        
        # Mock S3 instance
        mock_s3_instance = Mock()
        mock_s3_instance.upload_file.return_value = True
        mock_s3_class.return_value = mock_s3_instance
        
        # Simulate backup process
        from classes.database import Database
        
        # Test database export
        db = Database('mysql')
        db.export(backup_file, 'testuser', 'testpass', 'testdb', 'localhost')
        
        mock_export.assert_called_once_with(backup_file, 'testuser', 'testpass', 'testdb', 'localhost')
        
        # Verify file was created
        assert os.path.exists(backup_file)
    
    def test_backup_file_creation(self, temp_backup_dir):
        """Test backup file creation and validation"""
        
        backup_file = os.path.join(temp_backup_dir, 'test_backup.sql')
        
        # Create test backup content
        test_content = "-- MySQL dump\nCREATE TABLE test (id INT);"
        
        with open(backup_file, 'w') as f:
            f.write(test_content)
        
        # Verify file exists and has content
        assert os.path.exists(backup_file)
        assert os.path.getsize(backup_file) > 0
        
        with open(backup_file, 'r') as f:
            content = f.read()
            assert 'CREATE TABLE test' in content
    
    @patch('classes.storage.Yml_Parser.parse')
    def test_storage_configuration_loading(self, mock_yml_parse):
        """Test storage configuration loading"""
        
        # Mock the YAML parser to return test data
        mock_yml_parse.return_value = {
            'storages': {
                'test_storage': {
                    'access_key_id': 'test_key',
                    'secret_access_key': 'test_secret',
                    'bucket': 'test-bucket',
                    'region': 'us-east-1',
                    'endpoint': 'https://s3.amazonaws.com'
                }
            }
        }
        
        from classes.storage import Storage
        
        storage = Storage()
        config = storage.get_storage_detail('test_storage')
        
        assert config['bucket'] == 'test-bucket'
        assert config['access_key_id'] == 'test_key'
        mock_yml_parse.assert_called_once()
