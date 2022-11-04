"""

    Terminate apps using rest api on master server:
        ada nya fungsi pengecekan status aktif atau tidak ke main server (nyalakan terlebih dahulu setiap jam 12 malam)
        jika statusnya sudah tidak aktif maka tidak dapat menggunakan layanan
    
    will need this later (this doesnt work in rclone latest version)
    You'll need to use this (note the parameters are key value pairs from the config file).
    `rclone config create gdrive drive scope drive config_is_local false`
    Ref : https://github.com/rclone/rclone/issues/1010

    Compressing:
    - http://catchchallenger.first-world.info/wiki/Quick_Benchmark:_Gzip_vs_Bzip2_vs_LZMA_vs_XZ_vs_LZ4_vs_LZO
    - https://unix.stackexchange.com/questions/108100/why-are-tar-archive-formats-switching-to-xz-compression-to-replace-bzip2-and-wha/108103#108103
    - https://unix.stackexchange.com/questions/322746/7zip-xz-gzip-tar-etc-what-are-the-differences
"""
import sys, logging, os, logging, requests, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from core.mail import Mail
from decouple import config
from classes.s3 import s3
from models import Backup, BackupLog, BackupQueue, Configuration, User
from core.database import Database
from helpers import (
    addDays,
    executeCommand,
    getDateFromUnix,
    generate_token,
    toDateObject,
    zip,
    getAppPath,
    numberOfDays,
    firstDateNextMonth,
    getInt,
    toUnix,
)


