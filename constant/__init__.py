from os import path

# Bqckup Path
BQ_PATH="/etc/bqckup"

# Bqckup Storage Config Path
STORAGE_PATH=path.join(BQ_PATH, 'storages')

# Bqckup Site Config Path
FOLDER_PATH=path.join(BQ_PATH, 'folders')

# Sqlite Database Path
DATABASE_PATH="/var/bqckup/bqckup.db"

# Bqckup Database Config Path
SITE_CONFIG_PATH=path.join(BQ_PATH, 'databases')

# Bqckup Config Path
CONFIG_PATH=path.join(BQ_PATH, 'bqckup.cnf')

# Bqckup Information
VERSION="1.1.0"