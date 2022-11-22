from redis import Redis
from rq import Queue, Worker
from rq.job import Job
import func


"""
Reference:
    https://python-rq.org/docs/jobs/
    
requirements:
    pip3 install rq
    apt install redis
    
How to:
    rq worker --with-scheduler
"""


queue = Queue(name="Bqckup Queue", connection=Redis())

def queue_tasks():
    # how to create worker ?
    redis = Redis()
    q = Queue(connection=redis)
    worker = Worker(queues=[q], connection=redis)
    worker.work(with_scheduler=True)
    
    # How to create queue
    # job = q.fetch_job("my_job_id")
    # if job.get_status() == 'deferred' or job.get_status() == 'started':
    #     print("Job is still running")
    # else:
    #     job = q.enqueue(func.print_numbers, 5, job_id='my_job_id', depends_on="my_job_id")
    #     print("Job queued")
    
    
def main():
    queue_tasks()

if __name__ == "__main__":
    main()