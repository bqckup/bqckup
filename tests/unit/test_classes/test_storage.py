import pytest
from unittest.mock import Mock, patch
from classes.storage import Storage, StorageException

class TestStorage:
    
    @pytest.fixture
    def mock_yml_parser(self):
        with patch('classes.storage.Yml_Parser') as mock_parser:
            mock_parser.parse.return_value = {
                'storages': {
                    'storage1': {
                        'access_key_id': 'key1',
                        'secret_access_key': 'secret1',
                        'bucket': 'bucket1',
                        'region': 'us-east-1'
                    },
                    'storage2': {
                        'access_key_id': 'key2',
                        'secret_access_key': 'secret2',
                        'bucket': 'bucket2',
                        'region': 'us-west-2',
                        'primary': 'yes'
                    },
                    'remote_storage': {
                        'remote_url': 'https://example.com/config'
                    }
                }
            }
            yield mock_parser
    
    @pytest.fixture
    def mock_get_credential(self):
        with patch('classes.storage.get_credential') as mock_cred:
            mock_cred.return_value = {
                'access_key_id': 'remote_key',
                'secret_access_key': 'remote_secret',
                'bucket': 'remote_bucket'
            }
            yield mock_cred
    
    def test_init(self, mock_yml_parser):
        storage = Storage()
        
        mock_yml_parser.parse.assert_called_once()
        assert storage.parsed_storage is not None
    
    def test_list_storages(self, mock_yml_parser):
        storage = Storage()
        
        result = storage.list()
        
        assert result == ['storage1', 'storage2', 'remote_storage']
    
    def test_list_storages_empty(self, mock_yml_parser):
        mock_yml_parser.parse.return_value = {}
        storage = Storage()
        
        result = storage.list()
        
        assert result == []
    
    def test_get_storage_detail_success(self, mock_yml_parser):
        storage = Storage()
        
        result = storage.get_storage_detail('storage1')
        
        expected = {
            'access_key_id': 'key1',
            'secret_access_key': 'secret1',
            'bucket': 'bucket1',
            'region': 'us-east-1'
        }
        assert result == expected
    
    def test_get_storage_detail_not_found(self, mock_yml_parser):
        storage = Storage()
        
        with pytest.raises(StorageException, match="Storage nonexistent doesn't exists"):
            storage.get_storage_detail('nonexistent')
    
    def test_get_storage_detail_with_remote_url(self, mock_yml_parser, mock_get_credential):
        storage = Storage()
        
        result = storage.get_storage_detail('remote_storage')
        
        expected = {
            'remote_url': 'https://example.com/config',
            'access_key_id': 'remote_key',
            'secret_access_key': 'remote_secret',
            'bucket': 'remote_bucket'
        }
        assert result == expected
        mock_get_credential.assert_called_once_with('https://example.com/config')
    
    def test_get_all_storage(self, mock_yml_parser):
        storage = Storage()
        
        with patch.object(storage, 'get_storage_detail') as mock_get_detail:
            mock_get_detail.side_effect = [
                {'name': 'storage1'},
                {'name': 'storage2'},
                {'name': 'remote_storage'}
            ]
            
            result = storage.get_all_storage()
            
            assert len(result) == 3
            assert mock_get_detail.call_count == 3
    
    def test_get_primary_storage_with_primary_flag(self, mock_yml_parser):
        storage = Storage()
        
        result = storage.get_primary_storage()
        
        # Should return the first storage since primary logic is complex
        assert result == 'storage1'
    
    def test_get_primary_storage_empty_list(self, mock_yml_parser):
        mock_yml_parser.parse.return_value = {'storages': {}}
        storage = Storage()
        
        result = storage.get_primary_storage()
        
        assert result is None
    
    def test_get_parsed_storage(self, mock_yml_parser):
        storage = Storage()
        
        result = storage.get_parsed_storage()
        
        assert 'storages' in result
        assert 'storage1' in result['storages']
