# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.11.0] - 2026-06-04

### Added
- **Local provider for incremental backups.** Incremental (rustic) backups can
  now be stored on the local filesystem instead of requiring S3. Set
  `options.provider: local` and `options.save_locally_path`; the repository is
  created at `<save_locally_path>/<name>/incremental`. Restore, snapshot listing,
  repository check and retention all work for local repositories.
- **Email notifications.** SMTP email can be used as a notification channel
  alongside Discord (configurable per channel, with enable/disable and SMTP
  test support).
  
### Changed
- The `local` provider now uses `options.save_locally_path` as the single backup
  location for archive, incremental and database backups (previously the archive
  path was configured via `options.destination`).
- Improved database export logging and error handling.
- Improved email embed rendering, HTML structure and color handling.
- Updated `mysql-connector-python`.

### Fixed
- `download-latest` now shows a clear message for local-provider sites (archives
  already live on disk; use `restore` for incremental backups) instead of a
  confusing storage error.

## [1.10.0] - 2026-03-17

### Fixed
- Specify the database type during export to ensure compatibility.
- Check all recent backups instead of only the latest when deciding whether to
  skip a backup.

[1.11.0]: https://github.com/bqckup/bqckup/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/bqckup/bqckup/compare/v1.9.0...v1.10.0
