import os, errno, datetime, logging, sys
from os import path
from datetime import date, datetime
from pathlib import Path

"""
    all format with linux
    for example ( converted date )
    date1 = 2020-01-01 23:59:00
    date2 = 2020-01-02 00:00:00
    it will count as 1 day
"""
def difference_in_days(date1: int, date2: int) -> int:
    date1 = datetime.fromtimestamp(date1)
    date2 = datetime.fromtimestamp(date2)
    day1 = date1.date().day
    day2 = date2.date().day
    return day1 - day2

# dt = unix format
def time_since(dt, default="now", reverse=False):
    dt = datetime.fromtimestamp(dt)
    now = datetime.now()
    diff = now - dt
    days = diff.days
    
    if reverse:
        days = abs(days)
        
    periods = (
        (days / 365, "year", "years"),
        (days / 30, "month", "months"),
        (days / 7, "week", "weeks"),
        (days, "day", "days"),
        (diff.seconds / 3600, "hour", "hours"),
        (diff.seconds / 60, "minute", "minutes"),
        (diff.seconds, "second", "seconds"),
    )
    
    for period, singular, plural in periods:
        if period >= 1:
            if reverse:
                return "In %d %s " % (period, singular if period == 1 else plural)
            return "%d %s ago" % (period, singular if period == 1 else plural)
    return default


"""
convert bytes to megabytes, etc.
       sample code:
           print('mb= ' + str(bytesto(314575262000000, 'm')))
       sample output: 
           mb= 300002347.946
"""
def bytes_to(to, bytes, bsize=1024):
    a = {'k' : 1, 'm': 2, 'g' : 3, 't' : 4, 'p' : 5, 'e' : 6 }
    r = float(bytes)
    
    for i in range(a[to]):
        r = r / bsize

    return round(r)

def read_file_content(file_path):
    if not path.exists(file_path):
        raise Exception(f"Failed to read file, {file_path} is doesn't exists")
    return Path(file_path).read_text()

def splitNewLine(string):
    return string.splitlines()

# get default path app
def getAppPath():
    return path.abspath(path.join(path.dirname(__file__), ".."))


def date_diff(d1, d2, returnFormat=False):
    if not isinstance(d1, datetime):
        d1 = toDateObject(d1)

    if not isinstance(d2, datetime):
        d2 = toDateObject(d2)

    if returnFormat == "unix":
        return abs((d2 - d1).seconds)

    return abs((d2 - d1).days)


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

    # os.chdir(target)

    q = "cd {} && /usr/bin/zip -r {} .".format(target, fullPath)

    logging.info("Running command %s" % q)
    logging.info("Zipping {} as {}\n".format(target, fullPath))

    a, e = executeCommand(q)
    
    logging.info(a)
    logging.error(e)

    return fullPath


def get_date_from_unix(unix, typeDate=False, format="%Y-%m-%d"):
    if unix is None:
        return False

    unix = int(unix)
    if not typeDate:
        return datetime.fromtimestamp(unix).strftime(format)
    return datetime.fromtimestamp(unix).strftime("{}".format(typeDate))


def getInt(s):
    import re

    if isinstance(s, int):
        return s

    if not s:
        return 0

    arr = re.findall(r"\d+", s)
    return int(arr[0])

def get_today(format="%Y-%m-%d"):
    return date.today().strftime(format)


def getOlderFiles(path, fromDays):
    now = date.today().strftime("%Y-%m-%d")

    fileCount = sum(len(files) for _, _, files in os.walk(path))

    oldFiles = {}

    if fileCount >= 1:
        for f in os.listdir(path):
            f = path.join(path, f)

            # in second
            lastModifiedTime = os.stat(f).st_mtime
            readableModifiedTime = datetime.fromtimestamp(lastModifiedTime)
            readableModifiedTime = readableModifiedTime.strftime("%Y-%m-%d | %H:%M:%S")
            d, _ = readableModifiedTime.split("|")
            nOfDays = numberOfDays(now, d)

            # for debug
            # print("path : {}\n last modified : {}\n diff date : {} \n\n".format(f, readableModifiedTime, nOfDays))

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


