"""
    Doc : https://github.com/coleifer/peewee
    for migration:
    http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#schema-migrations
    New Update
"""

from logging import Logger, log
import logging
import sys, time, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from playhouse.migrate import *
from helpers import generate_token

from datetime import datetime, timedelta
from decouple import config
from flask_login import UserMixin, current_user

# dbc = {
#     "db_name":config('DB_NAME'),
#     "host":"127.0.0.1",
#     "user":config('DB_USER'),
#     "password":config('DB_PASS'),
#     "port":3306
# }

databasePath = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")) + "/database/"
)

db = SqliteDatabase(
    databasePath + config("DB_NAME") + ".db",
    pragmas={"journal_moda": "wal", "cache_size": -64 * 1000, "synchronous": 0},
)

# db = MySQLDatabase(dbc['db_name'], user=dbc['user'], password=dbc['password'], host=dbc['host'], port=dbc['port'])


class BaseModel(Model):
    class Meta:
        database = db

    def findOneByColumn(self, column, value):
        return self.getByColumn(self, column, value)

    def selectWhere(self, column, value):
        try:
            data = self.select().where(column == value).dicts()
        except:
            return False
        else:
            return data

    def getByColumn(self, column, value):
        try:
            data = self.select().where(column == value).get()
        except:
            return False
        else:
            return data

    def findOne(self, id):
        try:
            obj = self.getById(id)
        except:
            return False
        else:
            return obj

    def findMany(self):
        return self.select().dicts()

    def getById(self, id):
        try:
            data = self.get_by_id(id)
        except:
            return False

        return data

    def getByToken(self, token):
        try:
            data = self.select().where(self.token == token).get()
        except:
            data = False

        return data

    def deleteByColumn(self, columnName, value):
        status = True
        try:
            self.delete().where(columnName == value).execute()
            print("Deleting by column")
        except Exception as e:
            print(f"Error caught: {e}")
            status = False

        return status

    # posibble to delet multiple rows
    def deleteById(self, id):
        Success = True
        try:
            self.delete().where(self.id == id).execute()
            print("Deleting by id")
        except Exception as e:
            print(f"Error caught : {e}")
            Success = False
        else:
            print("Delete success")

        return Success


class BackupQueue(BaseModel):

    STATUS_RUNNING = 1
    STATUS_DONE = 0

    class Meta:
        table_name = "backup_queue"

    id = AutoField(primary_key=True)
    token = CharField(max_length=100)
    file = TextField()
    backup_id = IntegerField()
    status = IntegerField()  # 1 = On Progress, 0 = Done
    created_on = DateTimeField(default=datetime.now())

    def makeItDone(self, backup_id):
        try:
            BackupQueue().update(status=BackupQueue.STATUS_DONE).where(
                BackupQueue.backup_id == backup_id
            ).execute()
        except Exception as e:
            raise Exception("Change status queue to done failed, cause : %s" % e)

    def runningBackupExists(self):
        try:
            BackupQueue().select(BackupQueue.id).where(
                BackupQueue.status == BackupQueue.STATUS_RUNNING
            ).get()
        except Exception as e:
            return False
        else:
            return True

    def createOne(self, backup_id, path):
        try:
            BackupQueue().create(
                token=generate_token(10),
                backup_id=backup_id,
                status=BackupQueue.STATUS_RUNNING,
                file=path,
            )
        except Exception as e:
            raise Exception("Failed to created BackupQueue, cause : %s" % e)


class Task(BaseModel):
    class Meta:
        table_name = "task"

    id = AutoField(primary_key=True)
    command = TextField()
    status = IntegerField()
    type = IntegerField(null=True)
    msg = TextField(null=True)
    created_on = IntegerField(default=int(time.time()))
    execute_at = IntegerField(null=True)
    finish_at = IntegerField(null=True)

    def finishAt(self, id=False, mTime=False):
        if not mTime or not id:
            print("Nothing to do")
            return
        try:
            t = Task().update(finish_at=mTime).where(Task.id == id).execute()
        except Exception as e:
            print(f"Error Caught {e}")
        else:
            print("updated")


