import pytest
import time
from unittest.mock import patch, MagicMock
from peewee import SqliteDatabase
from models.log import Log

class TestLog:
    
    @pytest.fixture
    def test_db(self):
        test_db = SqliteDatabase(':memory:')
        with patch('models.database', test_db):
            test_db.bind([Log])
            test_db.create_tables([Log])
            yield test_db
            test_db.drop_tables([Log])
    
    def test_log_constants(self):
        assert Log.__SUCCESS__ == 1
        assert Log.__FAILED__ == 2
        assert Log.__ON_PROGRESS__ == 3
        assert Log.__DATABASE__ == 'database'
        assert Log.__FILES__ == 'files'
    
    def test_log_creation(self, test_db):
        log_data = {
            'name': 'test_backup',
            'file_path': '/tmp/test.sql',
            'description': 'Test backup',
            'type': Log.__DATABASE__,
            'storage': 'test_storage'
        }
        
        log = Log().write(log_data)
        
        assert log.name == 'test_backup'
        assert log.file_path == '/tmp/test.sql'
        assert log.description == 'Test backup'
        assert log.type == Log.__DATABASE__
        assert log.storage == 'test_storage'
        assert log.status == Log.__ON_PROGRESS__
        assert log.file_size == 0
        assert log.time_consume == 0
        assert isinstance(log.created_at, int)
    
    def test_update_status(self, test_db):
        log_data = {
            'name': 'test_backup',
            'file_path': '/tmp/test.sql',
            'description': 'Test backup',
            'type': Log.__DATABASE__,
            'storage': 'test_storage'
        }
        
        log = Log().write(log_data)
        
        with patch.object(Log, 'set_by_id') as mock_set:
            log.update_status(log.id, Log.__SUCCESS__, 'Backup completed', 5.5)
            
            mock_set.assert_any_call(log.id, {'status': Log.__SUCCESS__, 'time_consume': 5.5})
            mock_set.assert_any_call(log.id, {'description': 'Backup completed'})
    
    def test_update_status_without_description(self, test_db):
        log_data = {
            'name': 'test_backup',
            'file_path': '/tmp/test.sql',
            'description': 'Test backup',
            'type': Log.__DATABASE__,
            'storage': 'test_storage'
        }
        
        log = Log().write(log_data)
        
        with patch.object(Log, 'set_by_id') as mock_set:
            log.update_status(log.id, Log.__FAILED__)
            
            mock_set.assert_called_once_with(log.id, {'status': Log.__FAILED__, 'time_consume': 0})
