import os, datetime
from os import path
from datetime import date, datetime


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

