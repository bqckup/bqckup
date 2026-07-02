# Bqckup — Product Overview

## Purpose
Bqckup is a self-hosted, automated backup tool for Linux servers. It backs up databases and associated file assets to S3-compatible object storage, then notifies the operator only when something goes wrong. Motto: **"Backup and forget!"**

## Value Proposition
- Zero vendor lock-in — fully self-hosted, data stays on infrastructure you control
- Minimal operator attention — silent on success, loud on failure
- Dual interface — CLI for cron automation + web GUI for manual management
- Privacy-first — no telemetry beyond optional anonymous statistics

## Key Features
| Feature | Detail |
|---|---|
| Database backup | MySQL/MariaDB (`mysqldump`), PostgreSQL (`pg_dump`), SQLite |
| File/asset backup | Incremental snapshots via Rustic (Rust-based restic fork) |
| Storage targets | S3-compatible object storage (AWS S3, MinIO, Cloudflare R2, etc.) |
| Scheduling | Cron-driven (`bqckup run`); configurable time ranges per site |
| Notifications | Discord webhook and/or email (SMTP) on failure |
| Web GUI | Flask-based dashboard for managing sites, storages, and viewing logs |
| Auto-repair | Detects corrupt MySQL/MariaDB tables, runs `mysqlcheck --auto-repair`, retries dump |
| Corrupt protection | Last valid backup is never overwritten when a corrupt-table failure occurs |
| Retention/cleanup | Configurable backup retention policies |
| Config backup | Optionally backs up its own configuration files |

## Target Users
- Freelance developers and agencies managing multiple client servers
- Self-hosted infrastructure operators who want automated, unattended backups
- Teams that need audit trails (backup logs, history) without a SaaS dependency

## Current Version
`1.11.1` — supports Ubuntu 18.04, 20.04, 22.04

## Upcoming Features
- Unified multi-server backup dashboard
- Custom timezone support
- Additional storage providers: Google Drive, FTP, Dropbox
- Weekly email reports
