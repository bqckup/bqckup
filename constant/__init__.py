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

# how often (in seconds) to check on an in-progress automatic database
# repair (e.g. `mysqlcheck --repair`)
DB_REPAIR_POLL_INTERVAL = 30

# minimum time (in seconds) a repair may run before it is even considered
# for a "taking too long" warning - protects small/fast databases from
# noisy alerts
DB_REPAIR_BASE_WARNING_THRESHOLD = 900  # 15 minutes

# extra seconds of grace period per 100 MB of data being repaired. "Long
# enough" is relative to size: a table with millions of rows / many GB
# legitimately needs more time than a tiny one, so the warning threshold
# scales with it instead of being a single fixed number for every database.
# e.g. 100 MB -> 15 minutes, 200 MB -> 30 minutes, 1 GB -> 2.5 hours, etc.
DB_REPAIR_SECONDS_PER_100MB = 900  # 15 minutes per 100 MB

# The repair itself is NEVER aborted because of these thresholds - large
# databases can legitimately take hours (or longer) to repair. They are only
# used to decide when to send a one-time "still running, manual check
# recommended" notification while the repair keeps running.

LOG_DIR = Path(getenv("BQCKUP_LOG_DIR", "/var/log/bqckup"))

DEFAULT_HEADER = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": f"bqckup/{VERSION}",
}
