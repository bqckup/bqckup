from logging import LoggerAdapter, log
import os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from models import Task
from helpers import executeCommand
from helpers import isTarCorupt

class OJTask(object):
    # Type Archive
    COMPRESS = 1
    DECOMPRESS = 2

    def __init__(self):
        self._task_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) + '/logs/'

    def add_task(self, cmd, type = None):
        try:
            Task().create(
                command=cmd,
                status=0,
                type=type,
                created_on=int(time.time())
            )
        except Exception as e: print("Failed create a task,  %s" % e)


    def delete_log(self, type):
        logPath = self.get_log(type)
        if os.path.exists(logPath):
            os.remove(logPath)
    
    def get_log(self, type):
        return self._task_path + str(type) + '.log'
    
    def extract_archive(self, dest, target):
        q = False
        t_archive = target[-4:]
        
        if not os.path.exists(dest):
            raise Exception(f"{dest} not found")
        

        logPath = self._task_path + str(self.DECOMPRESS) + '.log'
        while not os.path.exists(logPath):
            open(logPath, 'a+')
            if os.path.exists(logPath): break

        if 'zip' in t_archive:
            q = f"cd {dest} && unzip -o {target} > {logPath} 2>&1 &"

        elif 'gz' in t_archive:
            # check if its corupt
            if isTarCorupt(target):
                raise Exception("Archive is corupted, can't be extracted")
            
            q = f"cd {dest} && tar zxvf {target}"
            
        # else:
        #     raise Exception("Unknown Archive format")
        
        self.add_task(q, OJTask.DECOMPRESS)
        self.execute_task()
        

    def create_archive(self, t, dest, target):
        logPath = self._task_path + str(self.COMPRESS) + '.log'
        while not os.path.exists(logPath):
            open(logPath, 'a+')
            if os.path.exists(logPath): break
            
        q = False
        
        if t == 'zip': q = f"zip -r {dest} {target} "
        elif t == 'targz': q = f"tar -zcvf {dest} {target} "
        
        q += f"> {logPath} 2>&1 &"

        if not q: return None

        self.add_task(q, OJTask.COMPRESS)
        self.execute_task()
        
    def execute_task(self):
        try:
            task = Task().select().where(Task.status == 0).order_by(Task.created_on.asc()).get()
        except Exception as e:
            raise Exception("Execute failed,Error occured, {}".format(e))
        else:
            executeCommand(task.command)
            task.execute_at = int(time.time())
            task.save()