import pytest
from unittest.mock import patch, mock_open
from helpers.utility import get_os_version, clearDomain, isNone, getInt, bytes_to

class TestUtility:
    
    @patch('os.path.isfile')
    @patch('builtins.open', new_callable=mock_open)
    def test_get_os_version_ubuntu(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        mock_file.return_value.read.return_value = 'DISTRIB_DESCRIPTION="Ubuntu 20.04.3 LTS"\nOTHER_LINE=value'
        
        result = get_os_version()
        assert result == "20.04.3"
    
    @patch('os.path.isfile')
    def test_get_os_version_no_file(self, mock_isfile):
        mock_isfile.return_value = False
        
        result = get_os_version()
        assert result == ""
    
    def test_clear_domain_with_https(self):
        result = clearDomain("https://www.example.com/path/")
        assert result == "example.com/path"
    
    def test_clear_domain_with_http(self):
        result = clearDomain("http://example.com")
        assert result == "example.com"
    
    def test_clear_domain_without_protocol(self):
        result = clearDomain("example.com/path")
        assert result == "example.com/path"
    
    def test_clear_domain_with_trailing_slash(self):
        result = clearDomain("example.com/")
        assert result == "example.com"
    
    def test_is_none_with_none(self):
        result = isNone(None)
        assert result == "-"
    
    def test_is_none_with_empty_string(self):
        result = isNone("")
        assert result == "-"
    
    def test_is_none_with_value(self):
        result = isNone("test")
        assert result == "test"
    
    def test_is_none_with_zero(self):
        result = isNone(0)
        assert result == "-"
    
    def test_get_int_with_integer(self):
        result = getInt(42)
        assert result == 42
    
    def test_get_int_with_string_number(self):
        result = getInt("123")
        assert result == 123
    
    def test_get_int_with_mixed_string(self):
        result = getInt("abc123def456")
        assert result == 123
    
    def test_get_int_with_empty_string(self):
        result = getInt("")
        assert result == 0
    
    def test_get_int_with_none(self):
        result = getInt(None)
        assert result == 0
    
    def test_bytes_to_megabytes(self):
        # 1024 bytes = 1 KB, 1024 KB = 1 MB
        result = bytes_to('m', 1024 * 1024)  # 1 MB in bytes
        assert result == 1.0
    
    def test_bytes_to_kilobytes(self):
        result = bytes_to('k', 1024)  # 1 KB in bytes
        assert result == 1.0
    
    def test_bytes_to_gigabytes(self):
        result = bytes_to('g', 1024 * 1024 * 1024)  # 1 GB in bytes
        assert result == 1.0
