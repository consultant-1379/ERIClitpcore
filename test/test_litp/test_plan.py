
import unittest
import mock

from litp.core.plan import Plan
from litp.core.model_type import ItemType
from litp.core.model_type import PropertyType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_type import Reference
from litp.core.model_type import Property
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import CleanupTask
from litp.core.task import RemoteExecutionTask
from litp.core import constants
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.core.worker.celery_app import celery_app

celery_app.conf.CELERY_ALWAYS_EAGER = True

class MockPlugin():
    def mock_callback(api):
        pass

class PlanTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()

        self.model.register_property_type(PropertyType("basic_string"))

        # Would it make sense to use the core model extensions instead?
        self.model.register_item_type(ItemType("root",
            ms=Child("node"),
            nodes=Collection("node"),
            profiles=Collection("os-profile"),
            systems=Collection("system"),
            graph=Collection("graph_node"),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            is_locked=Property("basic_string", default="false"),
            system=Reference("system"),
            os=Reference("os-profile", require="system"),
        ))
        self.model.register_item_type(ItemType("system",
            uid=Property("basic_string"),
            disks=Collection("disk"),
        ))
        self.model.register_item_type(ItemType("disk",
            mount=Property("basic_string"),
        ))
        self.model.register_item_type(ItemType("os-profile",
            name=Property("basic_string"),
            items=Collection("package"),
        ))
        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.model.register_item_type(ItemType("graph_node",
            dest=Reference("graph_node"),
            uid=Property("basic_string"),
        ))


        self.model.create_root_item("root")
        self.node_qi1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        self.os1 = self.model.create_item("os-profile", "/profiles/os1",
            name="rhel")
        self.vim = self.model.create_item("package",
            "/profiles/os1/items/vim", name="vim")
        self.sys1 = self.model.create_item("system", "/systems/sys1",
            uid="sys1")
        self.d1 = self.model.create_item("disk", "/systems/sys1/disks/d1",
            mount="/my/disk")

        self.model.create_inherited("/profiles/os1", "/nodes/node1/os")
        self.model.create_inherited("/systems/sys1", "/nodes/node1/system")

        # We duplicate this query in tests - should we bind the queryitem to an
        # attribute, eg. self.node_qi ?
        self.node_qi = QueryItem(self.model, self.model.query("node")[0])

        self.os_task = ConfigTask(self.node_qi, self.node_qi.os, "Install os", "os", "os1")
        self.sys_task = ConfigTask(self.node_qi, self.node_qi.system, "Install system",
            "system", "sys1")
        self.vim_task = ConfigTask(self.node_qi, self.node_qi.os.items.vim, "Install vim",
            "vim", "vim1")
        self.d_task = ConfigTask(self.node_qi, self.node_qi.system.disks.d1, "Install d1",
            "disk", "d1")
        self.os_task.group = self.sys_task.group = self.vim_task.group = \
            self.d_task.group = deployment_plan_groups.NODE_GROUP
        self.os_task.plugin_name = self.sys_task.plugin_name = self.vim_task.plugin_name = \
            self.d_task.plugin_name = 'Plugin'
        self.ms = self.model.create_item("node", "/ms", hostname="ms1")


        self.plan = Plan([[self.os_task, self.sys_task,
            self.vim_task, self.d_task]], [])
        self.plan.set_ready()

    def _mock_func(self, *args):
        pass

    def test_index_by_taskid(self):
        task1 = self.plan.phases[0][0]
        self.plan._task_id_index = {}
        self.plan._index_tasks_by_phase(0)
        self.assertEqual(self.plan._task_id_index[0][task1.task_id], task1)
        self.assertEqual(1, len(self.plan._task_id_index))

    def test_plan_get_phase(self):
        self.assertEqual(1, len(self.plan.phases))
        self.assertEqual(None, self.plan.get_phase(999))

        self.assertTrue(self.d_task in self.plan.get_phase(0))
        self.assertTrue(self.sys_task in self.plan.get_phase(0))
        self.assertTrue(self.vim_task in self.plan.get_phase(0))
        self.assertTrue(self.os_task in self.plan.get_phase(0))

    def test_plan_get_task(self):
        self.assertEqual(1, len(self.plan.phases))
        self.assertEqual(None,
                          self.plan.get_task(24, self.sys_task.task_id))

        self.assertEqual(self.d_task,
                          self.plan.get_task(0, self.d_task.task_id))
        self.assertEqual(self.sys_task,
                          self.plan.get_task(0, self.sys_task.task_id))
        self.assertEqual(self.vim_task,
                          self.plan.get_task(0, self.vim_task.task_id))
        self.assertEqual(self.os_task,
                          self.plan.get_task(0, self.os_task.task_id))


    def test_initial_state_no_tasks(self):
        new_plan = Plan([], [])
        new_plan.set_ready()
        self.assertEquals(False, new_plan.is_running())
        self.assertEquals("initial", new_plan.state)


    def test_initial_state_tasks(self):
        self.assertEquals(False, self.plan.is_running())
        self.assertEquals("initial", self.plan.state)

    def test_running_state(self):
        self.plan.run()
        self.assertEquals(True, self.plan.is_running())
        self.assertEquals("running", self.plan.state)

    def test_stopped_state(self):
        self.assertEquals("initial", self.plan.state)
        self.plan.run()
        self.plan.stop()
        self.assertEquals("stopping", self.plan.state)
        self.plan.end()

        self.assertEquals(False, self.plan.is_running())
        self.assertEquals("stopped", self.plan.state)

    def test_equality(self):
        identical_plan = Plan([[self.os_task, self.sys_task,
            self.vim_task, self.d_task]], [])
        identical_plan.set_ready()
        self.assertEquals(identical_plan, self.plan)

    def set_tasks_to_state(self, state):
        for phase in self.plan._phases:
            for task in phase:
                if task.state == constants.TASK_INITIAL:
                    task.state = state

    def test_plan_successful_state(self):
        self.assertFalse(self.plan.is_running())
        self.plan.run()
        self.assertTrue(self.plan.is_running())
        self.assertEquals(Plan.RUNNING, self.plan.state)
        self.set_tasks_to_state(constants.TASK_SUCCESS)
        self.plan.end()
        self.assertTrue(self.plan.is_final())
        self.assertEquals(Plan.SUCCESSFUL, self.plan.state)

    def test_plan_stopped_state(self):
        self.assertFalse(self.plan.is_running())
        self.plan.run()
        self.assertTrue(self.plan.is_running())
        self.assertEquals(Plan.RUNNING, self.plan.state)

        self.assertFalse(self.plan.is_stopping())
        self.plan.stop()
        self.assertTrue(self.plan.is_stopping())
        self.assertEquals(Plan.STOPPING, self.plan.state)

        self.plan.end()
        self.assertTrue(self.plan.is_final())
        self.assertEquals(Plan.STOPPED, self.plan.state)

    def test_plan_stopping_success(self):
        self.assertFalse(self.plan.is_running())
        self.plan.run()
        self.assertTrue(self.plan.is_running())
        self.assertEquals(Plan.RUNNING, self.plan.state)

        self.assertFalse(self.plan.is_stopping())
        self.plan.stop()
        self.assertTrue(self.plan.is_stopping())
        self.assertEquals(Plan.STOPPING, self.plan.state)
        self.set_tasks_to_state(constants.TASK_SUCCESS)

        self.plan.end()
        self.assertTrue(self.plan.is_final())
        self.assertEquals(Plan.SUCCESSFUL, self.plan.state)

    def test_plan_failed_state(self):
        self.assertFalse(self.plan.is_running())
        self.plan.run()
        self.assertTrue(self.plan.is_running())
        self.assertEquals(Plan.RUNNING, self.plan.state)

        self.assertFalse(self.plan.has_failures())
        self.vim_task.state = constants.TASK_FAILED
        self.assertTrue(self.plan.has_failures())

        self.plan.end()
        self.assertTrue(self.plan.is_final())
        self.assertEquals(Plan.FAILED, self.plan.state)

    def test_plan_stopped_state_with_failures(self):
        # note failed tasks change end state from stopping to failed
        self.assertFalse(self.plan.is_running())
        self.plan.run()
        self.assertTrue(self.plan.is_running())
        self.assertEquals(Plan.RUNNING, self.plan.state)

        self.assertFalse(self.plan.is_stopping())
        self.plan.stop()
        self.assertTrue(self.plan.is_stopping())
        self.assertEquals(Plan.STOPPING, self.plan.state)

        self.assertFalse(self.plan.has_failures())
        self.vim_task.state = constants.TASK_FAILED
        self.assertTrue(self.plan.has_failures())
        self.assertEquals(Plan.STOPPING, self.plan.state)

        self.plan.end()
        self.assertTrue(self.plan.is_final())
        self.assertEquals(Plan.STOPPED, self.plan.state)

    def test_plan_invalid_state(self):
        self.assertFalse(self.plan.is_running())
        self.plan.mark_invalid()
        self.assertTrue(self.plan.is_invalid())
        self.assertTrue(self.plan.is_final())

    def test_locked_node_with_empty_lock_tasks(self):
        node = self.model.query("node")[0]
        node.set_property('is_locked', "true")
        # Create Plan with no lock_tasks, but with a locked node.
        try:
            Plan([[self.os_task, self.sys_task, self.vim_task, self.d_task]],
                 [], lock_tasks={})
        except KeyError as e:
            self.fail(str(e))