def firstDateNextMonth(date):
    y, m, d = date.split("-")
    dt = datetime(int(y), int(m), int(d))
    theDate = (dt.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    return theDate.strftime("%Y-%m-%d")


# format = YYYY-MM-DD
# date1 = latest date
# date2 = early date
def numberOfDays(date1, date2):
    yyt, mmt, ddt = date1.split("-")
    yy, mm, dd = date2.split("-")
    date1 = date(int(yyt), int(mmt), int(ddt))
    date2 = date(int(yy), int(mm), int(dd))

    diff = date1 - date2

    return diff.days


def isNone(s):
    return "-" if s is None or not s else s


# generate random string
def generate_token(length=20):
    import random, string

    # Random string with the combination of lower and upper case
    letters = string.ascii_letters
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str


# date = dateobject
def convertDate(date):
    return datetime.strptime(date, "%m/%d/%Y")


def convertDatetime(obj, format="%m/%d/%Y"):
    return obj.strftime(format)



def timesince(dt, default="now"):
    now = datetime.now()
    diff = now - dt
    periods = (
        (diff.days / 365, "year", "years"),
        (diff.days / 30, "month", "months"),
        (diff.days / 7, "week", "weeks"),
        (diff.days, "day", "days"),
        (diff.seconds / 3600, "hour", "hours"),
        (diff.seconds / 60, "minute", "minutes"),
        (diff.seconds, "second", "seconds"),
    )
    for period, singular, plural in periods:
        if period >= 1:
            return "%d %s ago" % (period, singular if period == 1 else plural)
    return default

# unix -> date obj
def toDateObject(unix):

    if isinstance(unix, str):
        return datetime.strptime(unix, "%Y-%m-%d %H:%M:%S")

    date = datetime.fromtimestamp(unix)
    return date


# datetimeobjectt -> unix (int)
def toUnix(obj):
    from time import mktime

    r = mktime(obj.timetuple())
    return int(r)


# add (n) days to a date
def addDays(date, n):
    if not isinstance(date, date):
        if isinstance(date, str) and date.isnumeric():
            date = int(date)

        if not date:
            import time

            date = int(time.time())
            date = datetime.fromtimestamp(date)

        if isinstance(date, int):
            date = datetime.fromtimestamp(date)

    return date + datetime.timedelta(n)


def today24Format(combined=False):
    now = datetime.now()
    if combined:
        return now.strftime("%m/%d/%Y, %H:%M:%S")

    data = {
        "year": now.strftime("%Y"),
        "month": now.strftime("%m"),
        "day": now.strftime("%d"),
        "hour": now.strftime("%H"),
        "minute": now.strftime("%M"),
        "second": now.strftime("%S"),
    }

    return data


# remove protocol and slash
def clearDomain(domain):
    import re

    regex = re.compile(r"https?://(www\.)?")
    return regex.sub("", domain).strip().strip("/")


# Ref : https://www.cyberciti.biz/tips/what-is-devshm-and-its-practical-usage.html
# https://superuser.com/a/45509
def executeCommand(cmdstring, shell=True):
    a = ""
    e = ""
    import subprocess, tempfile
    from hashlib import md5

    try:
        rx = md5(cmdstring.encode("utf-8"))
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
            cmdstring,
            close_fds=True,
            shell=shell,
            bufsize=128,
            stdout=succ_f,
            stderr=err_f,
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

    return a, e


def timeSince(time=False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime

    now = datetime.now()

    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    elif not time:
        diff = now - now

    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(int(second_diff / 60)) + " minutes ago"
        if second_diff < 7200:
            return "an hour ago"
        if second_diff < 86400:
            return str(int((second_diff / 3600))) + " hours ago"

    if day_diff == 1:
        return "Yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(day_diff / 7) + " weeks ago"
    if day_diff < 365:
        return str(day_diff / 30) + " months ago"

    return str(day_diff / 365) + " years ago"


# get cwd of a file
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


def isTarCorupt(file):
    if not os.path.exists(file):
        raise FileNotFoundError("File not found")

    _, err = executeCommand(f"gzip -t {file}")

    if len(err.strip()) <= 1:
        return False

    return True


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


# if  __name__ == '__main__':
#     x = readLastNLines('/etc/OJTBackup/tmp/1.log', 10)
#     print(x)


def executeCommand(cmdstring, shell=True):
    a = ""
    e = ""
    import subprocess, tempfile
    from hashlib import md5

    try:
        rx = md5(cmdstring.encode("utf-8"))
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
            cmdstring,
            close_fds=True,
            shell=shell,
            bufsize=128,
            stdout=succ_f,
            stderr=err_f,
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

    return a, e

def initialization():
        return not os.path.exists(getAppPath() + '/.nv')

def executeCommand(q):
    a = ""
    e = ""
    import tempfile, subprocess
    from hashlib import md5

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

    return a, e