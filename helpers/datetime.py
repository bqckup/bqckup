import datetime
from datetime import date, datetime

# Date and time-related functions
def difference_in_days(date1: int, date2: int) -> int:
    date1 = datetime.fromtimestamp(date1)
    date2 = datetime.fromtimestamp(date2)
    day1 = date1.date().day
    day2 = date2.date().day
    return day1 - day2

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

def date_diff(d1, d2, returnFormat=False):
    if not isinstance(d1, datetime):
        d1 = toDateObject(d1)

    if not isinstance(d2, datetime):
        d2 = toDateObject(d2)

    if returnFormat == "unix":
        return abs((d2 - d1).seconds)

    return abs((d2 - d1).days)

def get_date_from_unix(unix, typeDate=False, format="%Y-%m-%d"):
    if unix is None:
        return False

    unix = int(unix)
    if not typeDate:
        return datetime.fromtimestamp(unix).strftime(format)
    return datetime.fromtimestamp(unix).strftime("{}".format(typeDate))

def get_today(format="%d-%B-%Y"):
    return datetime.today().strftime(format)

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

def toDateObject(unix):
    if isinstance(unix, str):
        return datetime.strptime(unix, "%Y-%m-%d %H:%M:%S")

    date = datetime.fromtimestamp(unix)
    return date

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

def interval_in_number( interval: str) -> int:
    if interval == 'weekly':
        return 7
    elif interval == 'monthly':
        return 30
    return 1