class PlanFindTasksTest(unittest.TestCase):
    # TODO: test cache hits
    def setUp(self):
        model = ModelManager()

        model.register_property_type(PropertyType("basic_string"))
        model.register_item_types([
            ItemType("root",
                nodes=Collection("node"),
                ms=Child("node"),
            ),
            ItemType("node",
                hostname=Property("basic_string")
            )
        ])

        model.create_root_item("root")
        model.create_item(
            "node", "/nodes/node1", hostname="node1")
        model.create_item("node", "/ms", hostname="ms1")
        node = QueryItem(model, model.query_by_vpath("/nodes/node1"))
        self.tasks = [
            ConfigTask(node, node, "", "foo", "bar"),
            CallbackTask(node, "", mock.Mock()),
            CleanupTask(node)
        ]
        self.model_item = node
        self.tasks[0].state = 'Success'
        self.tasks[1].state = 'Initial'
        self.tasks[2].state = 'Initial'
        phases = [[self.tasks[0]], [self.tasks[1]]]
        self.plan = Plan(phases, cleanup_tasks=[self.tasks[2]])

    def test_no_criteria(self):
        result = self.plan.find_tasks()
        self.assertTrue(self.tasks[0] in result)
        self.assertTrue(self.tasks[1] in result)
        self.assertEquals({(None, None): set(self.tasks)},
                          self.plan._find_tasks_cache)

    def test_find_by_current_phase(self):
        self.plan.current_phase = 0
        result1 = self.plan.find_tasks(phase='current')
        self.assertEqual(set([self.tasks[0]]), result1)
        self.assertEquals({(0, None): result1}, self.plan._find_tasks_cache)

        self.plan.current_phase = None
        result2 = self.plan.find_tasks(phase='current')
        self.assertFalse(result2)
        self.assertEquals({(0, None): result1}, self.plan._find_tasks_cache)

    def test_find_by_phase_index(self):
        result1 = self.plan.find_tasks(phase=0)
        self.assertEqual(set([self.tasks[0]]), result1)
        self.assertEquals({(0, None): result1}, self.plan._find_tasks_cache)

        result2 = self.plan.find_tasks(phase=1)
        self.assertEqual(set([self.tasks[1]]), result2)
        self.assertEquals({(0, None): result1,
                           (1, None): result2}, self.plan._find_tasks_cache)

        result3 = self.plan.find_tasks(phase=-1)
        self.assertFalse(result3)

        # Phase 2 is the "cleanup phase"
        result4 = self.plan.find_tasks(phase=2)
        self.assertEquals(set([self.tasks[2]]), result4)

        result5 = self.plan.find_tasks(phase=3)
        self.assertFalse(result5)

        self.assertEquals(
            {
                (0, None): result1,
                (1, None): result2,
                (2, None): result4
            }, self.plan._find_tasks_cache
        )

    def test_find_by_model_item(self):
        result1 = self.plan.find_tasks(model_item=self.model_item)
        self.assertTrue(self.tasks[0] in result1)
        self.assertTrue(self.tasks[1] in result1)
        result2 = self.plan.find_tasks(phase=0, model_item=self.model_item)
        self.assertTrue(self.tasks[0] in result2)
        self.assertTrue(self.tasks[1] not in result2)
        result3 = self.plan.find_tasks(phase=1, model_item=self.model_item)
        self.assertTrue(self.tasks[0] not in result3)
        self.assertTrue(self.tasks[1] in result3)

    def test_find_by_state(self):
        result1 = self.plan.find_tasks(state=self.tasks[0].state)
        self.assertTrue(self.tasks[0] in result1)
        self.assertTrue(self.tasks[1] not in result1)

        result2 = self.plan.find_tasks(state=[self.tasks[0].state])
        self.assertTrue(self.tasks[0] in result2)
        self.assertTrue(self.tasks[1] not in result2)

        self.tasks[1].state = self.tasks[0].state
        result3 = self.plan.find_tasks(phase=0, model_item=self.model_item,
                                       state=self.tasks[0].state)
        self.assertTrue(self.tasks[0] in result3)
        self.assertTrue(self.tasks[1] not in result3)

    def test_get_tasks_no_filter(self):
        all_tasks = self.plan.get_tasks()
        self.assertEquals(
            self.tasks,
            all_tasks
        )

    def test_get_tasks_with_filter(self):
        self.assertEquals(
            [self.tasks[0]],
            self.plan.get_tasks(ConfigTask)
        )

        self.assertEquals(
            [self.tasks[1]],
            self.plan.get_tasks(CallbackTask)
        )

        self.assertEquals(
            [self.tasks[2]],
            self.plan.get_tasks(CleanupTask)
        )


