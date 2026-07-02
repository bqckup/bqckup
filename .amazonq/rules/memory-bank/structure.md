# Bqckup — Project Structure

## Directory Layout

```
bqckup/
├── bqckup.py              # CLI entry point (Typer commands: run, history, restore, etc.)
├── app.py                 # Flask web GUI entry point; registers blueprints, initialises DB
├── bq_worker.py           # RQ (Redis Queue) worker for async tasks
│
├── constant/
│   └── __init__.py        # Global constants: paths, VERSION, MAX_RETRIES, BACKOFF, LOG_DIR
│
├── classes/               # Core domain logic
│   ├── bqckup.py          # Orchestrator — drives the full backup workflow per site
│   ├── database.py        # DB export (mysqldump/pg_dump/sqlite), auto-repair, exceptions
│   ├── rustic.py          # Incremental file backup via Rustic (restic fork)
│   ├── s3.py              # S3-compatible object storage upload/download/list
│   ├── storage.py         # Parses storages.yml, resolves primary storage
│   ├── config.py          # Reads/writes bqckup.cnf (INI config)
│   ├── file.py            # File utilities (create, delete, compress)
│   ├── tar.py             # TAR archive helpers
│   ├── mail.py            # Email notification sender
│   ├── auth.py            # Web GUI authentication
│   ├── server.py          # Server info (disk usage, etc.)
│   ├── progress.py        # ProgressSpinner context manager for CLI output
│   ├── queue.py           # RQ job queue helpers
│   ├── report.py          # Backup report generation
│   ├── master.py          # Multi-server master dashboard client
│   ├── yml_checker.py     # YAML config validation
│   └── yml_parser.py      # YAML config parsing helpers
│
├── models/                # Peewee ORM models (SQLite3 at /etc/bqckup/database/bqckup.db)
│   ├── __init__.py        # BaseModel + database connection
│   ├── log.py             # Log model — backup history records
│   └── notification_log.py # NotificationLog — dedup sent notifications
│
├── modules/               # Flask Blueprint route handlers
│   ├── auth.py            # /auth/* routes (login, logout, password change)
│   └── backup.py          # /backup/* routes (CRUD for sites, run, history)
│
├── helpers/               # Pure utility functions
│   ├── cli.py             # CLI output helpers (rich-based)
│   ├── datetime.py        # Date/time formatting helpers
│   ├── file.py            # File path/size helpers
│   ├── hook.py            # Webhook (after_backup_completed) dispatcher
│   ├── network.py         # Network/HTTP helpers
│   └── utility.py         # Misc utilities (bytes_to, etc.)
│
├── lib/notifications/     # Notification channel implementations
│   ├── discord.py         # Discord webhook sender
│   └── email.py           # Email notification sender
│
├── core/
│   └── mail.py            # Low-level SMTP mail core
│
├── config/
│   └── storages.yml.example   # Example storage configuration
│
├── sites/
│   └── domain.yml.example     # Example site/backup configuration
│
├── templates/             # Jinja2 HTML templates for Flask GUI
├── static/                # CSS, JS, images (Tabler UI framework)
│
└── tests/
    ├── conftest.py        # Shared pytest fixtures
    ├── fixtures/          # YAML fixture configs for tests
    ├── unit/test_classes/ # Unit tests per class
    └── integration/       # End-to-end backup workflow tests
```

## Core Components & Relationships

```
CLI (bqckup.py / Typer)
        │
        ▼
classes/bqckup.py  ←── Orchestrator (class Bqckup)
    │   │   │
    │   │   ├── classes/database.py   ← mysqldump / pg_dump / sqlite export + auto-repair
    │   │   ├── classes/rustic.py     ← incremental file snapshots
    │   │   └── classes/s3.py         ← upload to object storage
    │   │
    │   ├── models/log.py             ← write backup history to SQLite
    │   └── lib/notifications/        ← send Discord / email alerts
    │
Flask (app.py)
    ├── modules/auth.py    ← /auth/* routes
    └── modules/backup.py  ← /backup/* routes (calls classes/bqckup.py)
```

## Configuration Files (runtime, not in repo)

| Path | Purpose |
|---|---|
| `/etc/bqckup/bqckup.cnf` | Main INI config (web port, auth, notifications, SMTP) |
| `/etc/bqckup/config/storages.yml` | S3 storage credentials |
| `/etc/bqckup/sites/*.yml` | Per-site backup definitions |
| `/etc/bqckup/database/bqckup.db` | SQLite3 operational database |
| `/var/log/bqckup/` | Log files (database.log, etc.) |

## Architectural Patterns

- **Orchestrator pattern** — `classes/bqckup.py` coordinates all backup steps; individual classes handle one concern each
- **Result dict pattern** — backup methods return `dict` with `success`, `message`, `error`, `traceback`, `time_consumed` keys rather than raising exceptions to the caller
- **Retry loop with early exit** — `backup_databases()` retries up to `MAX_RETRIES` (3) times with `BACKOFF` (30s) delay, but breaks early on corrupt-table failures
- **Log-offset detection** — corruption detection reads only the log bytes written during the current attempt (tracked via file offset before each attempt)
- **Blueprint-based Flask** — web GUI split into `auth` and `backup` blueprints registered on `app.py`
- **Peewee ORM** — lightweight ORM over SQLite3 for backup logs and notification dedup
