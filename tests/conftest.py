import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from moto import mock_aws
import boto3
from peewee import SqliteDatabase

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def mock_database():
    test_db = SqliteDatabase(':memory:')
    with patch('models.database', test_db):
        yield test_db

@pytest.fixture
def mock_s3_client():
    with mock_aws():
        yield boto3.client('s3', region_name='us-east-1')

@pytest.fixture
def sample_config():
    return {
        'storage': {
            'test_storage': {
                'access_key_id': 'test_key',
                'secret_access_key': 'test_secret',
                'bucket': 'test-bucket',
                'region': 'us-east-1',
                'endpoint': 'https://s3.amazonaws.com'
            }
        }
    }
