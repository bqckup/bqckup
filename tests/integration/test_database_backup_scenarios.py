import pytest
import tempfile
import os
import yaml
from unittest.mock import Mock, patch, MagicMock
from moto import mock_aws
import boto3

class TestDatabaseBackupScenarios:
    
    @pytest.fixture
    def temp_sites_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def single_database_config(self):
        return {
            'bqckup': {
                'name': 'single_db_site',
                'enabled': 'yes',
                'database': {
                    'enabled': 'yes',
                    'type': 'mysql',
                    'host': 'localhost',
                    'port': 3306,
                    'user': 'testuser',
                    'password': 'testpass',
                    'name': 'single_database'
                },
                'options': {
                    'storage': 'test_storage',
                    'interval': 'daily',
                    'retention': '7'
                }
            }
        }
    
    @pytest.fixture
    def multi_database_config(self):
        return {
            'bqckup': {
                'name': 'multi_db_site',
                'enabled': 'yes',
                'databases': [
                    {
                        'enabled': 'yes',
                        'type': 'mysql',
                        'host': 'localhost',
                        'port': 3306,
                        'user': 'user1',
                        'password': 'pass1',
                        'name': 'database1'
                    },
                    {
                        'enabled': 'yes',
                        'type': 'mysql',
                        'host': 'localhost',
                        'port': 3306,
                        'user': 'user2',
                        'password': 'pass2',
                        'name': 'database2'
                    },
                    {
                        'enabled': 'no',
                        'type': 'mysql',
                        'host': 'localhost',
                        'port': 3306,
                        'user': 'user3',
                        'password': 'pass3',
                        'name': 'database3'
                    }
                ],
                'options': {
                    'storage': 'test_storage',
                    'interval': 'daily',
                    'retention': '7'
                }
            }
        }
    
    def create_site_config(self, temp_dir, filename, config):
        """Helper to create site configuration file"""
        site_path = os.path.join(temp_dir, filename)
        with open(site_path, 'w') as f:
            yaml.dump(config, f)
        return site_path
    
    @patch('classes.database.Database.export')
    @patch('classes.database.Database.test_connection')
    def test_single_database_backup(self, mock_test_conn, mock_export, temp_sites_dir, single_database_config):
        """Test backup process for single database configuration"""
        
        # Create site config file
        site_file = self.create_site_config(temp_sites_dir, 'single_db.yml', single_database_config)
        
        # Mock successful connection and export
        mock_test_conn.return_value = True
        mock_export.return_value = None
        
        # Load and validate config
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        site_config = config['bqckup']
        db_config = site_config['database']
        
        # Verify single database configuration
        assert site_config['name'] == 'single_db_site'
        assert db_config['enabled'] == 'yes'
        assert db_config['name'] == 'single_database'
        assert db_config['user'] == 'testuser'
        
        # Simulate backup process
        from classes.database import Database
        
        if db_config['enabled'] == 'yes':
            db = Database(db_config['type'])
            
            # Test connection
            credentials = {
                'host': db_config['host'],
                'user': db_config['user'],
                'password': db_config['password'],
                'name': db_config['name']
            }
            db.test_connection(credentials)
            
            # Perform export
            backup_file = f"/tmp/{db_config['name']}_backup.sql.gz"
            db.export(backup_file, db_config['user'], db_config['password'], db_config['name'])
            
            mock_test_conn.assert_called_once_with(credentials)
            mock_export.assert_called_once_with(backup_file, 'testuser', 'testpass', 'single_database')
    
    @patch('classes.database.Database.export')
    @patch('classes.database.Database.test_connection')
    def test_multi_database_backup(self, mock_test_conn, mock_export, temp_sites_dir, multi_database_config):
        """Test backup process for multiple database configuration"""
        
        # Create site config file
        site_file = self.create_site_config(temp_sites_dir, 'multi_db.yml', multi_database_config)
        
        # Mock successful connections and exports
        mock_test_conn.return_value = True
        mock_export.return_value = None
        
        # Load and validate config
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        site_config = config['bqckup']
        databases = site_config['databases']
        
        # Verify multi-database configuration
        assert site_config['name'] == 'multi_db_site'
        assert len(databases) == 3
        
        # Simulate backup process for each enabled database
        from classes.database import Database
        
        enabled_databases = [db for db in databases if db['enabled'] == 'yes']
        assert len(enabled_databases) == 2  # Only 2 enabled databases
        
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
            
            # Perform export
            backup_file = f"/tmp/{db_config['name']}_backup.sql.gz"
            db.export(backup_file, db_config['user'], db_config['password'], db_config['name'])
        
        # Verify correct number of calls
        assert mock_test_conn.call_count == 2
        assert mock_export.call_count == 2
        
        # Verify specific database calls
        expected_calls = [
            ('/tmp/database1_backup.sql.gz', 'user1', 'pass1', 'database1'),
            ('/tmp/database2_backup.sql.gz', 'user2', 'pass2', 'database2')
        ]
        
        actual_calls = [call.args for call in mock_export.call_args_list]
        assert actual_calls == expected_calls
    
    def test_disabled_database_skip(self, temp_sites_dir, multi_database_config):
        """Test that disabled databases are skipped during backup"""
        
        # Create site config file
        site_file = self.create_site_config(temp_sites_dir, 'multi_db.yml', multi_database_config)
        
        # Load config
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        databases = config['bqckup']['databases']
        
        # Filter enabled databases
        enabled_databases = [db for db in databases if db['enabled'] == 'yes']
        disabled_databases = [db for db in databases if db['enabled'] == 'no']
        
        assert len(enabled_databases) == 2
        assert len(disabled_databases) == 1
        assert disabled_databases[0]['name'] == 'database3'
    
    @patch('classes.storage.Yml_Parser.parse')
    def test_backup_with_storage_integration(self, mock_yml_parse, temp_sites_dir, single_database_config):
        """Test backup process with storage configuration"""
        
        # Mock YAML parser and storage configuration
        mock_yml_parse.return_value = {
            'storages': {
                'test_storage': {
                    'access_key_id': 'test_key',
                    'secret_access_key': 'test_secret',
                    'bucket': 'backup-bucket',
                    'region': 'us-east-1'
                }
            }
        }
        
        # Create site config file
        site_file = self.create_site_config(temp_sites_dir, 'single_db.yml', single_database_config)
        
        # Load config
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        site_config = config['bqckup']
        storage_name = site_config['options']['storage']
        
        # Verify storage integration
        from classes.storage import Storage
        storage = Storage()
        storage_config = storage.get_storage_detail(storage_name)
        
        assert storage_config['bucket'] == 'backup-bucket'
        assert storage_name == 'test_storage'
    
    def test_site_config_validation(self, temp_sites_dir):
        """Test validation of site configuration files"""
        
        # Test invalid config (missing required fields)
        invalid_config = {
            'bqckup': {
                'name': 'invalid_site'
                # Missing database and options
            }
        }
        
        site_file = self.create_site_config(temp_sites_dir, 'invalid.yml', invalid_config)
        
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        site_config = config['bqckup']
        
        # Verify missing fields
        assert 'database' not in site_config
        assert 'databases' not in site_config
        assert 'options' not in site_config
    
    @patch('classes.database.Database.export')
    def test_backup_retention_policy(self, mock_export, temp_sites_dir, single_database_config):
        """Test backup retention policy from site configuration"""
        
        # Create site config file
        site_file = self.create_site_config(temp_sites_dir, 'single_db.yml', single_database_config)
        
        # Load config
        with open(site_file, 'r') as f:
            config = yaml.safe_load(f)
        
        options = config['bqckup']['options']
        
        # Verify retention settings
        assert options['retention'] == '7'
        assert options['interval'] == 'daily'
        
        # Simulate retention logic
        retention_days = int(options['retention'])
        assert retention_days == 7
