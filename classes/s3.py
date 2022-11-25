import os, sys, boto3
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import *
from helpers import getInt
from hurry.filesize import size, alternative
from boto3.s3.transfer import TransferConfig
from classes.progresspercentage import ProgressPercentage
from classes.storage import Storage

class s3(object):
    def __init__(self, storage_name: str):
        self.storage = Storage().get_storage_detail(storage_name)
        self.root_folder_name = 'bqckup'
        self.clientInit()
        self.bucket_name = self.storage['bucket']

    def clientInit(self):
        session = boto3.session.Session()
        try:
            self.client = session.client(
                "s3",
                region_name=self.storage['region'],
                endpoint_url=self.storage['endpoint'],
                aws_access_key_id=self.storage['access_key_id'],
                aws_secret_access_key=self.storage['secret_access_key'],
            )
        except Exception as e:
            print(f"Failed to connect because : {e}") 
            self.client = False

    def isAuthorized(self):
        return True if self.client else False

    def cloudStorageFull(self) -> bool:
        # TODO: with config
        limit = 20
        current = self.getCloudDiskUsage()

        if getInt(current["free"]) <= int(limit):
            return True
        return False
        #     # TODO: with config ( send mail)
        #     sendMail = False
        #     if sendMail:
        #         from models import User
        #         from core.mail import Mail

        #         user = User().get()
        #         if user.email:
        #             data = {
        #                 "target": user.email,
        #                 "subject": "Server disk full !",
        #                 "message": f"Your server disk is {current['free']} left",
        #             }

        #         Mail(data).send()

    def getCloudDiskUsage(self, prefix=""):
        files = self.list(prefix)

        if not len(files):
            return {"used": 0, "free": 250}

        sizeFile = 0
        for f in files:
            sizeFile += f["Size"]

        used = size(sizeFile, system=alternative)

        # 250 GB Max S3 Size, More than that will get charge
        used = f"{round((getInt(used) / 1024), 2)} GB" if "MB" in used else used

        # TODO: Fix this ( 250 GB )
        free = 250 - getInt(used)

        # in GB
        usage = {"used": used, "free": "%s GB" % free}


        return usage

    # prefix for filtering
    def list(self, prefix=""):
        try:
            files = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)[
                "Contents"
            ]
        except KeyError:
            return []  # empty array
        else:
            return files

    """
        No directoris/folders in s3
        format name : token_site.com_date.zip
    """
    def upload(self, pathFile, newFileName):
        newFileName = os.path.join(self.root_folder_name, newFileName)
        config = TransferConfig(
            multipart_threshold=1024 * 25,
            max_concurrency=10,
            multipart_chunksize=1024 * 25,
            use_threads=True,
        )
        try:
            self.client.upload_file(
                pathFile,
                self.bucket_name,
                newFileName,
                Config=config,
                Callback=ProgressPercentage(pathFile),
            )
        except Exception as errorMsg:
            print(
                "File: {} , Upload error, reason: {}\n".format(pathFile, errorMsg)
            )
            raise Exception("Msg : {}\n".format(errorMsg))

    # fileName = Key
    def delete(self, fileName):
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=fileName)
        except Exception as errorMsg:
            print(
                "File: {} Delete failed, reason: {}\n".format(fileName, errorMsg)
            )
            raise Exception("Msg : {}\n".format(errorMsg))

    def getLinkDownload(self, fileName=False):
        try:
            link = self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": fileName,
                    "ResponseContentDisposition": f"attachment; filename = {fileName}",
                },
                ExpiresIn=86400,# One Day
            )
        except Exception as e:
            print("Get link download failed, reason {}".format(e))
            link = False
            raise Exception("Msg : %s\n " % e)
        else:
            return link

    # fileName = siteName
    def deleteOldFiles(self, fileName, days=3):
        files = self.list(prefix=fileName)
        getLastModified = lambda obj: int(obj['LastModified'].strftime('%s'))
        fileSorted = [obj['Key'] for obj in sorted(files, key=getLastModified)]
        if fileSorted:
            for f in fileSorted[:2]:
                self.delete(f)
        