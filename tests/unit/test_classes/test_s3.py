import pytest
from unittest.mock import Mock, patch, MagicMock
from moto import mock_aws
import boto3
from botocore.exceptions import ClientError
from classes.s3 import s3

class TestS3:
    
    @pytest.fixture
    def mock_storage_detail(self):
        return {
            'access_key_id': 'test_key',
            'secret_access_key': 'test_secret',
            'bucket': 'test-bucket',
            'region': 'us-east-1',
            'endpoint': 'https://s3.amazonaws.com'
        }
    
    @pytest.fixture
    def mock_config(self):
        with patch('classes.s3.bqckup_config') as mock_config_class:
            mock_config_instance = Mock()
            mock_config_instance.read.return_value = 'bqckup'
            mock_config_class.return_value = mock_config_instance
            yield mock_config_instance
    
    @pytest.fixture
    def mock_storage(self, mock_storage_detail):
        with patch('classes.s3.Storage') as mock_storage_class:
            mock_storage_instance = Mock()
            mock_storage_instance.get_storage_detail.return_value = mock_storage_detail
            mock_storage_class.return_value = mock_storage_instance
            yield mock_storage_instance
    
    def test_s3_init_success(self, mock_storage, mock_config):
        with mock_aws():
            s3_instance = s3('test_storage')
            
            assert s3_instance.storage['bucket'] == 'test-bucket'
            assert s3_instance.bucket_name == 'test-bucket'
            assert s3_instance.root_folder_name == 'bqckup'
            assert s3_instance.client is not False
    
    def test_s3_init_failure(self, mock_storage, mock_config):
        with patch('boto3.session.Session') as mock_session:
            mock_session.return_value.client.side_effect = Exception("Connection failed")
            
            s3_instance = s3('test_storage')
            
            assert s3_instance.client is False
    
    def test_is_authorized_true(self, mock_storage, mock_config):
        with mock_aws():
            s3_instance = s3('test_storage')
            
            assert s3_instance.isAuthorized() is True
    
    def test_is_authorized_false(self, mock_storage, mock_config):
        with patch('boto3.session.Session') as mock_session:
            mock_session.return_value.client.side_effect = Exception("Connection failed")
            
            s3_instance = s3('test_storage')
            
            assert s3_instance.isAuthorized() is False
    
    def test_list_objects(self, mock_storage, mock_config):
        with mock_aws():
            # Create S3 client and bucket for testing
            client = boto3.client('s3', region_name='us-east-1')
            client.create_bucket(Bucket='test-bucket')
            
            s3_instance = s3('test_storage')
            
            # Mock the client to return test data
            mock_response = {
                'Contents': [
                    {'Key': 'file1.txt', 'Size': 100},
                    {'Key': 'file2.txt', 'Size': 200}
                ]
            }
            
            with patch.object(s3_instance.client, 'list_objects_v2', return_value=mock_response):
                result = s3_instance.list('test-prefix')
                
                assert result == mock_response
    
    def test_list_objects_empty(self, mock_storage, mock_config):
        with mock_aws():
            s3_instance = s3('test_storage')
            
            with patch.object(s3_instance.client, 'list_objects_v2', side_effect=KeyError):
                result = s3_instance.list('test-prefix')
                
                assert result == []
    
    def test_get_total_used(self, mock_storage, mock_config):
        with mock_aws():
            s3_instance = s3('test_storage')
            
            mock_files = {
                'Contents': [
                    {'Key': 'file1.txt', 'Size': 100},
                    {'Key': 'file2.txt', 'Size': 200}
                ]
            }
            
            with patch.object(s3_instance, 'list', return_value=mock_files):
                total_size = s3_instance.get_total_used('test-prefix')
                
                assert total_size == 300
    
    def test_get_total_used_empty(self, mock_storage, mock_config):
        with mock_aws():
            s3_instance = s3('test_storage')
            
            with patch.object(s3_instance, 'list', return_value=[]):
                total_size = s3_instance.get_total_used('test-prefix')
                
                assert total_size == 0
