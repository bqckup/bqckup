from redis import Redis
from rq.worker import Worker
from rq import Queue
from classes.config import Config

class Bq_Worker:
    def __init__(self):
        self._redis = Redis(Config().read('redis', 'host'), Config().read('redis', 'port'), Config().read('redis', 'password'))
        self.queue = Queue(connection=self._redis)
        
    def run(self):
        worker = Worker(queues=[self.queue], connection=self._redis)
        worker.work(with_scheduler=True)
    