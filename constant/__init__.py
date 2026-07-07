from os import getenv, path
from pathlib import Path

# Bqckup Path
BQ_PATH = "/etc/bqckup"

# Bqckup Storage Config Path
STORAGE_CONFIG_PATH = path.join(BQ_PATH, "config", "storages.yml")

# Bqckup Site Config Path
SITE_CONFIG_PATH = path.join(BQ_PATH, "sites")

# Bqckup Config Path
CONFIG_PATH = path.join(BQ_PATH, "bqckup.cnf")

RUSTIC_CONFIG_PATH = "/etc/rustic"

# Bqckup Information
VERSION = "1.11.1"

# YOURLS Credentials
YOURLS_HOST = ""

YOURLS_SECRET_KEY = ""

# max retries for backup operations
MAX_RETRIES = 3

# retry backoff; in seconds
BACKOFF = 30

DB_REPAIR_POLL_INTERVAL = 30

DB_REPAIR_BASE_WARNING_THRESHOLD = 900  # 15 minutes

DB_REPAIR_SECONDS_PER_100MB = 900  # 15 minutes per 100 MB


LOG_DIR = Path(getenv("BQCKUP_LOG_DIR", "/var/log/bqckup"))

DEFAULT_HEADER = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": f"bqckup/{VERSION}",
}