class User(BaseModel, UserMixin):
    class Meta:
        table_name = "users"

    id = AutoField(primary_key=True)
    token = CharField(max_length=70)
    name = CharField(max_length=100)
    email = CharField(max_length=100)
    username = CharField(max_length=100)
    password = TextField()
    created_on = IntegerField(default=int(time.time()))
    forgot_password_token = TextField(null=True)
    forgot_password_time = DateTimeField(null=True)

    def currentUser(self):
        try:
            user = User().get_by_id(current_user)
        except:
            return False
        else:
            return user

    def currentUserStorage(self):
        user = User().currentUser()
        if not user:
            return 0

        storage = Configuration().generalConfig(name="cloud_storage", user_id=user.id)

        if not storage:
            return False

        return storage

    def is_authenticated(self):
        return False

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def resetTmpCode(self, id):
        return (
            User()
            .update(
                {
                    User.forgot_password_token: None,
                    User.forgot_password_time: None,
                }
            )
            .where(User.id == id)
            .execute()
        )

    def getByTmpCode(self, code: str):
        try:
            user = (
                User()
                .select(User.id, User.forgot_password_token, User.forgot_password_time)
                .where(User.forgot_password_token == code)
                .get()
            )
        except Exception as e:
            print(e)
            user = False

        return user

    def generateTmpCode(self, user):
        import secrets

        code = secrets.token_urlsafe(20)
        timeExpired = datetime.now() + timedelta(minutes=15)
        user.forgot_password_token = code
        user.forgot_password_time = timeExpired
        user.save()
        return user.forgot_password_token


class MailLog(BaseModel):
    class Meta:
        table_name = "backup_email_log"

    id = AutoField(primary_key=True)
    sender = CharField(max_length=100)
    to = CharField(max_length=100)
    content = TextField()
    status = IntegerField()
    statusMsg = TextField()
    sent_at = DateTimeField(default=datetime.now())


# Database Site
class BackupDatabase(BaseModel):
    class Meta:
        table_name = "backup_database"

    id = AutoField(primary_key=True)
    token = CharField(max_length=70)
    backup_id = IntegerField()
    host = CharField(max_length=50)
    user = CharField(max_length=100)
    password = TextField()
    db_name = CharField(max_length=100)
    updated_on = IntegerField(default=int(time.time()))
    tipe = CharField(max_length=50)

    def findManyByBackup(self, backup_id):
        return (
            BackupDatabase.select().where(BackupDatabase.backup_id == backup_id).dicts()
        )

        # Configuration


# keep_files, email_notification, schedule, max_file_retention, day_keep_files, schedule_time
class Configuration(BaseModel):
    class Meta:
        table_name = "backup_config"

    id = AutoField(primary_key=True)
    name = TextField()
    value = TextField()
    user_id = IntegerField()
    backup_id = IntegerField()
    updated_on = IntegerField(default=int(time.time()))

    def generalConfig(self, name=False, alias=False, user_id=False):
        user_id = user_id if user_id else User().currentUser().id
        try:
            if name:
                config = (
                    Configuration()
                    .select()
                    .where(
                        (Configuration.name == name)
                        & (Configuration.user_id == user_id)
                    )
                    .get()
                )
                config = config.value
            else:
                config = Configuration().select()

        except:
            return alias
        else:
            return config

    # alias to handle if its doesnt exist
    def getValue(self, backup_id, name, alias="", user_id=None):
        try:
            data = (
                Configuration.select(Configuration.value, Configuration.updated_on)
                .where(
                    (Configuration.backup_id == backup_id)
                    & (Configuration.name == name)
                )
                .get()
            )
        except:
            return alias
        else:
            return data.value


