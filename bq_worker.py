from redis import Redis
from rq.worker import Worker
from rq import Queue
from config import REDIS_PORT, REDIS_HOST, REDIS_PASSWORD

class Bq_Worker:
    def __init__(self):
        self._redis = Redis(REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)
        self.queue = Queue(connection=self._redis)
        
    def run(self):
        worker = Worker(queues=[self.queue], connection=self._redis)
        worker.work(with_scheduler=True)
        
if __name__ == '__main__':
    try:
        Bq_Worker().run()
    except Exception as e:
        print(f"Failed to running Worker : {e}")