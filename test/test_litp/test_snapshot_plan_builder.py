import mock
import unittest

from litp.core import constants
from litp.core.plan import SnapshotPlan
from litp.core.plan_builder import SnapshotPlanBuilder
from litp.core.task import CallbackTask
from litp.plan_types.remove_snapshot import remove_snapshot_tags


class SnpashotPlanBuilderTestCase(unittest.TestCase):
    _tasks = None

    def setUp(self):
        self.model_manager = mock.MagicMock(autospec=True)
        self.builder = SnapshotPlanBuilder(
            self.model_manager, constants.REMOVE_SNAPSHOT_PLAN, self.tasks
        )

    @property
    def tasks(self):
        if self._tasks is None:
            model_item_1 = mock.MagicMock(autospec=True)
            model_item_2 = mock.MagicMock(autospec=True)
            task_1 = mock.Mock(
                spec=CallbackTask,
                tag_name=remove_snapshot_tags.PEER_NODE_LVM_VOLUME_TAG,
                model_item=model_item_1,
                all_model_items=set([model_item_1])
            )
            task_2 = mock.Mock(
                spec=CallbackTask,
                tag_name='foo_tag',
                model_item=model_item_2,
                all_model_items=set([model_item_2])
            )
            task_3 = mock.Mock(
                spec=CallbackTask,
                tag_name=remove_snapshot_tags.VALIDATION_TAG,
                model_item=model_item_2,
                all_model_items=set([model_item_2])
            )
            self._tasks = [task_1, task_2, task_3]
        return self._tasks

    def test_group_order(self):
        expected = [
            'REMOVE_SNAPSHOT_VALIDATION_GROUP',
            'REMOVE_SNAPSHOT_PRE_OPERATION_GROUP',
            'REMOVE_SNAPSHOT_LMS_LVM_VOLUME_GROUP',
            'REMOVE_SNAPSHOT_PEER_NODE_LVM_VOLUME_GROUP',
            'REMOVE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_GROUP',
            'REMOVE_SNAPSHOT_NAS_FILESYSTEM_GROUP',
            'REMOVE_SNAPSHOT_SAN_LUN_GROUP',
            'REMOVE_SNAPSHOT_DEFAULT_GROUP',
            'REMOVE_SNAPSHOT_POST_OPERATION_GROUP',
            'REMOVE_SNAPSHOT_FINAL_GROUP'
        ]

        output = self.builder._topsort_groups()
        self.assertTrue(
            all(group == output[idx] for idx, group in enumerate(expected))
        )

    def test_ruleset_group_from_task(self):
        self.assertEquals(
            'REMOVE_SNAPSHOT_PEER_NODE_LVM_VOLUME_GROUP',
            self.builder._extract_ruleset_group_from_task(self.tasks[0])
        )
        self.assertEquals(
            'REMOVE_SNAPSHOT_DEFAULT_GROUP',
            self.builder._extract_ruleset_group_from_task(self.tasks[1])
        )
        self.assertEquals(
            'REMOVE_SNAPSHOT_VALIDATION_GROUP',
            self.builder._extract_ruleset_group_from_task(self.tasks[2])
        )

    def test_task_groups(self):
        expected = [
            ('REMOVE_SNAPSHOT_VALIDATION_GROUP', [self.tasks[2]]),
            ('REMOVE_SNAPSHOT_PRE_OPERATION_GROUP', []),
            ('REMOVE_SNAPSHOT_LMS_LVM_VOLUME_GROUP', []),
            ('REMOVE_SNAPSHOT_PEER_NODE_LVM_VOLUME_GROUP', [self.tasks[0]]),
            ('REMOVE_SNAPSHOT_PEER_NODE_VXVM_VOLUME_GROUP', []),
            ('REMOVE_SNAPSHOT_NAS_FILESYSTEM_GROUP', []),
            ('REMOVE_SNAPSHOT_SAN_LUN_GROUP', []),
            ('REMOVE_SNAPSHOT_DEFAULT_GROUP', [self.tasks[1]]),
            ('REMOVE_SNAPSHOT_POST_OPERATION_GROUP', []),
            ('REMOVE_SNAPSHOT_FINAL_GROUP', [])
        ]
        self.assertEquals(
            expected,
            self.builder._group_tasks()
        )

    def test_plan_creation(self):
        phases = [[self.tasks[2]], [self.tasks[0]], [self.tasks[1]]]
        plan = self.builder.build()
        self.assertTrue(isinstance(plan, SnapshotPlan))
        self.assertEquals(phases, plan.phases)

    def test_rulesets(self):
        task_item = mock.MagicMock(autospec=True)
        task = mock.Mock(
            spec=CallbackTask,
            model_item=task_item,
            all_model_items=set([task_item])
        )
        task.tag_name = None
        builder = SnapshotPlanBuilder(
            self.model_manager, constants.CREATE_SNAPSHOT_PLAN, [task])
        self.assertTrue(isinstance(builder.build(), SnapshotPlan))

    def test_valid_tag(self):
        task = mock.Mock(spec=CallbackTask)
        task.tag_name = remove_snapshot_tags.PEER_NODE_LVM_VOLUME_TAG
        builder = SnapshotPlanBuilder(
            self.model_manager, constants.REMOVE_SNAPSHOT_PLAN, [task])
        self.assertTrue(builder._is_valid_tag(task.tag_name))

    def test_invalid_tag(self):
        task = mock.Mock(spec=CallbackTask)
        task.tag_name = 'dummy'
        builder = SnapshotPlanBuilder(
            self.model_manager, constants.REMOVE_SNAPSHOT_PLAN, [task])
        self.assertFalse(builder._is_valid_tag(task.tag_name))
