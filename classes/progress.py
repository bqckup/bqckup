import os, threading, sys
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.text import Text
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class ProgressPercentage(object):
    def __init__(self, filename, label):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()
        task_description = ""
        
        self._progress = Progress(
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        )
        self._progress.start()
        self._task = self._progress.add_task(task_description, total=self._size)

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            self._progress.update(self._task, advance=bytes_amount)
            if self._seen_so_far >= self._size:
                self._progress.stop()
                

class ProgressSpinner:
    def __init__(self, message: str):
        self.message = message
        self.console = Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        )

    def __enter__(self):
        self.task = self.progress.add_task(self.message, total=None)
        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.progress.stop()