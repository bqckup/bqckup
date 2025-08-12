from os import path

# Debug Mode
DEBUG = False

# Bqckup Path
BQ_PATH = "/etc/bqckup"

# Bqckup Storage Config Path
STORAGE_CONFIG_PATH = path.join(BQ_PATH, 'config', 'storages.yml')

# Bqckup Site Config Path
SITE_CONFIG_PATH = path.join(BQ_PATH, 'sites')

# Bqckup Config Path
CONFIG_PATH = path.join(BQ_PATH, 'bqckup.cnf')

RUSTIC_CONFIG_PATH = "/etc/rustic"

# Bqckup Information
VERSION = "1.7.0"

# YOURLS Credentials
YOURLS_HOST = ""

YOURLS_SECRET_KEY = ""