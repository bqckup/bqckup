import os
BQ_PATH="/etc/bqckup"
STORAGE_CONFIG_PATH=os.path.join(BQ_PATH, 'config', 'storages.yml')
SITE_CONFIG_PATH=os.path.join(BQ_PATH, 'sites')
CONFIG_PATH=os.path.join(BQ_PATH, 'bqckup.cnf')
VERSION="1.0.0"