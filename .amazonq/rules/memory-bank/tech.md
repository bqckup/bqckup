# Bqckup — Technology Stack

## Language & Runtime
- Python 3 (no version pin in repo; tested on Ubuntu 18.04–22.04 system Python)
- Distributed as a single-file binary via PyInstaller (`make install`)

## Key Dependencies

### Backend / CLI
| Package | Purpose |
|---|---|
| `typer` | CLI framework (`bqckup.py` commands) |
| `Flask` + `Flask-Login` + `Flask-WTF` + `Flask-Cors` | Web GUI |
| `gunicorn` | Production WSGI server for Flask |
| `peewee` | Lightweight ORM over SQLite3 |
| `boto3==1.35.99` | AWS S3 / S3-compatible storage client |
| `PyYAML` + `ruamel.yaml` | YAML config parsing (sites, storages) |
| `configparser` / `python-decouple` | INI config (`bqckup.cnf`) |
| `rich` | Coloured CLI output and progress spinners |
| `rq` + `redis` | Async job queue for background backup tasks |
| `mysql-connector-python==8.0.21` | MySQL/MariaDB connectivity |
| `psycopg2-binary` | PostgreSQL connectivity |
| `requests` | HTTP client (webhooks, master dashboard) |
| `humanfriendly` + `hurry.filesize` | Human-readable size formatting |
| `emails` | Email sending helper |
| `packaging` | Version comparison utilities |
| `wget` | File download helper |

### Testing
| Package | Purpose |
|---|---|
| `pytest>=7.0.0` | Test runner |
| `pytest-mock>=3.10.0` | `mocker` fixture / `unittest.mock` integration |
| `pytest-cov>=4.0.0` | Coverage reporting (min 70% enforced) |
| `moto>=4.2.0` | AWS service mocking (S3) |
| `pytest-flask>=1.2.0` | Flask test client fixtures |

## External System Dependencies (runtime)
- `mysqldump` / `mysqlcheck` — MySQL/MariaDB database export and repair
- `pg_dump` — PostgreSQL database export
- `rustic` binary — incremental file backup snapshots
- Redis — required only when using async queue (`bq_worker.py`)
- SQLite3 — operational database at `/etc/bqckup/database/bqckup.db`

## Configuration Format
- **INI** (`bqckup.cnf`) — main app config (web, auth, notifications, SMTP, webhooks)
- **YAML** (`storages.yml`, `sites/*.yml`) — storage credentials and per-site backup definitions

## Build & Development Commands

```bash
# Set up virtual environment and install all dependencies
make setup
# equivalent: python3 -m venv venv && ./venv/bin/pip3 install -r requirements.txt

# Build single-file binary with PyInstaller
make install

# Clean build artifacts
make clean

# Run all tests (unit + integration) with coverage
./run_tests.sh

# Run only unit tests
python -m pytest tests/unit/ -v

# Run only integration tests
python -m pytest tests/integration/ -v

# Run specific test file
python -m pytest tests/unit/test_classes/test_database_repair.py -v

# Run full suite (as configured in pytest.ini)
python -m pytest tests/unit tests/integration -q

# Start web GUI (development)
python app.py

# Run backup (CLI)
bqckup run

# Run backup for a specific site
bqckup run --site domain --force
```

## CI/CD
- GitHub Actions workflows in `.github/workflows/`
  - `test.yml` — runs pytest suite on push/PR
  - `build.yml` — builds distribution packages

## Installation (production)
```bash
curl https://raw.githubusercontent.com/bqckup/bqckup/1x/install.sh | bash
```
Installs to `/etc/bqckup/`, registers `bqckup` on `$PATH`.

## Cron Scheduling (recommended)
```cron
# /etc/cron.d/bqckup
*/5 * * * * root /usr/bin/bqckup run
```

## Coverage Requirements
- Minimum 70% overall coverage enforced by `pytest.ini` (`--cov-fail-under=70`)
- HTML report generated at `htmlcov/index.html`
