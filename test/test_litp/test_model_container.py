
import copy
import os
import json
import unittest
from time import sleep
from tempfile import mkstemp
from itertools import permutations

from mock import Mock, MagicMock, patch

from litp.core.nextgen.model_manager import ModelManager
from litp.core.model_manager import QueryItem
from litp.core.model_item import ModelItem
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_item import CollectionItem
from litp.core.model_type import Property
from litp.core.model_type import Reference
from litp.core.model_type import RefCollection
from litp.core.model_type import PropertyType
from litp.core.validators import ValidationError
from litp.core.model_container import ModelItemContainer
from litp.core.exceptions import ModelItemContainerException
from litp.core.execution_manager import ExecutionManager
from litp.core.execution_manager import Task
from litp.core.execution_manager import ConfigTask
from litp.core.execution_manager import CallbackTask
from litp.core.future_property_value import FuturePropertyValue
from litp.core.task import RemoteExecutionTask
from litp.core.puppet_manager import PuppetManager
from litp.core.plugin import Plugin
from litp.core.plan import Plan
from litp.core.constants import TASK_INITIAL, TASK_SUCCESS, LIVE_MODEL, TASK_FAILED
from serializer.litp_serializer import take_ticket, release_ticket
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.constants import CURRENT_PLAN_ID
from litp.data.test_db_engine import get_engine


class MockPluginManager(object):
    def __init__(self):
        self.plugin_info = [
            {
                'name': 'bob',
                'class': 'foo.bar.baz',
                'version': '1.0.0'
            },
            {
                'name': 'Geronimo',
                'class': 'really.silly.module.class',
                'version': '1.2.4'
            }
        ]
        self.extensions = [
            {
                'name': 'bob',
                'class': 'foo.bar.baz',
                'version': '1.0.0'
            },
            {
                'name': 'Geronimo',
                'class': 'really.silly.module.class',
                'version': '1.2.4'
            }
        ]
        self.plugins = {'test_model_container.MockPlugin': MockPlugin()}

    def get_plugin_info(self):
        return self.plugin_info

    def get_extension_info(self):
        return self.extensions

    def get_plugin(self, plugin_class):
        return self.plugins.get(plugin_class)


class MockPlugin(Plugin):
    def callback(self, arg1, param1=None):
        self.called_args = arg1, param1


def mock_set_debug(force_debug=False):
    pass


class MockPuppetManager(object):
    def __init__(self):
        self.node_tasks = {}

    def attach_handler(self, *args, **kwargs):
        pass


