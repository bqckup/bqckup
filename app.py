from modules.docs import docs
from modules.config import mConfig
from modules.auth import auth
from helpers import (
    generate_token,
    initialization,
    splitNewLine,
    isNone,
    getDateFromUnix,
    getInt,
    convertDatetime,
    today24Format,
    timeSince,
)
from classes.s3 import s3
from models import BackupQueue
from config import *
import sys
import logging
import time
import os
from datetime import timedelta
from flask.json import jsonify
from decouple import config
from flask import (
    Flask,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    session,
    abort,
)
from flask_login import LoginManager, login_required, logout_user, current_user
from flask_caching import Cache
from playhouse.shortcuts import model_to_dict

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))


app = Flask(__name__)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = "basic"

# user loader needed by flask_login


@login_manager.user_loader
def load_user(id):
    from models import User

    try:
        user = User().get_by_id(id)
    except:
        return None
    else:
        return user


app.config["SECRET_KEY"] = ")mEV=i7uyoybyq<"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300


app.register_blueprint(auth, url_prefix="/auth/")
app.register_blueprint(mConfig, url_prefix="/config/")
app.register_blueprint(docs, url_prefix="/docs/")


cache = Cache(app)


# assign global variable
# ref : https://stackoverflow.com/a/43336023
@app.context_processor
def globalVariable():
    currentUser = False
    currentUrl = request.url
    currentUrlSplit = request.url.split("/")
    currentTime = today24Format()
    currentVersion = config("VERSION")

    if current_user.is_authenticated:
        from models import User

        currentUser = User().currentUser()

    return dict(
        currentUser=currentUser,
        currentUrl=currentUrl,
        currentUrlSplit=currentUrlSplit,
        currentTime=currentTime,
        currentVersion=currentVersion,
    )


@app.errorhandler(500)
def page_internal_error(e):
    # import traceback
    # traceback = traceback.format_exc()
    # data = {
    #     'target':'this.nugroho@gmail.com',
    #     'subject':'Error OJTBackup',
    #     'message':traceback
    # }
    # Mail(data).send()
    return render_template("500.html"), 500


