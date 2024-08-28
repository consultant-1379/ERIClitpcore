import unittest
import mock

from litp.core.plan_builder import (BasePlanBuilder,
                                    PlanBuilder,
                                    bridge_static_and_plugin_dependencies,
                                    TaskCollection,
                                    merge_prev_successful_and_current_tasks,)
from litp.core.plan_builder import get_task_node, _associated_items_determinable
from litp.core.task import Task
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Collection
from litp.core.model_type import Child
from litp.core.model_type import View
from litp.core.model_type import RefCollection
from litp.core.model_manager import QueryItem
import litp.core.constants as constants
from litp.core.litp_logging import LitpLogger
from litp.core.exceptions import CyclicGraphException
from litp.core.exceptions import ViewError
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.core.plan import Plan
from litp.extensions.core_extension import CoreExtension
from litp.core.future_property_value import FuturePropertyValue
from litp.plan_types.deployment_plan.deployment_plan_tags import (
    VXVM_UPGRADE_TAG
)


log = LitpLogger()
falsevaluereturn = mock.Mock(return_value=False)

def cb_attrs():
    pass


def _cb(*args, **kwargs):
    pass
_cb.im_class = cb_attrs
_cb.im_func = cb_attrs


def _cb2(*args, **kwargs):
    pass
_cb2.im_class = cb_attrs
_cb2.im_func = cb_attrs


class PlanBuilderTestMixin(object):
    def get_lock_unlock_tasks(self, node):
        for node_vpath, tasks in self.lock_tasks.iteritems():
            if node_vpath == node.get_vpath():
                return tasks
        raise KeyError("no lock/unlock tasks for node %s" % node)

    def get_lock_task(self, node):
        return self.get_lock_unlock_tasks(node)[0]

    def get_unlock_task(self, node):
        return self.get_lock_unlock_tasks(node)[1]

    def get_lock_phase_index(self, task, phases):
        node = get_task_node(task)
        lock_task = self.get_lock_task(node)
        unlock_task = self.get_unlock_task(node)

        locked = False
        for pindex, phase in enumerate(phases):
            if phase == [lock_task]:
                locked = True
                lock_index = pindex
            elif phase == [unlock_task]:
                locked = False
            if task in phase:
                return lock_index if locked else -1
        raise ValueError("task %s is not found in phases: %s" %
                         (task, phases))

    def is_task_locked(self, task, phases):
        node = get_task_node(task)
        if not node:
            locked = False
            task_found = False
            for phase in phases:
                if task_found:
                    break
                for phase_task in phase:
                    if not locked and phase_task in self.all_lock_tasks:
                        locked = True
                        continue
                    elif locked and phase_task in self.all_unlock_tasks:
                        locked = False
                        continue
                    if phase_task is task:
                        task_found = True
                        break
            ret = locked
        else:
            ret = self.get_lock_phase_index(task, phases) >= 0
        return ret

    def tasks_in_same_lock(self, tasks, phases):
        pindex = self.get_lock_phase_index(tasks[0], phases)
        if pindex < 0:
            raise ValueError("some tasks %s are not in lock in phases: %s"
                             % (tasks, phases))
        for task in tasks[1:]:
            if pindex != self.get_lock_phase_index(task, phases):
                return False
        return True

    def assertTaskLocked(self, task, phases):
        if not self.is_task_locked(task, phases):
            raise AssertionError("task %s is not locked in phases: %s" %
                                 (task, phases))

    def assertTaskNotLocked(self, task, phases):
        if self.is_task_locked(task, phases):
            raise AssertionError("task %s is locked in phases: %s" %
                                 (task, phases))

    def assertTasksInSameLock(self, tasks, phases):
        if not self.tasks_in_same_lock(tasks, phases):
            raise AssertionError(
                "tasks %s are not in the same lock in phases: %s" %
                (tasks, phases))

    def assertTasksNotInSameLock(self, tasks, phases):
        if self.tasks_in_same_lock(tasks, phases):
            raise AssertionError(
                "tasks %s are in the same lock in phases: %s" %
                (tasks, phases))


