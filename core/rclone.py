import os, subprocess, sys, logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models import Configuration, User

from helpers import getAppPath, getInt

# return list code
return_code = {}
return_code[0] = "success"
return_code[1] = "Syntax or usage error"
return_code[2] = "Error not otherwise categorised"
return_code[3] = "Directory not found"
return_code[4] = "File not found"
return_code[5] = "Temporary error (one that more retries might fix) (Retry errors)"
return_code[6] = "Less serious errors (like 461 errors from dropbox) (NoRetry errors)"
return_code[
    7
] = "Fatal error (one that more retries wont fix, like account suspended) (Fatal errors)"

# default config


class Rclone(object):
    def __init__(self, user_id=False):

        if User().currentUser():
            user_id = User().currentUser().id

        self.user_id = user_id
        self.configPath = (
            getAppPath()
            + "/config/"
            + Configuration().generalConfig(
                name="google_config_name", user_id=user_id, alias="rclone.conf"
            )
        )

        self.output = False
        self.logPath = False
        self.remoteFolder = False

        self._setConfig(self.configPath)
        self._setRemoteName()

    def isAuthorized(self):
        q = f"size {self.remoteFolder}:"
        result, error = self.execute(q)
        return False if "Error" in result.decode('utf-8') or "authError" else True

    def _setLogFile(self, logName):
        logPath = getAppPath() + "/logs/"

        if not os.path.exists(logPath):
            os.makedirs(logPath)

        self.logPath = "--log-file=" + logPath + logName + ".json"

    def _setRemoteName(self):
        remoteName = Configuration().generalConfig(
            name="google_config_name", user_id=self.user_id
        )
        remoteName = remoteName[:-5] if remoteName else ''
        self.remoteFolder = f"{remoteName}:OJTBackup/"

    def _setConfig(self, configPath):
        if os.path.exists(configPath):
            self.config = "--config=" + configPath

    def getConfigPath(self):
        return self.configPath

    def getAuthUri(self):
        import hashlib

        stateCode = hashlib.sha256(os.urandom(1024)).hexdigest()
        url = "https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=202264815644.apps.googleusercontent.com&redirect_uri=urn%3Aietf%3Awg%3Aoauth%3A2.0%3Aoob&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive&state={}".format(
            stateCode
        )
        return url

    """
        Create custom config
        How:
            get_uri -> auth -> get code
            -> input code & config name -> done

        saved in /home/pg/config
    """

    def createConfig(self, configName, codeAuth):
        from helpers import executeCommand

        configName = configName.lower()
        configLocation = getAppPath() + "/config/"

        if not os.path.exists(configLocation):
            os.makedirs(configLocation)

        configPath = configLocation + configName + ".conf"

        q = "/usr/bin/yes {} | /usr/bin/rclone --config={} config create {} drive scope drive config_is_local false".format(
            codeAuth, configPath, configName
        )

        logging.error("command is %s" % q)

        try:
            executeCommand(q)
        except Exception as e:
            logging.error("Error caught, %s" % e)
            return False
        else:
            self._setConfig(configPath)
            return True

    # to execute the command
    def execute(self, q, type="check_output"):
        a = ""
        e = ""
        import tempfile
        from hashlib import md5


        q = "/usr/bin/rclone --config={} {}".format(self.configPath, q)

        logging.debug("Running this query: %s" % q)

        try:
            rx = md5(q.encode("utf-8"))
            rx = rx.hexdigest()
            # creating temp to write sucess and error output
            # /dev/shm as temp storage, much faster than /tmp
            succ_f = tempfile.SpooledTemporaryFile(
                max_size=4096,
                mode="wb+",
                suffix="_succ",
                prefix="ojtex_" + rx,
                dir="/dev/shm",
            )
            err_f = tempfile.SpooledTemporaryFile(
                max_size=4096,
                mode="wb+",
                suffix="_err",
                prefix="ojtex_" + rx,
                dir="/dev/shm",
            )

            sub = subprocess.Popen(
                q, close_fds=True, shell=True, bufsize=128, stdout=succ_f, stderr=err_f
            )
            sub.wait()
            err_f.seek(0)
            succ_f.seek(0)
            a = succ_f.read()
            e = err_f.read()
            if not err_f.closed:
                err_f.close()
            if not succ_f.closed:
                succ_f.close()
        except:
            import traceback

            return traceback.format_exc()
        try:
            if type(a) == bytes:
                a = a.decode("utf-8")
            if type(e) == bytes:
                e = e.decode("utf-8")
        except:
            pass


        if e:
            logging.error(e)

        return a, e

    def cloudStorageFull(self):
        # drive default 15
        limit = Configuration().generalConfig("cloud_storage_limit", "15")
        current = self.getCloudDiskUsage()

        if getInt(current["free"]) <= int(limit):
            # write send mail down here
            return True
        return False

    def getCloudDiskUsage(self, folder=""):
        list = self.list(folder)

        defaultSize = 15  # in GB
        summary = {"free": str(defaultSize) + " GB", "used": 0}

        if not list:
            return summary

        for file in list:
            summary["used"] += file["Size"]  # in bytes

        from hurry.filesize import size, alternative

        usedSize = size(summary["used"], system=alternative)
        usedSizeGb = getInt(usedSize) / 1024
        used = defaultSize - round(usedSizeGb)
        usedSizeGb = f"{round(usedSizeGb, 2)} GB" if "GB" not in usedSize else usedSize

        summary["used"] = usedSizeGb
        summary["free"] = f"{round(used)} GB"

        return summary

    """
        Get list folder on remote
        return as json
        param folder's name
    """

    def list(self, remoteFolderPath=""):
        q = "lsjson -R " + self.remoteFolder + remoteFolderPath
        try:
            r, e = self.execute(q)
        except Exception as e:
            return {"status": "No Datas"}
        else:
            result = []

            if "Failed to lsjson: error in ListJSON:" in e.decode("utf-8").strip() or "directory not found" in e.decode('utf-8').strip():
                self.createFolder(remoteFolderPath)
                return result

            import json

            response = r.decode("utf-8")
            response = "{}" if not response else response.strip()
            return json.loads(response)

    def emptyTrash(self):
        q = f"cleanup {self.remoteName}"
        # q = ['cleanup', self.remoteName]
        return self.execute(q)

    # min-age = 7d
    # folderName = PGBackup/<folder name>
    def deleteOldFiles(self, folderName, day=7):
        # delete
        # q = ["-q", "--min-age", "7d", "delete", self.remoteFolder + folderName]
        q = f"-q --min-age {day}d delete {self.remoteFolder}{folderName}"

        try:
            self.execute(q)
        except subprocess.CalledProcessError as e:
            logging.debug("Directory not found, msg : %s" % e)

        # delete in current too
        # check this because there is option to backup monthly
        # q = ['-q', '--min-age', '7d', 'rmdirs', '--leave-root', self.remoteFolder + folderName]
        q = f"-q --min-age 7d rmdirs --leave-root {self.remoteFolder}{folderName}"

        try:
            self.execute(q)
        except subprocess.CalledProcessError as e:
            logging.debug("Directory not found, msg : %s" % e)

    def getLinkDownload(self, fileName="", fileId=False):
        # using this instead `rclone link` (able to private.)
        if fileId:
            return f"https://drive.google.com/uc?export=download&id={fileId}"

        q = f"link {self.remoteFolder}{fileName} --expire 60"

        a, e = self.execute(q)

        if e:
            return e

        return a.decode("utf-8")

    def upload(self, source, fileName=None):
        from datetime import date, datetime

        yesterday = date.fromordinal(date.today().toordinal() - 1).strftime("%F")

        yesterday = datetime.strptime(yesterday, "%Y-%m-%d").strftime("%d-%B-%Y")

        folder, file = [f for f in fileName.split("/") if f]

        self._setLogFile(yesterday)

        # https://forum.rclone.org/t/best-procedures-for-uploading-large-files-to-google-drive/25838
        q = f"copy -u -c {self.logPath} --use-json-log --chunker-chunk-size 1024M --chunker-hash-type sha1 {source} {self.remoteFolder}{folder}"

        self.execute(q)

    def createFolder(self, folderName):
        q = f"mkdir {self.remoteFolder}{folderName}"
        self.execute(q)

    # def sync(self, source, folderName):
    #     self._setLogFile(folderName)
    #     googleFolder = self.remoteName + folderName + '/current'

    #     q = ['sync', self.logPath, '--use-json-log', source, googleFolder]
    #     returnCode = self.execute(q)

    #     if returnCode == 3:
    #         self.createFolder(folderName)
    #         # try to sync again
    #         self.execute(q)


if __name__ == "__main__":
    pass
