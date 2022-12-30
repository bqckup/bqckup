## How to Build
```
Build menggunakan lirbary `pyinstaller`
```shell
pyinstaller bqckup --onefile --add-data 'templates:templates' --add-data 'static:static'
```


## Server Requirements
1. Sqlite3


## Tested Server
| Command      | Description |
| ------------ | ----------- |
| Ubuntu 18.04 | ✅          |
| Ubuntu 20.04 | ✅          |
| Ubuntu 22.04 | ✅          |
| Centos 7     | ✅          |
| Rocky Linux  | ✅          |

## Command List
| Command     | Description                       |
| ----------- | --------------------------------- |
| gui-active  | Enable GUI                        |
| run         | Run Bqckup                        |
| run --force | Force Run Bqckup without schedule | 


# Docs
1. https://pyinstaller.org/en/stable/