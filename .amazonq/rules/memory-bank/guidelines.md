# Bqckup — Development Guidelines

## Code Quality Standards

### Python Style
- Standard library imports first, then third-party, then local — no blank lines between groups within a block
- `from rich import print` replaces the built-in `print` everywhere for coloured CLI output
- Type hints used on all public method signatures; `Optional`, `List`, `Dict`, `Any`, `Tuple` imported from `typing`
- `pathlib.Path` preferred over `os.path` string manipulation for file paths
- f-strings used exclusively for string formatting (no `.format()` or `%`)

### Naming Conventions
- Classes: `PascalCase` (`Database`, `Rustic`, `DatabaseCorruptException`)
- Methods/functions: `snake_case`; private helpers prefixed with `_` (`_get_mysql_command`, `_repair_mysql_database`)
- Constants: `UPPER_SNAKE_CASE` (`CORRUPTION_KEYWORDS`, `MAX_RETRIES`, `DATABASE_LOG`)
- CLI commands registered with `@bq_cli.command()` use `snake_case` function names that become `kebab-case` CLI commands automatically via Typer

### Docstrings
- Public methods that return non-obvious values get a one-line docstring plus a `Returns:` block
- Complex methods document their parameters inline with comments rather than full docstrings
- Example output documented in docstrings for data-transformation methods (see `get_snapshots`, `parse_snapshot` in `rustic.py`)

---

## Architectural Patterns

### Result Dict Pattern
Backup methods return a plain `dict` rather than raising exceptions to the caller. The dict always contains:
```python
result = {
    "success": bool,
    "message": str,
    "error": Exception | None,
    "traceback": str | None,
    "started_at": int,       # unix timestamp
    "ended_at": int,
    "time_consumed": float,
    "file_size": int,        # on success
}
```
Callers check `result["success"]` and inspect `result.get("corrupt")`, `result.get("repair_attempted")`, etc. for specialised failure handling.

### Exception Hierarchy
Domain-specific exceptions extend a base class for that domain:
```python
class DatabaseException(Exception): pass
class DatabaseCorruptException(DatabaseException):
    def __init__(self, message, repair_attempted=False, repair_succeeded=False): ...

class RusticError(Exception): ...
class RusticCommandError(CalledProcessError, RusticError): ...  # multiple inheritance
class RusticBackupError(RusticCommandError): ...
class RusticRestoreError(RusticCommandError): ...
```
Catch the most specific exception first, then the base class, then `Exception`.

### Subprocess Pattern
All external tool invocations follow one of two patterns:

**Streaming (for large output piped to gzip):**
```python
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, env=env)
with gzip.open(output, "wb") as gz:
    for chunk in iter(lambda: process.stdout.read(4096), b""):
        gz.write(chunk)
process.wait()
if process.returncode == 0:
    return
```

**Captured (for JSON output or short commands):**
```python
output = subprocess.run(command, capture_output=True, text=True, check=True)
# raises CalledProcessError on non-zero exit; re-raised as domain exception
```
`Rustic` stores subprocess kwargs in `self.__subprocess_args` and unpacks with `**self.__subprocess_args` to avoid repetition.

### Retry Loop with Early Exit
```python
for attempt in range(MAX_RETRIES):
    result = self.backup_database(...)
    if result["success"]:
        break
    if result.get("corrupt"):
        # no point retrying — break immediately
        break
    if attempt < MAX_RETRIES - 1:
        time.sleep(BACKOFF)
else:
    # all retries exhausted
```

### Log-Offset Detection
When detecting errors in log output that may span multiple attempts, record the file offset before each attempt and seek to it before reading:
```python
log_offset = log_file.stat().st_size if log_file.exists() else 0
# ... run subprocess writing to log_file ...
with open(log_file, "rb") as f:
    f.seek(log_offset)
    log_content = f.read().lower()
is_corrupt = _is_corruption_detected(log_content)
```

### Static Helper Extraction
Pure boolean checks extracted as `@staticmethod` for testability:
```python
@staticmethod
def _is_corruption_detected(log_content: bytes) -> bool:
    return any(keyword in log_content for keyword in CORRUPTION_KEYWORDS)

@staticmethod
def is_enabled(config: dict) -> bool: ...

@staticmethod
def is_installed() -> bool:
    return shutil.which('rustic') is not None
```

---

## CLI Patterns (Typer)

- All commands registered on a single `bq_cli = typer.Typer()` instance
- `@bq_cli.callback()` used for global flags (`--version`, `--verbose`, `--keep-rustic-secret`)
- Global flags set environment variables (`os.environ["BQCKUP_VERBOSE"] = "1"`) so downstream code can read them without passing arguments
- Environment variable helpers centralised in `helpers/utility.py`:
  ```python
  def is_debug() -> bool: return os.environ.get('BQCKUP_DEBUG', "0") == "1"
  def is_verbose() -> bool: ...
  def should_keep_rustic_secrets() -> bool: ...
  ```
