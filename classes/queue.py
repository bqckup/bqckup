from rq import Queue as rQueue
from redis import Redis
from classes.config import Config

class Queue:
    def __init__(self):
        self._connection = Redis(Config().read('redis', 'host'), Config().read('redis', 'port'), Config().read('redis', 'password'))
        self.queue = rQueue(connection=self._connection)
        
        
    def add(self, job_id: str, func, *args):
        if self.check_status(job_id) == 'deferred' or self.check_status(job_id) == 'started':
            print(f"{job_id} already running")
            return None
        print(func)
        self.queue.enqueue(func, args=args, job_id=job_id)
    
    def check_status(self, job_id: str):
        jobs = self.queue.fetch_job(job_id=job_id)
        if not jobs:
            return None
        return jobs.get_status()