class PlanBuilderTest(unittest.TestCase, PlanBuilderTestMixin):

    def setUp(self):
        self.manager = ModelManager()
        self.manager.register_property_type(
            PropertyType("basic_string")
        )
        self.manager.register_item_type(
            ItemType(
                "foo"
            )
        )
        self.manager.register_item_type(
            ItemType(
                "ms",
                hostname=Property("basic_string"),
                routes=Collection('dummy-item'),
                items=RefCollection("software-item"),
                configs=Collection('dummy-item')
            )
        )
        self.manager.register_item_type(
            ItemType(
                "os",
                name=Property("basic_string")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "system",
                name=Property("basic_string")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "network",
                name=Property("basic_string")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "route-base",
                name=Property("basic_string")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "infrastructure",
                resources=Collection("infra-stuff")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "infra-stuff",
                name=Property("basic_string")
            )
        )
        self.manager.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string"),
                is_locked=Property("basic_string", default="false"),
                network=Child("network", require="os"),
                os=Child("os", require="system"),
                system=Child("system"),
                items=RefCollection("software-item"),
                foo=Child("foo"),
                routes=Collection("route-base"),
                services=RefCollection("service-base"),
                test_property=Property("basic_string",
                                updatable_rest=True,
                                updatable_plugin=True),
            )
        )
        self.manager.register_item_type(
            ItemType(
                "root",
                #nodes=Collection("node", require="ms"),
                deployments=Collection("deployment"),
                ms=Child("ms"),
                infrastructure=Child("infrastructure"),
                software=Child("software", required=True),
            ),
        )
        self.manager.register_item_type(
            ItemType(
                "software",
                items=Collection("software-item"),
                services=Collection("service-base"),
            ),
        )
        self.manager.register_item_type(
            ItemType(
                "deployment",
                clusters=Collection("cluster"),
                ordered_clusters=View("basic_list",
                    callable_method=CoreExtension.get_ordered_clusters),
            ),
        )
        self.manager.register_item_type(
            ItemType(
                "cluster-base",
            )
        )
        self.manager.register_item_type(
            ItemType(
                "service-base",
            )
        )
        self.manager.register_item_type(
            ItemType(
                "service",
                extend_item="service-base",
                name=Property("basic_string"),
                packages=RefCollection("software-item"),
            )
        )
        self.manager.register_item_type(
            ItemType(
                "cluster",
                extend_item="cluster-base",
                dependency_list=Property("basic_string", default=""),
                nodes=Collection("node"),
                services=Collection("clustered-service", require="software"),
                software=RefCollection("software-item", require="nodes"),
            )
        )
        self.manager.register_item_type(
            ItemType(
                "clustered-service",
                name=Property("basic_string",
                              prop_description="Name of clustered service"),
                applications=RefCollection("service"),
            ),
        )
        self.manager.register_item_type(
            ItemType(
                "software-item",
            )
        )
        self.manager.register_item_type(
            ItemType(
                "package",
                extend_item="software-item",
                name=Property("basic_string"),
            )
        )
        self.manager.register_item_type(
            ItemType(
                "package-extended",
                extend_item="package",
            )
        )

        self.manager.register_item_type(
            ItemType(
                "yum-repository",
                extend_item="software-item",
            )
        )
        self.manager.register_item_type(
            ItemType(
                "yum-repository-extended",
                extend_item="yum-repository",
            )
        )

        self.manager.create_root_item("root")
        self.manager.register_item_type(
            ItemType("dummy-item")
        )
        self.manager.create_item("ms", "/ms", hostname="ms")
        self.manager.create_item("infrastructure", "/infrastructure")
        self.manager.create_item("deployment", "/deployments/d1")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c1")

        self.manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node1", hostname="node1")
        self.manager.create_item("os", "/deployments/d1/clusters/c1/nodes/node1/os", name="os1")
        self.manager.create_item("system", "/deployments/d1/clusters/c1/nodes/node1/system", name="sys1")
        self.manager.create_item("network", "/deployments/d1/clusters/c1/nodes/node1/network", name="net1")
        self.manager.create_item("package", "/software/items/package_a")
        self.manager.create_inherited("/software/items/package_a", "/deployments/d1/clusters/c1/nodes/node1/items/package_a")
        self.manager.create_item("package-extended", "/software/items/package_b")
        self.manager.create_inherited("/software/items/package_b", "/deployments/d1/clusters/c1/nodes/node1/items/package_b")
        self.manager.create_item("yum-repository", "/software/items/repo_a")
        self.manager.create_inherited("/software/items/repo_a", "/deployments/d1/clusters/c1/nodes/node1/items/repo_a")
        self.manager.create_item("yum-repository-extended", "/software/items/repo_b")
        self.manager.create_inherited("/software/items/repo_b", "/deployments/d1/clusters/c1/nodes/node1/items/repo_b")

        self.manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node2", hostname="node2")
        self.manager.create_item("os", "/deployments/d1/clusters/c1/nodes/node2/os", name="os2")
        self.manager.create_item("system", "/deployments/d1/clusters/c1/nodes/node2/system", name="sys2")
        self.manager.create_item("network", "/deployments/d1/clusters/c1/nodes/node2/network", name="net2")
        self.manager.create_item("package", "/software/items/package_a")
        self.manager.create_inherited("/software/items/package_a", "/deployments/d1/clusters/c1/nodes/node2/items/package_a")
        self.manager.create_item("package-extended", "/software/items/package_b")
        self.manager.create_inherited("/software/items/package_b", "/deployments/d1/clusters/c1/nodes/node2/items/package_b")
        self.manager.create_item("yum-repository", "/software/items/repo_a")
        self.manager.create_inherited("/software/items/repo_a", "/deployments/d1/clusters/c1/nodes/node2/items/repo_a")
        self.manager.create_item("yum-repository-extended", "/software/items/repo_b")
        self.manager.create_inherited("/software/items/repo_b", "/deployments/d1/clusters/c1/nodes/node2/items/repo_b")

        self.manager.create_inherited("/software/items/package_a", "/ms/items/package_a")

        ms = self.manager.query_by_vpath("/ms")
        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")

        self.lock_tasks = {
            node1.get_vpath(): (
                RemoteExecutionTask([node1], ms, "lock node1",
                                    "node", "lock", node=node1.hostname),
                RemoteExecutionTask([node1], ms, "unlock node1",
                                    "node", "unlock", node=node1.hostname),
            ),
            node2.get_vpath(): (
                RemoteExecutionTask([node2], ms, "lock node2", "node",
                                    "lock", node=node2.hostname),
                RemoteExecutionTask([node2], ms, "unlock node2", "node",
                                    "unlock", node=node2.hostname),
            )
        }

        self.all_lock_tasks = []
        self.all_unlock_tasks = []
        for lock_task, unlock_task in self.lock_tasks.values():
            self.all_lock_tasks.append(lock_task)
            self.all_unlock_tasks.append(unlock_task)

    def qi(self, mi):
        return QueryItem(self.manager, mi)

    def test_dont_reuse_equal_task_with_diff_group(self):
        # LITPCDS-13759
        node_qi = self.qi(self.manager.query("node")[0])
        prev_task = ConfigTask(node_qi, node_qi, 'Foo', 'bar', 'baz')
        prev_task.state = "Success"
        # Same task but with a different group
        current_task = ConfigTask(node_qi, node_qi, 'Foo', 'bar', 'baz')
        current_task.group = "DEPLOYMENT_MS_GROUP"
        self.assertEqual(prev_task, current_task)
        self.assertNotEqual(prev_task.group, current_task.group)
        # Current task correct group is used instead of previous task
        merged = merge_prev_successful_and_current_tasks(
                [prev_task], [current_task])
        self.assertEqual(1, len(merged))
        self.assertTrue(merged[0] is current_task)
        self.assertFalse(merged[0] is prev_task)

    def test_distinguish_between_initial_and_update_tasks_for_apd(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node1_qi._model_item.applied_properties_determinable = False

        # Different tasks, but considered the same for filtering
        prev_task = ConfigTask(node1_qi, node1_qi, "Previously Successful Task", "1", "1_1")
        prev_task.state = constants.TASK_SUCCESS
        current_task = ConfigTask(node1_qi, node1_qi, "Current Task", "1", "1_1")
        self.assertEqual(prev_task, current_task)

        builder = PlanBuilder(self.manager, [current_task])
        builder.previously_successful_tasks = [prev_task]
        # phases is a merge of prev successful and current tasks
        phases = [[prev_task, current_task]]

        # Assert that task1 doesn't come back due to its APD=False
        new_phase = builder._remove_prev_successful_tasks(phases)
        self.assertEqual([[current_task]], new_phase)
        self.assertEqual(len(new_phase), 1)
        self.assertEqual(len(new_phase[0]), 1)
        self.assertEqual("Current Task", new_phase[0][0].description)
        self.assertEqual(constants.TASK_INITIAL, new_phase[0][0].state)

    def test_require_dependency_with_another_task(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "1", "1_2")
        task1.requires = set([task2])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1, phases[0])
        self.assertEqual(task1._requires, set([task2.unique_id]))
        self.assertFalse(task2._requires)
        self.assertEqual(1, len(phases))

    def test_require_dependency_with_query_item(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "1", "1_2")
        task1.requires = set([node1_qi])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1 in phases[0])
        self.assertEqual(task1._requires, set([task2.unique_id]))
        self.assertFalse(task2._requires)
        self.assertEqual(1, len(phases))

    def test_require_dependency_with_query_item_between_callback_tasks(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = CallbackTask(node1_qi, "cb_task", _cb)
        task2 = CallbackTask(node2_qi, "cb_task", _cb2)
        task1.requires = set([node2_qi])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1 in phases[0])
        self.assertEqual(1, len(phases))

    def test_require_duplicate_dependencies(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "1", "1_2")
        # all dependencies resolve to same task
        task1.requires = set([node1_qi, task2])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1 in phases[0])
        self.assertEqual(task1._requires, set([task2.unique_id]))
        self.assertFalse(task2._requires)
        self.assertEquals(1, len(phases))

    def test_static_require_dependency(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_2")
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1 in phases[0])
        self.assertEqual(task1._requires, set([task2.unique_id]))
        self.assertFalse(task2._requires)
        self.assertEquals(1, len(phases))

    def test_indirect_static_require_dependency(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi.network, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_2")
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task1 in phases[0])
        self.assertEqual(task1._requires, set([task2.unique_id]))
        self.assertFalse(task2._requires)
        self.assertEquals(1, len(phases))

    def test_overriding_static_require_dependency(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_2")
        task2.requires = set([task1])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertEqual(task2._requires, set([task1.unique_id]))
        self.assertFalse(task1._requires)
        self.assertEquals(1, len(phases))

    def test_callback_without_require_in_same_phase(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = CallbackTask(node1_qi, "cb_task", _cb)
        task1.group = task2.group = deployment_plan_groups.MS_GROUP
        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task1 in phases[1])
        self.assertTrue(task2 in phases[0])
        self.assertFalse(task1._requires)
        self.assertEquals(2, len(phases))

    def test_config_with_require_on_callback_in_later_phase(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = CallbackTask(node1_qi, "cb_task", _cb)
        task1.requires = set([task2])
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2])
        phases = builder.build()
        #print phases
        self.assertTrue(task1 in phases[1])
        self.assertTrue(task2 in phases[0])
        self.assertFalse(task1._requires)
        self.assertEquals(2, len(phases))

    def test_callback_with_require_on_config_in_later_phase(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        task3 = CallbackTask(node1_qi, "cb_task", _cb)
        task2.requires = set([task1])
        task3.requires = set([task2])
        task1.group = task2.group = task3.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2, task3])
        phases = builder.build()
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task3 in phases[1])
        self.assertFalse(task1._requires)
        self.assertEqual(task2._requires, set([task1.unique_id]))
        self.assertEquals(2, len(phases))

    def test_callback_with_require_on_two_configs_in_later_phase(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        task3 = CallbackTask(node1_qi, "cb_task", _cb)
        task3.requires = set([task1, task2])
        task1.group = task2.group = task3.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task1, task2, task3])
        phases = builder.build()
        #print phases
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task3 in phases[1])
        self.assertFalse(task1._requires)
        self.assertFalse(task2._requires)
        self.assertEquals(2, len(phases))

    def test_callbacks_in_phase_ordered_as_input(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = CallbackTask(node1_qi, "cb_task", _cb)
        task2 = CallbackTask(node1_qi, "cb_task", _cb2)
        task1.group = task2.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task2, task1])
        phases = builder.build()

        self.assertEquals(1, len(phases))
        self.assertTrue(phases[0].index(task2) < phases[0].index(task1))

        # test when previous tasks are present
        task0 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task0.state = constants.TASK_SUCCESS
        task0a = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task1 = CallbackTask(node1_qi, "cb_task", _cb)
        task2 = CallbackTask(node1_qi, "cb_task", _cb2)
        task0.group = task0a.group = task1.group = task2.group \
            = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, [task2, task0a, task1])
        builder.previously_successful_tasks = [task0]
        phases = builder.build()

        self.assertEquals(1, len(phases))
        self.assertEquals(2, len(phases[0]))
        self.assertTrue(phases[0].index(task2) < phases[0].index(task1))

    def test_main_order(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "1", "1_2")
        task3 = ConfigTask(node1_qi, node1_qi, "", "1", "1_3")
        task4 = ConfigTask(node1_qi, node1_qi, "", "1", "1_4")

        task1.group = deployment_plan_groups.MS_GROUP
        task2.group = deployment_plan_groups.MS_GROUP
        task3.group = deployment_plan_groups.NODE_GROUP
        task4.group = deployment_plan_groups.CLUSTER_GROUP

        builder = PlanBuilder(self.manager, [task1, task2, task3, task4])
        phases = builder.build()

        self.assertEquals(3, len(phases))
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task3 in phases[1])
        self.assertTrue(task4 in phases[2])

    def test_initial_plan(self):
        """
        This UT simulates an end-to-end initial plan creation scenario.
        """

        tasks = []
        self.manager.create_item("infra-stuff", "/infrastructure/resources/infra", name="foo")

        ms_qi = self.qi(self.manager.query_by_vpath("/ms"))
        ms_task = ConfigTask(ms_qi, ms_qi, "", "cobbler", "node1")
        ms_task.group = deployment_plan_groups.MS_GROUP
        tasks.append(ms_task)

        def _wait_for_pxe_boot(*args, **kwargs):
            pass
        _wait_for_pxe_boot.im_class = cb_attrs
        _wait_for_pxe_boot.im_func = cb_attrs

        def _pre_node_cluster_operation(*args, **kwargs):
            pass
        _pre_node_cluster_operation.im_class = cb_attrs
        _pre_node_cluster_operation.im_func = cb_attrs

        def _post_node_cluster_operation(*args, **kwargs):
            pass
        _post_node_cluster_operation.im_class = cb_attrs
        _post_node_cluster_operation.im_func = cb_attrs

        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        boot_task = CallbackTask(node1_qi, "", _wait_for_pxe_boot)
        boot_task.plugin_name = 'bootmgr_plugin'
        boot_task.group = deployment_plan_groups.BOOT_GROUP
        tasks.append(boot_task)

        node_task = ConfigTask(node1_qi, node1_qi, "", "foo", "bar")
        node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node_task)

        node_cbtask = CallbackTask(node1_qi, "", _cb)
        node_cbtask.group = deployment_plan_groups.NODE_GROUP
        node_cbtask.requires.add(node_task)
        tasks.append(node_cbtask)

        other_node_task = ConfigTask(node1_qi, node1_qi, "", "baz", "quux")
        other_node_task.requires.add(node_cbtask)
        other_node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(other_node_task)

        cluster_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1"))
        pre_node_cluster_task = CallbackTask(cluster_qi, "", _pre_node_cluster_operation)
        pre_node_cluster_task.group = deployment_plan_groups.PRE_NODE_CLUSTER_GROUP
        tasks.append(pre_node_cluster_task)

        post_node_cluster_task = CallbackTask(cluster_qi, "", _post_node_cluster_operation)
        post_node_cluster_task.group = deployment_plan_groups.CLUSTER_GROUP
        tasks.append(post_node_cluster_task)

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()
        self.assertEquals(7, len(phases))
        self.assertTrue(all(1 == len(phase) for phase in phases))
        self.assertEquals([ms_task], phases[0])
        self.assertEquals([boot_task], phases[1])
        self.assertEquals([pre_node_cluster_task], phases[2])
        self.assertEquals([node_task], phases[3])
        self.assertEquals([node_cbtask], phases[4])
        self.assertEquals([other_node_task], phases[5])
        self.assertEquals([post_node_cluster_task], phases[6])

    def test_reinstall_plan(self):
        """
        This UT simulates an end-to-end reinstall plan creation scenario.
        """

        tasks = []
        self.manager.create_item("infra-stuff", "/infrastructure/resources/infra", name="foo")

        ms_qi = self.qi(self.manager.query_by_vpath("/ms"))
        ms_task = ConfigTask(ms_qi, ms_qi, "", "cobbler", "node1")
        ms_task.group = deployment_plan_groups.MS_GROUP
        tasks.append(ms_task)

        def _wait_for_pxe_boot(*args, **kwargs):
            pass

        _wait_for_pxe_boot.im_class = cb_attrs
        _wait_for_pxe_boot.im_func = cb_attrs

        def _pre_node_cluster_operation(*args, **kwargs):
            pass

        _pre_node_cluster_operation.im_class = cb_attrs
        _pre_node_cluster_operation.im_func = cb_attrs

        def _post_node_cluster_operation(*args, **kwargs):
            pass

        _post_node_cluster_operation.im_class = cb_attrs
        _post_node_cluster_operation.im_func = cb_attrs

        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        boot_task = CallbackTask(node1_qi, "", _wait_for_pxe_boot)
        boot_task.plugin_name = 'bootmgr_plugin'
        boot_task.group = deployment_plan_groups.BOOT_GROUP
        tasks.append(boot_task)

        node_task = ConfigTask(node1_qi, node1_qi, "", "foo", "bar")
        node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node_task)

        node_cbtask = CallbackTask(node1_qi, "", _cb)
        node_cbtask.group = deployment_plan_groups.NODE_GROUP
        node_cbtask.requires.add(node_task)
        tasks.append(node_cbtask)

        other_node_task = ConfigTask(node1_qi, node1_qi, "", "baz", "quux")
        other_node_task.requires.add(node_cbtask)
        other_node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(other_node_task)

        cluster_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1"))
        pre_node_cluster_task = CallbackTask(cluster_qi, "", _pre_node_cluster_operation)
        pre_node_cluster_task.group = deployment_plan_groups.PRE_NODE_CLUSTER_GROUP
        tasks.append(pre_node_cluster_task)

        post_node_cluster_task = CallbackTask(cluster_qi, "", _post_node_cluster_operation)
        post_node_cluster_task.group = deployment_plan_groups.CLUSTER_GROUP
        tasks.append(post_node_cluster_task)

        def _lock_node_operation(*args, **kwargs):
            pass

        _lock_node_operation.im_class = cb_attrs
        _lock_node_operation.im_func = cb_attrs

        def _unlock_node_operation(*args, **kwargs):
            pass

        _unlock_node_operation.im_class = cb_attrs
        _unlock_node_operation.im_func = cb_attrs

        lock_task = CallbackTask(node1_qi, "", _lock_node_operation)
        unlock_task = CallbackTask(node1_qi, "", _unlock_node_operation)

        builder = PlanBuilder(self.manager, tasks,
                              lock_tasks={
                              "/deployments/d1/clusters/c1/nodes/node1":
                                  (lock_task, unlock_task)})
        phases = builder.build()
        self.assertEquals(9, len(phases))
        self.assertTrue(all(1 == len(phase) for phase in phases))
        self.assertEquals([ms_task], phases[0])
        self.assertEquals([boot_task], phases[1])
        self.assertEquals([pre_node_cluster_task], phases[2])
        self.assertEquals([lock_task], phases[3])
        self.assertEquals([node_task], phases[4])
        self.assertEquals([node_cbtask], phases[5])
        self.assertEquals([other_node_task], phases[6])
        self.assertEquals([unlock_task], phases[7])
        self.assertEquals([post_node_cluster_task], phases[8])

    def test_upgrade_plan(self):
        """
        This UT simulates an end-to-end upgrade plan creation scenario.
        """

        tasks = []
        self.manager.create_item("infra-stuff", "/infrastructure/resources/infra", name="foo")

        def _lock_node_operation(*args, **kwargs):
            pass
        _lock_node_operation.im_class = cb_attrs
        _lock_node_operation.im_func = cb_attrs

        def _unlock_node_operation(*args, **kwargs):
            pass
        _unlock_node_operation.im_class = cb_attrs
        _unlock_node_operation.im_func = cb_attrs

        def _pre_node_cluster_operation(*args, **kwargs):
            pass
        _pre_node_cluster_operation.im_class = cb_attrs
        _pre_node_cluster_operation.im_func = cb_attrs

        def _post_node_cluster_operation(*args, **kwargs):
            pass
        _post_node_cluster_operation.im_class = cb_attrs
        _post_node_cluster_operation.im_func = cb_attrs

        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node1.set_applied()

        node1_qi = self.qi(node1)
        lock_task = CallbackTask(node1_qi, "", _lock_node_operation)
        unlock_task = CallbackTask(node1_qi, "", _unlock_node_operation)

        node_task = ConfigTask(node1_qi, node1_qi, "", "foo", "bar")
        node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node_task)

        node_cbtask = CallbackTask(node1_qi, "", _cb)
        node_cbtask.group = deployment_plan_groups.NODE_GROUP
        node_cbtask.requires.add(node_task)
        tasks.append(node_cbtask)

        other_node_task = ConfigTask(node1_qi, node1_qi, "", "baz", "quux")
        other_node_task.requires.add(node_cbtask)
        other_node_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(other_node_task)

        cluster_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1"))
        pre_node_cluster_task = CallbackTask(cluster_qi, "", _pre_node_cluster_operation)
        pre_node_cluster_task.group = deployment_plan_groups.PRE_NODE_CLUSTER_GROUP
        tasks.append(pre_node_cluster_task)

        post_node_cluster_task = CallbackTask(cluster_qi, "", _post_node_cluster_operation)
        post_node_cluster_task.group = deployment_plan_groups.CLUSTER_GROUP
        tasks.append(post_node_cluster_task)

        builder = PlanBuilder(self.manager, tasks, lock_tasks={"/deployments/d1/clusters/c1/nodes/node1": (lock_task, unlock_task)})
        phases = builder.build()
        self.assertEquals(7, len(phases))
        self.assertTrue(all(1 == len(phase) for phase in phases))
        self.assertEquals([pre_node_cluster_task], phases[0])
        self.assertEquals([lock_task], phases[1])
        self.assertEquals([node_task], phases[2])
        self.assertEquals([node_cbtask], phases[3])
        self.assertEquals([other_node_task], phases[4])
        self.assertEquals([unlock_task], phases[5])
        self.assertEquals([post_node_cluster_task], phases[6])

    def test_upgrade_plan_node_left_locked(self):
        """
        This UT simulates an upgrade plan creation scenario that involves
        unlocking a node left locked by a previous failed plan..
        """

        tasks = []
        self.manager.create_item("infra-stuff", "/infrastructure/resources/infra", name="foo")

        def _lock_node_operation(*args, **kwargs):
            pass
        _lock_node_operation.im_class = cb_attrs
        _lock_node_operation.im_func = cb_attrs

        def _unlock_node_operation(*args, **kwargs):
            pass
        _unlock_node_operation.im_class = cb_attrs
        _unlock_node_operation.im_func = cb_attrs

        def _pre_node_cluster_operation(*args, **kwargs):
            pass
        _pre_node_cluster_operation.im_class = cb_attrs
        _pre_node_cluster_operation.im_func = cb_attrs

        def _post_node_cluster_operation(*args, **kwargs):
            pass
        _post_node_cluster_operation.im_class = cb_attrs
        _post_node_cluster_operation.im_func = cb_attrs

        node1_mi = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node1_mi.set_property("is_locked", "false")
        node1_mi.set_updated()
        node1_qi = self.qi(node1_mi)

        # Node 2 is left in a locked state
        node2_mi = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")
        node2_mi.set_property("is_locked", "true")
        node2_mi.set_updated()
        node2_qi = self.qi(node2_mi)

        self.assertEquals(node2_mi, self.manager._node_left_locked())

        node1_lock_task = CallbackTask(node1_mi, "", _lock_node_operation)
        node1_lock_task.lock_type = Task.TYPE_LOCK
        node1_unlock_task = CallbackTask(node1_mi, "", _unlock_node_operation)
        node1_unlock_task.lock_type = Task.TYPE_UNLOCK

        node2_lock_task = CallbackTask(node2_mi, "", _lock_node_operation)
        node2_lock_task.lock_type = Task.TYPE_LOCK
        node2_unlock_task = CallbackTask(node2_mi, "", _unlock_node_operation)
        node2_unlock_task.lock_type = Task.TYPE_UNLOCK


        # Create another cluster
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2")
        self.manager.create_item("node", "/deployments/d1/clusters/c2/nodes/node3", hostname="node3")
        node3_mi = self.manager.query_by_vpath("/deployments/d1/clusters/c2/nodes/node3")
        node3_qi = self.qi(node3_mi)

        self.manager.query_by_vpath("/deployments/d1/clusters/c1").set_property("dependency_list", "c2")


        # Generate ConfigTasks
        node1_task = ConfigTask(node1_qi, node1_qi, "", "foo", "bar")
        node1_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node1_task)
        node2_task = ConfigTask(node2_qi, node2_qi, "", "foo", "bar")
        node2_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node2_task)
        node3_task = ConfigTask(node3_qi, node3_qi, "", "foo", "bar")
        node3_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(node3_task)

        # ... And CallbackTasks
        node1_cbtask = CallbackTask(node1_qi, "", _cb)
        node1_cbtask.group = deployment_plan_groups.NODE_GROUP
        node1_cbtask.requires.add(node1_task)
        tasks.append(node1_cbtask)
        node2_cbtask = CallbackTask(node2_qi, "", _cb)
        node2_cbtask.group = deployment_plan_groups.NODE_GROUP
        node2_cbtask.requires.add(node2_task)
        tasks.append(node2_cbtask)

        other_node1_task = ConfigTask(node1_qi, node1_qi, "", "baz", "quux")
        other_node1_task.requires.add(node1_cbtask)
        other_node1_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(other_node1_task)
        other_node2_task = ConfigTask(node2_qi, node2_qi, "", "baz", "quux")
        other_node2_task.requires.add(node2_cbtask)
        other_node2_task.group = deployment_plan_groups.NODE_GROUP
        tasks.append(other_node2_task)

        cluster_mi = self.manager.query_by_vpath("/deployments/d1/clusters/c1")
        pre_node_cluster_task = CallbackTask(self.qi(cluster_mi), "", _pre_node_cluster_operation)
        pre_node_cluster_task.group = deployment_plan_groups.PRE_NODE_CLUSTER_GROUP
        tasks.append(pre_node_cluster_task)

        post_node_cluster_task = CallbackTask(self.qi(cluster_mi), "", _post_node_cluster_operation)
        post_node_cluster_task.group = deployment_plan_groups.CLUSTER_GROUP
        tasks.append(post_node_cluster_task)

        lock_tasks={
            "/deployments/d1/clusters/c1/nodes/node1": (node1_lock_task, node1_unlock_task),
            "/deployments/d1/clusters/c1/nodes/node2": (node2_lock_task, node2_unlock_task),
        }
        builder = PlanBuilder(
            self.manager,
            tasks,
            lock_tasks=lock_tasks,
        )
        phases = builder.build()

        # Cluster 2 is processed first
        self.assertEquals([node3_task], phases[0])
        self.assertEquals([pre_node_cluster_task], phases[1])
        self.assertEquals([node2_unlock_task], phases[2])

    def test_config_task_order_in_phase_reflects_dependencies(self):
        node1 = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2 = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = ConfigTask(node1, node1, "", "1", "1_1")
        task2 = ConfigTask(node1, node1, "", "1", "1_2")
        task3 = ConfigTask(node1, node1, "", "1", "1_3")
        task4 = ConfigTask(node1, node1, "", "1", "1_4")
        task5 = ConfigTask(node1, node2, "", "1", "1_5")
        task6 = ConfigTask(node1, node2, "", "1", "1_6")
        task7 = ConfigTask(node1, node1, "", "1", "1_7")
        task8 = ConfigTask(node1, node1, "", "1", "1_8")
        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP
        task5.group = task6.group = task7.group = task8.group = deployment_plan_groups.NODE_GROUP
        task1.requires.add(task2)
        task1.requires.add(task3)
        task3.requires.add(task4)
        builder = PlanBuilder(self.manager, [task4, task7, task6, task8,
                                             task5, task2, task3, task1])
        phases = builder.build()
        self.assertTrue(phases[0].index(task1) > phases[0].index(task2))
        self.assertTrue(phases[0].index(task1) > phases[0].index(task3))
        self.assertTrue(phases[0].index(task3) > phases[0].index(task4))

    def test_node_locking_tasks(self):
        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")
        node1.set_updated()
        node2.set_updated()

        node1_qi = self.qi(node1)
        node2_qi = self.qi(node2)
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        task3 = ConfigTask(node2_qi, node2_qi, "", "3", "1_3")
        task4 = ConfigTask(node2_qi, node2_qi, "", "3", "1_4")

        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(self.manager, [task1, task2, task3, task4], self.lock_tasks)
        #builder.lock_tasks = self.lock_tasks
        phases = builder.build()

        self.assertTasksNotInSameLock([task1, task3], phases)
        #print phases
        self.assertEquals(6, len(phases))
        self.assertTasksInSameLock([task1, task2], phases)
        self.assertTasksInSameLock([task3, task4], phases)
        self.assertTasksNotInSameLock([task1, task3], phases)

    def test_node_locking_tasks_when_multiple_node_phases(self):
        def cb_attrs():
            pass
        _cb.im_class = cb_attrs
        _cb.im_func = cb_attrs

        def _cb2(*args, **kwargs):
            pass
        _cb2.im_class = cb_attrs
        _cb2.im_func = cb_attrs

        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")
        node1.set_updated()
        node2.set_updated()

        node1_qi = self.qi(node1)
        node2_qi = self.qi(node2)
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = CallbackTask(node1_qi, "cb_task", _cb)
        task3 = ConfigTask(node2_qi, node2_qi, "", "3", "1_3")
        task4 = CallbackTask(node2_qi, "cb_task", _cb2)

        task2.requires = set([task1])
        task4.requires = set([task3])
        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(self.manager, [task1, task2, task3, task4],
                self.lock_tasks)
        #builder.lock_tasks = self.lock_tasks
        phases = builder.build()
        #print phases
        self.assertEquals(8, len(phases))
        self.assertTasksInSameLock([task1, task2], phases)
        self.assertTasksInSameLock([task3, task4], phases)
        self.assertTasksNotInSameLock([task1, task3], phases)

    def test_node_locking_tasks_when_node_in_initial(self):
        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")

        node1_qi = self.qi(node1)
        node2_qi = self.qi(node2)
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        task3 = ConfigTask(node2_qi, node2_qi, "", "3", "1_3")
        task4 = ConfigTask(node2_qi, node2_qi, "", "4", "1_4")

        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP

        # only one node locked
        lock_tasks = dict([(k, v) for k, v in self.lock_tasks.items()
                           if k == node1.get_vpath()])
        builder = PlanBuilder(self.manager, [task1, task2, task3, task4],
               [])
        #builder.lock_tasks = lock_tasks
        phases = builder.build()
        #print phases

        # We want the lock/unlock task pair for node1 to be discarded
        # There is no reason to segregate the nodes - everything should be in one phase
        self.assertEquals(1, len(phases))
        for phase in phases:
            self.assertFalse(lock_tasks[node1.get_vpath()][0] in phase)
            self.assertFalse(lock_tasks[node1.get_vpath()][1] in phase)
            for task in phase:
                self.assertTaskNotLocked(task, phases)

    def test_config_task_requiring_multiple_config_tasks(self):
        node1 = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        task1 = ConfigTask(node1, node1, "", "1", "1_1")
        task2 = ConfigTask(node1, node1, "", "2", "1_2")
        task3 = ConfigTask(node1, node1, "", "3", "1_3")

        task1.group = task2.group = task3.group = deployment_plan_groups.NODE_GROUP
        task1.requires = set([task2, task3])

        builder = PlanBuilder(self.manager, [task1, task2, task3])
        phases = builder.build()
        #print phases
        self.assertTrue(1, len(phases))
        self.assertEqual(task1._requires, set([task2.unique_id,
                                               task3.unique_id]))

    def test_no_requires_for_children_of_dependent_colls_across_nodes(self):
        manager = ModelManager()
        manager.register_property_type(PropertyType("basic_string"))
        manager.register_item_types([
            ItemType("os"),
            ItemType("system"),
            ItemType("node", hostname=Property("basic_string"),
                     is_locked=Property("basic_string", default="false"),
                     os=Child("os"),
                     system=Child("system", require="os")),

            ItemType("root", deployments=Collection("deployment")),
            ItemType(
                "deployment",
                clusters=Collection("cluster"),
                ordered_clusters=View("basic_list",
                    callable_method=CoreExtension.get_ordered_clusters),
            ),
            ItemType(
                "cluster-base",
            ),
            ItemType(
                "cluster",
                extend_item="cluster-base",
                nodes=Collection("node"),
            ),
        ])
        manager.create_root_item("root")
        manager.create_item("deployment", "/deployments/d1")
        manager.create_item("cluster", "/deployments/d1/clusters/c1")
        manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node1", hostname="node1")
        manager.create_item("os", "/deployments/d1/clusters/c1/nodes/node1/os")
        manager.create_item("system", "/deployments/d1/clusters/c1/nodes/node1/system")
        manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node2", hostname="node2")
        manager.create_item("os", "/deployments/d1/clusters/c1/nodes/node2/os")
        manager.create_item("system", "/deployments/d1/clusters/c1/nodes/node2/system")

        node1_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))

        task1 = ConfigTask(node1_qi, node1_qi.os, "task node1_qi os",
                           "node1_qi os", "1")
        task2 = ConfigTask(node1_qi, node1_qi.system, "task node1_qi system",
                           "node1_qi node1_qi system", "2")
        task3 = ConfigTask(node2_qi, node2_qi.system, "task node2_qi system",
                           "node2_qi node2_qi system", "3")
        task4 = ConfigTask(node1_qi, node2_qi.system, "task node2_qi system",
                           "node1_qi node2_qi system", "4")
        task5 = ConfigTask(node2_qi, node1_qi.system, "task node1_qi system",
                           "node2_qi node1_qi system", "5")

        task1.group = task2.group = task3.group \
            = task4.group = task5.group = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(manager, [task1, task2, task3, task4, task5])
        builder.build()
        self.assertEquals(task1._requires, set())
        self.assertEquals(task2._requires, set([task1.unique_id]))
        self.assertEquals(task3._requires, set())
        self.assertEquals(task4._requires, set())
        self.assertEquals(task5._requires, set())

    def test_cluster_fw_config_tasks_treated_like_node_routes_tasks(self):
        manager = ModelManager()
        manager.register_property_type(
            PropertyType("basic_string", regex=r"^.*$"))

        manager.register_item_types([
            ItemType("root", deployments=Collection("deployment")),
            ItemType(
                "deployment",
                clusters=Collection("cluster"),
                ordered_clusters=View("basic_list",
                    callable_method=CoreExtension.get_ordered_clusters),
            ),
            ItemType(
                "cluster-base",
            ),
            ItemType(
                "cluster",
                extend_item="cluster-base",
                nodes=Collection("node"),
                configs=Collection("cluster-config")
            ),
            ItemType("cluster-config", rules=Collection("dummy-item")),
            ItemType("firewall-cluster-config", extend_item="cluster-config",
                     rules=Collection("dummy-item")),
            ItemType("node",
                     hostname=Property("basic_string"),
                     is_locked=Property("basic_string"),
                     configs=Collection("dummy-item",
                                        require="file_systems"),
                     routes=Collection("dummy-item"),
                     file_systems=Collection("dummy-item",
                                             require="routes")),
            ItemType("dummy-item")])

        manager.create_root_item("root")
        manager.create_item("deployment", "/deployments/d1")
        manager.create_item("cluster", "/deployments/d1/clusters/c1")
        manager.create_item("cluster-config", "/deployments/d1/clusters/c1/configs/cfg")
        manager.create_item("firewall-cluster-config",
                            "/deployments/d1/clusters/c1/configs/fw_cfg1")
        manager.create_item("firewall-cluster-config",
                            "/deployments/d1/clusters/c1/configs/fw_cfg2")
        manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node1")
        manager.create_item("dummy-item",
                            "/deployments/d1/clusters/c1/nodes/node1/file_systems/fs")


        # We need to bind self.manager to the ModelManager instance prepared in
        # this test in order to use the qi conversion method
        self.manager = manager
        node_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        fs_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/file_systems/fs"))
        cfg_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/configs/cfg"))
        fw_cfg1_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/configs/fw_cfg1"))
        fw_cfg2_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/configs/fw_cfg2"))


        task1 = ConfigTask(node_qi, fs_qi, "task node1 filesystem",
                           "task node1 filesystem", "1")
        task2 = ConfigTask(node_qi, cfg_qi, "task cluster config",
                           "task cluster config", "2")
        task3 = ConfigTask(node_qi, fw_cfg1_qi, "task fw cluster config",
                           "task fw cluster config", "3")
        task4 = ConfigTask(node_qi, fw_cfg2_qi, "task fw cluster config",
                           "task fw cluster config", "4")
        task1.group = task2.group = task3.group = task4.group \
            = deployment_plan_groups.NODE_GROUP
        builder = PlanBuilder(manager, [task1, task2, task3, task4])
        builder.build()

        # config other than firewall-cluster-config shouldn't be treated
        # in a special way
        self.assertEquals(task1._requires, set([task3.unique_id,
                                                task4.unique_id]))
        self.assertEquals(task2.model_item, cfg_qi)
        self.assertEquals(task3.model_item, fw_cfg1_qi)
        self.assertEquals(task4.model_item, fw_cfg2_qi)

    def test_node_fw_config_tasks_treated_like_node_routes_tasks(self):
        manager = ModelManager()
        manager.register_property_type(
            PropertyType("basic_string", regex=r"^.*$"))
        manager.register_item_types([
            ItemType("root", deployments=Collection("deployment")),
            ItemType(
                "deployment",
                clusters=Collection("cluster"),
                ordered_clusters=View("basic_list",
                    callable_method=CoreExtension.get_ordered_clusters),
            ),
            ItemType("cluster-base"),
            ItemType("cluster", extend_item="cluster-base", nodes=Collection("node")),
            ItemType("node-config", rules=Collection("dummy-item")),
            ItemType("firewall-node-config", extend_item="node-config",
                     rules=Collection("dummy-item")),
            ItemType("node",
                     hostname=Property("basic_string"),
                     is_locked=Property("basic_string"),
                     configs=Collection("node-config",
                                        require="file_systems"),
                     routes=Collection("dummy-item"),
                     file_systems=Collection("dummy-item",
                                             require="routes")),
            ItemType("dummy-item")])

        manager.create_root_item("root")
        manager.create_item("deployment", "/deployments/d1")
        manager.create_item("cluster", "/deployments/d1/clusters/c1")
        manager.create_item("node", "/deployments/d1/clusters/c1/nodes/node1")
        manager.create_item("node-config",
                            "/deployments/d1/clusters/c1/nodes/node1/configs/cfg")
        manager.create_item("firewall-node-config",
                            "/deployments/d1/clusters/c1/nodes/node1/configs/fw_cfg1")
        manager.create_item("firewall-node-config",
                            "/deployments/d1/clusters/c1/nodes/node1/configs/fw_cfg2")
        manager.create_item("dummy-item",
                            "/deployments/d1/clusters/c1/nodes/node1/file_systems/fs")

        self.manager = manager
        node_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        fs_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/file_systems/fs"))
        cfg_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/configs/cfg"))
        fw_cfg1_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/configs/fw_cfg1"))
        fw_cfg2_qi = self.qi(manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/configs/fw_cfg2"))

        task1 = ConfigTask(node_qi, fs_qi, "task node1 filesystem",
                           "task node1 filesystem", "1")
        task2 = ConfigTask(node_qi, cfg_qi, "task cluster config",
                           "task cluster config", "2")
        task3 = ConfigTask(node_qi, fw_cfg1_qi, "task fw cluster config",
                           "task fw cluster config", "3")
        task4 = ConfigTask(node_qi, fw_cfg2_qi, "task fw cluster config",
                           "task fw cluster config", "4")
        task1.group = task2.group = task3.group = task4.group \
            = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(manager, [task1, task2, task3, task4])
        builder.build()

        # config other than firewall-node-config shouldn't be treated
        # in a special way
        self.assertEquals(task1._requires, set([task3.unique_id,
                                                task4.unique_id]))
        self.assertEquals(task2.model_item, cfg_qi)
        self.assertEquals(task3.model_item, fw_cfg1_qi)
        self.assertEquals(task4.model_item, fw_cfg2_qi)

    def test_ms_fw_config_tasks_treated_like_ms_routes_tasks(self):
        manager = ModelManager()
        manager.register_property_type(
            PropertyType("basic_string", regex=r"^.*$"))
        manager.register_item_types([
            ItemType("root", cluster=Child("cluster"), ms=Child('ms')),
            ItemType("cluster", nodes=Collection("dummy-item")),
            ItemType("node-config", rules=Collection("dummy-item")),
            ItemType("firewall-node-config", extend_item="node-config",
                     rules=Collection("dummy-item")),
            ItemType("ms",
                     hostname=Property("basic_string"),
                     configs=Collection("node-config",
                                        require="file_systems"),
                     routes=Collection("dummy-item"),
                     file_systems=Collection("dummy-item",
                                             require="routes")),
            ItemType("dummy-item")])

        manager.create_root_item("root")
        manager.create_item("cluster", "/cluster")
        manager.create_item("ms", "/ms")
        manager.create_item("node-config",
                            "/ms/configs/cfg")
        manager.create_item("firewall-node-config",
                            "/ms/configs/fw_cfg1")
        manager.create_item("firewall-node-config",
                            "/ms/configs/fw_cfg2")
        manager.create_item("dummy-item",
                            "/ms/file_systems/fs")

        self.manager = manager
        ms_qi = self.qi(manager.query_by_vpath("/ms"))
        fs_qi = self.qi(manager.query_by_vpath("/ms/file_systems/fs"))
        cfg_qi = self.qi(manager.query_by_vpath("/ms/configs/cfg"))
        fw_cfg1_qi = self.qi(manager.query_by_vpath("/ms/configs/fw_cfg1"))
        fw_cfg2_qi = self.qi(manager.query_by_vpath("/ms/configs/fw_cfg2"))

        task1 = ConfigTask(ms_qi, fs_qi, "task node1 filesystem",
                           "task node1 filesystem", "1")
        task2 = ConfigTask(ms_qi, cfg_qi, "task cluster config",
                           "task cluster config", "2")
        task3 = ConfigTask(ms_qi, fw_cfg1_qi, "task fw cluster config",
                           "task fw cluster config", "3")
        task4 = ConfigTask(ms_qi, fw_cfg2_qi, "task fw cluster config",
                           "task fw cluster config", "4")
        task1.group = task2.group = task3.group = task4.group \
            = deployment_plan_groups.MS_GROUP
        builder = PlanBuilder(manager, [task1, task2, task3, task4])
        builder.build()

        # config other than firewall-node-config shouldn't be treated
        # in a special way
        self.assertEquals(task1._requires, set([task3.unique_id,
                                                task4.unique_id]))
        self.assertEquals(task2._requires, set([task1.unique_id,
                                                task3.unique_id,
                                                task4.unique_id]))
        self.assertEquals(task2.model_item, cfg_qi)
        self.assertEquals(task3.model_item, fw_cfg1_qi)
        self.assertEquals(task4.model_item, fw_cfg2_qi)

    def test_task_dependencies_task_in_separate_phase(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        tasks = []
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        tasks.append(task1)
        task2 = CallbackTask(node1_qi, "cb_task 2", _cb)
        tasks.append(task2)
        task2.requires.add(task1)
        task3 = ConfigTask(node1_qi, node1_qi, "", "3", "1_3")
        tasks.append(task3)
        task3.requires.add(task2)
        # FIXME!!!
        # do we ever allow Callback tasks with same node and callback????
        #task4 = CallbackTask(node1, "cb_task 4", _cb)
        task4 = CallbackTask(node1_qi, "cb_task 4", _cb2)
        tasks.append(task4)
        task4.requires.add(task3)
        task5 = ConfigTask(node1_qi, node1_qi, "", "5", "1_5")
        tasks.append(task5)
        task5.requires.add(task4)
        # should be in the same phase as task5
        task6 = ConfigTask(node1_qi, node1_qi, "", "6", "1_6")
        tasks.append(task6)
        task6.requires.add(task5)

        for task in tasks:
            task.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(5, len(phases))
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[1])
        self.assertTrue(task3 in phases[2])
        self.assertTrue(task4 in phases[3])
        self.assertTrue(task5 in phases[4])
        self.assertTrue(task6 in phases[4])
        self.assertEqual(set(), task1._requires)
        self.assertEqual(set([task1.unique_id]), task3._requires)
        self.assertEqual(set([task1.unique_id, task3.unique_id]),
                         task5._requires)

    def test_task_dependencies_configtask_requires_callbacktask(self):
        # LITPCDS-7693
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        tasks = []

        task0 = CallbackTask(node1_qi, "cb", _cb)
        tasks.append(task0)

        task11 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task11.requires.add(task0)
        tasks.append(task11)
        task12 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_2")
        task12.requires.add(task11)
        tasks.append(task12)
        task13 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_3")
        task13.requires.add(task12)
        tasks.append(task13)

        task2 = ConfigTask(node1_qi, node1_qi.os, "", "2", "2_1")
        task2.requires.add(task13)
        tasks.append(task2)

        for task in tasks:
            task.group = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(2, len(phases))
        self.assertTrue(task0 in phases[0])
        self.assertTrue(task11 in phases[1])
        self.assertTrue(task12 in phases[1])
        self.assertTrue(task13 in phases[1])
        self.assertTrue(task2 in phases[1])

    def test_bond_task_dependencies_vxvm_upgrade_case1(self):
        # TORF-323439
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))

        task0 = CallbackTask(node1_qi, "cb1", _cb)
        task1 = CallbackTask(node1_qi, "cb2", _cb2)
        task2 = CallbackTask(node2_qi, "cb3", _cb)
        task3 = CallbackTask(node2_qi, "cb4", _cb2)
        tasks = [task0, task1, task2, task3]

        for task in tasks:
            task.group = deployment_plan_groups.VXVM_UPGRADE_GROUP
            task.tag_name = VXVM_UPGRADE_TAG


        task11 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task11.group = deployment_plan_groups.NODE_GROUP
        task11._pre_vxvm_bond = True
        tasks.append(task11)
        task12 = ConfigTask(node2_qi, node2_qi, "", "1", "1_2")
        task12.group = deployment_plan_groups.NODE_GROUP
        task12._pre_vxvm_bond = True
        tasks.append(task12)

        builder = PlanBuilder(self.manager, tasks)
        builder._ensure_presence_of_both_vxvm_upgrade_and_bond(tasks)

        self.assertTrue(task11.group == deployment_plan_groups.VXVM_UPGRADE_GROUP)
        self.assertTrue(task12.group == deployment_plan_groups.VXVM_UPGRADE_GROUP)

    def test_bond_task_dependencies_vxvm_upgrade_case2(self):
        # TORF-323439
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))

        task0 = CallbackTask(node1_qi, "cb1", _cb)
        task1 = CallbackTask(node1_qi, "cb2", _cb2)
        task2 = CallbackTask(node2_qi, "cb3", _cb)
        task3 = CallbackTask(node2_qi, "cb4", _cb2)
        tasks = [task0, task1, task2, task3]

        for task in tasks:
            task.group = deployment_plan_groups.VXVM_UPGRADE_GROUP
            task.tag_name = VXVM_UPGRADE_TAG


        task11 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task11.group = deployment_plan_groups.NODE_GROUP
        tasks.append(task11)
        task12 = ConfigTask(node2_qi, node2_qi, "", "1", "1_2")
        task12.group = deployment_plan_groups.NODE_GROUP
        tasks.append(task12)

        builder = PlanBuilder(self.manager, tasks)
        builder._ensure_presence_of_both_vxvm_upgrade_and_bond(tasks)

        self.assertTrue(task11.group != deployment_plan_groups.VXVM_UPGRADE_GROUP)
        self.assertTrue(task12.group != deployment_plan_groups.VXVM_UPGRADE_GROUP)

    def test_bond_task_dependencies_vxvm_upgrade_case3(self):
        # TORF-323439
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))

        task0 = CallbackTask(node1_qi, "cb1", _cb)
        task1 = CallbackTask(node1_qi, "cb2", _cb2)
        tasks = [task0, task1]

        for task in tasks:
            task.group = deployment_plan_groups.VXVM_UPGRADE_GROUP
            task.tag_name = VXVM_UPGRADE_TAG


        task11 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task11.group = deployment_plan_groups.NODE_GROUP
        task11._pre_vxvm_bond = True
        tasks.append(task11)
        task12 = ConfigTask(node2_qi, node2_qi, "", "1", "1_2")
        task12.group = deployment_plan_groups.NODE_GROUP
        task12._pre_vxvm_bond = True
        tasks.append(task12)

        builder = PlanBuilder(self.manager, tasks)
        builder._ensure_presence_of_both_vxvm_upgrade_and_bond(tasks)

        self.assertTrue(task11.group == deployment_plan_groups.VXVM_UPGRADE_GROUP)
        self.assertTrue(task12.group != deployment_plan_groups.VXVM_UPGRADE_GROUP)

    def test_task_dependencies_dependency_type_task(self):
        self.manager.create_item("foo", "/deployments/d1/clusters/c1/nodes/node1/foo")
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        tasks = []
        task1 = ConfigTask(node1_qi, node1_qi.foo, "", "1", "1_1")
        tasks.append(task1)
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        tasks.append(task2)
        task2.requires.add(task1)
        task3 = ConfigTask(node1_qi, node1_qi.system, "", "3", "1_3")
        tasks.append(task3)
        task4 = ConfigTask(node1_qi, node1_qi.os, "", "4", "1_4")
        tasks.append(task4)
        task4.requires.add(task3)

        for task in tasks:
            task.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(1, len(phases))
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task3 in phases[0])
        self.assertTrue(task4 in phases[0])

        # check if dependency info for puppet set
        self.assertEqual(set(), task1._requires)
        self.assertEqual(set([task1.unique_id]), task2._requires)
        self.assertEqual(set(), task3._requires)
        self.assertEqual(set([task3.unique_id]), task4._requires)

    def test_task_dependencies_dependency_type_item(self):
        self.manager.create_item("foo", "/deployments/d1/clusters/c1/nodes/node1/foo")
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        tasks = []
        task1 = ConfigTask(node1_qi, node1_qi.foo, "", "1", "1_1")
        tasks.append(task1)
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        tasks.append(task2)
        task2.requires.add(node1_qi.foo)
        task3 = ConfigTask(node1_qi, node1_qi.system, "", "3", "1_3")
        tasks.append(task3)
        task4 = ConfigTask(node1_qi, node1_qi.os, "", "4", "1_4")
        tasks.append(task4)
        task4.requires.add(node1_qi.system)

        for task in tasks:
            task.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(1, len(phases))
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])
        self.assertTrue(task3 in phases[0])
        self.assertTrue(task4 in phases[0])

        # check if dependency info for puppet set
        self.assertEqual(set(), task1._requires)
        self.assertEqual(set([task1.unique_id]), task2._requires)
        self.assertEqual(set(), task3._requires)
        self.assertEqual(set([task3.unique_id]), task4._requires)

    def test_task_dependencies_dependency_type_model(self):
        self.manager.create_item("foo", "/deployments/d1/clusters/c1/nodes/node1/foo")
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        tasks = []
        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        tasks.append(task1)
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "2", "1_2")
        tasks.append(task2)

        for task in tasks:
            task.group = deployment_plan_groups.MS_GROUP

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(1, len(phases))
        self.assertTrue(task1 in phases[0])
        self.assertTrue(task2 in phases[0])

        # check if dependency info for puppet set
        self.assertEqual(set(), task1._requires)
        self.assertEqual(set([task1.unique_id]), task2._requires)

    def _cluster_dependencies_helper(self):
        self._cluster_items()
        return self._cluster_tasks()

    def _cluster_items(self):
        self.manager.create_item("node",
                "/deployments/d1/clusters/c2/nodes/node1", hostname="node1")
        self.manager.create_item("node",
                "/deployments/d1/clusters/c2/nodes/node2", hostname="node2")
        self.manager.create_item("node",
                "/deployments/d1/clusters/c3/nodes/node1", hostname="node1")
        self.manager.create_item("node",
                "/deployments/d1/clusters/c3/nodes/node2", hostname="node2")
        self.manager.create_item("node",
                "/deployments/d1/clusters/c4/nodes/node1", hostname="node1")
        self.manager.create_item("node",
                "/deployments/d1/clusters/c4/nodes/node2", hostname="node2")

    def _cluster_tasks(self):
        c1node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        c1node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        c2node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c2/nodes/node1"))
        c2node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c2/nodes/node2"))
        c3node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c3/nodes/node1"))
        c3node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c3/nodes/node2"))
        c4node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c4/nodes/node1"))
        c4node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c4/nodes/node2"))

        task1 = ConfigTask(c1node1_qi, c1node1_qi, "task1", "1", "1_1")
        task2 = ConfigTask(c1node2_qi, c1node2_qi, "task2", "1", "1_2")
        task3 = ConfigTask(c2node1_qi, c2node1_qi, "task3", "1", "2_1")
        task4 = ConfigTask(c2node2_qi, c2node2_qi, "task4", "1", "2_2")
        task5 = ConfigTask(c3node1_qi, c3node1_qi, "task5", "1", "3_1")
        task6 = ConfigTask(c3node2_qi, c3node2_qi, "task6", "1", "3_2")
        task7 = ConfigTask(c4node1_qi, c4node1_qi, "task7", "1", "4_1")
        task8 = ConfigTask(c4node2_qi, c4node2_qi, "task8", "1", "4_2")
        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP
        task5.group = task6.group = task7.group = task8.group = deployment_plan_groups.NODE_GROUP
        return [task1, task2, task3, task4, task5, task6, task7, task8]

    def _cluster_lock_tasks(self, node_vpath):
        node_qi = self.qi(self.manager.query_by_vpath(node_vpath))
        lock_task = ConfigTask(node_qi, node_qi, "lock", "1", "mock lock")
        unlock_task = ConfigTask(node_qi, node_qi, "unlock", "1", "mock unlock")
        return {node_qi.get_vpath():[lock_task, unlock_task]}

    def test_cluster_no_dependencies(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)

        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[2]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[3]), set([tasks[6],tasks[7]]))

    def test_cluster_dependencies(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c3")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c1")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c2")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[2]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[3]), set([tasks[6],tasks[7]]))

        self.manager.set_all_applied()
        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[2]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[3]), set([tasks[6],tasks[7]]))

    def test_cluster_dependencies_locked_tasks(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c3")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c1")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c2")

        tasks = self._cluster_dependencies_helper()
        lock_tasks = self._cluster_lock_tasks("/deployments/d1/clusters/c3/nodes/node2")
        builder = PlanBuilder(self.manager, tasks, [])
        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[2]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[3]), set([tasks[6],tasks[7]]))

        self.manager.set_all_applied()
        lock_tasks = self._cluster_lock_tasks("/deployments/d1/clusters/c2/nodes/node2")
        builder = PlanBuilder(self.manager, tasks, lock_tasks)
        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[2]), set([lock_tasks.values()[0][0]]))
        self.assertEquals(set(phases[3]), set([tasks[3]]))
        self.assertEquals(set(phases[4]), set([lock_tasks.values()[0][1]]))
        self.assertEquals(set(phases[5]), set([tasks[2]]))
        self.assertEquals(set(phases[6]), set([tasks[6],tasks[7]]))

    def test_cluster_multi_dependencies_1(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c1")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c1")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c1")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)
        c2node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c2/nodes/node2")

        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[2]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[3]), set([tasks[6],tasks[7]]))

    def test_cluster_multi_dependencies_2(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c1")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)

        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[6],tasks[7]]))
        self.assertEquals(set(phases[2]), set([tasks[2],tasks[3]]))
        self.assertEquals(set(phases[3]), set([tasks[4],tasks[5]]))

    def test_cluster_multi_dependencies_3(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c1,c3,c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c1,c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c1")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)

        phases = builder.build()
        self.assertEquals(set(phases[0]), set([tasks[0],tasks[1]]))
        self.assertEquals(set(phases[1]), set([tasks[6],tasks[7]]))
        self.assertEquals(set(phases[2]), set([tasks[4],tasks[5]]))
        self.assertEquals(set(phases[3]), set([tasks[2],tasks[3]]))

    def test_cluster_cyclic_dependencies(self):
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c3")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c2")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)

        self.assertRaises(ViewError, builder.build)

        # testing multi-cyclic dependencies
        self.manager.create_item("cluster", "/deployments/d1/clusters/c2",
                dependency_list="c1,c3,c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c3",
                dependency_list="c1,c4")
        self.manager.create_item("cluster", "/deployments/d1/clusters/c4",
                dependency_list="c1,c3")

        tasks = self._cluster_dependencies_helper()
        builder = PlanBuilder(self.manager, tasks)

        self.assertRaises(ViewError, builder.build)

    def test_no_tasks_are_kept_between_plans(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_1")
        task1.group = task2.group = deployment_plan_groups.MS_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(2, len([task for phase in phases for task in phase]))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_1")
        task1.group = task2.group = deployment_plan_groups.MS_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        self.assertEquals(2, len([task for phase in phases for task in phase]))

    def test_prev_successful_tasks_are_not_in_plan(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task1a = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task1a.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2.group = task1a.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = [task1a]
        phases = builder.build()
        self.assertEquals([[task2]], phases)
        # but their unique_ids are retained for puppet manifest generation
        # as per LITPCDS-8257
        self.assertTrue(task1.unique_id in task2._requires)

    def test_prev_successful_tasks_are_in_plan_if_future_property_value(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))

        fpv = FuturePropertyValue(node1_qi, "test_property")
        node1_qi._updatable = True
        node1_qi.test_property = 'value'

        # Previous task with FuturePropertyValue
        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a=fpv)
        task1a = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a="value")
        task1a.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2.group = task1a.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = [task1a]
        phases = builder.build()
        self.assertEquals([[task1, task2]], phases)
        self.assertTrue(task1.unique_id in task2._requires)

        # Current task with FuturePropertyValue
        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a="value")
        task1a = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a=fpv)
        task1a.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2.group = task1a.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = [task1a]
        phases = builder.build()
        self.assertEquals([[task1, task2]], phases)
        self.assertTrue(task1.unique_id in task2._requires)

        # Both tasks with FuturePropertyValue
        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a=fpv)
        task1a = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a=fpv)
        task1a.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2.group = task1a.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = [task1a]
        phases = builder.build()
        self.assertEquals([[task1, task2]], phases)
        self.assertTrue(task1.unique_id in task2._requires)

    def test_tasks_passed_as_ignored_are_in_puppet_requires(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task1.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2.group = deployment_plan_groups.NODE_GROUP
        tasks = [task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = [task1]
        phases = builder.build()
        self.assertEquals([[task2]], phases)
        self.assertTrue(task1.unique_id in task2._requires)

    def test_successful_task_replaced_with_new_with_same_unique_id(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        other_item = self.qi(self.manager.query_by_vpath("/ms"))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task1.state = constants.TASK_SUCCESS
        # same task
        task2a = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        # identical unique_id but different task kwargs, eg configure-deconfigure
        task2b = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1", a=1)
        task3 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_2")
        task1.group = task2a.group = task2b.group = task3.group \
            = deployment_plan_groups.NODE_GROUP

        current_tasks = [task2a, task3]
        combined = merge_prev_successful_and_current_tasks([task1], current_tasks)
        task_ids = [id(task) for task in combined]

        # The old task is there and its state is untouched since the task's
        # items are all determinably applied
        self.assertTrue(id(task1) in task_ids)
        self.assertEqual(task1.state, constants.TASK_SUCCESS)
        self.assertFalse(id(task2a) in task_ids)

        current_tasks = [task2b, task3]
        combined = merge_prev_successful_and_current_tasks([task1], current_tasks)
        task_ids = [id(task) for task in combined]
        # The old task has been filtered out
        self.assertFalse(id(task1) in task_ids)
        self.assertTrue(id(task2b) in task_ids)
        self.assertEqual(task2b.state, constants.TASK_INITIAL)

        # case where the new task's primary model item isn't determinably applied
        node1_qi.system._model_item.applied_properties_determinable = False
        current_tasks = [task2a, task3]
        combined = merge_prev_successful_and_current_tasks([task1], current_tasks)
        task_ids = [id(task) for task in combined]

        # The old task is present in the output
        self.assertTrue(id(task1) in task_ids)
        self.assertFalse(id(task2a) in task_ids)
        # ...but its state has been reset to initial
        self.assertTrue(task2a.state, constants.TASK_INITIAL)

        # case where one of the new task's extra model item isn't determinably applied
        node1_qi.system._model_item.applied_properties_determinable = True
        other_item._model_item.applied_properties.clear()
        task.model_items |= set([other_item])

        current_tasks = [task2a, task3]
        combined = merge_prev_successful_and_current_tasks([task1], current_tasks)
        task_ids = [id(task) for task in combined]

        # The old task is present in the output
        self.assertTrue(id(task1) in task_ids)
        self.assertFalse(id(task2a) in task_ids)
        # ...but its state has been reset to initial
        self.assertTrue(task2a.state, constants.TASK_INITIAL)

    def test_associated_items_determinable(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = ConfigTask(node1_qi, node1_qi, 'blah', '1', '1_1')
        task2 = ConfigTask(node2_qi, node2_qi, 'blah', '2', '2_2')
        task3 = ConfigTask(node1_qi, node1_qi, 'blah', '3', '3_3')
        tasks = set([task1, task2, task3])
        builder = PlanBuilder(self.manager, tasks)
        self.assertTrue(_associated_items_determinable(tasks))

        node2_qi._model_item.applied_properties_determinable = False
        self.assertFalse(_associated_items_determinable(tasks))

    def test_config_task_filtering_in_build(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = ConfigTask(node1_qi, node1_qi, 'blah', '1', '1_1', ensure='installed')
        task2 = ConfigTask(node2_qi, node2_qi, 'blah', '2', '2_2', ensure='installed')
        prev_task1 = ConfigTask(node1_qi, node1_qi, 'different', '1', '1_1', ensure='installed')
        prev_task1.state = constants.TASK_SUCCESS
        prev_task2 = ConfigTask(node2_qi, node2_qi, 'different', '2', '2_2', ensure='installed')
        prev_task2.state = constants.TASK_SUCCESS
        task1.group = deployment_plan_groups.MS_GROUP
        task2.group = deployment_plan_groups.MS_GROUP
        prev_task1.group = deployment_plan_groups.MS_GROUP
        prev_task2.group = deployment_plan_groups.MS_GROUP

        tasks = [task1, task2]
        prev_tasks = [prev_task1, prev_task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = prev_tasks
        self.assertEqual(set(builder.tasks), set(builder.previously_successful_tasks))

        # Current tasks identical to previously_successful => All filtered out
        self.assertEquals(builder.build(), [])
        # Task1's item APD=False => Task1 returned only
        node1_qi._model_item.applied_properties_determinable = False
        self.assertEquals(builder.build(), [[prev_task1]])


    def test_config_task_filtering_in_remove_prev_successful_tasks(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = ConfigTask(node1_qi, node1_qi, 'blah', '1', '1_1', ensure='installed')
        task2 = ConfigTask(node2_qi, node2_qi, 'blah', '2', '2_2', ensure='installed')
        prev_task1 = ConfigTask(node1_qi, node1_qi, 'different', '1', '1_1', ensure='installed')
        prev_task1.state = constants.TASK_SUCCESS
        prev_task2 = ConfigTask(node2_qi, node2_qi, 'different', '2', '2_2', ensure='installed')
        prev_task2.state = constants.TASK_SUCCESS
        task1.group = 'other'
        task2.group = 'other'
        prev_task1.group = 'other'
        prev_task2.group = 'other'

        tasks = [task1, task2]
        prev_tasks = [prev_task1, prev_task2]
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = prev_tasks
        self.assertEqual(set(builder.tasks), set(builder.previously_successful_tasks))

        # Current tasks identical to previously_successful => All removed
        self.assertEqual(builder._remove_prev_successful_tasks([tasks]), [])
        # Task1's item APD=False => Task1 returned only
        node1_qi._model_item.applied_properties_determinable = False
        self.assertEquals(builder._remove_prev_successful_tasks([tasks]), [[prev_task1]])

    def test_tasks_all_node_tasks_ignored_adds_no_lock_tasks(self):
        node1 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node2 = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2")
        node1.set_updated()
        node2.set_updated()

        node1_qi = self.qi(node1)
        node2_qi = self.qi(node2)
        task1 = ConfigTask(node1_qi, node1_qi.system, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "1", "1_1")
        task3 = ConfigTask(node2_qi, node2_qi.os, "", "1", "1_1")
        task1.group = task2.group = task3.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2, task3]
        builder = PlanBuilder(self.manager, tasks, self.lock_tasks)
        #builder.lock_tasks = self.lock_tasks
        builder.previously_successful_tasks = [task1, task2]

        phases = builder.build()
        lock_task, unlock_task = self.lock_tasks[node2_qi.get_vpath()]
        self.assertEqual(3, len(phases))
        self.assertEqual([lock_task], phases[0])
        self.assertEqual([task3], phases[1])
        self.assertEqual([unlock_task], phases[2])

    def test_tasks_passed_as_ignored_get_puppet_requires_updated(self):
        sibling_deps = {
            '/deployments/d1/clusters/c1/nodes/node1/A': set(['/deployments/d1/clusters/c1/nodes/node1/B']),
            '/deployments/d1/clusters/c1/nodes/node1/B': set(),
        }
        self.manager.get_dependencies = mock.Mock(return_value=sibling_deps)
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.vpath = '/deployments/d1/clusters/c1/nodes/node1/A'
        item_B.vpath = '/deployments/d1/clusters/c1/nodes/node1/B'
        node = mock.Mock(spec=QueryItem, name="node1")
        node.query.return_value = set()
        node.vpath = '/deployments/d1/clusters/c1/nodes/node1'
        node.hostname = 'mn1'
        node._model_item = mock.Mock()
        item_A.get_node.return_value = node
        item_B.get_node.return_value = node
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn

        task1 = ConfigTask(node, item_A, "task 1", "1", "1_1")
        task1._requires = set()
        task1.state = constants.TASK_SUCCESS
        task2 = ConfigTask(node, item_B, "task 2", "2", "1_2")
        task1.group = task2.group = deployment_plan_groups.NODE_GROUP
        tasks = [task2]

        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks=[task1]
        builder.build()
        self.assertTrue(task2.unique_id in task1._requires)

    def test_no_node_segregation_without_lock_tasks(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        task1 = ConfigTask(node1_qi, node1_qi, "", "1", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi, "", "2", "1_2")
        task3 = ConfigTask(node2_qi, node2_qi, "", "3", "1_3")
        task4 = ConfigTask(node2_qi, node2_qi, "", "4", "1_4")

        task1.group = task2.group = task3.group = task4.group = deployment_plan_groups.NODE_GROUP

        builder = PlanBuilder(
            self.manager,
            [task1, task2, task3, task4],
            []
        )
        phases = builder.build()

        # For an initial plan, we do not and cannot have lock/unlock tasks for
        # the nodes, yet the planbuilder logic still iterates on the nodes
        # under the cluster being installed
        self.assertEquals(1, len(phases))
        self.assertEquals(4, len(phases[0]))
        self.assertTrue(any(task.node == node1_qi for task in phases[0]))
        self.assertTrue(any(task.node == node2_qi for task in phases[0]))

    def test_indirect_task_dependency(self):
        # Test scenario:
        # paths /A, /B, /C
        # static dependency /A -> /B
        # tasks T(/A), T(/B), T1(/C), T2(/C)
        # plugin dependencies:
        # T(/B) -> T1(/C)
        # T1(/C) -> T2(/C)
        # ensure final dependencies:
        # T(/A) -> T(/B) model type dependency
        # T(/A) -> T1(/C) task type dependency
        # T(/A) -> T2(/C) task type dependency
        # T(/B) -> T1(/C) task type dependency
        # T1(/B) -> T1(/C) task type dependency

        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
            '/C': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_C = mock.Mock(name="item C")
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_C.vpath = '/C'

        node = mock.Mock(spec=QueryItem, name="node1")
        node.vpath = '/node'
        node.hostname = 'mn1'
        node._model_item = mock.Mock()

        item_A.get_node.return_value = node
        item_B.get_node.return_value = node
        item_C.get_node.return_value = node

        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_C.is_for_removal = falsevaluereturn

        task1 = ConfigTask(node, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(node, item_B, "task 2", "2", "1_2")
        task3 = ConfigTask(node, item_C, "task 3", "3", "1_3")
        task4 = ConfigTask(node, item_C, "task 4", "4", "1_4")

        task2.requires.add(task3)
        task3.requires.add(task4)

        tasks = TaskCollection([task1, task2, task3, task4])
        for task in tasks:
            task.group = deployment_plan_groups.NODE_GROUP
        graph = BasePlanBuilder._create_graph_from_task_requires(tasks)
        graph = BasePlanBuilder.create_graph_from_static_sibling_require(tasks,
                                                         sibling_deps,
                                                         graph)
        result = bridge_static_and_plugin_dependencies(graph)
        self.assertEquals(result[task1], set([task2, task3, task4]))
        self.assertEquals(result[task2], set([task3, task4]))

    def test_update_package_tasks(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))
        n1_package_a = self.qi(self.manager.query_by_vpath(
                "/deployments/d1/clusters/c1/nodes/node1/items/package_a"))
        n1_package_b = self.qi(self.manager.query_by_vpath(
                "/deployments/d1/clusters/c1/nodes/node1/items/package_b"))
        n1_repo_a = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/items/repo_a"))
        n1_repo_b = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/items/repo_b"))

        n2_package_a = self.qi(self.manager.query_by_vpath(
                "/deployments/d1/clusters/c1/nodes/node2/items/package_a"))
        n2_package_b = self.qi(self.manager.query_by_vpath(
                "/deployments/d1/clusters/c1/nodes/node2/items/package_b"))
        n2_repo_a = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2/items/repo_a"))
        n2_repo_b = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2/items/repo_b"))

        task1 = ConfigTask(node1_qi, n1_package_a, "", "n1_package_a", "1")
        task2 = ConfigTask(node1_qi, n1_package_b, "", "n1_package_b", "2")
        task3 = ConfigTask(node1_qi, n1_repo_a, "", "n1_repo_a", "3")
        task4 = ConfigTask(node1_qi, n1_repo_b, "", "n1_repo_b", "4")

        task5 = ConfigTask(node1_qi, n2_package_a, "", "n2_package_a", "4")
        task6 = ConfigTask(node1_qi, n2_package_b, "", "n2_package_b", "5")
        task7 = ConfigTask(node1_qi, n2_repo_a, "", "n2_repo_a", "7")
        task8 = ConfigTask(node1_qi, n2_repo_b, "", "n2_repo_b", "8")

        tasks = [task1, task2, task3, task4, task5, task6, task7, task8]
        for task in tasks:
            task.group = deployment_plan_groups.NODE_GROUP

        # Make sure no "requires" is set before PlanBuilder comes in.
        for task in tasks:
            self.assertEquals(set(), task.requires)

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()
        self.assertEqual(task1._requires,
                set([task3.unique_id, task4.unique_id]))
        self.assertEqual(task2._requires,
                set([task3.unique_id, task4.unique_id]))

        self.assertEqual(task5._requires,
                set([task7.unique_id, task8.unique_id]))
        self.assertEqual(task6._requires,
                set([task7.unique_id, task8.unique_id]))

        self.assertFalse(task3._requires)
        self.assertFalse(task4._requires)
        self.assertFalse(task7._requires)
        self.assertFalse(task8._requires)

        self.assertEqual(1, len(phases))

    def test_litpcds_12114_all_package_tasks_as_node_level_tasks(self):
        """
        Install plan:

        Task status
        -----------
        Success     ...loyments/d1/clusters/c1/nodes/n1/items/httpd-tools
                    Install package "httpd-tools" on node "node1"
        Success     ...services/apachecs/applications/httpd/packages/pkg1
                    Install package "httpd" on node "node1"

        ----------------------------------------------------------------------

        Removal plan:

        Task status
        -----------
        Success     /deployments/d1/clusters/c1/nodes/n1
                    Update versionlock file on node "node1"
        Failed      ...loyments/d1/clusters/c1/nodes/n1/items/httpd-tools
                    Remove package "httpd-tools" on node "node1"
        Failed      ...services/apachecs/applications/httpd/packages/pkg1
                    Remove package "httpd" on node "node1"

        """
        self.manager.remove_item("/deployments/d1/clusters/c1/nodes/node1/items/repo_a")
        self.manager.remove_item("/deployments/d1/clusters/c1/nodes/node1/items/repo_b")

        self.manager.create_item("package", "/software/items/httpd-tools", name="httpd-tools")
        self.manager.create_item("package", "/software/items/httpd", name="httpd")
        self.manager.create_item("service", "/software/services/httpd", name="httpd")
        self.manager.create_inherited("/software/items/httpd-tools", "/deployments/d1/clusters/c1/nodes/node1/items/httpd-tools")
        self.manager.create_item("clustered-service", "/deployments/d1/clusters/c1/services/apachecs", name="cs1")
        self.manager.create_inherited("/software/items/httpd", "/software/services/httpd/packages/pkg1")
        self.manager.create_inherited("/software/services/httpd", "/deployments/d1/clusters/c1/services/apachecs/applications/httpd")

        # self.manager.create_inherited("/software/items/httpd-tools", "/deployments/d1/clusters/c1/software/httpd-tools")

        httpd_package_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/services/apachecs/applications/httpd/packages/pkg1"))
        httpd_tools_package_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1/items/httpd-tools"))

        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))

        task1 = ConfigTask(node1_qi, httpd_package_qi, "", "package", "httpd_package")
        # Even though the model item is a cluster item, the package removal
        # ConfigTask would be sorted in the node group
        task1.group = deployment_plan_groups.NODE_GROUP
        task2 = ConfigTask(node1_qi, httpd_tools_package_qi, "", "package", "httpd_tools_package")
        task2.group = deployment_plan_groups.NODE_GROUP
        # Task1 will only have a dependency against task2 if the planbuilder
        # processes them in the same group
        tasks = [task1, task2]

        builder = PlanBuilder(self.manager, tasks)
        phases = builder.build()

        # Make sure the "_requires" attribute used by the PuppetManager to
        # write Puppet resource dependencies is empty after PlanBuilder has
        # done its job.
        for task in tasks:
            self.assertEquals(set(), task._requires)

    def test_filtering_prev_successful_tasks(self):
        node1_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1"))
        node2_qi = self.qi(self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node2"))

        task1 = ConfigTask(node1_qi, node1_qi.system, "", "Resource_A", "1_1")
        task2 = ConfigTask(node1_qi, node1_qi.os, "", "Resource_A", "1_2")
        task3 = ConfigTask(node2_qi, node2_qi.os, "", "Resource_B", "1_3")
        task4 = ConfigTask(node1_qi, node1_qi.system, "", "Resource_A", "1_4")
        task5 = ConfigTask(node1_qi, node1_qi.os, "", "Resource_B", "1_5")
        task6 = ConfigTask(node2_qi, node2_qi.os, "", "Resource_C", "1_6")

        task1.group = task2.group = task3.group = deployment_plan_groups.NODE_GROUP
        tasks = [task1, task2, task3, task4]

        # No ignored tasks!
        # test fast access prev tasks creation first
        builder = PlanBuilder(self.manager, tasks)
        builder.previously_successful_tasks = []
        result = builder._remove_prev_successful_tasks([tasks])
        self.assertEquals([tasks], result)

        builder.previously_successful_tasks = tasks[::-1]
        result = builder._remove_prev_successful_tasks([[task5, task6]])
        self.assertEquals(result, [[task5, task6]])

        builder.previously_successful_tasks = tasks[::-1]
        result = builder._remove_prev_successful_tasks(
            [[task1, task2, task5], [task6]]
        )
        self.assertEquals(2, len(result))
        self.assertEquals([task5], result[0])
        self.assertEquals([task6], result[1])

    def _create_vcs_cluster(self, with_nodes, view_method):
        self.manager.register_item_type(
            ItemType(
                "vcs-cluster",
                extend_item="cluster",
                item_description="vcs-cluster like item type",
                node_upgrade_ordering=View(
                    "basic_list",
                    view_method,
                    view_description="A comma seperated list of the node "
                    "ordering for upgrade."),
                )
            )
        self.manager.create_item("vcs-cluster",
                "/deployments/d1/clusters/vcs_cluster")
        if with_nodes:
            self.manager.create_item("node",
                    "/deployments/d1/clusters/vcs_cluster/nodes/node1",
                    hostname="vcs_node1")
            self.manager.create_item("node",
                    "/deployments/d1/clusters/vcs_cluster/nodes/node2",
                    hostname="vcs_node2")

    def _get_vcs_cluster_and_nodes(self):
        vcs_node1 = self.manager.query_by_vpath(
                "/deployments/d1/clusters/vcs_cluster/nodes/node1")
        vcs_node2 = self.manager.query_by_vpath(
                "/deployments/d1/clusters/vcs_cluster/nodes/node2")
        vcs_cluster = self.manager.query_by_vpath(
                "/deployments/d1/clusters/vcs_cluster")
        return vcs_cluster, vcs_node1, vcs_node2

    def test_get_nodes_empty_cluster_empty_view(self):
        """ Scenario: [] returned from model and [] from the view """
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return []
        self._create_vcs_cluster(
                with_nodes=False,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster = self.manager.query_by_vpath(
                "/deployments/d1/clusters/vcs_cluster")

        self.assertEquals([], builder._get_nodes(vcs_cluster))

    def test_get_nodes_nonempty_cluster_empty_view(self):
        """
        Scenario: [<nonempty>] returned from cluster and [] from the view
        """
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return []
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        self.assertEquals(
                sorted([vcs_node1, vcs_node2]),
                sorted(builder._get_nodes(vcs_cluster)))

    def test_get_nodes_nonempty_cluster_nonempty_view_ordered(self):
        """
        Scenario: [<nonempty>] returned from the model and
        [<nonempty ordered>] from the view

        """
        def dummy_get_node_upgrade_ordering_ordered(api_context, cluster):
            return ['node1', 'node2']
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering_ordered)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        self.assertEquals(
                [vcs_node1, vcs_node2],
                builder._get_nodes(vcs_cluster))

    def test_get_nodes_nonempty_cluster_nonempty_view_reversed(self):
        """
        Scenario: [<nonempty>] returned from the model and
        [<nonempty reversed>] from the view

        """
        def dummy_get_node_upgrade_ordering_reversed(api_context, cluster):
            return ['node2', 'node1']
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering_reversed)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        self.assertEquals(
                [vcs_node2, vcs_node1],
                builder._get_nodes(vcs_cluster))

    def test_get_nodes_none_returned_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return None
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        self.assertEquals(
                sorted([vcs_node2, vcs_node1]),
                sorted(builder._get_nodes(vcs_cluster)))

    def test_get_nodes_not_a_list_returned_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return 1
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        try:
            builder._get_nodes(vcs_cluster)
        except ViewError as e:
            self.assertEquals(
                str(e),
                '"node_upgrade_ordering" must return a list. '
                '<type \'int\'> returned')
        else:
            self.fail('Expected exception not raised: "ViewError"')

    def test_get_nodes_list_of_invalid_types_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return [1, 2]
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        try:
            builder._get_nodes(vcs_cluster)
        except ViewError as e:
            self.assertEquals(
                str(e),
                '"node_upgrade_ordering" must be a list of "basestring". '
                '<type \'int\'> found in the list')
        else:
            self.fail('Expected exception not raised: "ViewError"')

    def test_get_nodes_list_of_invalid_node_ids_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return ['no_such_node1', 'no_such_node2']
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        try:
            builder._get_nodes(vcs_cluster)
        except ViewError as e:
            self.assertEquals(
                str(e),
                '"node_upgrade_ordering" contains a node id that is not '
                'present in the cluster: no_such_node1')
        else:
            self.fail('Expected exception not raised: "ViewError"')

    def test_get_nodes_nonunique_value_returned_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return ['node1', 'node1', 'node2']
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        try:
            builder._get_nodes(vcs_cluster)
        except ViewError as e:
            self.assertEquals(
                str(e),
                '"node_upgrade_ordering" contains duplicated node ids: node1')
        else:
            self.fail('Expected exception not raised: "ViewError"')

    def test_get_nodes_missing_value_returned_from_view(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            return ['node1']
        self._create_vcs_cluster(
                with_nodes=True,
                view_method=dummy_get_node_upgrade_ordering)
        builder = PlanBuilder(self.manager, tasks=[])
        vcs_cluster, vcs_node1, vcs_node2 = self._get_vcs_cluster_and_nodes()
        try:
            builder._get_nodes(vcs_cluster)
        except ViewError as e:
            self.assertEquals(
                str(e),
                '"node_upgrade_ordering" does not contain all the nodes '
                'within the cluster. Missing node ids: node2')
        else:
            self.fail('Expected exception not raised: "ViewError"')

    def test_get_task_collection_for_cluster(self):
        node = self.manager.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        ms = self.manager.query_by_vpath("/ms")
        ms_package = self.manager.query_by_vpath("/ms/items/package_a")
        node_qi = QueryItem(self.manager, node)
        ms_qi = QueryItem(self.manager, ms)
        ms_package_qi = QueryItem(self.manager, ms_package)
        group = deployment_plan_groups.CLUSTER_GROUP

        # Test scenario: CLUSTER_GROUP, node: node, item: /deployments/.../node1
        task = ConfigTask(node_qi, node_qi, "task", "call_type", "call_id")
        task.group = group
        builder = PlanBuilder(self.manager, [task])
        builder.sortable_tasks = [task]
        self.assertEquals(task, builder._get_task_collection_for_cluster(
            group, '/deployments/d1/clusters/c1')[0])

        # Test scenario: CLUSTER_GROUP, node: ms, item: /ms/items/package_a
        task = ConfigTask(ms_qi, ms_package_qi, "task", "call_type", "call_id")
        task.group = group
        builder = PlanBuilder(self.manager, [task])
        builder.sortable_tasks = [task]
        self.assertEquals([], builder._get_task_collection_for_cluster(
            group, '/deployments/d1/clusters/c1'))


class PluginRequireGraph(unittest.TestCase):
    def setUp(self):
        self.node = mock.Mock(spec=QueryItem, name="node1")
        self.node._model_item = mock.Mock()
        self.node.vpath = "/node"
        self.node.hostname = 'mn1'

    def test_create_graph_from_task_requires_with_task_hash_collision(self):
        # LITPCDS-9264 test - TaskCollection.get_plugin_requires() issue

        # Previous plan
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node, self.node, "task 3", "3", "1_3")
        task1.state = task2.state = task3.state = constants.TASK_SUCCESS
        task2.requires.add(task3)

        # Current plan
        task1a = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2a = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3a = ConfigTask(self.node, self.node, "task 3", "3", "1_3")

        task1a.requires.add(task2a)
        task2a.requires.add(task3a)

        tasks = TaskCollection([task2, task1a, task2a, task3a])

        try:
            BasePlanBuilder._create_graph_from_task_requires(tasks)
        except KeyError:
            self.fail("TaskCollection._found_taks_plugin_requires wrongly hit")


    def test_create_graph_from_task_requires_with_cyclic_dependency(self):
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node, self.node, "task 3", "3", "1_3")
        task1.requires.add(task2)
        task2.requires.add(task3)
        task3.requires.add(task1)
        tasks = TaskCollection([task1, task2, task3])
        result = BasePlanBuilder._create_graph_from_task_requires(tasks)
        # yes, these are cyclic dependencies
        self.assertEquals(result[task1], set([task2, task3]))
        self.assertEquals(result[task2], set([task1, task3]))
        self.assertEquals(result[task3], set([task1, task2]))

    def test_create_graph_from_task_requires_with_indirect_cyclic_dependency(self):
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node, self.node, "task 3", "3", "1_3")
        task1.requires.add(task3)
        task2.requires.add(task3)
        task3.requires.add(task1)
        tasks = TaskCollection([task1, task2, task3])
        result = BasePlanBuilder._create_graph_from_task_requires(tasks)
        # yes, these are cyclic dependencies
        self.assertEquals(result[task1], set([task3]))
        self.assertEquals(result[task2], set([task1, task3]))
        self.assertEquals(result[task3], set([task1]))

    def test_create_graph_from_task_requires_update_tasks(self):
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task1.requires.add(task2)
        tasks = TaskCollection([task1])
        result = BasePlanBuilder._create_graph_from_task_requires(tasks)
        for deps in result.values():
            for dep_task in deps:
                self.assertEquals(dep_task , task2)

    def test_create_graph_from_task_requires_task_type_dependency(self):
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node, self.node, "task 3", "3", "1_3")
        task4 = ConfigTask(self.node, self.node, "task 4", "4", "1_4")
        task1.requires.add(task2)
        task2.requires.add(task3)
        task3.requires.add(task4)

        tasks = TaskCollection([task1, task2, task3, task4])
        result = BasePlanBuilder._create_graph_from_task_requires(tasks)
        self.assertEquals(result[task1],
                          set([task2, task3, task4]))
        self.assertEquals(result[task2],
                          set([task3, task4]))
        self.assertEquals(result[task3], set([task4]))
        self.assertFalse(result[task4])

    def test_create_graph_from_task_requires_item_type_dependency(self):
        task1 = ConfigTask(self.node, self.node, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node, self.node, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node, self.node, "task 3", "3", "1_3")
        task4 = ConfigTask(self.node, self.node, "task 4", "4", "1_4")
        task1.requires.add(self.node)

        tasks = TaskCollection([task1, task2, task3, task4])
        result = BasePlanBuilder._create_graph_from_task_requires(tasks)

        self.assertEquals(result[task1],
                          set([task2, task3, task4]))
        self.assertFalse(result[task2])
        self.assertFalse(result[task3])
        self.assertFalse(result[task4])


class ModelExtensionSiblingRequireGraph(unittest.TestCase):
    def setUp(self):
        self.node = self.node1 = mock.Mock(name="node1")
        self.node2 = mock.Mock(name="node2")

    def test_indirect_task_dependency_becomes_direct(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(['/C']),
            '/C': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_C = mock.Mock(name="item C")
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_C.is_for_removal = falsevaluereturn
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_C.vpath = '/C'

        item_A.get_node.return_value = self.node1
        item_B.get_node.return_value = self.node1
        item_C.get_node.return_value = self.node1

        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_B, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node1, item_C, "task 3", "3", "1_3")

        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2, task3]), sibling_deps)

        self.assertEquals(result[task1], set([task2, task3]))
        self.assertEquals(result[task2], set([task3]))

    def test_tasks_with_different_nodes_dont_require_each_other(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value = self.node1
        # Keep the item node the same
        item_B.get_node.return_value = self.node1
        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node2, item_B, "task 2", "2", "1_2")
        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2]), sibling_deps)
        # print result
        self.assertFalse(result[task1])
        self.assertFalse(result[task2])

    def test_tasks_with_same_nodes_diff_item_nodes_no_require_each_other(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value = self.node1
        item_B.get_node.return_value = self.node2
        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_B, "task 2", "2", "1_2")
        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2]), sibling_deps)
        # print result
        self.assertFalse(result[task1])
        self.assertFalse(result[task2])

    def test_task_with_item_node_requires_task_without_item_node(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value = self.node1
        item_B.get_node.return_value \
            = item_B.get_ms.return_value = None
        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_B, "task 2", "2", "1_2")
        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2]), sibling_deps)
        # print result
        self.assertEqual(result[task1], set([task2]))
        self.assertFalse(result[task2])

    def test_task_without_item_node_requires_task_with_item_node(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value \
            = item_A.get_ms.return_value = None
        item_B.get_node.return_value = self.node1
        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_B, "task 2", "2", "1_2")
        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2]), sibling_deps)
        self.assertEqual(result[task1], set([task2]))
        self.assertFalse(result[task2])

    def test_task_without_item_node_requires_task_without_item_node(self):
        sibling_deps = {
            '/A': set(['/B']),
            '/B': set(),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value \
            = item_A.get_ms.return_value = None
        item_B.get_node.return_value \
            = item_B.get_ms.return_value = None
        task1 = ConfigTask(self.node1, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_B, "task 2", "2", "1_2")
        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2]), sibling_deps)
        self.assertEqual(result[task1], set([task2]))
        self.assertFalse(result[task2])

    def test_one_tasks_require_setup_doesnt_prevent_require_setup_for_another(
            self):
        sibling_deps = {
            '/A': set(['/B']),
        }
        item_A = mock.Mock(name="item A")
        item_B = mock.Mock(name="item B")
        item_A.is_for_removal = falsevaluereturn
        item_B.is_for_removal = falsevaluereturn
        item_A.vpath = '/A'
        item_B.vpath = '/B'
        item_A.get_node.return_value \
            = item_A.get_ms.return_value = self.node1
        item_B.get_node.return_value \
            = item_B.get_ms.return_value = self.node1

        task1 = ConfigTask(self.node2, item_A, "task 1", "1", "1_1")
        task2 = ConfigTask(self.node1, item_A, "task 2", "2", "1_2")
        task3 = ConfigTask(self.node1, item_B, "task 3", "3", "1_3")

        result = BasePlanBuilder.create_graph_from_static_sibling_require(
            TaskCollection([task1, task2, task3]), sibling_deps)
        # LITPCDS-6248
        # IF there was static dependency A->B
        # AND there were 2 tasks T1(node1, itemA) and T2(node2, itemA) - diff
        # task nodes
        # AND there was a task T3(node1, itemB) - the same task node as first of
        # the two tasks T1 and T2
        # AND initially T3 would be marked as potential dependency for T1 and T2
        #
        # THEN when T2 happened to be processed before T1 and potential
        # dependency would be discarded due to non-matching nodes
        # BUG PART: it would make remove T3 from the list of potential
        # dependencies for T1 even if in this case T3 was a legitimate
        # dependency of T1.
        #
        # CHECK:
        self.assertEqual(result[task1], set())
        self.assertEqual(result[task2], set([task3]))
        self.assertFalse(result[task3])


