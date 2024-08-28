from litp.data.types import Base as DbBase
from litp.data.types import PlanTask as DbPlanTask


class PlanTask(DbPlanTask, DbBase):
    def __init__(self, task, phase_seq_id, task_seq_id):
        super(PlanTask, self).__init__()
        self.task = task
        self.phase_seq_id = phase_seq_id
        self.task_seq_id = task_seq_id
