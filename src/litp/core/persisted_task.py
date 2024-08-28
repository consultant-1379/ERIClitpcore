from litp.data.types import Base as DbBase
from litp.data.types import PersistedTask as DbPersistedTask


class PersistedTask(DbPersistedTask, DbBase):
    def __init__(self, hostname, task, task_seq_id):
        super(PersistedTask, self).__init__()
        self.hostname = hostname
        self.task = task
        self.task_seq_id = task_seq_id
