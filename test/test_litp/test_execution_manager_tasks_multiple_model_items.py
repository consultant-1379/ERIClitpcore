import unittest
from litp.core.execution_manager import ExecutionManager
from mock import Mock


class TasksWithMultipleModelItemsTest(unittest.TestCase):
    """Tests only model items with tasks in regular non-snapshot phases
    Snapshot model items are tested in test_plugin_context_api.py
    """
    def setUp(self):
        self.plan = Mock()
        self.plan.is_active.return_value = True
        self.plan.get_phase.return_value = True
        self.plan.get_snapshot_phase.return_value = None
        self.plan.is_snapshot_plan = False
        self.exec_mgr = ExecutionManager(Mock(), Mock(), Mock())
        self.exec_mgr.plan = self.plan

    def test_no_effect_on_mitem_from_failed_task_with_another(self):
        model_item_success = create_model_item_mock('Initial')
        query_item_success = create_query_item_mock(model_item_success)
        task_success = create_task_mock(query_item_success, 'Success')

        model_item_failed = create_model_item_mock('Initial')
        query_item_failed = create_query_item_mock(model_item_failed)
        task_failed = create_task_mock(query_item_failed, 'Failed')

        # The actual find_tasks expects to be passed an instance of ModelItem
        def find_tasks(model_item=None):
            if model_item is model_item_success:
                return set([task_success])
            elif model_item is model_item_failed:
                return set([task_failed])

        self.plan.find_tasks.side_effect = find_tasks

        self.exec_mgr._update_item_states([task_success, task_failed])
        self.assertEquals('Applied', model_item_success._state)
        self.assertEquals('Initial', model_item_failed._state)


# create test methods
task_states_cfg = [
    # first two are completed; third is another task sharing same model item
    ('Failed',  None,   None,),
    ('Failed',  None,   'Failed',),
    ('Failed',  None,   'Running',),
    ('Failed',  None,   'Stopped',),
    ('Failed',  None,   'Success',),
    ('Failed',  None,   'Initial',),

    ('Success', None,  None,),
    ('Success', None,  'Failed',),
    ('Success', None,  'Running',),
    ('Success', None,  'Stopped',),
    ('Success', None,  'Success',),
    ('Success', None,  'Initial',),

    ('Failed',  'Failed',  None,),
    ('Failed',  'Failed',  'Failed',),
    ('Failed',  'Failed',  'Running',),
    ('Failed',  'Failed',  'Stopped',),
    ('Failed',  'Failed',  'Success',),
    ('Failed',  'Failed',  'Initial',),

    ('Success', 'Success',  None,),
    ('Success', 'Success',  'Failed',),
    ('Success', 'Success',  'Running',),
    ('Success', 'Success',  'Stopped',),
    ('Success', 'Success',  'Success',),
    ('Success', 'Success',  'Initial',),

    ('Success', 'Failed',  None,),
    ('Success', 'Failed',  'Failed',),
    ('Success', 'Failed',  'Running',),
    ('Success', 'Failed',  'Stopped',),
    ('Success', 'Failed',  'Success',),
    ('Success', 'Failed',  'Initial',),

    ('Failed',  'Success',  None,),
    ('Failed',  'Success',  'Failed',),
    ('Failed',  'Success',  'Running',),
    ('Failed',  'Success',  'Stopped',),
    ('Failed',  'Success',  'Success',),
    ('Failed',  'Success',  'Initial',),
]

model_item_states = [
    'Initial', 'Applied', 'Updated', 'ForRemoval', 'Removed']

allowed_transitions = {
    'Initial': 'Applied',
    'Updated': 'Applied',
    'ForRemoval': 'Removed',
}


def get_final_state(task_states, init_state):
    if any([state != 'Success' for state in task_states if state]):
        return init_state
    # final state should be the same as initial if initial state not in
    # allowed_transitions
    return allowed_transitions.get(init_state, init_state)


def create_task_mock(model_item, task_state):
    return Mock(name="Task", all_model_items=set([model_item]),
                state=task_state, requires=set())


def create_model_item_mock(init_state):
    model_item = Mock(name="ModelItem")
    model_item._state = init_state
    model_item.is_initial.return_value = (
        model_item._state == 'Initial')
    model_item.is_updated.return_value = (
        model_item._state == 'Updated')
    model_item.is_for_removal.return_value = (
        model_item._state == 'ForRemoval')

    def set_removed():
        model_item._state = 'Removed'

    def set_applied():
        model_item._state = 'Applied'
    model_item.set_removed.side_effect = set_removed
    model_item.set_applied.side_effect = set_applied

    model_item.get_vpath = lambda: '/item'
    return model_item

def create_query_item_mock(model_item):
    query_item = Mock(name="QueryItem")
    query_item._model_item = model_item
    return query_item


def create_check(acting_tasks_states, other_task_state, init_state,
                 expected_final_state):

    model_item = create_model_item_mock(init_state)
    query_item = create_query_item_mock(model_item)

    acting_tasks = []
    for state in acting_tasks_states:
        acting_tasks.append(create_task_mock(query_item, state))
    all_tasks = acting_tasks[:]
    other_task = None
    if other_task_state:
        other_task = create_task_mock(query_item, other_task_state)
        all_tasks.append(other_task)

    # it's a blunder but nose matches this as a test function before it's added
    # as a method of TasksWithMultipleModelItemsTest and complains about self
    # not being passed to it
    def do_check_expected(self=None):
        if self:
            self.plan.find_tasks.return_value = set(all_tasks)
            self.exec_mgr._update_item_states(acting_tasks)
            self.assertEqual(expected_final_state, query_item._model_item._state)

    return do_check_expected

# dynamically create test_methods
for task_states in task_states_cfg:
    acting_tasks_states = [ts for ts in task_states[:2] if ts]  # skip Nones
    other_task_state = task_states[-1]
    for model_item_state in model_item_states:
        expected_final_state = get_final_state(task_states,
                                               model_item_state)
        _check_method = create_check(acting_tasks_states,
                                     other_task_state,
                                     model_item_state,
                                     expected_final_state)
        if other_task_state:
            other = 'other_task_{0}'.format(other_task_state.lower())
        else:
            other = 'no_other_task'
        method_name = (
            'test_completed_{acting}_{other}'
            '_model_item_state_{init_state}_to_{end_state}').format(
                acting='_and_'.join(
                    [x.lower() for x in acting_tasks_states]),
                init_state=model_item_state.lower(),
                end_state=expected_final_state.lower(),
                other=other)

        _check_method.__name__ = method_name

        # magick over
        setattr(TasksWithMultipleModelItemsTest,
                _check_method.__name__, _check_method)
