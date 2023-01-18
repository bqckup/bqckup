## Bqkcup

Bqckup is a tool that helps you to regularly and automatically perform backups on your servers. It is a simple and easy to use tool that can be used by anyone. It is written in Python and uses Sqlite3 as a database. It is a free and open source tool.


## Installation

```shell
curl https://raw.githubusercontent.com/bqckup/bqckup/1x/install.sh | bash
```

## Usage

it is necessary to first create the necessary storage and site configurations. You can find detailed instructions on how to do this by visiting the following link:
1. [How to add Storage ?](https://docs.bqckup.com/index/storages/add-storage)
2. [How to add new Backup ?](https://docs.bqckup.com/index/backup/add-backup)

Once the storage and site configurations have been created, you can run the following command to initiate the backup process:

```shell
bqckup run
```

To automate the backup process, you can add the above command to the cron schedule.here is how i do it 

Create a file named `bqckup` in `/etc/cron.d/` and add the following code to it:

```cron
*/5 * * * * root /usr/local/bin/bqckup run
```
## Getting help & Getting involved
1. **Read the documentation**: Our project's documentation is a great place to start. It covers everything from setting up your development environment to contributing code.

2. **Report bugs**: If you've found a bug in the project, please report it on our issue tracker. Make sure to include as much information as possible, including steps to reproduce the bug and OS Information.

3. **Feature Request**: you can add your feature request or idea on our issue tracker or [Bqckup Feature Requests](https://bqckup.canny.io)

4. **Submit a pull request**: If you're interested in contributing code to the project, please submit a pull request on this GitHub repository. Make sure to follow the contributing guidelines before submitting.

5. If you have any questions or need help getting started, please reach out to me, you can contact me at <me@bqckup.com>

## Open source licensing info
1. [LICENSE](https://raw.githubusercontent.com/bqckup/bqckup/1x/LICENSE)
2. TERMS
3. Source Code Policy

## Documentation

You can [Visit Here](https://docs.bqckup.com) to view full documentation


## Tested OS

| Command      | Description |
| ------------ | ----------- |
| Ubuntu 18.04 | ✅          |
| Ubuntu 20.04 | ✅          |
| Ubuntu 22.04 | ✅          |
| Centos 7     | ✅          |
| Rocky Linux  | ✅          |