@app.errorhandler(401)
def page_unauthorized(e):
    return redirect(url_for('auth.login'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.before_request
def before_request():
    if not initialization():
        return "Access blocked"


@app.route("/get_link_download", methods=["GET"])
def get_link_download():
    from core.ojtbackup import OJTBackup
    url = None
    data = request.args

    if not data:
        return jsonify(url=None)

    from models import User

    if User().currentUserStorage() == "drive":
        url = OJTBackup().getLinkDownload(fileId=data.get("key"))
    else:
        url = OJTBackup().getLinkDownload(
            data.get("key"), clearFolderName(data.get("key"))
        )

    return jsonify(url=url)


@app.route("/do_update", methods=["GET"])
def doUpdate():
    from core.ojtbackup import OJTBackup

    if session["need_update"]:
        status = 0
        if OJTBackup().doUpdate():
            status = 1
            session["need_update"] = False

        return jsonify(status=status)


@app.route("/get_backup_detail", methods=["GET"])
def getBackupDetail():
    from models import Backup, BackupDatabase, Configuration

    req = request.args
    token = req.get("token")

    if not token:
        return False

    backup = Backup().getByColumn(Backup.token, token)

    if not backup:
        return False

    database = BackupDatabase().getByColumn(BackupDatabase.backup_id, backup.id)

    config = Configuration().selectWhere(Configuration.backup_id, backup.id)

    backupDict = model_to_dict(backup)
    databaseDict = {}
    configDict = {}

    if database:
        databaseDict = model_to_dict(database)

    if config:
        configDict = list(config)

    return jsonify(error=0, folder=backupDict, database=databaseDict, config=configDict)


@app.route("/get_config_detail", methods=["GET"])
def getConfigDetail():
    from models import Backup, Configuration

    req = request.args
    id = req.get("id")  # site id

    if not id:
        return False

    try:
        backup = Backup().get_by_id(id)
        configs = list(
            Configuration().select().where(Configuration.backup_id == backup.id).dicts()
        )

    except Exception as e:
        return jsonify(error=1, data="Data not found, Reason : %s" % e)

    return jsonify(error=0, data=configs)


@app.route("/get_last_backup", methods=["GET"])
def get_last_backup():
    from models import BackupLog, User, Backup
    from core.ojtbackup import OJTBackup

    user = User().currentUser().token
    lastBackup = BackupLog().getLastBackup(user)

    timeNextBackup, nextBackupId = OJTBackup().getNextBackup()
    nextBackup = Backup().findOne(nextBackupId)

    return render_template(
        "last_backup_ajax.html",
        lastBackup=lastBackup,
        timeNextBackup=timeNextBackup,
        nextBackup=nextBackup,
    )


@app.route("/get_list_backup", methods=["GET"])
def get_list_backup():
    from models import User, Backup

    user = User().currentUser().token
    backups = Backup().selectWhere(Backup.user_token, user)

    return render_template("list_backup_ajax.html", backups=backups)


@app.route("/get_list_logs", methods=["GET"])
def get_list_logs():
    from models import BackupLog, User

    token = User().currentUser().token
    logs = BackupLog().getLastBackup(token=token, all=True)

    return render_template("log_ajax.html", logs=logs)


@app.route("/list_files", methods=["GET"])
def listFiles():
    from models import Backup
    from core.ojtbackup import OJTBackup

    data = request.args
    token = data.get("token")

    try:
        backup = Backup().select().where(Backup.token == token).get()
        backupName = (
            backup.backup_name
            if " " not in backup.backup_name
            else backup.backup_name.replace(" ", "_")
        )
        listFiles = OJTBackup().list(backupName + "_" + backup.token)
    except Exception as e:
        return jsonify(error=1, data=f"Site not found{e}")

    return render_template("list_files_ajax.html", files=listFiles)


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        return redirect(url_for("auth.login"))
    abort(401)


@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
@login_required
# @cache.cached(timeout=60)
def index():
    from models import User
    from core.ojtbackup import OJTBackup

    user = User.get_by_id(current_user)

    ojtbackup = OJTBackup()

    # backup_token = generate_token()
    # db_token = generate_token()
    user_token = user.token
    serverUsage = ojtbackup.getServerDiskUsage()
    serverStorageFull = ojtbackup.serverStorageFull()
    backup_token = 'backup_token'
    db_token = 'db_token'

    if not AWS_S3_BUCKET:
        return redirect(url_for('mConfig.index'))

    print(session)

    cloudUsage = ojtbackup.getCloudDiskUsage()
    cloudStorageFull = ojtbackup.cloudStorageFull()

    # checking update
    if session["check_update"]:
        session["need_update"] = False
        # if OJTBackup().checkUpdate() != 0:
        #     session["need_update"] = True
        #     session["check_update"] = False

    return render_template(
        "index.html",
        cloudStorage='s3',
        backup_token=backup_token,
        db_token=db_token,
        user_token=user_token,
        serverUsage=serverUsage,
        cloudUsage=cloudUsage,
        title_bar="Dashboard",
        currentVersion=config("VERSION"),
        serverStorageFull=serverStorageFull,
        cloudStorageFull=cloudStorageFull,
    )


# @csrf.exempt
@app.route("/delete_backup", methods=["POST"])
@login_required
def delete_backup():
    from models import Backup, BackupDatabase, BackupLog, Configuration

    post = request.form

    if not post.get("id"):
        return False

    try:
        backup = Backup().select(Backup.id).where(Backup.token == post.get("id")).get()
    except:
        return jsonify(error=1)

    BackupDatabase().deleteByColumn(BackupDatabase.backup_id, backup.id)
    Configuration().deleteByColumn(Configuration.backup_id, backup.id)
    BackupLog().deleteByColumn(BackupLog.backup_id, backup.id)
    backup.delete_instance()

    return jsonify(error=0)


@app.route("/save_folder", methods=["POST"])
@login_required
def save_folder():
    from models import Backup, User
    from os import path

    post = request.form

    for p in post.get("path").splitlines():
        if not path.exists(p):
            return jsonify(error=1, msg="Path %s doesn't exists" % p)

        if not os.path.isdir(p):
            return jsonify(error=1, msg="Path %s is not a directory/folder" % p)

    user = User().getById(current_user)

    try:
        backup, created = Backup.get_or_create(
            token=post.get("token"),
            defaults={
                "user_token": user.token,
                "backup_name": post.get("backup_name"),
                "site": post.get("site"),
                "path": post.get("path"),
            },
        )

        if not created:
            backup.backup_name = post.get("backup_name")
            backup.token = post.get("token")
            backup.site = post.get("site")
            backup.path = post.get("path")
            backup.save()

    except Exception as e:
        return jsonify(error=1, msg="Error caught : %s" % e)

    # backup = Backup.select().where(Backup.token == post.get('token')
    # ).get()

    return jsonify(error=0, backup_id=backup.id)


@app.route("/save_database", methods=["POST"])
@login_required
def save_database():
    from models import BackupDatabase
    import mysql.connector

    post = request.form
    try:
        databaseCredentials = {
            "user": post.get("user"),
            "password": post.get("password"),
            "host": post.get("host"),
            "database": post.get("db_name"),
        }
        c = mysql.connector.connect(**databaseCredentials)
    except mysql.connector.Error as e:
        return jsonify(error=1, msg="Can't connect to your database")
    else:
        c.close()

    database, created = BackupDatabase.get_or_create(
        backup_id=int(post.get("backup_id")),
        defaults={
            "token": post.get("db_token"),
            "host": post.get("host"),
            "user": post.get("user"),
            "password": post.get("password"),
            "db_name": post.get("db_name"),
            "tipe": post.get("tipe"),
        },
    )

    return jsonify(error=0)


@app.route("/backup_now", methods=["GET"])
@login_required
def backup_now():
    data = request.args

    if not data.get("token"):
        abort(404)

    from models import Backup
    from core.ojtbackup import OJTBackup

    backup = Backup().getByColumn(Backup.token, data.get("token"))

    # check if there is any backup runnig
    isExists = BackupQueue().runningBackupExists()

    if isExists:
        return jsonify(error=1, msg="There is doing backup Progress,Please wait until it done")

    if not backup:
        abort(404)

    OJTBackup().run(backup.id, True)

    return jsonify(error=0, msg="Progress")


# @csrf.exempt
@app.route("/save_backup", methods=["POST"])
@login_required
def save_backup():
    from models import Backup, Configuration, User

    post = request.form
    backup_id = post.get("backup_id")
    backup = Backup().findOne(backup_id)
    user_id = User().currentUser().id
    try:
        for p in post:
            value = 1 if post.get(p) == "on" else post.get(p)
            c, created = Configuration().get_or_create(
                name=p,
                user_id=user_id,
                backup_id=backup.id,
                defaults={"value": value, "backup_id": backup.id},
            )

            if not created:
                c.user_id = user_id
                c.name = p
                c.value = value
                c.save()

    except Exception as e:
        return jsonify(error=1, msg="Failed add config, because %s" % e)

    return jsonify(error=0, redirect=url_for("index"))


@app.route("/add_backup", methods=["POST"])
@login_required
def save():
    from models import Backup, BackupDatabase, db, User

    if request.method != "POST":
        return False

    post = request.form

    # validation
    from os import path

    for p in post.get("path").splitlines():
        if not path.exists(p):
            flash("Path %s doesn't exists" % p, "error")
            return redirect(url_for("index"))

    # check connection database
    if (
        post.get("user")
        and post.get("password")
        and post.get("db_name")
        and post.get("tipe") == "mysql"
    ):
        import mysql.connector

        try:
            databaseCredentials = {
                "user": post.get("user"),
                "password": post.get("password"),
                "host": post.get("host"),
                "database": post.get("db_name"),
            }

            c = mysql.connector.connect(**databaseCredentials)
        except mysql.connector.Error as e:
            flash("Something wrong with your database configuation, %s" %
                  e, "error")
            return redirect(url_for("index"))
        else:
            c.close()

    # start transaction
    user = User.get_by_id(current_user)
    with db.atomic() as trx:
        try:
            backupName = (
                post.get("backup_name")
                if len(post.get("backup_name")) > 0
                else post.get("site")
            )
            Backup().get_or_create(
                token=post["token"],
                defaults={
                    "backup_name": backupName,
                    "token": post.get("token"),
                    "site": post.get("site"),
                    "user_token": user.token,
                    "path": post.get("path"),
                    "created_on": int(time.time()),
                },
            )

            backup = Backup().select().where(Backup.token == post.get("token")).get()

            BackupDatabase().get_or_create(
                backup_id=int(backup.id),
                defaults={
                    "token": post["db_token"],
                    "host": post["host"],
                    "user": post["user"],
                    "password": post["password"],
                    "db_name": post["db_name"],
                    "tipe": post["tipe"],
                },
            )

        except Exception as e:
            # doing rollback if its failed
            trx.rollback()
            flash(
                f"Failed added {post.get('site')}, cause : {e.strip()}", "error")
            return redirect(url_for("index"))

        flash(f"Success added {post.get('site')}", "success")
        return redirect(url_for("index"))


# jinja
@app.template_filter("tSince")
def tSince(s):
    if not s:
        return "-"
    return timeSince(s)


@app.template_filter("convertDate")
def convDate(v):
    return convertDatetime(v, "%d %B %Y")


@app.template_filter("getUsage")
def getUsageByBackup(token):
    if not token:
        return "0"

    from models import Backup
    from core.ojtbackup import OJTBackup

    backup = (
        Backup()
        .select(
            Backup.backup_name,
        )
        .where(Backup.token == token)
        .get()
    )
    backupName = backup.backup_name
    if " " in backupName:
        backupName = backup.backup_name.replace(" ", "_")

    backupName += "_" + token

    return OJTBackup().getUsage(backupName)["used"]


@app.template_filter("getSiteName")
def getSiteName(id):
    from models import Backup

    return Backup().name(id)


@app.template_filter("getStatusLabel")
def getStatusLabel(status):
    if not status:
        return '<span class="badge bg-red-lt">Failed</span>'
    else:
        return '<span class="badge bg-green-lt">Success</span>'


@app.template_filter("humanReadableSize")
def humanReadableSize(s):
    if not isinstance(s, int):
        return "-"

    from hurry.filesize import size, alternative

    return size(s, system=alternative)


@app.template_filter("getFilenameFromFullPath")
def getFilenameFromFullPath(s):
    arr = s.split("/")
    return arr[-1]


@app.template_filter("getInt")
def jinjaGetInt(s):
    return getInt(s)


@app.template_filter("split_new_lines")
def jinjaSplitNewLine(s):
    return splitNewLine(s)


@app.template_filter("isNone")
def jinjaIsNone(s):
    return isNone(s)


@app.template_filter("getDateFromUnix")
def jinjaGetDateFromUnix(s):
    return getDateFromUnix(s, format="%d %B %Y | %H:%M")


@app.template_filter("clearFolderName")
def clearFolderName(s):
    if "/" in s:
        arr = s.split("/")
        arr.pop(0)
        s = "".join(arr)
    return s


if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=True, port=9393)
else:
    logging.basicConfig(
        filename="OJTBackup.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s",
    )
    # logging.basicConfig(filename='demo.log', level=logging.DEBUG)
    # gunicorn_logger = logging.getLogger("gunicorn.error")
    # app.logger.handlers = gunicorn_logger.handlers
    # app.logger.setLevel(gunicorn_logger.level)
