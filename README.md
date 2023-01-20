## Background

As a programmer with multiple clients to manage, the importance of regularly backing up databases and associated assets cannot be overstated. As my client base expands, so too must the tools I use to ensure that these backups are comprehensive, reliable, and automated. I need a system that handles backups seamlessly, with minimal input from me, and only alerts me when there is an issue that requires my attention, such as a failed backup. Furthermore, I require a tool that supports a wide range of storage providers, including S3 protocol, giving me the flexibility and control I need to ensure that my backups are secure and easily accessible. 

Our motto  **"Backup and forget!"** sums up the peace of mind that an automated backup system can provide.

[**Bqckup**](https://bqckup.com) is a powerful tool that helps you to safeguard your critical data and keep it protected from any potential disasters. With Bqckup, you can enjoy the peace of mind that comes with regularly and automatically performing backups on your servers. This easy-to-use tool, written in Python and using Sqlite3 as its database, is designed to be intuitive and user-friendly. It's free, open-source and accessible to anyone.

But that's not all, Bqckup also prioritizes **your privacy**, so you don't have to worry about your sensitive information being shared or exposed. With Bqckup, you retain full control over your data and can trust that it will be kept safe and secure at all times. Keep your data safe and secure with Bqckup 🥳

Install now and forget about back up!

## Features 
- With this software, you can easily backup your database and it's associated assets to  S3 or Object Storage 
- You'll never have to worry about missing a backup failure again, thanks to our built-in email notification system.
- You can configure backups based on your specific time range, making it easy to schedule backups that work for you.
- Whether you prefer working from the command line or a web-based GUI, we've got you covered. It provides both options.
- Compatible with various Linux operating systems, so it can be used on a wide range of systems.


## Upcoming Features
- If you have multiple servers, our **unified** backup feature allows you to manage all your backups from one central location.
- Custom Timezone
- Support more storage such as Google Drive, FTP, Dropbox, etc
- Weekly report for the backup

(When our target of usage adoptation reach 500 😊)

## Preview 
image here


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
1. **Read the documentation**: Our project's documentation is a great place to start. It covers everything from setting up your development environment to contributing code. [Click here](https://docs.bqckup.com)

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
