import pytest
import os
import yaml
from unittest.mock import Mock, patch, MagicMock

class TestSiteBackupIntegration:
    
    @pytest.fixture
    def single_db_site_config(self):
        return os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'single_database_site.yml')
    
    @pytest.fixture
    def multi_db_site_config(self):
        return os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'multi_database_site.yml')
    
    def load_site_config(self, config_path):
        """Load site configuration from YAML file"""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    @patch('classes.database.Database.export')
    @patch('classes.database.Database.test_connection')
    @patch('classes.s3.s3')
    def test_single_database_site_backup_workflow(self, mock_s3, mock_test_conn, mock_export, single_db_site_config):
        """Test complete backup workflow for single database site"""
        
        # Load site configuration
        config = self.load_site_config(single_db_site_config)
        site_config = config['bqckup']
        
        # Mock successful operations
        mock_test_conn.return_value = True
        mock_export.return_value = None
        mock_s3_instance = Mock()
        mock_s3.return_value = mock_s3_instance
        
        # Verify site configuration
        assert site_config['name'] == 'single_db_test'
        assert site_config['enabled'] is True
        assert 'database' in site_config
        assert 'databases' not in site_config
        
        # Process database backup
        db_config = site_config['database']
        if db_config['enabled'] is True:
            from classes.database import Database
            
            db = Database(db_config['type'])
            
            # Test connection
            credentials = {
                'host': db_config['host'],
                'user': db_config['user'],
                'password': db_config['password'],
                'name': db_config['name']
            }
            db.test_connection(credentials)
            
            # Create backup
            backup_file = f"/tmp/{site_config['name']}_{db_config['name']}.sql.gz"
            db.export(backup_file, db_config['user'], db_config['password'], db_config['name'], db_config['host'])
            
            # Verify calls
            mock_test_conn.assert_called_once_with(credentials)
            mock_export.assert_called_once_with(backup_file, 'single_user', 'single_pass', 'single_database', 'localhost')
    
    @patch('classes.database.Database.export')
    @patch('classes.database.Database.test_connection')
    @patch('classes.s3.s3')
    def test_multi_database_site_backup_workflow(self, mock_s3, mock_test_conn, mock_export, multi_db_site_config):
        """Test complete backup workflow for multi-database site"""
        
        # Load site configuration
        config = self.load_site_config(multi_db_site_config)
        site_config = config['bqckup']
        
        # Mock successful operations
        mock_test_conn.return_value = True
        mock_export.return_value = None
        mock_s3_instance = Mock()
        mock_s3.return_value = mock_s3_instance
        
        # Verify site configuration
        assert site_config['name'] == 'multi_db_test'
        assert site_config['enabled'] is True
        assert 'databases' in site_config
        assert 'database' not in site_config
        
        # Process multiple databases
        databases = site_config['databases']
        enabled_databases = [db for db in databases if db['enabled'] is True]
        
        assert len(databases) == 3
        assert len(enabled_databases) == 2
        
        from classes.database import Database
        
        backup_files = []
        for db_config in enabled_databases:
            db = Database(db_config['type'])
            
            # Test connection
            credentials = {
                'host': db_config['host'],
                'user': db_config['user'],
                'password': db_config['password'],
                'name': db_config['name']
            }
            db.test_connection(credentials)
            
            # Create backup
            backup_file = f"/tmp/{site_config['name']}_{db_config['name']}.sql.gz"
            backup_files.append(backup_file)
            db.export(backup_file, db_config['user'], db_config['password'], db_config['name'], db_config['host'])
        
        # Verify correct number of operations
        assert mock_test_conn.call_count == 2
        assert mock_export.call_count == 2
        assert len(backup_files) == 2
        
        # Verify specific database backups
        expected_databases = ['app_database', 'analytics_database']
        for i, call in enumerate(mock_export.call_args_list):
            args = call[0]
            assert expected_databases[i] in args[0]  # backup file path
            assert args[3] == expected_databases[i]  # database name
            assert args[4] == 'localhost'  # database host
    
    def test_site_configuration_validation(self, single_db_site_config, multi_db_site_config):
        """Test validation of site configuration structures"""
        
        # Test single database configuration
        single_config = self.load_site_config(single_db_site_config)
        single_site = single_config['bqckup']
        
        assert 'database' in single_site
        assert single_site['database']['enabled'] is True
        assert single_site['options']['retention'] == '7'
        
        # Test multi-database configuration
        multi_config = self.load_site_config(multi_db_site_config)
        multi_site = multi_config['bqckup']
        
        assert 'databases' in multi_site
        assert len(multi_site['databases']) == 3
        assert multi_site['options']['retention'] == '14'
        assert multi_site['options']['save_locally'] is True
    
    @patch('classes.storage.Yml_Parser.parse')
    def test_backup_storage_configuration(self, mock_yml_parse, single_db_site_config):
        """Test storage configuration integration with site backup"""
        
        # Mock YAML parser
        mock_yml_parse.return_value = {
            'storages': {
                'test_storage': {
                    'access_key_id': 'test_key',
                    'secret_access_key': 'test_secret',
                    'bucket': 'site-backups',
                    'region': 'us-east-1',
                    'endpoint': 'https://s3.amazonaws.com'
                }
            }
        }
        
        # Load site configuration
        config = self.load_site_config(single_db_site_config)
        site_config = config['bqckup']
        
        # Get storage configuration
        storage_name = site_config['options']['storage']
        
        from classes.storage import Storage
        storage = Storage()
        storage_config = storage.get_storage_detail(storage_name)
        
        # Verify storage integration
        assert storage_config['bucket'] == 'site-backups'
        assert storage_name == 'test_storage'
    
    def test_backup_options_processing(self, multi_db_site_config):
        """Test processing of backup options from site configuration"""
        
        config = self.load_site_config(multi_db_site_config)
        options = config['bqckup']['options']
        
        # Verify backup options
        assert options['interval'] == 'daily'
        assert options['retention'] == '14'
        assert options['save_locally'] is True
        assert options['save_locally_path'] == '/tmp/backups'
        assert options['provider'] == 's3'
        
        # Simulate retention logic
        retention_days = int(options['retention'])
        assert retention_days == 14
        
        # Simulate local save logic
        if options['save_locally'] is True:
            local_path = options['save_locally_path']
            assert local_path == '/tmp/backups'