class TestGetTaskCluster(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()

        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_item_types([
            ItemType("root",
                clusters=Collection("cluster-base"),
                ms=Child("node"),
                infrastructure=Child("infra", required=True),
            ),
            ItemType("node",
                hostname=Property("basic_string"),
                items=Collection("item"),
            ),
            ItemType("cluster-base",
                nodes=Collection("node"),
                fencing_disk=Child("disk"),
                items=Collection("item"),
            ),
            ItemType("infra",
                systems=Collection("system"),
                luns=Collection("disk"),
            ),
            ItemType("system",
                disks=Collection("disk"),
            ),
            ItemType("disk",
                uuid=Property("basic_string"),
            ),
            ItemType("item",
                prop=Property("basic_string"),
            ),
        ])

        self.model.create_root_item("root")
        self.model.create_item("node", "/ms", hostname="ms1")
        self.model.create_item("item", "/ms/items/item", prop="popop")
        self.model.create_item("system", "/infrastructure/systems/sys1")
        self.model.create_item("disk", "/infrastructure/systems/sys1/disks/disk0", uuid="foo")
        self.model.create_item("disk", "/infrastructure/luns/lun0", uuid="bar")
        #
        self.model.create_item("cluster-base", "/clusters/c1")
        self.model.create_item("disk", "/clusters/c1/fencing_disk", uuid="f3432432")
        self.model.create_item("node", "/clusters/c1/nodes/n1", hostname="node1")
        self.model.create_item("item", "/clusters/c1/nodes/n1/items/foo", prop="foo")
        self.model.create_item("node", "/clusters/c1/nodes/n2", hostname="node2")
        self.model.create_item("item", "/clusters/c1/nodes/n2/items/foo", prop="foo")
        self.model.create_item("item", "/clusters/c1/items/bar", prop="dfdsfs")

        self.plan = Plan([], [])
        self.c1 = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1"))

    def test_ms_cbtask(self):
        ms_item = QueryItem(self.model, self.model.query_by_vpath("/ms"))
        task = CallbackTask(ms_item, "", mock.Mock())
        self.assertEqual(None, self.plan._get_task_cluster(task))

    def test_ms_item_cbtask(self):
        ms_item_item = QueryItem(self.model, self.model.query_by_vpath("/ms/items/item"))
        task = CallbackTask(ms_item_item, "", mock.Mock())
        self.assertEqual(None, self.plan._get_task_cluster(task))

    def test_infra_cbtask(self):
        infra_item = QueryItem(self.model, self.model.query_by_vpath("/infrastructure/luns/lun0"))
        task = CallbackTask(infra_item, "", mock.Mock())
        self.assertEqual(None, self.plan._get_task_cluster(task))

    def test_cluster_cbtask(self):
        cluster_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1"))
        task = CallbackTask(cluster_item, "", mock.Mock())
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_cluster_fencing_disk_cbtask(self):
        fencing_disk_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/fencing_disk"))
        task = CallbackTask(fencing_disk_item, "", mock.Mock())
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_cluster_item_cbtask(self):
        cluster_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/items/bar"))
        task = CallbackTask(cluster_item, "", mock.Mock())
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_node_cbtask(self):
        node_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n1"))
        task = CallbackTask(node_item, "", mock.Mock())
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_node_item_cbtask(self):
        node_item_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n1/items/foo"))
        task = CallbackTask(node_item_item, "", mock.Mock())
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_node_cfgtask(self):
        node_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n1"))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1"))
        task = ConfigTask(node_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/ms"))
        task = ConfigTask(node_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n2"))
        task = ConfigTask(node_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_ms_cfgtask(self):
        ms_item = QueryItem(self.model, self.model.query_by_vpath("/ms"))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1"))
        task = ConfigTask(ms_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(None, self.plan._get_task_cluster(task))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/ms"))
        task = ConfigTask(ms_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(None, self.plan._get_task_cluster(task))

        cfgtask_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n2"))
        task = ConfigTask(ms_item, cfgtask_item, "", "foo", "bar")
        self.assertEqual(None, self.plan._get_task_cluster(task))

    def test_cleanuptask(self):
        cluster_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1"))
        task = CleanupTask(cluster_item)
        self.assertEqual(None, self.plan._get_task_cluster(task))

        node_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n1"))
        task = CleanupTask(node_item)
        self.assertEqual(None, self.plan._get_task_cluster(task))

        ms_item = QueryItem(self.model, self.model.query_by_vpath("/ms/items/item"))
        task = CleanupTask(ms_item)
        self.assertEqual(None, self.plan._get_task_cluster(task))

    def test_remoteexecutiontask(self):
        ms_item = QueryItem(self.model, self.model.query_by_vpath("/ms"))
        node1_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n1"))
        node2_item = QueryItem(self.model, self.model.query_by_vpath("/clusters/c1/nodes/n2"))

        task = RemoteExecutionTask([ms_item, node1_item, node2_item], ms_item, "", "foo", "bar")
        self.assertEqual(None, self.plan._get_task_cluster(task))

        task = RemoteExecutionTask([node1_item, node2_item], ms_item, "", "foo", "bar")
        self.assertEqual(self.c1, self.plan._get_task_cluster(task))

    def test_get_phase_cluster(self):
        phase = [
            CallbackTask(self.c1.nodes.n1.items.foo, "CB task for n1", mock.Mock()),
            CallbackTask(self.c1.nodes.n2.items.foo, "CB task for n2", mock.Mock()),
        ]
        self.plan = Plan([phase,], [])
        self.assertEquals(self.c1, self.plan._get_cluster_phase(0))

    def test_get_phase_cluster_deleted_item_on_resume(self):
        phase = [
            CallbackTask(self.c1.nodes.n1.items.foo, "CB task for n1", mock.Mock()),
            CallbackTask(self.c1.nodes.n2.items.foo, "CB task for n2", mock.Mock()),
        ]
        phase[0].state = constants.TASK_SUCCESS
        phase[0]._model_item = self.c1.nodes.n1.items.foo.vpath
        phase[1].state = constants.TASK_FAILED
        self.plan = Plan([phase,], [])

        # XXX
        # HOW ABOUT a test for get_clusters_in_phase when there's no deleted
        # item
    def test_get_clusters_in_phase(self):
        phase = [
            CallbackTask(self.c1.nodes.n1.items.foo, "CB task for n1", mock.Mock()),
            CallbackTask(self.c1.nodes.n2.items.foo, "CB task for n2", mock.Mock()),
        ]
        self.plan = Plan([phase,], [])
        self.assertEquals(set([self.c1]), self.plan._get_clusters_in_phase(0))

        def test_get_clusters_in_phase_deleted_item_on_resume(self):
            phase = [
                CallbackTask(self.c1.nodes.n1.items.foo, "CB task for n1", mock.Mock()),
                CallbackTask(self.c1.nodes.n2.items.foo, "CB task for n2", mock.Mock()),
            ]
            phase[0].state = constants.TASK_SUCCESS
            phase[0]._model_item = self.c1.nodes.n1.items.foo.vpath
            phase[1].state = constants.TASK_FAILED
            self.plan = Plan([phase,], [])
            self.assertEquals(self.c1, self.plan._get_cluster_phase(0))
        self.assertEquals(
            set([self.c1]),
            self.plan._get_clusters_in_phase(0)
        )