# Site
class Backup(BaseModel):
    class Meta:
        table_name = "backup"

    id = AutoField(primary_key=True)
    token = CharField(max_length=70)
    user_token = CharField(max_length=70)
    backup_name = TextField(null=True)
    site = TextField()
    path = TextField()
    last_backup = IntegerField(null=True)
    updated_on = IntegerField(default=int(time.time()))

    def listByUserToken(self, user_token):
        try:
            backups = Backup().select().where(Backup.user_token == user_token)
        except:
            return {}
        else:
            return backups
    def getBySchedule(self, schedule):
        try:
            result = (
                Backup.select()
                .join(Configuration, on=(Backup.id == Configuration.backup_id))
                .where(Configuration.value == schedule)
                .dicts()
            )
        except Exception as e:
            return False
        else:
            return result

    def getLastBackupNull(self):
        try:
            backup = (
                Backup()
                .select()
                .where(Backup.last_backup.is_null())
                .order_by(Backup.created_on.asc())
                .get()
            )
        except:
            return False

        return backup

    def getEarliestBackup(self):
        try:
            backup = Backup().select().order_by(Backup.last_backup.asc())
        except:
            return False

        return backup

    def findMany(self):
        return Backup.select().dicts()

    def name(self, id):
        if not isinstance(id, int):
            return "-"

        return Backup.get_by_id(id).backup_name

    # Updating last backup
    def updateLastBackup(self, id):
        try:
            q = Backup.update(last_backup=time.time()).where(Backup.id == id)
            q.execute()
        except Exception as e:
            raise Exception("Error Updating Last Backup, msg : %s" % e)


# Log
class BackupLog(BaseModel):
    class Meta:
        table_name = "backup_logs"

    id = AutoField(primary_key=True)
    token = CharField(max_length=70)
    path = TextField()
    size = BigIntegerField()
    backup_id = IntegerField()
    status = IntegerField()
    msg = TextField()
    created_on = IntegerField(default=int(time.time()))

    def getLastBackup(self, token, all=False):
        try:
            ids = Backup().select(Backup.id).where(Backup.user_token == token).dicts()
            ids = [_["id"] for _ in ids]

            logs = (BackupLog().select().limit(5).where(BackupLog.backup_id << ids)).order_by(
                BackupLog.created_on.desc()
            )

            if all:
                logs = logs.dicts()
            else:
                logs = logs.get()
        except:
            return False
        else:
            return logs

    def lastBackup(self):
        try:
            data = BackupLog.select().order_by(BackupLog.created_on.desc()).get()
            return data
        except Exception as e:
            return False

    def getLogs(self, backupId, limit=False):
        try:
            
            logs = BackupLog().select()
            
            if not limit:
                logs = logs.limit(limit)

            logs = logs.where(BackupLog.backup_id == backupId).order_by(BackupLog.created_on.desc()).dicts()

        except Exception as e:
            msg = f"getLogs for backup_id = {backupId} error, {e}"
            logging.error(msg)
            return [] #return empty array
        else:
            return logs

class ResponseLog(BaseModel):
    class Meta:
        table_name = "backup_response_log"

    id = AutoField(primary_key=True)
    user_token = CharField(max_length=70)
    backup_token = CharField(max_length=70)
    token = CharField(max_length=70)
    function_name = TextField()
    response = TextField()
    time = DateTimeField(default=datetime.now())

    def byFunc(self, backup_token):
        return (
            ResponseLog.select()
            .where(ResponseLog.backup_token == backup_token)
            .order_by(ResponseLog.time.desc())
            .get()
        )


def Migrate():
    pass
    # migrator = SqliteMigrator(db)
    # migrate(
    #     migrator.add_column('backup_config','user_id', IntegerField(null=True))
    # )
    # with db:
    # db.create_tables([Task])


def DBInitialization():
    if not os.path.exists(databasePath):
        os.makedirs(databasePath)

    if not os.path.exists(databasePath + config("DB_NAME") + ".db"):
        with db:
            db.create_tables(
                [
                    Backup,
                    Configuration,
                    BackupDatabase,
                    BackupLog,
                    User,
                    MailLog,
                    BackupQueue,
                    Task,
                ]
            )
    # import mysql.connector
    # try:
    #     myDb = mysql.connector.connect(
    #         host=dbc['host'],
    #         user=dbc['user'],
    #         password=dbc['password'],
    #        # auth_plugin='mysql_native_password'
    #     )

    #     c = myDb.cursor()
    #     c.execute('use %s' % dbc['db_name'])
    # except mysql.connector.Error as e:
    #     if e.errno == 1049:
    #         print("Database not found creating new database \n")
    #         c.execute('create database %s' % dbc['db_name'])
    #         db.create_tables([Site, Configuration, DatabaseSite, BackUpLog])


if __name__ == "__main__":
    # print(login_manager)
    if len(sys.argv) > 1:
        if sys.argv[1] == "migrate":
            print("Migrating..")
            Migrate()
    else:
        DBInitialization()
