import unittest
import mock

from litp.core.plan_builder import (PlanBuilder)
from litp.core.task import Task
from litp.plan_types.deployment_plan.deployment_plan_groups import CLUSTER_GROUP
from litp.core.task import ConfigTask

from test_plan_builder import PlanBuilderTestMixin
from litp.plan_types.deployment_plan import deployment_plan_groups


class UpgradePlanBuilderTest(unittest.TestCase, PlanBuilderTestMixin):
    """Test UpgradPlanBuilder class"""
    def setUp(self):
        self.model_manager = mock.Mock(
            auto_spec="litp.core.plan_builder.ModelManager")
        self.model_manager.cluster_iterator = mock.Mock()

    def test_passing_lock_task_returns_correct_subclass(self):
        lock_tasks = {'/node1': [], '/node2': []}
        self.assertEqual(PlanBuilder,
                         type(PlanBuilder(mock.Mock(), [],
                                          lock_tasks=lock_tasks)))

    def _get_task(self, name=None):
        return mock.MagicMock(auto_spec=ConfigTask, group=deployment_plan_groups.NODE_GROUP,
                              name=name, requires=set())

    @mock.patch("litp.core.plan_builder.get_task_node",
                side_effect=lambda task: task.node)
    def test_get_task_collection_for_group(self, get_task_node):
        node = mock.Mock()
        task1 = self._get_task()
        task2 = self._get_task()
        task2.group = deployment_plan_groups.CLUSTER_GROUP
        task1.node = task2.node = node
        task3 = self._get_task()
        task3.group = deployment_plan_groups.MS_GROUP

        task4 = self._get_task()  # node group but different node path
        tasks = [task1, task2, task3, task4]

        group_tag = [deployment_plan_groups.NODE_GROUP, deployment_plan_groups.CLUSTER_GROUP]

        builder = PlanBuilder(self.model_manager, tasks,
                                     lock_tasks={'dummy': 'value'})
        builder.sortable_tasks = tasks
        collection = builder._get_task_collection_for_group(
            group_tag,
            [node.vpath]
        )
        self.assertEquals(2, len(collection))
        self.assertTrue(task1 in collection)
        self.assertTrue(task2 in collection)

        # test when node_vpath is None
        collection = builder._get_task_collection_for_group(group_tag)
        self.assertEquals(3, len(collection))
        self.assertTrue(task1 in collection)
        self.assertTrue(task2 in collection)
        self.assertTrue(task4 in collection)

    def test_get_task_collection_for_cluster(self):
        task1 = self._get_task()
        task2 = self._get_task()
        task3 = self._get_task()
        task4 = self._get_task()
        # tasks 1-3 are cluster group; task 4 is node
        task1.group = task2.group = task3.group = deployment_plan_groups.CLUSTER_GROUP
        # tasks 1,2,4 will have cluster with same vpath;
        for task in [task1, task2, task4]:
            task.model_item.get_cluster.return_value.vpath \
                = '/cluster'

        tasks = [task1, task2, task3, task4]
        builder = PlanBuilder(self.model_manager, tasks,
                                     lock_tasks={'dummy': 'value'})
        builder.sortable_tasks = tasks

        collection = builder._get_task_collection_for_cluster(CLUSTER_GROUP, '/cluster')
        self.assertEquals(2, len(collection))
        self.assertTrue(task1 in collection)
        self.assertTrue(task2 in collection)

        collection = builder._get_task_collection_for_cluster(CLUSTER_GROUP, None)
        self.assertEquals(0, len(collection))