- CLI output uses rich markup: `[green]...[/green]`, `[red]...[/red]`, `[yellow]...[/yellow]`, `[bold]...[/bold]`
- `ProgressSpinner` context manager wraps long-running operations:
  ```python
  with ProgressSpinner("getting backup list..."):
      objects = _s3.list(prefix=prefix)
  ```
- Validation errors exit with `raise typer.Exit(code=1)` after printing a message

---

## Configuration Patterns

### Reading Config
```python
from classes.config import Config
value = Config().read("section", "key", default="fallback")
```

### YAML Writing
Always use `ruamel.yaml` (not `PyYAML`) for writing YAML to preserve formatting:
```python
import ruamel.yaml as rYaml
yml = rYaml.YAML()
yml.indent(sequence=4, offset=2)
yml.dump(config_dict, file_handle)
```

### Site Config Structure
```yaml
bqckup:
  name: domain
  path: [/var/www/html]
  enabled: yes
  exclude_path: [.git]
  database:
    type: mysql        # mysql | postgresql | sqlite
    host: localhost
    port: 3306
    user: root
    password: root
    name: database
  databases: []        # optional list for multi-DB sites
  incremental:
    enabled: yes
    password: secret
  options:
    storage: storage_name
    interval: daily    # daily | weekly | monthly
    retention: "7"
    save_locally: no
    provider: s3       # s3 | local
```

---

## Testing Patterns

### Test File Organisation
- One test file per feature/class: `test_database.py` (basic), `test_database_repair.py` (corrupt/repair flow)
- Integration tests in `tests/integration/`, unit tests in `tests/unit/test_classes/`
- Fixtures shared via `tests/conftest.py`

### Mocking Subprocess
```python
def test_repair_succeeds(mocker):
    mock_popen = mocker.patch("classes.database.subprocess.Popen")
    mock_proc = Mock()
    mock_proc.stdout.read.side_effect = [b"dump data", b""]
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc
    # ...
```

### Shared Fixtures (conftest.py)
```python
@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def mock_s3_client():
    with mock_aws():
        yield boto3.client('s3', region_name='us-east-1')
```

### Parametrized Tests
Used for testing multiple real-world error message variants:
```python
@pytest.mark.parametrize("error_msg", [
    b"Incorrect file format 'demo'",
    b"Table 'demo' is marked as crashed",
    b"try to repair it",
])
def test_real_world_corruption_messages_are_detected(error_msg): ...
```

### Coverage Requirement
Minimum 70% overall coverage enforced in `pytest.ini` (`--cov-fail-under=70`).

---

## Frontend Patterns (jQuery / Tabler UI)

### AJAX Form Submission
All forms with class `form_ajax` or `ajax_form` are auto-wired:
```javascript
$(".form_ajax, .ajax_form").each(function() {
    $(this).on("submit", function(e) {
        e.preventDefault();
        $(this).ajaxSubmit(ajax_options);
    });
});
```
Standard `ajax_options` object: `{ error: ajaxError, success: ajaxResponse, dataType: "json", beforeSubmit: showPostLoading }`.

### Response Convention
Backend JSON responses use `error: 0` for success, `error: 1` for failure (not HTTP status codes alone):
```javascript
if (responseText.error == 0) { successNotification(msg); }
if (responseText.error == 1) { errorNotification(msg); }
```

### Notifications
```javascript
successNotification("message");   // green SweetAlert2 toast
errorNotification("message");     // red SweetAlert2 toast
swalError("message");             // modal error dialog
```

### Delete Confirmation
```javascript
// HTML: <a class="delete_confirm" href="/url" data-id="123">Delete</a>
// JS auto-wired via:
$(document).on("click", ".delete_confirm", function(e) { ... deleteConfirm(url, id, ...); });
```

---

## Security Practices

- Rustic config files written with `chmod 0o600` (owner read/write only)
- Rustic config directory created with `mode=0o700`
- Log directory created with `mode=0o700`
- `dump_config(with_credentials=False)` strips S3 credentials from the on-disk TOML after use (unless `BQCKUP_KEEP_RUSTIC_SECRETS=1`)
- PostgreSQL password passed via `PGPASSWORD` environment variable, not CLI argument
- Flask `SECRET_KEY` is hardcoded as `"secret_key"` — **must be changed in production**
- CLI requires root user (`getpass.getuser() != "root"` check at entry point)

---

## Common Idioms

```python
# Safe dict access with fallback
value = site_config.get("options", {}).get("interval", "daily")

# Walrus operator for optional single-item extraction
if database := site_config.get("database", {}):
    databases.append(database)

# Peewee ORM query
log = Log.select().where(Log.name == name).order_by(Log.id.desc()).get_or_none()

# Rich table construction
table = Table("Col1", "Col2", "Col3")
table.add_row(val1, val2, val3)
Console().print(table)

# Rich Panel
print(Panel(content, title="Title", border_style="green", expand=False, title_align="left"))

# Cleanup incomplete file on failure
if os.path.exists(output):
    os.remove(output)
```