class OJTBackup:
    def __init__(self):
        self._provider = False
        self._checkUrl = "https://panel.ini-sudah.online/api/v1/ojtbackup/validate"
        self.linkCheckUpdate = "https://openjournaltheme.com/utilities/ojtBackup/check_update.php"
        self._setProvider()

        self.tmp = getAppPath() + "/tmp/"


    def isAuthorized(self):
        return self._provider.isAuthorized()
    
    def dailyCheck(self):
        pass
        isActive = self.getStatus()
        # .nv = not validated
        creditFile = getAppPath() + "/.nv"
        if not isActive and not os.path.exists(creditFile):
            os.system("touch %s" % creditFile)

    def getStatus(self):
        import json

        ip_address, e = executeCommand("curl ifconfig.me")
        payload = {"ip_address": ip_address}
        response = requests.post(self._checkUrl, data=payload)
        response = json.loads(response.text)
        try:
            isActive = response["data"]["active"]
        except:
            return False
        else:
            return isActive

    def _setProvider(self):
        self._provider = s3()

    def getCloudDiskUsage(self):
        return self._provider.getCloudDiskUsage()

    def cloudStorageFull(self):
        limit = Configuration().generalConfig("cloud_storage_limit", "20")
        current = self.getCloudDiskUsage()

        if getInt(current["free"]) <= int(limit):
            sendMail = Configuration().generalConfig("disk_full_notification")
            if sendMail:
                from models import User
                from core.mail import Mail

                user = User().get()
                if user.email:
                    data = {
                        "target": user.email,
                        "subject": "Server disk full !",
                        "message": f"Your server disk is {current['free']} left",
                    }

                Mail(data).send()
            return True

        return False

    def getServerDiskUsage(self):
        import shutil
        from hurry.filesize import size, alternative

        total, used, free = shutil.disk_usage("/")

        results = {
            "total": size(total, system=alternative),
            "used": size(used, system=alternative),
            "free": size(free, system=alternative),
        }

        return results

    def serverStorageFull(self) -> bool:
        limit = int(Configuration().generalConfig("server_disk_limit", "5"))

        current = self.getServerDiskUsage()

        if getInt(current["free"]) <= limit:
            return True

        return False

    # fileId for google drive
    def getLinkDownload(self, fileName=False, fileId=False):
        return self._provider.getLinkDownload(fileName=fileName, fileId=fileId)

    def checkUpdate(self):
        from random import randint

        userAgent = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.7; rv:7.0.1) Gecko/20100101 Firefox/7.0.1",
            "Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.1.9) Gecko/20100508 SeaMonkey/2.0.4",
            "Mozilla/5.0 (Windows; U; MSIE 7.0; Windows NT 6.0; en-US)",
            "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_6_7; da-dk) AppleWebKit/533.21.1 (KHTML, like Gecko) Version/5.0.5 Safari/533.21.1",
        ]
        headers = {"user-agent": userAgent[randint(0, 3)]}
        payload = {"version": config("VERSION")}
        needToUpdate = 0

        try:
            r = requests.post(self.linkCheckUpdate, data=payload, headers=headers)
            if r.status_code == 200:
                needToUpdate = r.text

                if needToUpdate:
                    logging.info("Apps need to be updated")

        except Exception as e:
            logging.error(f"error caught while checking update :  {e}")

        return int(needToUpdate)

    def getUsage(self, name):
        return self._provider.getCloudDiskUsage(name)

    def sendNotification(self, backup_id):
        backup = Backup().getById(backup_id)
        logs = BackupLog().select().where(BackupLog.backup_id == backup_id).dicts()

        if not Configuration().generalConfig("email_master"):
            logging.info("E-mail master not found")
            return

        try:
            config = (
                Configuration()
                .select(Configuration.value)
                .where(
                    (Configuration.backup_id == backup.id)
                    & (Configuration.name == "email_notification")
                )
                .get()
            )

        except:
            return True
        else:
            email = config.value
        theDate = getDateFromUnix(backup.last_backup, "%d %B %Y")
        header = """
            <body>
                <h3 style="color:#343A40;">{}</h3>
                <h3 style="color:#343A40;">Here is your backup report :</h3>
            <table border="1" style="border-collapse: collapse;width:60%;">
                <thead>
                    <tr>
                        <th style="background-color:#293B5F;color:white;border-color: #ddd;padding:.5em 1em;text-align:center;">No</th>
                        <th style="background-color:#293B5F;color:white;border-color: #ddd;padding:.5em 1em;text-align:center;">File</th>
                        <th style="background-color:#293B5F;color:white;border-color: #ddd;padding:.5em 1em;text-align:center;">Status</th>
                        <th style="background-color:#293B5F;color:white;border-color: #ddd;padding:.5em 1em;text-align:center;">Time</th>
                    </tr>
                </thead>
                <tbody>
            """.format(
            backup.backup_name
        )
        for n, log in enumerate(logs):
            n += 1
            statusLabel = """
            <div class="success" style="color:white;background: #2ecc71;border-radius:.4em;width:100%;margin:0 auto;">
                Success
            </div>
            """

            if not int(log["status"]):
                statusLabel = """
                    <div class="error" style="color:white;background: #e74c3c;border-radius:.4em;width:100%;margin:0 auto;">
                        Failed
                    </div>
                        """

            header += """
            <tr>
                <td style="border-color:#ddd;color:#343A40;padding:.5em 1em;text-align:center;">{}</td>
                <td style="border-color:#ddd;color:#343A40;padding:.5em 1em;text-align:center;">{}</td>
                <td style="border-color:#ddd;color:#343A40;padding:.5em 1em;text-align:center;">{}</td>
                <td style="border-color:#ddd;color:#343A40;padding:.5em 1em;text-align:center;">{}</td>
            </tr>
            """.format(
                n, log["path"], statusLabel, getDateFromUnix(log["created_on"])
            )

        footer = """</tbody>
                    </table>
                <div class="footer" style="border-top:1px solid #ddd;padding-top:.5em;margin-top:4em;">
                    By OJTBackup
                </div>
                </body>"""

        header += footer

        payload = {
            "target": email,
            "subject": f"{backup.backup_name} Backup Report {theDate}",
            "message": header,
        }
        try:
            Mail(payload).send()
        except Exception as e:
            logging.error("Send mail error, cause : %s" % e)
            return True

    def list(self, name):
        return self._provider.list(name)

    def doUpdate(self):
        import subprocess

        fileName = self.linkUpdate.split("/")[-1]
        r = requests.get(self.linkUpdate)
        scriptUpdate = getAppPath() + "/" + fileName
        updateStatus = True

        if r.status_code == 200:
            open(scriptUpdate, "wb").write(r.content)
        else:
            logging.error("Update failed status %s\n" % r.status_code)

        if os.path.exists(scriptUpdate):
            try:
                process = subprocess.Popen(
                    ["sh", scriptUpdate],
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )
                while True:
                    # output = process.stdout.readline()
                    return_code = process.poll()
                    if return_code is not None:
                        print(f"Return Code = {return_code}")

                        for output in process.stdout.readlines():
                            print(output.strip())
                        break

            except Exception as e:
                print(f"Error caught {e}\n")
                updateStatus = False

        return updateStatus

    def renewCron(self, cronTime=2):
        cron1 = "*/5 * * * * root /etc/OJTBackup/venv/bin/python3 /etc/OJTBackup/core/ojtbackup.py\n"
        cron2 = f"0 */{cronTime} * * * root sudo service ojtbackup stop\n"
        cron3 = "0 0 * * * root /etc/OJTBackup/venv/bin/python3 /etc/OJTBackup/core/ojtbackup.py check\n"
        cronLocation = "/etc/cron.d/ojtbackup"

        try:
            with open(cronLocation, "w+") as cron:
                cron.write(cron1 + cron2 + cron3)
        except Exception as e:
            logging.error("Write cron failed, cause : %s" % e)

    def getNextBackup(self):
        schedule = ["daily", "weekly", "monthly"]
        bTime, bId = False, False
        for s in schedule:
            backups = Backup().getBySchedule(s)
            if not backups:
                continue
            for i, b in enumerate(backups):
                lastBackup = b["last_backup"]
                timeToBackup = Configuration().getValue(
                    b["id"], "schedule_time", "01:00"
                )

                if lastBackup:
                    if s == "daily":
                        timeAfter = addDays(lastBackup, 1)

                    elif s == "weekly":
                        timeAfter = addDays(lastBackup, 7)

                    elif s == "monthly":
                        timeAfter = addDays(lastBackup, 30)
                else:
                    from datetime import datetime

                    if timeToBackup >= "00:00" and (
                        timeToBackup < time.strftime("%H:%M")
                    ):
                        timeAfter = addDays(int(time.time()), 1)
                    else:
                        timeAfter = datetime.fromtimestamp(int(time.time()))

                timeAfter = timeAfter.strftime("%Y-%m-%d")
                timeAfter += " " + timeToBackup + ":00"
                timeAfteDateObj = toDateObject(timeAfter)
                nextBackup = toUnix(timeAfteDateObj)

                if not bTime or nextBackup < bTime:
                    bTime, bId = nextBackup, b["id"]

        return bTime, bId

    # jika sudah 10 stack maka delete logs
    # TODO : Delete logs local (Some.log)
    def cleanLog(self, backupId=None):
        if backupId is None: return False
        logs = BackupLog().getLogs(backupId=backupId, limit=10)

        if int(len(logs)) >= 10:
            for log in logs:
                try:
                    backupLog = BackupLog().get_by_id(log['id'])
                    backupLog.delete_instance()
                except Exception as e:
                    logging.error(f"Error caught while deleting logs for backup_id {backupId} : {e}")


    def run(self, backupId=None, on_demand=False):
        # carefull
        if os.path.exists(getAppPath() + "/.nv"):
            logging.info("Can't use the apps")
            return

        if BackupQueue().runningBackupExists():
            logging.info("Waiting for next check, there is backup running")
            return

        from datetime import datetime

        today = datetime.today().strftime("%Y-%m-%d")

        users = User().findMany()
        

        for user in users:
            backups = (
                Backup().select().where(Backup.user_token == user["token"]).dicts()
            )

            self._setProvider()

            for backup in backups:
                if backupId:
                    if backupId != backup["id"]:
                        continue


                # Bersihkan logs
                self.cleanLog(backup['id'])

                schedule = Configuration().getValue(backup["id"], "schedule", "daily")
                keepFile = Configuration().getValue(backup["id"], "keep_files", "0")
                backupName = (
                    backup["backup_name"].replace(" ", "_") + "_" + backup["token"]
                )

                if not on_demand:
                    if backup["last_backup"]:
                        lastBackup = getDateFromUnix(backup["last_backup"])
                        print("Today = %s\nLast Backup:%s\n" % (today, lastBackup))
                        if schedule == "daily":
                            if today <= lastBackup:
                                continue

                        elif schedule == "weekly":
                            diffDays = numberOfDays(lastBackup, today)
                            if diffDays != 7:
                                continue

                        elif schedule == "monthly":
                            if today != firstDateNextMonth(lastBackup):
                                continue

                currentTime = time.strftime("%H:%M")
                backupTime = Configuration().getValue(
                    backup["id"], "schedule_time", "01:00"
                )
                if backup['last_backup'] and backupTime and not on_demand:
                    if currentTime < backupTime:
                        print(
                            "Not the time for %s to doing backup"
                            % backup["backup_name"]
                        )
                        continue

                files = self._provider.list(backupName)
                fileRetention = Configuration().getValue(
                    backup["id"], "max_file_retention", 7
                )

                if files and len(files) >= int(fileRetention):
                    self._provider.deleteOldFiles(backupName, 1)

                folderTmp = self.tmp + backupName + "/"

                if not os.path.exists(folderTmp):
                    os.makedirs(folderTmp)

                for path in backup["path"].splitlines():
                    sitePath = path.strip()

                    if not os.path.exists(sitePath):
                        logging.error("%s doesn't exists\n" % sitePath)
                        continue

                    pathName = list(filter(None, sitePath.split("/")))
                    pathName = pathName[-1]

                    zipName = "{}.zip".format(
                        backupName + "_" + pathName + "_" + today
                    )

                    # create queue
                    BackupQueue().createOne(backup["id"], folderTmp + zipName)

                    zipFile = zip(sitePath, folderTmp, zipName)
                    sizeFile = os.stat(zipFile).st_size

                    try:
                        self._provider.upload(zipFile, backupName + "/" + zipName)
                        msg = "Upload Success"
                        status = 1
                    except Exception as errorMsg:
                        logging.error("Err, Backup Database, Msg : %s" % errorMsg)
                        msg = errorMsg
                        status = 0
                    finally:
                        BackupLog().create(
                            token=generate_token(10),
                            path=zipFile,
                            backup_id=backup["id"],
                            status=status,
                            msg=msg,
                            size=sizeFile,
                            created_on=int(time.time()),
                        )

                        BackupQueue().makeItDone(backup["id"])
                        Backup().updateLastBackup(backup["id"])

                        if not int(keepFile):
                            logging.info("Removing %s\n" % zipFile)
                            os.remove(zipFile)

                    dbs = Database().backUp(backup["id"])

                    if dbs:
                        for db in dbs:
                            fileName = db.split("/")[-1]
                            sizeFile = os.stat(db).st_size
                            try:
                                # doing backup
                                self._provider.upload(db, backupName + "/" + fileName)
                                msg = "Upload Success"
                                status = 1
                            except Exception as errorMsg:
                                logging.error(
                                    "Err, Backup Database, Msg : %s" % errorMsg
                                )
                                msg = errorMsg
                                status = 0
                            else:
                                BackupQueue().makeItDone(backup["id"])
                                Backup().updateLastBackup(backup["id"])

                                if not int(keepFile):
                                    logging.info("Removing %s\n" % db)
                                    os.remove(db)

                            finally:
                                BackupLog().create(
                                    token=generate_token(10),
                                    path=db,
                                    backup_id=backup["id"],
                                    status=status,
                                    msg=msg,
                                    size=sizeFile,
                                    created_on=int(time.time()),
                                )

                    print("\nBackup Done\n")

                # self.sendNotification(backup["id"])


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "check":
            OJTBackup().dailyCheck()
    else:
        OJTBackup().run()