class ModelContainerTest(unittest.TestCase):
    def setUp(self):
        self.db_storage = DbStorage(get_engine())
        self.db_storage.reset()
        self.data_manager = DataManager(self.db_storage.create_session())

        self.manager = ModelManager()
        self.data_manager.configure(self.manager)
        self.manager.data_manager = self.data_manager

        self.manager.register_property_type(PropertyType("basic_string"))
        self.manager.register_item_type(ItemType("root",
            services=Collection("clusteredservice"),
            nodes=Collection("node"),
            systems=Collection("system"),
            blades=Collection("blade"),
        ))
        self.manager.register_item_type(ItemType("os"))
        self.manager.register_item_type(ItemType("network"))
        self.manager.register_item_type(ItemType("clusteredservice",
            nodes=RefCollection("node"),
        ))
        self.manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            is_locked=Property("basic_string", default="false"),
            system=Reference("system"),
            os=Child("os", require="system"),
            network=Child("network", require="os"),
        ))
        self.manager.register_item_type(ItemType("system",
            name=Property("basic_string"),
            description=Property("basic_string"),
            blade=Reference("blade"),
        ))
        self.manager.register_item_type(ItemType("blade",
            blade_type=Property("basic_string"),
        ))

        plugin_manager = MockPluginManager()

        puppet_manager = MockPuppetManager()
        self.execution = ExecutionManager(
            self.manager, puppet_manager, None)

        self.model_container = ModelItemContainer(
            self.manager, plugin_manager, self.execution)

        original_do_unpickling = self.model_container._do_unpickling
        def do_unpickling(*args, **kwargs):
            self.model_container.data_manager.rollback()
            self.db_storage.reset()
            return original_do_unpickling(*args, **kwargs)
        self.model_container._do_unpickling = do_unpickling

        self.plugin1 = MockPlugin()

    def tearDown(self):
        self.data_manager.rollback()
        self.data_manager.close()

    def test_pickle_unpickle_applied_properties_determinable_true(self):
        # Test with True flag
        root_mi = self.manager.create_root_item("root")
        self.assertEqual(True, root_mi.applied_properties_determinable)
        actual_lkc_json = self.model_container.serialize()
        self.model_container.do_unpickling(json.loads(actual_lkc_json))
        root_qi = self.model_container.model_manager.query_by_vpath("/")
        self.assertEqual(True, root_qi.applied_properties_determinable)

    def test_pickle_unpickle_applied_properties_determinable_false(self):
        # Test with False flag
        root_mi = self.manager.create_root_item("root")
        root_mi._set_applied_properties_determinable(False)
        actual_lkc_json = self.model_container.serialize()
        self.model_container.do_unpickling(json.loads(actual_lkc_json))
        root_qi = self.model_container.model_manager.query_by_vpath("/")
        self.assertEqual(False, root_qi.applied_properties_determinable)

    def test_model_persistence_ref_collection(self):
        self.manager.create_root_item("root")
        service = self.manager.create_item("clusteredservice",
            "/services/service1")
        self.assertEqual(0, len(service.nodes))
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        node = self.manager.create_inherited(
            "/nodes/node1",
            "/services/service1/nodes/node1")
        self.assertEqual(1, len(service.nodes))
        self.assertEqual(ModelItem, type(node))

        actual = self.model_container.serialize()
        expected = open(os.path.join(os.path.dirname(__file__),
            "expected1.json")).read()

        self.assertEqual(json.loads(expected), json.loads(actual))

    def test_model_persistence_applied_properties(self):
        self.manager.create_root_item("root")
        service = self.manager.create_item("clusteredservice",
            "/services/service1")
        self.manager.create_item("node", "/nodes/node1",
            hostname="node1.com")
        self.assertEqual(0, len(service.nodes))
        node = self.manager.create_inherited("/nodes/node1",
            "/services/service1/nodes/node1")
        self.assertEqual(1, len(service.nodes))
        self.assertEqual(ModelItem, type(node))


        self.manager.set_all_applied()

        self.manager.update_item('/nodes/node1', hostname="new.com")

        actual = self.model_container.serialize()
        expected = open(os.path.join(os.path.dirname(__file__),
            "expected_applied_updated.json")).read()

        self.assertEqual(json.loads(expected), json.loads(actual))

    def test_model_persistence_with_plan(self):
        self.manager.create_root_item("root")

        node1 = self.manager.create_item("node", "/nodes/node1",
            hostname="node1")
        self.sys1 = self.manager.create_item("system", "/systems/sys1",
            name="sys1")
        self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")

        self.node = QueryItem(self.manager, node1)
        # Test pickling/unpickling of FuturePropertyValue
        future_property_value = FuturePropertyValue(self.node, 'hostname')
        self.node_task = ConfigTask(self.node, self.node, "Node Task", "node1",
            "task1", my_name=future_property_value)
        self.sys_task = ConfigTask(self.node, self.node.system,
            "Install system", "system", "sys1", param="value")
        self.call_task = CallbackTask(self.node.system, "Callback 1",
            self.plugin1.callback, "arg1", param1="value1")
        self.call_task.model_items.add(self.node)

        self.remote_execution_task = RemoteExecutionTask([self.node],
                self.node.system, "RemoteExecutionTask 1", "agent", "action",
                param1="value1")
        self.remote_execution_task.model_items.add(self.node)

        self.node_task.group = self.sys_task.group = self.call_task.group \
            = deployment_plan_groups.NODE_GROUP
        self.node_task.plugin_name = self.sys_task.plugin_name \
            = self.call_task.plugin_name = 'Plugin'
        self.sys_task.state = "Success"

        self.node_task._id = "92bbd88b-c48d-4ba4-9734-088da83a9714"
        self.sys_task._id = "dedbb1ed-f16b-4248-8b7d-ebad10e8c608"

        self.plan = Plan([], [])
        self.plan._phases = [[self.node_task, self.sys_task,
            self.call_task, self.remote_execution_task]]
        self.plan.set_ready()
        self.execution.plan = self.plan

        self.execution.puppet_manager.node_tasks[self.node.hostname] = \
            [self.node_task]

        actual_lkc_json = self.model_container.serialize()
        expected = open(os.path.join(os.path.dirname(__file__),
            "expected_plan.json")).read()

        self.assertEqual(json.loads(expected), json.loads(actual_lkc_json))
        # Make sure the plan gets unpickled with FuturePropertyValue instance.
        self.data_manager.commit()
        self.data_manager.session.expunge_all()
        self.model_container.do_unpickling(json.loads(actual_lkc_json))
        plan = self.data_manager.get_plan(CURRENT_PLAN_ID)
        for t in plan.phases[0]:
            my_name = t.kwargs.get('my_name')
            if my_name:
                self.assertTrue(isinstance(my_name, FuturePropertyValue))
                self.assertEquals("node1", my_name.value)
                break
        else:
            self.fail("Task with FuturePropertyValue in kwargs not found")

    def test_load(self):
        expected = open(os.path.join(os.path.dirname(__file__),
            "expected1.json")).read()
        self.model_container.do_unpickling(json.loads(expected))

        self.assertEqual(ModelItem,
            type(self.manager.get_item("/services/service1/nodes/node1")))
        self.assertEqual("/services/service1/nodes/node1",
            self.manager.get_item("/services/service1/nodes/node1").get_vpath())

        self.assertEqual("/nodes/node1",
            self.manager.query("node")[0].get_vpath())

    def test_load_plan(self):
        expected = open(os.path.join(os.path.dirname(__file__),
            "expected_plan.json")).read()
        self.model_container.do_unpickling(json.loads(expected))

        self.assertEqual("node1",
            self.manager.get_item("/nodes/node1").hostname)
        self.assertEqual("/nodes/node1",
            self.manager.get_item("/nodes/node1").get_vpath())

        plan = self.data_manager.get_plan(CURRENT_PLAN_ID)
        for t in plan._tasks:
            t.group = deployment_plan_groups.NODE_GROUP
        self.assertEquals(4, len(plan._tasks))
        self.assertEquals(1, len(plan._phases))
        self.assertEquals("Success", plan._tasks[1].state)
        self.assertEquals({'param': 'value'},
            plan._tasks[1].kwargs)

        # ensure default sort order is the same as unpickled
        # NO! Plan shouldn't be sorting anything
        # plan = Plan(self.manager, self.execution.plan.get_tasks(), [])
        # self.assertEquals(plan.phases, self.execution.plan.phases)

    def test_removed_items(self):
        # 1. create a plan with some tasks
        manager = self.manager
        manager.create_root_item('root')
        manager.create_item('system', '/systems/sys1', name='sys1')
        node1 = manager.create_item('node', "/nodes/node1", hostname="node1")
        sys1 = manager.create_inherited('/systems/sys1', "/nodes/node1/system")
        node = QueryItem(self.manager, self.manager.query("node")[0])
        node_task = ConfigTask(node,
            manager.query_by_vpath('/nodes/node1'),
            "Node Task", "node1", "task1")
        node_task.state = TASK_SUCCESS
        sys_task = ConfigTask(node,
            manager.query_by_vpath('/nodes/node1/system'),
            "Install system", "system",
            "sys1", param='value')
        sys_task.state = TASK_SUCCESS
        node_task.group = sys_task.group = deployment_plan_groups.NODE_GROUP
        node_task.plugin_name = sys_task.plugin_name = 'Plugin'
        # Don't pass successful tasks to plan as they'll get filtered by
        # PlanBuildee
        # Plan currently uses PlanBuilder in the constructor to construct
        # itself. That has to change as the coupling of these two is too high.
        self.execution.plan = Plan([], [])
        self.execution.plan._phases = [[node_task, sys_task]]

        # 2. now remove items referenced by tasks
        errors = manager.remove_item('/nodes/node1')
        self.assertEqual(manager.get_item('/nodes/node1'), None)
        manager.remove_item('/nodes/node1/system')
        self.assertEqual(manager.get_item('/nodes/node1/system'), None)

        # 3. encode & decode
        encoded = self.model_container.serialize()
        self.model_container.do_unpickling(json.loads(encoded))

        # 4. check items are still removed
        self.assertEqual(manager.get_item('/nodes/node1'), None)
        self.assertEqual(manager.get_item('/nodes/node1/system'), None)

        # 5. retrieve decoded tasks
        self.assertEqual(2, len(self.execution.plan.get_tasks()))
        dec_node_task = None
        dec_sys_task = None
        for task in self.execution.plan.get_tasks():
            if task.call_id == node_task.call_id:
                dec_node_task = task
            elif task.call_id == sys_task.call_id:
                dec_sys_task = task

        # 6. finally check tasks restored with correct items
        dec_node1_qi = dec_node_task.model_item
        self.assertNotEqual(dec_node1_qi, None)
        self.assertEqual(dec_node1_qi.vpath, node1.vpath)
        dec_sys1_qi = dec_sys_task.model_item
        self.assertNotEqual(dec_sys1_qi, None)
        self.assertEqual(dec_sys1_qi.vpath, sys1.vpath)

    def test_pickle_unpickle_remote_execution_task(self):
        self.manager.create_root_item("root")
        self.manager.create_item("system", "/systems/system1", name="sys1")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("node", "/nodes/node2", hostname="node2")

        system = QueryItem(self.manager, self.manager.query("system")[0])
        nodes = [QueryItem(self.manager, model_item)
                for model_item in self.manager.query("node")]

        kwargs = {"kw1": "val1", "kw2": "val2", "kw3": "val3"}
        task = RemoteExecutionTask(nodes, system, "", "agent", "action", **kwargs)

        obj = self.model_container._pickle_remote_execution_task(task)
        task2 = self.model_container._unpickle_remote_execution_task(obj)

        self.assertEquals(task, task2)

    def test_pickle_inherited(self):
        self.manager.create_root_item("root")
        self.manager.create_item("system", "/systems/system1", name="sys1", description="foo")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_inherited("/systems/system1", "/nodes/node1/system", name="sys2")

        system = self.manager.get_item("/systems/system1")
        node_system = self.manager.get_item("/nodes/node1/system")
        self.assertEquals(system.vpath, node_system.source_vpath)

        lkc_json = self.model_container.serialize()
        self.model_container.do_unpickling(json.loads(lkc_json))

        system = self.manager.get_item("/systems/system1")
        node_system = self.manager.get_item("/nodes/node1/system")
        self.assertEquals(system.vpath, node_system.source_vpath)
        self.assertEquals("sys2", node_system.properties.get("name"))
        self.assertTrue("description" not in node_system.properties)

    def test_removed_item_type(self):
        lkc_json = """\
{
    "puppet_manager": {
        "node_tasks": {}
    },
    "items": {
        "/": {
            "__type__": "ModelItem",
            "item_type_id": "nonexistent",
            "item_status": "Initial",
            "item_previous_status": null,
            "item_previous_state_cascade": null,
            "item_properties": {},
            "item_applied_properties": {},
            "item_source": null
        }
    },
    "removed_items": {},
    "plan": null,
    "extensions": [
        {
            "version": "1.0.0",
            "name": "foo_ext",
            "class": "litp.foo_ext.FooExtension"
        }
    ],
    "plugins": [
        {
            "version": "1.0.0",
            "name": "foo_plugin",
            "class": "litp.foo_plugin.FooPlugin"
        }
    ]
}\
"""
        self.assertRaises(ModelItemContainerException, self.model_container.do_unpickling, json.loads(lkc_json))

    def test_removed_plugin(self):
        lkc_json = """\
{
    "puppet_manager": {
        "node_tasks": {}
    },
    "items": {
        "/": {
            "__type__": "ModelItem",
            "item_app_prop_det": false,
            "item_type_id": "system",
            "item_status": "Initial",
            "item_previous_status": null,
            "item_previous_state_cascade": null,
            "item_properties": {},
            "item_applied_properties": {},
            "item_source": null
        },
        "/blade": {
            "__type__": "ModelItem",
            "item_app_prop_det": false,
            "item_type_id": "blade",
            "item_status": "Initial",
            "item_previous_status": null,
            "item_previous_state_cascade": null,
            "item_properties": {},
            "item_applied_properties": {},
            "item_source": null
        }
    },
    "removed_items": {},
    "plan": {
        "__type__": "Plan",
        "phases": [
            [
                {
                    "__type__": "CallbackTask",
                    "model_item": "/blade",
                    "callback": "callback",
                    "state": "Initial",
                    "description": "Callback 1",
                    "plugin": "nonexistent",
                    "kwargs": {
                        "param1": "value1"
                    },
                    "args": [
                        "arg1"
                    ]
                }
            ]
        ],
        "has_cleanup_phase": false,
        "is_snapshot_plan": false,
        "state": "initial"
    },
    "extensions": [
        {
            "version": "1.0.0",
            "name": "foo_ext",
            "class": "litp.foo_ext.FooExtension"
        }
    ],
    "plugins": [
        {
            "version": "1.0.0",
            "name": "foo_plugin",
            "class": "litp.foo_plugin.FooPlugin"
        }
    ]
}\
"""
        self.assertRaises(ModelItemContainerException, self.model_container.do_unpickling, json.loads(lkc_json))

    def test_pickling_and_rebuilding_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("system", "/systems/sys1", name="sys1")
        self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        self.manager.create_item("os", "/nodes/node1/os")
        self.manager.create_item("network", "/nodes/node1/network")
        node1 = QueryItem(self.manager,
                self.manager.query_by_vpath("/nodes/node1"))

        task1 = ConfigTask(node1, node1.system, "", "1", "1_1")
        task2 = ConfigTask(node1, node1.os, "", "1", "1_2")
        task3 = ConfigTask(node1, node1.network, "", "1", "1_3")
        task1.state = task2.state = task3.state = TASK_SUCCESS

        task2.requires.add(task1)
        task3.requires.add(task1.model_item)
        task3.requires.add(task2)

        tasks = [task1, task2, task3]

        self._add_attribs_to_model_container()

        # pickle first
        pickled = [self.model_container._pickle_config_task(task)
                   for task in [task1, task2, task3]]

        self.assertFalse(pickled[0]['requires']['items'])
        self.assertFalse(pickled[0]['requires']['tasks'])
        self.assertTrue(task1.unique_id in pickled[1]['requires']['tasks'])
        self.assertFalse(pickled[1]['requires']['items'])
        self.assertTrue(task1.model_item.vpath in
                        pickled[2]['requires']['items'])
        self.assertTrue(task2.unique_id in pickled[2]['requires']['tasks'])

        # unpickle - test all possible orders of tasks
        unpickle_fn = self.model_container._unpickle_config_task
        for order in permutations(zip(tasks, pickled)):
            unpickled = [unpickle_fn(task_pickled[1]) for task_pickled in order]
            self.assertEqual(order[0][0], unpickled[0])
            self.assertEqual(order[1][0], unpickled[1])
            self.assertEqual(order[2][0], unpickled[2])

        # after processing all tasks there should be no unersolved task deps
        self.assertFalse(self.model_container._unresolved_task_dependencies)

    def _add_attribs_to_model_container(self):
        """this normally is done by ModelContainer.do_pickling() which also
        takes care of deleting them when no longer needed"""
        # stores pointers to tasks with unresolved task dependencies to be
        # updated as soon as the dependency task is unpickled
        self.model_container._unresolved_task_dependencies = {}
        # stores unpickled config tasks for rebuilding `requires` collection
        self.model_container._unpickled_config_tasks = {}

    def test_pickle_unpickle_call_type_call_id_in_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        node1 = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))

        task = ConfigTask(node1, node1, "", "1", "1_1")
        call_type_call_id = ("2", "2_1")
        task.requires.add(call_type_call_id)
        task.state = TASK_SUCCESS

        self._add_attribs_to_model_container()

        pickled = self.model_container._pickle_config_task(task)

        task_a = self.model_container._unpickle_config_task(pickled)
        self.assertEqual(set([call_type_call_id]), task_a.requires)

    def test_unpickling_nonsuccessful_task_no_rebuilding_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        node1 = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))

        task1 = ConfigTask(node1, node1, "", "1", "1_1")
        task2 = ConfigTask(node1, node1, "", "2", "2_1")
        task2.requires.add(task1)

        self._add_attribs_to_model_container()

        pickled1 = self.model_container._pickle_config_task(task1)
        pickled2 = self.model_container._pickle_config_task(task2)
        task1a = self.model_container._unpickle_config_task(pickled1)
        task2a = self.model_container._unpickle_config_task(pickled2)
        self.assertFalse(task1a.requires)
        self.assertFalse(task2a.requires)
        self.assertFalse(self.model_container._unpickled_config_tasks)
        self.assertFalse(self.model_container._unresolved_task_dependencies)

    def test_unpickling_task_removed_node_no_rebuilding_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        system = self.manager.create_item("system", "/systems/sys1", name="sys1")
        #self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        node1 = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))

        task1 = ConfigTask(node1, system, "", "1", "1_1")
        task2 = ConfigTask(node1, system, "", "2", "2_1")
        task1.state = task2.state = TASK_SUCCESS

        self._add_attribs_to_model_container()

        pickled1 = self.model_container._pickle_config_task(task1)
        pickled2 = self.model_container._pickle_config_task(task2)

        self.manager.remove_item('/nodes/node1')
        task1a = self.model_container._unpickle_config_task(pickled1)
        task2a = self.model_container._unpickle_config_task(pickled2)
        task2.requires.add(task1)
        self.assertFalse(task1a.requires)
        self.assertFalse(task2a.requires)
        self.assertFalse(self.model_container._unpickled_config_tasks)
        self.assertFalse(self.model_container._unresolved_task_dependencies)

    def test_unpickling_task_with_removed_model_item_no_rebuilding_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("system", "/systems/sys1", name="sys1")
        self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        self.manager.create_item("os", "/nodes/node1/os")
        node1 = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))

        task1 = ConfigTask(node1, node1.system, "", "1", "1_1")
        task2 = ConfigTask(node1, node1.os, "", "2", "2_1")
        task2.requires.add(task1)
        task1.state = task2.state = TASK_SUCCESS

        self._add_attribs_to_model_container()

        pickled1 = self.model_container._pickle_config_task(task1)
        pickled1 = self.model_container._pickle_config_task(task1)
        pickled2 = self.model_container._pickle_config_task(task2)

        self.manager.remove_item('/nodes/node1/system')
        task1a = self.model_container._unpickle_config_task(pickled1)
        task2a = self.model_container._unpickle_config_task(pickled2)
        self.assertFalse(task1a.requires)
        self.assertFalse(task2a.requires)
        # ModelContainer._unpickled_config_tasks
        # and ModelContainer._unresolved_task_dependencies
        # should be dirty at this point - they get cleared by the caller of
        # ModelContainer._unpickle_config_task
        self.assertTrue((task2a.node.hostname, task2a.unique_id) in
                        self.model_container._unpickled_config_tasks)
        self.assertEqual(task2a,
                         self.model_container._unpickled_config_tasks[
                             (task2a.node.hostname, task2a.unique_id)])
        self.assertTrue((task1a.node.hostname, task1a.unique_id) in
                        self.model_container._unresolved_task_dependencies)
        self.assertEqual(set([task2a]),
                         self.model_container._unresolved_task_dependencies[
                             (task1a.node.hostname, task1a.unique_id)])

    def test_pickle_unpickle_configtask_requires(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        node = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))

        task = ConfigTask(node, node, "", "1", "1_1")
        obj = self.model_container._pickle_config_task(task)
        self.assertFalse(obj['dependency_unique_ids'])

        dep_task = ConfigTask(node, node, "Direct task dependency", "2", "2_1")
        # dep_qitem is node
        dep_task_from_qitem = ConfigTask(node, node,
                                         "Task from query item dependency",
                                         "3", "3_1")
        required_unique_ids = set([dep_task.unique_id,
                                   dep_task_from_qitem.unique_id])
        task._requires = required_unique_ids
        obj = self.model_container._pickle_config_task(task)
        self.assertTrue(obj['dependency_unique_ids'])
        self.assertEquals(2, len(obj["dependency_unique_ids"]))
        self.assertTrue(dep_task.unique_id in obj["dependency_unique_ids"])
        self.assertTrue(dep_task_from_qitem.unique_id in
                        obj["dependency_unique_ids"])

        task = self.model_container._unpickle_config_task(obj)
        self.assertEquals(required_unique_ids, task._requires)

    def test_pickle_configtask_extra_items(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("system", "/systems/sys1", name="foo", description="bar")
        self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        self.manager.create_item("blade", "/blades/blade", blade_type="serrated")

        node = QueryItem(self.manager, self.manager.query_by_vpath("/nodes/node1"))
        blade = QueryItem(self.manager, self.manager.query_by_vpath("/blades/blade"))

        task = ConfigTask(node, node.system, "alpha", "bravo", "charlie")
        task.group = deployment_plan_groups.NODE_GROUP
        task.model_items.add(blade)
        task.replaces.add(("call_type_2", "call_id_2"))
        pickled_task = self.model_container._pickle_config_task(task)

        expected_pickled_task = {
            'node': '/nodes/node1',
            'model_item': '/nodes/node1/system',
            'model_items': ['/blades/blade'],
            'description': 'alpha',
            'call_type': 'bravo',
            'call_id': 'charlie',
            'kwargs': {},
            'state': TASK_INITIAL,
            'group': deployment_plan_groups.NODE_GROUP,
            'uuid': task.uuid,
            'dependency_unique_ids': [],
            'persist': True,
            'requires': {"tasks": [], "items": [], "call_type_call_id": []},
            'replaces': [["call_type_2", "call_id_2"]]
        }
        self.assertTrue(isinstance(pickled_task, dict))
        self.assertEquals(expected_pickled_task, pickled_task)

    def test_unpickle_configtask_extra_items(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("system", "/systems/sys1", name="foo", description="bar")
        self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        self.manager.create_item("blade", "/blades/blade", blade_type="serrated")

        node = QueryItem(self.manager,
                self.manager.query_by_vpath("/nodes/node1"))
        blade = QueryItem(self.manager,
                self.manager.query_by_vpath("/blades/blade"))

        pickled_task = {
            'node': '/nodes/node1',
            'model_item': '/nodes/node1/system',
            'model_items': ['/blades/blade'],
            'description': 'alpha',
            'call_type': 'bravo',
            'call_id': 'charlie',
            'kwargs': {},
            'state': TASK_INITIAL,
            'is_snapshot_task': True,
            'replaces': [["call_type_2", "call_id_2"]]
        }

        unpickled_task = self.model_container._unpickle_config_task(pickled_task)
        self.assertTrue(isinstance(unpickled_task, ConfigTask))

        self.assertTrue(isinstance(unpickled_task.node, QueryItem))
        self.assertEqual(node, unpickled_task.node)

        self.assertTrue(isinstance(unpickled_task.model_item, QueryItem))
        self.assertEqual(node.system, unpickled_task.model_item)

        # We can't currently hash QueryItems so we can't directly compare sets
        # of QueryItems
        self.assertTrue(isinstance(unpickled_task.model_items, set))
        self.assertEqual(1, len(unpickled_task.model_items))
        self.assertEqual(blade, unpickled_task.model_items.pop())

        self.assertTrue(isinstance(unpickled_task.description, str))
        self.assertEqual('alpha', unpickled_task.description)

        self.assertTrue(isinstance(unpickled_task.call_type, str))
        self.assertEqual('bravo', unpickled_task.call_type)

        self.assertTrue(isinstance(unpickled_task.call_id, str))
        self.assertEqual('charlie', unpickled_task.call_id)

        self.assertTrue(isinstance(unpickled_task.kwargs, dict))
        self.assertEqual({}, unpickled_task.kwargs)

        self.assertTrue(isinstance(unpickled_task.is_snapshot_task, bool))
        self.assertEqual(True, unpickled_task.is_snapshot_task)

        self.assertTrue(isinstance(unpickled_task.replaces, set))
        self.assertEqual(
            set([("call_type_2", "call_id_2")]),
            unpickled_task.replaces)

    def test_pickle_set(self):
        obj = set([1, "a"])
        ret = self.model_container._pickle_callback(obj)
        self.assertTrue("__type__" in ret)
        self.assertEquals("set", ret["__type__"])
        self.assertTrue("data" in ret)
        self.assertEquals(list, type(ret["data"]))
        self.assertEquals(set(ret["data"]), obj)

    def test_unpickle_set(self):
        obj = {
            "__type__": "set",
            "data": [1, "a"]
        }
        ret = self.model_container._unpickle_callback(obj)
        self.assertTrue(set, type(ret))
        self.assertEquals(set(obj["data"]), ret)

    def test_unpickle_config_task_model_items(self):
        self.manager.create_root_item("root")
        self.manager.create_item("node", "/nodes/node1", hostname="node1")
        self.manager.create_item("os", "/nodes/node1/os")
        self.manager.create_item("system", "/systems/sys1", name="sys1")
        self.manager.create_item("network", "/nodes/node1/network")
        network = QueryItem(self.manager,
                self.manager.query_by_vpath("/nodes/node1/network"))
        sys = QueryItem(self.manager,
                self.manager.query_by_vpath("/systems/sys1"))

        task_data = {
            'node':'/nodes/node1',
            'model_item':'/nodes/node1/os',
            'description':'ConfigTask 1',
            'call_type':'foo',
            'call_id':'bar',
            'group':'test',
            'state':'Success',
            'uuid':'123',
            'model_items':[
                '/nodes/node1/network',
                '/systems/sys1',
                '/NO/ITEM/EXISTS/HERE',
            ],
        }

        self.model_container._unpickled_config_tasks = {}
        self.model_container._unresolved_task_dependencies = {}

        pickled_task = self.model_container._unpickle_config_task(task_data)
        # LITPCDS-11456: If model items doesn't exist, don't add to model_items
        self.assertEqual(set([network, sys]), pickled_task.model_items)

    def test_plugin_or_extension_change_unordered(self):
        data = {}
        data['extensions'] = [
                {
                    u'version': u'1.2.3',
                    u'name': u'core_extension',
                    u'class': u'litp.extensions.core_extension.CoreExtension'
                },
                {
                    u'version': u'1.2.3',
                    u'name': u'dummy_package_like_extension',
                    u'class': u'dummy_package_like_extension.DummyPackageLikeExtension'
                },
                {
                    u'version': u'1.2.3',
                    u'name': u'mock_package_extension',
                    u'class': u'mock_package_extension.mock_package_extension.MockPackageExtension'
                }
            ]
        data['plugins'] = [
                {
                    u'class': u'litp.plugins.core.puppet_manager_plugin.PuppetManagerPlugin',
                    u'name': u'puppet_manager',
                    u'version': u'1.2.3'
                },
                {
                    u'class': u'dummy_package_like_plugin.DummyPackageLikePlugin',
                    u'name': u'dummy_package_like_plugin',
                    u'version': u'1.2.3'
                },
                {
                    u'class': u'litp.plugins.core.core_plugin.CorePlugin',
                    u'name': u'core_plugin',
                    u'version': u'1.2.3'
                },
                {
                    u'class': u'mock_package_plugin.mock_package_plugin.MockPackagePlugin',
                    u'name': u'mock_package_plugin',
                    u'version': u'1.2.3'
                }
            ]
        # PluginManagers plugins and extensions collections are in different order
        mock_plugin_manager = Mock()
        mock_plugin_manager.get_plugin_info.return_value = [
                {
                    'version': '1.2.3',
                    'name': 'puppet_manager',
                    'class': 'litp.plugins.core.puppet_manager_plugin.PuppetManagerPlugin'
                },
                {
                    'version': '1.2.3',
                    'name': 'mock_package_plugin',
                    'class': 'mock_package_plugin.mock_package_plugin.MockPackagePlugin'
                },
                {
                    'version': '1.2.3',
                    'name': 'core_plugin',
                    'class': 'litp.plugins.core.core_plugin.CorePlugin'
                },
                {
                    'version': '1.2.3',
                    'name': 'dummy_package_like_plugin',
                    'class': 'dummy_package_like_plugin.DummyPackageLikePlugin'
                }
            ]
        mock_plugin_manager.get_extension_info.return_value = [
                {
                    'version': '1.2.3',
                    'name': 'core_extension',
                    'class': 'litp.extensions.core_extension.CoreExtension'
                },
                {
                    'version': '1.2.3',
                    'name': 'mock_package_extension',
                    'class': 'mock_package_extension.mock_package_extension.MockPackageExtension'
                },
                {
                    'version': '1.2.3',
                    'name': 'dummy_package_like_extension',
                    'class': 'dummy_package_like_extension.DummyPackageLikeExtension'
                }
            ]
        container = ModelItemContainer(Mock(), mock_plugin_manager, Mock())
        self.assertFalse(container._plugin_or_extension_change(data))

    def test_plan_unpickling_does_not_pollute_persisted_configtask_cache(self):
        pass  # TODO: will be removed from master
        # # LITPCDS-13298
        # self.manager.create_root_item("root")
        #
        # node1 = self.manager.create_item("node", "/nodes/node1",
        #     hostname="node1")
        # self.sys1 = self.manager.create_item("system", "/systems/sys1",
        #     name="sys1")
        # self.manager.create_inherited("/systems/sys1", "/nodes/node1/system")
        #
        # self.node = QueryItem(self.manager, node1)
        #
        # persisted_task = ConfigTask(
        #     self.node,
        #     self.node.system,
        #     "Persisted task",
        #     "persistent_resource",
        #     "arbitrary_resource_id"
        # )
        # non_persisted_task = ConfigTask(
        #     self.node,
        #     self.node.system,
        #     "Non-persisted task",
        #     "non_persistent_resource",
        #     "arbitrary_resource_id"
        # )
        # non_persisted_task.persist = False
        # persisted_task.requires.add(non_persisted_task)
        #
        #
        # persisted_task.group = non_persisted_task.group = \
        #     deployment_plan_groups.NODE_GROUP
        #
        # persisted_task.plugin_name = non_persisted_task.plugin_name = 'Plugin'
        #
        # persisted_task.state = non_persisted_task.state = "Success"
        #
        # persisted_task.uuid = "92bbd88b-c48d-4ba4-9734-088da83a9714"
        # non_persisted_task.uuid = "dedbb1ed-f16b-4248-8b7d-ebad10e8c608"
        #
        # self.plan = Plan([], [])
        # self.plan._phases = [[persisted_task, non_persisted_task]]
        # self.execution.plan = self.plan
        #
        # self.execution.puppet_manager.node_tasks[self.node.hostname] = \
        #     [persisted_task]
        #
        # successful_plan_json = self.model_container.serialize()
        #
        # # Make sure the plan gets unpickled
        # self.execution.plan = None
        # self.model_container.do_unpickling(json.loads(successful_plan_json))
        #
        # # The non-persisted task is not present in node_tasks
        # self.assertTrue(any(non_persisted_task == plan_task for
        #     plan_task in self.execution.plan.get_tasks()))
        # # ...but it is present in the plan
        # self.assertFalse(any(non_persisted_task == persisted for
        #     persisted in self.execution.puppet_manager.node_tasks['node1']))
        # # The non-persisted task is not found when the persisted task's
        # # 'requires' set is rebuilt
        # self.assertEquals(
        #     set(),
        #     self.execution.puppet_manager.node_tasks['node1'][0].requires
        # )