class PhasesCompacting(unittest.TestCase):
    def setUp(self):
        self.node = mock.Mock()
        self.mitem = mock.Mock()
        self.cfg1 = ConfigTask(self.node, self.mitem, "", "cfg", "1")
        self.cfg1._net_task = False
        self.cfg1.model_item._model_item.is_instance = lambda t: False
        self.cfg2 = ConfigTask(self.node, self.mitem, "", "cfg", "2")
        self.cfg2._net_task = False
        self.cfg2.model_item._model_item.is_instance = lambda t: False
        self.cfg3 = ConfigTask(self.node, self.mitem, "", "cfg", "3")
        self.cfg3._net_task = False
        self.cfg3.model_item._model_item.is_instance = lambda t: False
        self.cb1 = CallbackTask(self.node, "", _cb)
        self.cb1._net_task = False
        self.cb1.model_item._model_item.is_instance = lambda t: False
        self.cb2 = CallbackTask(self.node, "", _cb2)
        self.cb2._net_task = False
        self.cb2.model_item._model_item.is_instance = lambda t: False
        self.graph = {self.cfg1: set(), self.cfg2: set(),
                      self.cb1: set(), self.cb2: set()}

    def _get_graph(self):
        return {self.cfg1: set(), self.cfg2: set(),
                self.cb1: set(), self.cb2: set()}

    def test_cfg_cfg(self):
        graph = self._get_graph()

        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        graph[self.cfg2].add(self.cfg1)

        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

    def test_cfg_cb(self):
        graph = self._get_graph()

        phases = [[self.cfg1, self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        graph[self.cfg1].add(self.cb1)
        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        graph = self._get_graph()

        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

    def test_cb_cb(self):
        phases = [[self.cb1, self.cb2]]
        graph = self._get_graph()
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[0])

        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[0])

        graph[self.cb2].add(self.cb1)
        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

    def test_cfgnet_cfgnet(self):
        self.cfg1._net_task = self.cfg2._net_task = True
        graph = self._get_graph()

        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        # dependency between 2 cfg net tasks
        graph[self.cfg1].add(self.cfg2)
        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])

    def test_cfgnet_cbnet(self):
        self.cfg1._net_task = self.cb1._net_task = True
        graph = self._get_graph()

        phases = [[self.cfg1, self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[0])

        # cfg net task depends on cb net task
        graph[self.cfg1].add(self.cb1)

        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        graph = self._get_graph()
        # cb net task depends on cfg net task
        graph[self.cb1].add(self.cfg1)

        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

    def test_cbnet_cbnet(self):
        self.cb1._net_task = self.cb2._net_task = True
        graph = self._get_graph()

        phases = [[self.cb1, self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[0])

        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[0])

        # cb net task depends on cb net task
        graph[self.cb2].add(self.cb1)
        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

    def test_cfgnet_cfg(self):
        self.cfg1._net_task = True
        graph = self._get_graph()

        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[1])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[1])

        phases = [[self.cfg2], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[1])

        # cfg task depends on cfg net task
        graph[self.cfg2].add(self.cfg1)
        phases = [[self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[1])

        phases = [[self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[1])

        graph = self._get_graph()

        # cfg net task depends on cfg task
        graph[self.cfg1].add(self.cfg2)
        phases = [[self.cfg2], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cfg2 in result[0])

    def test_cfgnet_cb(self):
        self.cfg1._net_task = True
        graph = self._get_graph()

        phases = [[self.cfg1, self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

        # cfg net task depends on cb task
        graph[self.cfg1].add(self.cb1)
        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        # cb task depends on cfg net task
        graph = self._get_graph()
        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

    def test_cbnet_cb(self):
        self.cb1._net_task = True
        graph = self._get_graph()

        phases = [[self.cb1, self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

        phases = [[self.cb2], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

        # cb net task depends on cb task
        graph[self.cb1].add(self.cb2)
        phases = [[self.cb2], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[1])
        self.assertTrue(self.cb2 in result[0])

        # cb task depends on cb net task
        graph = self._get_graph()
        graph[self.cb2].add(self.cb1)
        phases = [[self.cb1], [self.cb2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cb1 in result[0])
        self.assertTrue(self.cb2 in result[1])

    def test_cbnet_cfg(self):
        self.cb1._net_task = True
        graph = self._get_graph()

        phases = [[self.cfg1, self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

        # cb net task depends on cfg task
        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg1], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cb1 in result[1])

        # cfg task depends on cb net task
        graph = self._get_graph()
        graph[self.cfg1].add(self.cb1)
        phases = [[self.cb1], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[1])
        self.assertTrue(self.cb1 in result[0])

    def test_net_net_regular(self):
        self.cfg1._net_task = self.cfg2._net_task = True

        graph = self._get_graph()

        phases = [[self.cfg1, self.cb1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

        phases = [[self.cb1], [self.cfg1, self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

        phases = [[self.cb1, self.cfg1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

        graph[self.cfg2].add(self.cfg1)
        phases = [[self.cfg1, self.cb1], [self.cfg2]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

        graph = self._get_graph()
        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg1, self.cfg2], [self.cb1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[0])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

        graph = self._get_graph()
        graph[self.cfg1].add(self.cb1)
        phases = [[self.cb1, self.cfg2], [self.cfg1]]
        result = BasePlanBuilder._compact_phases(phases, graph)
        self.assertTrue(self.cfg1 in result[2])
        self.assertTrue(self.cfg2 in result[0])
        self.assertTrue(self.cb1 in result[1])

    def test_update_phases_with_segregated_config_tasks(self):
        graph = self._get_graph()
        phases = [[self.cb1, self.cfg2, self.cfg1, self.cb2]]
        segregated_config_tasks = [self.cfg2, self.cfg1]
        phase_index = 0
        BasePlanBuilder.update_phases_with_segregated_config_tasks(
                    phase_index, phases, segregated_config_tasks, graph)
        self.assertEquals(2, len(phases))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(phases[1]))

    def test_segregation_no_net_tasks_no_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        phases = [[self.cb1, self.cfg2, self.cfg1, self.cb2]]
        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(2, len(result))
        self.assertEquals(set([self.cb1, self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))

    def test_segregation_no_net_tasks_cb_2_cfg_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cb1] = set([self.cfg1])
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_no_net_tasks_cb_2_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cb1] = set([self.cb2])
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_no_net_tasks_cb_2_cb_and_cfg_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cb1] = set([self.cb2, self.cfg1])
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_no_net_tasks_cfg_2_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cfg1] = set([self.cb2])
        phases = [[self.cfg2, self.cb1, self.cb2], [self.cfg1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(2, len(result))
        self.assertEquals(set([self.cb2, self.cb1]), set(result[0]))
        # cb1 and cb2 can coexist in the same phase because they don't have
        # dependencies against one another
        self.assertEquals(set([self.cfg2, self.cfg1]), set(result[1]))

    def test_segregation_no_net_tasks_cfg_2_cfg_and_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cfg1] = set([self.cfg2, self.cb1])
        phases = [[self.cfg2, self.cb1, self.cb2], [self.cfg1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        # cb1 and cb2 can coexist in the same phase because they don't have
        # dependencies against one another
        self.assertEquals(set([self.cb2, self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cfg1]), set(result[2]))

    def test_segregation_no_net_tasks_cb_2_cfg_and_cfg_2_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cfg1] = set([self.cb2])
        graph[self.cb1] = set([self.cfg1])
        phases = [[self.cfg2, self.cb2], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2, self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_no_net_tasks_cb_2_cfg_and_cb_2_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cb1] = set([self.cb2])
        graph[self.cb2] = set([self.cfg1])
        phases = [[self.cfg2, self.cb2], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2, self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_no_net_tasks_cfg_2_cfg_and_cfg_2_cb_dependencies(self):
        # No net_tasks
        graph = self._get_graph()

        graph[self.cfg1] = set([self.cb2])
        graph[self.cfg2] = set([self.cfg1])
        phases = [[self.cfg2, self.cb2], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2, self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_net_tasks_cfg_2_cb_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = True

        phases = [[self.cb1, self.cfg1], [self.cfg2, self.cb2]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(4, len(result))
        self.assertEquals(set([self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb2]), set(result[2]))
        self.assertEquals(set([self.cfg2]), set(result[3]))

    def test_segregation_net_tasks_no_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = True

        phases = [[self.cb1, self.cfg1], [self.cb2]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        # cb1 and cb2 cannot be in the same phase as they do not share the same
        # "network task" status
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb2]), set(result[2]))

    def test_segregation_net_tasks_cb_2_cfg_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = True

        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_net_tasks_cb_2_cb_and_cfg_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = True
        self.cb2._net_task = True

        graph[self.cb1].add(self.cb2)
        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_segregation_net_tasks_cfg_2_cfg_and_cb_dependencies(self):
        graph = self._get_graph()
        self.cb1._net_task = True
        self.cfg1._net_task = True
        self.cfg2._net_task = True

        graph[self.cfg1].add(self.cfg2)
        graph[self.cfg1].add(self.cb1)
        phases = [[self.cfg2, self.cb1, self.cb2], [self.cfg1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        # cb1 and cb2 can coexist in the same phase because they don't have
        # dependencies against one another
        self.assertEquals(set([self.cb2, self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cfg1]), set(result[2]))

    def test_segregation_net_tasks_cb_2_cb_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = True

        graph[self.cb2].add(self.cb1)
        phases = [[self.cb1, self.cfg1], [self.cb2]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg1]), set(result[1]))
        # cb1 and cb2 can coexist in the same phase because they don't have
        # dependencies against one another
        self.assertEquals(set([self.cb2]), set(result[2]))

    def test_segregation_net_tasks_cfg_2_cfg_and_cfg_2_cb_dependencies(self):
        graph = self._get_graph()
        self.cb1._net_task = True
        self.cb2._net_task = True
        self.cfg1._net_task = True
        self.cfg2._net_task = True

        graph[self.cfg1].add(self.cb2)
        graph[self.cfg2].add(self.cfg1)
        phases = [[self.cfg2, self.cb2], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2, self.cfg1]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_any_net_tasks(self):
        graph = self._get_graph()
        self.cb1._net_task = True
        self.cb2._net_task = True
        self.cfg1._net_task = True
        self.cfg2._net_task = True
        self.cfg3._net_task = True

        graph[self.cfg1].add(self.cb2)
        graph[self.cfg2].add(self.cfg1)
        phases = [[self.cfg2, self.cb2, self.cfg3], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2, self.cfg1, self.cfg3]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_mixed_segregation_net_tasks_cb_2_cb_and_cfg_dependencies(self):
        graph = self._get_graph()
        self.cfg1._net_task = True
        self.cb1._net_task = False
        self.cb2._net_task = True

        graph[self.cb1].add(self.cb2)
        graph[self.cb1].add(self.cfg1)
        phases = [[self.cfg2, self.cfg1, self.cb2], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg1, self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cb1]), set(result[2]))

    def test_mixed_segregation_net_tasks_cfg_2_cfg_and_cb_dependencies(self):
        graph = self._get_graph()
        self.cb1._net_task = True
        self.cfg1._net_task = False
        self.cfg2._net_task = True

        graph[self.cfg1].add(self.cfg2)
        graph[self.cfg1].add(self.cb1)
        phases = [[self.cfg2, self.cb1, self.cb2], [self.cfg1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(3, len(result))
        # cb1 and cb2 can coexist in the same phase because they don't have
        # dependencies against one another
        self.assertEquals(set([self.cb2, self.cb1]), set(result[0]))
        self.assertEquals(set([self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cfg1]), set(result[2]))

    def test_mixed_segregation_net_tasks_cfg_2_cfg_and_cfg_2_cb_dependencies(self):
        graph = self._get_graph()
        self.cb1._net_task = True
        self.cb2._net_task = False
        self.cfg1._net_task = True
        self.cfg2._net_task = False

        graph[self.cfg1].add(self.cb2)
        graph[self.cfg2].add(self.cfg1)
        phases = [[self.cfg2, self.cb2], [self.cfg1], [self.cb1]]

        result = BasePlanBuilder._segregate_callback_tasks(phases, graph)
        self.assertEquals(4, len(result))
        self.assertEquals(set([self.cb2]), set(result[0]))
        self.assertEquals(set([self.cfg2]), set(result[1]))
        self.assertEquals(set([self.cfg1]), set(result[2]))
        self.assertEquals(set([self.cb1]), set(result[3]))


class TestTaskCollection(unittest.TestCase):
    def setUp(self):
        self.node = mock.Mock()
        self.mitem = mock.Mock()

    def test_get_plugin_requires_with_call_type_call_id(self):
        cfg1 = ConfigTask(self.node, self.mitem, "", "cfg", "1")
        cfg2 = ConfigTask(self.node, self.mitem, "", "cfg", "2")
        requires = set([(cfg1.call_type, cfg1.call_id),
                        (cfg2.call_type, cfg2.call_id)])
        tasks = [cfg1, cfg2]
        for task in tasks:
            task.requires |= requires
        task_collection = TaskCollection(tasks)
        self.assertEqual(set([cfg2]), task_collection.get_plugin_requires(cfg1))
        self.assertEqual(set([cfg1]), task_collection.get_plugin_requires(cfg2))

    def test_get_plugin_requires_with_successful_callback_is_empty(self):
        cb1 = CallbackTask(self.node, "", _cb)
        cb1.state = constants.TASK_SUCCESS
        cfg1 = ConfigTask(self.node, self.mitem, "", "cfg", "1")
        cfg1.requires.add(cb1)
        task_collection = TaskCollection([cfg1, cb1])
        self.assertFalse(task_collection.get_plugin_requires(cfg1))

    def test_stowaway_configtask(self):
        cfg1 = ConfigTask(self.node, self.mitem, "Prev successful task", "alpha", "1")
        cfg1.state = constants.TASK_SUCCESS
        cfg1_dep = ConfigTask(self.node, self.mitem, "", "charlie", "1")
        cfg1_dep.state = constants.TASK_SUCCESS
        cfg1.requires.add(cfg1_dep)
        cfg2 = ConfigTask(self.node, self.mitem, "Other prev successful task", "bravo", "2")
        cfg2_dep = ConfigTask(self.node, self.mitem, "", "delta", "1")
        cfg2_dep.state = constants.TASK_SUCCESS
        cfg2.state = constants.TASK_SUCCESS
        cfg3 = ConfigTask(self.node, self.mitem, "New task", "charlie", "1")
        cfg3.state = constants.TASK_INITIAL

        collection = TaskCollection((cfg1, cfg2, cfg3))
        self.assertEquals(set([cfg1_dep]), collection.get_plugin_requires(cfg1))
        self.assertEquals(set([]), collection.get_plugin_requires(cfg2))
