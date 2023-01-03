import os, sys, boto3
from helpers import getInt
from boto3.s3.transfer import TransferConfig
from botocore.config import Config
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
                config=Config(
                    retries = dict(
                        max_attempts = 5
                    )
                )
            )
        except Exception as e:
            print(f"Failed to connect because : {e}") 
            self.client = False

    def isAuthorized(self):
        return True if self.client else False

    def get_total_used(self, prefix=""):
        files = self.list(prefix)

        if not len(files):
            return 0


        return sum([int(f["Size"]) for f in files.get('Contents')])

    # prefix for filtering
    def list(self, prefix="", Delimiter=""):
        try:
            files = self.client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, Delimiter=Delimiter)
        except KeyError:
            return []  # empty array
        else:
            return files

    """
        No directoris/folders in s3
        format name : token_site.com_date.zip
    """
    def upload(self, pathFile, newFileName, showProgress=True):
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
                Callback=ProgressPercentage(pathFile) if showProgress else None,
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