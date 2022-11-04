
import subprocess, os, time, sys, logging
sys.path.append('..')
from helpers import clearDomain, executeCommand, getAppPath

from models import BackupDatabase, Backup, BackupQueue

from os import path
class Database(object):
    def __init__(self):
        self.tmp = getAppPath() + '/tmp/'
    
    def backUp(self, backup_id):
        dbs = BackupDatabase().findManyByBackup(backup_id)
        pathArr = []
        for db in dbs:
            backup = Backup().get_by_id(backup_id)
            backupName = backup.backup_name.replace(' ', '_') + '_' + backup.token
            siteDomain = clearDomain(backupName)
            today = time.strftime('%Y-%m-%d')
            dbBackupPath = self.tmp + siteDomain + '/_db/'
            

            if not path.exists(dbBackupPath):
                logging.info("Creating Folder _db in %s" % dbBackupPath)
                os.makedirs(dbBackupPath)

            # 2 database option
            # mysql and postgre
            fileName = "{}_{}".format(siteDomain, today)

            # create queue
            BackupQueue().createOne(backup.id, dbBackupPath + fileName + ".sql.gz")

            if db['tipe'] == 'mysql':
                fileName = dbBackupPath + fileName + ".sql.gz"
                dumpcmd = '/usr/bin/mysqldump -u {} -p"{}" {} | /bin/gzip > {}'.format(
                    db['user'], 
                    db['password'], 
                    db['db_name'],
                    fileName
                )

            elif db['tipe'] == 'postgresql':
                fileName = dbBackupPath + fileName + '.gz'
                dumpcmd = "/usr/bin/pg_dump {} | /bin/gzip > {}".format(db['db_name'], fileName)

                
            a, e = executeCommand(dumpcmd);                

            logging.info("Backup Database %s \n" % a)

            if e:
                logging.error("Error caught while backup database : %s" % e)
            
            pathArr.append(fileName)

        return pathArr
