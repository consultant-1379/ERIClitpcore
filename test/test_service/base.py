from litp.core.plan import Plan


class MethodCallLogger(object):

    def __init__(self, method):
        self.method = method
        self.was_called = False

    def __call__(self, *args):
        self.was_called = True
        return self.method(*args)


class Mock(object):
    """Base mocking class"""


class MockPlan(object):

    __class__ = Plan
    _phases = []
    running = False
    stopping = False
    valid = True
    state = "state"
    _phases = []
    allow_create_plan = True
    plan_type='Deployment'

    @property
    def phases(self):
        return self._phases

    def get_phase(self, index):
        try:
            return self._phases[index]
        except IndexError:
            return None

    @property
    def phase_tree_graph(self):
        return {"next_phases": {},
        "required_phases": {}}

    def get_task(self, phase_index, task_unique_id):
        if self.get_phase(phase_index):
            for task in self.get_phase(phase_index):
                if task.unique_id == task_unique_id:
                    return task

    def mark_running(self):
        pass

    def is_running(self):
        return self.running

    def is_stopping(self):
        return self.stopping

    def can_create_plan(self):
        return self.allow_create_plan

    def get_tasks(self, filter_type=None):
        tasks = []
        for phase in self.phases:
            for task in phase:
                if filter_type is not None and isinstance(task, filter_type):
                    tasks.append(task)
        return tasks


class MockTask(object):

    state = None
    description = "task description"
    call_id = "call_id"
    call_type = "call_type"
    task_id = "task_id"
    _id = "task_id"

    def __init__(self):
        self._model_item = MockItem()

    def format_parameters(self):
        return {}

    @property
    def unique_id(self):
        return 'my_unique_id'

    @property
    def item_vpath(self):
        return self.model_item.vpath

    @property
    def model_item(self):
        return self._model_item


class MockItem(object):

    @property
    def vpath(self):
        return '/foo/bar/baz/item_id'

    @property
    def item_id(self):
        return 'item_id'

    def get_cluster(self):
        return MockItem()


class MockExecutionManager(object):

    plan = None
    allow_create_plan = True

    def create_plan(self):
        # override this method to return a list of validation errror or a plan
        return self.plan

    def plan_exists(self):
        if self.plan:
            return True
        else:
            return False

    def delete_plan(self):
        return {"success": "plan deleted"}

    def run_plan(self, job):
        return {'success': True}

    def stop_plan(self):
        return {"success": "Plan stopped."}

    def can_create_plan(self):
        return self.allow_create_plan

    def is_plan_running(self):
        return self.plan.is_running()
