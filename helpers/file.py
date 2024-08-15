import os
import shutil
import errno
import logging
from os import path
from pathlib import Path
from datetime import date, datetime
from helpers.cli import executeCommand
from helpers.timedate import numberOfDays

def initialization():
    return not os.path.exists(getAppPath() + '/.nv')

def remove_folder(path):
    if os.path.exists(path):
        shutil.rmtree(path)

def read_file_content(file_path):
    if not path.exists(file_path):
        raise Exception(f"Failed to read file, {file_path} is doesn't exists")
    return Path(file_path).read_text()

def splitNewLine(string):
    return string.splitlines()

# get default path app
def getAppPath():
    return path.abspath(path.join(path.dirname(__file__), ".."))

# filePath = target path
# example  usage:
# zip('/root/nugroho/s3_old/','/root/nugroho/PGBackup/tmp/', '1.zip')
def zip(target, filePath, fileName):
    fullPath = filePath + fileName
    if path.exists(fullPath):
        try:
            os.remove(fullPath)
        except OSError as e:
            if e.error != errno.ENOENT:
                raise Exception("Zipping error caus e %e" % str(e))

    q = "cd {} && /usr/bin/zip -r {} .".format(target, fullPath)

    logging.info("Running command %s" % q)
    logging.info("Zipping {} as {}\n".format(target, fullPath))

    a, e = executeCommand(q)
    
    logging.info(a)
    logging.error(e)

    return fullPath

def getOlderFiles(path, fromDays):
    now = date.today().strftime("%Y-%m-%d")

    fileCount = sum(len(files) for _, _, files in os.walk(path))

    oldFiles = {}

    if fileCount >= 1:
        for f in os.listdir(path):
            f = path.join(path, f)

            lastModifiedTime = os.stat(f).st_mtime
            readableModifiedTime = datetime.fromtimestamp(lastModifiedTime)
            readableModifiedTime = readableModifiedTime.strftime("%Y-%m-%d | %H:%M:%S")
            d, _ = readableModifiedTime.split("|")
            nOfDays = numberOfDays(now, d)

            if nOfDays >= fromDays:
                oldFiles[f] = {
                    "last_modified": readableModifiedTime,
                }

    return oldFiles

def deletePastFiles(path, fromDays):
    files = getOlderFiles(path, fromDays)

    if bool(files) == False:
        print("Nothing to delete\n")
        return

    for f in files:
        os.remove(f)

    return

def folderOfFile(filePath):
    arr = [x for x in filePath.split("/") if x]
    arr.pop(len(arr) - 1)
    return "/" + "/".join(arr)

"""
Permission
0o777, 0o775
"""
def changePermission(filePath, permission):
    if not os.path.exists(filePath):
        print(f"File {filePath} doesnt exists")
    else:
        try:
            os.chmod(filePath, permission)
        except Exception as e:
            print(f"Eror caught {e}")

def isAllowed(fullPath):
    pa = [p for p in fullPath.split("/") if p]
    if len(pa) <= 2:
        if pa[0] == "home":
            return False
    return True

def getOwnerGroup(location):
    from pathlib import Path

    try:
        path = Path(location)
        owner = path.owner()
        group = path.group()
    except Exception as e:
        print(f"Error caught {e}")
        return False

    else:
        return owner, group

def defaultOwnerGroup(file):
    cwd = file if os.path.isdir(file) else folderOfFile(file)
    o, g = getOwnerGroup(cwd)
    changeOwnerGroup(file, o, g)

def changeOwnerGroup(filePath, owner, group):
    if not os.path.exists(filePath):
        print(f"File {filePath} doesnt exists")
    else:
        try:
            import pwd, grp

            uid = pwd.getpwnam(owner).pw_uid
            gid = grp.getgrnam(group).gr_gid
            os.chown(filePath, uid, gid)
        except Exception as e:
            print(f"Eror caught {e}")

def readLastNLines(fname, N):
    assert N >= 0
    pos = N + 1
    lines = []
    with open(fname) as f:
        while len(lines) <= N:
            try:
                f.seek(-pos, 2)
            except IOError:
                f.seek(0)
                break
            finally:
                lines = ["<br />".join(ff.split("\n")) for ff in list(f) if ff]
            pos *= 2
    return lines[-N:]
