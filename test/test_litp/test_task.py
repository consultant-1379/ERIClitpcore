import unittest
from mock import Mock, patch

from litp.core.model_type import ItemType
from litp.core.model_type import PropertyType
from litp.core.model_type import Collection
from litp.core.model_type import Reference
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.task import Task
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import OrderedTaskList
from litp.core.task import RemoteExecutionTask
from litp.core.task import CleanupTask
from litp.core.task import can_have_dependency, can_have_dependency_for_validation
from litp.core.task_utils import serialize_arg_value_from_object
from litp.core.task_utils import deserialize_arg_value_to_object
from litp.core.task import clean_classname
from litp.core.future_property_value import FuturePropertyValue
from litp.core.exceptions import TaskValidationException
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.core.future_property_value import FuturePropertyValue

falsevaluereturn = Mock(return_value=False)

class CleanClassnameTest(unittest.TestCase):
    def test_basic(self):
        res1 = clean_classname('abcdefg1234')
        self.assertEquals(res1, 'abcdefg1234')

    def test_nonrange(self):
        res2 = clean_classname('abcd efg')
        self.assertEquals(res2, 'abcd_20efg')

    def test_escape(self):
        res3 = clean_classname('abcd_efg')
        self.assertEquals(res3, 'abcd__efg')


class TaskTest(unittest.TestCase):

    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(
            ItemType(
                "root",
                nodes=Collection("node"),
                systems=Collection("system"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string"),
                system=Reference("system"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "system",
                uid=Property("basic_string"),
            )
        )

        self.model.create_root_item("root")
        self.model.create_item(
            "system", "/systems/sys1", uid="sys1")
        self.model.create_item(
            "node", "/nodes/node1", hostname="node1")
        self.model.create_inherited(
            "/systems/sys1", "/nodes/node1/system")
        self.model.create_item(
            "node", "/nodes/node2", hostname="node2")
        self.model.create_inherited(
            "/systems/sys1", "/nodes/node2/system")

    def test_task_check_args(self):
        node = self.model.query("node")[0]
        task = Task(node, "")

        task._check_args("")
        task._check_args(u"")
        task._check_args(0)
        task._check_args(0.1)
        task._check_args(True)
        task._check_args(None)
        task._check_args([])
        task._check_args(set())
        task._check_args(tuple())
        task._check_args({})

        self.assertRaises(TypeError, task._check_args, self)  # object
        self.assertRaises(TypeError, task._check_args, self.__class__)  # class
        self.assertRaises(TypeError, task._check_args, self.setUp)  # method
        self.assertRaises(TypeError, task._check_args, [self])
        self.assertRaises(TypeError, task._check_args, tuple([self]))
        self.assertRaises(TypeError, task._check_args, set([self]))
        self.assertRaises(TypeError, task._check_args, {"": self})

    def test_config_task(self):
        node = self._convert_to_query_item(self.model.query("node")[0])

        ConfigTask(node, node.system, "", "1", "2")

#        self.assertRaises(TypeError, ConfigTask, node, "", "", "1", "2")
#        self.assertRaises(TypeError, ConfigTask, "", node.system, "", "1", "2")

    def test_callback_task(self):
        node = self.model.query("node")[0]

        CallbackTask(node.system, "", None)

#        self.assertRaises(TypeError, CallbackTask, "", "", None)

        task = CallbackTask(node.system, "", None, "a", "b", x=1, y=2)
        task._check_args = Mock()
        task.validate()
        task._check_args.assert_any_call(("a", "b"))
        task._check_args.assert_any_call({"x": 1, "y": 2})

    def test_callback_task_equality(self):
        # TORF-155243: CallbackTasks with different dependencies were equal
        class FooPlugin(object):
            def callback_method():
                pass
        # VcsPlugin creates a new Plugin object each time it sets the callback
        # attribute of a CallbackTasks
        node = self.model.query("node")[0]
        t1 = CallbackTask(node.system, "Callback1", FooPlugin().callback_method)
        t2 = CallbackTask(node.system, "Callback1", FooPlugin().callback_method)
        # Perfectly the same callback tasks
        self.assertEqual(t1, t2)
        test_set = set([t1, t2])
        self.assertEqual(1, len(test_set))
        # Similar callback tasks with different dependencies - we want an order
        t2.requires.add(node)
        self.assertNotEqual(t1, t2)
        test_set = set([t1, t2])
        self.assertEqual(2, len(test_set))

    def test_remote_execution_task(self):
        system_qi = self._convert_to_query_item(self.model.query("system")[0])
        node_qis = [self._convert_to_query_item(node_mi) for node_mi in self.model.query("node")]

        task = RemoteExecutionTask([], system_qi, "", "agent", "action")
        self.assertRaises(ValueError, task.validate)
        task = RemoteExecutionTask([system_qi], system_qi, "", "agent", "action")
        self.assertRaises(ValueError, task.validate)

        task = RemoteExecutionTask(node_qis, system_qi, "", "agent", "action", x=1, y=2)
        task._check_args = Mock()
        task.validate()
        task._check_args.assert_any_call({"x": 1, "y": 2})

        kwargs = {"kw1": "val1", "kw2": "val2", "kw3": "val3"}
        task = RemoteExecutionTask(
            node_qis, system_qi, "", "agent", "action", **kwargs)

        l = task._generate_command_args(**kwargs)
        l = l[l.index("agent"):]

        self.assertEquals(["agent", "action"], l[0:2])
        self.assertEquals(
            set(["kw1=val1", "kw2=val2", "kw3=val3"]),
            set(l[2:5])
        )
        self.assertEquals(["-I", "-I"], [l[5], l[7]])
        self.assertEquals(set(["node1", "node2"]), set([l[6], l[8]]))

    def test_remote_execution_task(self):
        node1 = self.model.query("node")[0]
        task1 = RemoteExecutionTask([node1], node1, "RemoteExecutionTask 1", "lock_unlock", "lock_a")
        task2 = RemoteExecutionTask([node1], node1, "RemoteExecutionTask 2", "lock_unlock", "lock_B")
        self.assertNotEquals(task1, task2)
        self.assertNotEquals(hash(task1), hash(task2))

    def test_remote_execution_task_node_order(self):
        node1 = self.model.query("node")[1]
        node2 = self.model.query("node")[0]
        task1 = RemoteExecutionTask([node1, node2], node1, "RemoteExecutionTask 1", "lock_unlock", "lock_a")
        task2 = RemoteExecutionTask([node2, node1], node1, "RemoteExecutionTask 1", "lock_unlock", "lock_a")
        self.assertEquals(task1, task2)
        self.assertEquals(hash(task1), hash(task2))


    def test_remote_execution_task_diff_kwargs(self):
        node1 = self.model.query("node")[0]
        class A(dict):
            def __str__(self):
                return 'a repr'
            def __repr__(self):
                return 'a repr'
        class B(dict):
            def __str__(self):
                return 'b repr'
            def __repr__(self):
                return 'u"b repr"'
        a = A(something="diff", name="unique")
        b = B(something=u"diff", name=u"unique")
        self.assertNotEqual(str(a), str(b))
        self.assertEqual(dict(a), dict(b))

        task1 = RemoteExecutionTask([node1], node1, "RemoteExecutionTask 1", "lock_unlock", "lock_a", **a)
        task2 = RemoteExecutionTask([node1], node1, "RemoteExecutionTask 2", "lock_unlock", "lock_B", **b)
        self.assertNotEquals(task1, task2)
        self.assertNotEquals(hash(task1), hash(task2))

    def test_ordered_task_list(self):
        root_qi = self._convert_to_query_item(self.model.query("root")[0])
        node1_qi = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        node2_qi = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node2"))

        tasks = [
            ConfigTask(node1_qi, node1_qi.system, "", "1", "2")
        ]

        OrderedTaskList(node1_qi, tasks)
#        self.assertRaises(TypeError, OrderedTaskList, "", tasks)

        tasks = [
            ConfigTask(node1_qi, node1_qi.system, "", "1", "1"),
            CallbackTask(node1_qi.system, "", self.fail),
            RemoteExecutionTask([node1_qi], root_qi, "", "agent", "action"),
        ]
        otl = OrderedTaskList(root_qi, tasks)
        otl.validate()

        tasks.append(
            OrderedTaskList(root_qi, [
                ConfigTask(node1_qi, node1_qi.system, "", "2", "2"),
                CallbackTask(node1_qi.system, "", self.fail),
                RemoteExecutionTask([node1_qi], root_qi, "", "agent", "action"),
            ])
        )
        otl = OrderedTaskList(root_qi, tasks)
        self.assertRaises(TaskValidationException, otl.validate)

        tasks = [
            ConfigTask(node1_qi, node1_qi.system, "", "1", "1"),
            ConfigTask(node2_qi, node2_qi.system, "", "2", "2"),
            CallbackTask(node1_qi.system, "", self.fail),
            RemoteExecutionTask([node1_qi], root_qi, "", "agent", "action"),
        ]
        otl = OrderedTaskList(root_qi, tasks)
        self.assertRaises(TaskValidationException, otl.validate)

        tasks = [
        ]
        otl = OrderedTaskList(root_qi, tasks)
        self.assertRaises(TaskValidationException, otl.validate)

        tasks = [
            ConfigTask(node1_qi, node1_qi.system, "", "1", "1"),
            CallbackTask(node1_qi.system, "", self.fail),
            CallbackTask(node2_qi.system, "", self.fail),
            RemoteExecutionTask([node1_qi], root_qi, "", "agent", "action"),
        ]
        otl = OrderedTaskList(root_qi, tasks)
        self.assertRaises(TaskValidationException, otl.validate)

        tasks = [
            ConfigTask(node1_qi, node1_qi.system, "", "1", "1"),
            CallbackTask(node1_qi.system, "", self.fail),
            RemoteExecutionTask([node2_qi], root_qi, "", "agent", "action"),
        ]
        otl = OrderedTaskList(root_qi, tasks)
        self.assertRaises(TaskValidationException, otl.validate)

    def test_initial_model_items_attr_always_contains_primary_model_item(self):
        node1 = self.model.query_by_vpath("/nodes/node1")
        self.assertTrue(node1 in Task(node1, '').all_model_items)



class ConfigTaskTests(unittest.TestCase):
    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(ItemType("root",
                                               nodes=Collection("node"),
                                               ))
        self.model.register_item_type(
            ItemType("node",
                     hostname=Property("basic_string"),
                     comps=Collection("component"),
                     ))
        self.model.register_item_type(
            ItemType("component",
                     name=Property("basic_string",
                         updatable_plugin=True,
                         updatable_rest=True)))
        self.model.create_root_item("root")

    def test_unique_id(self):
        node1 = self.model.create_item("node", "/nodes/node1",
                                       hostname="node1")
        self.model.create_item("component", "/nodes/node1/comps/comp1")
        node1 = self._convert_to_query_item(node1)

        task = ConfigTask(node1, node1.comps.comp1, "Test Task", "colon::colon",
                          "UPPERCASE", foo='bar', bar=123, baz='12.34.56.78')
        task_clean_id = "node1__colon_3a_3acolon___55_50_50_45_52_43_41_53_45"

        task_id = task.unique_id
        self.assertEquals(task_clean_id, task_id)

    def test_equality_check_doesnt_use_group(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        task1 = ConfigTask(node, node, "Test Task", "call type 1", "call id 1")
        task2 = ConfigTask(node, node, "Test Task", "call type 1", "call id 1")
        task1.group = deployment_plan_groups.MS_GROUP
        task2.group = deployment_plan_groups.NODE_GROUP
        self.assertEqual(task1, task2)

    def test_persist_equality_hash(self):
        node = self.model.create_item("node", "/nodes/node1",
                hostname="node1")
        node = QueryItem(self.model, node)
        # Same task but with different persist attribute
        t1 = ConfigTask(node, node, "Desc", "foo", "bar")
        t1.persist = True
        t2 = ConfigTask(node, node, "Desc", "foo", "bar")
        t2.persist = False
        self.assertNotEqual(t1, t2)

    def test_equality_for_differing_requires(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("component", "/nodes/node1/comps/comp1")
        self.model.create_item("component", "/nodes/node1/comps/comp2")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        node_comp1 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp1"))
        node_comp2 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp2"))

        task1 = ConfigTask(node, node_comp1, "Test Task", "call type 1", "call id 1")
        task2 = ConfigTask(node, node_comp1, "Test Task", "call type 1", "call id 1")

        # requires contain only identical tasks
        dep_task = ConfigTask(node, node_comp2, "Test Task", "call type 1", "call id 1")
        task1.requires = set([dep_task])
        task2.requires = set([dep_task])
        self.assertEqual(task1, task2)

        # reuires contain one extra task
        task1.requires = set([ConfigTask(node, node_comp1, "Test Task", "call type x",
                                         "call id x")])
        self.assertNotEqual(task1, task2)

        # requires contain a task, and a query item
        task1.requires = set([node_comp2])
        self.assertNotEqual(task1, task2)

        # requires contain equal query items
        task1.requires = set([node_comp1])
        task2.requires = set([node_comp1])
        self.assertEqual(task1, task2)

        # requires contain non-equal query items
        task2.requires = set([node_comp2])
        self.assertNotEqual(task1, task2)

    def test_is_deconfigure(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        regular_item = self.model.create_item("component", "/nodes/node1/comps/comp1")
        removal_item = self.model.create_item("component", "/nodes/node1/comps/comp2")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        node_comp1 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp1"))
        node_comp2 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp2"))
        removal_item.set_for_removal()

        task1 = ConfigTask(node, node_comp1, "Test Task", "call type 1", "call id 1")
        task2 = ConfigTask(node, node_comp2, "Test Task", "call type 2", "call id 2")

        self.assertFalse(task1.is_deconfigure())
        self.assertTrue(task2.is_deconfigure())

    def test_can_have_dependency(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        regular_item = self.model.create_item("component", "/nodes/node1/comps/comp1")
        removal_item = self.model.create_item("component", "/nodes/node1/comps/comp2")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        node_comp1 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp1"))
        node_comp2 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp2"))
        removal_item.set_for_removal()

        task1 = ConfigTask(node, node_comp1, "Test Task", "call type 1", "call id 1")
        task2 = ConfigTask(node, node_comp2, "Test Task", "call type 2", "call id 2")
        task3 = ConfigTask(node, node_comp1, "Test Task", "call type 3", "call id 3")
        task4 = ConfigTask(node, node_comp2, "Test Task", "call type 4", "call id 4")

        self.assertFalse(task1.is_deconfigure())
        self.assertTrue(task2.is_deconfigure())
        self.assertFalse(task3.is_deconfigure())
        self.assertTrue(task4.is_deconfigure())

        self.assertFalse(can_have_dependency(task1, task2))
        self.assertTrue(can_have_dependency(task1, task3))
        self.assertTrue(can_have_dependency(task4, task2))

    def test_equality_check_future_property_value(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        self.model.create_item("component", "/nodes/node1/comps/comp1")
        comp = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1/comps/comp1"))
        comp._updatable = True

        fpv = FuturePropertyValue(comp, "name")
        comp.name = "test_value"

        # Should be equal - no FuturePropertyValue
        task1 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name="test_value")
        task2 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name="test_value")
        self.assertTrue(task1 == task2)

        # The same value but one is a FuturePropertyValue - shouldn't be equal
        task1 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name=fpv)
        task2 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name="test_value")
        self.assertFalse(task1 == task2)

        # The same values stored as FuturePropertyValue - shouldn't be equal
        task1 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name=fpv)
        task2 = ConfigTask(node, comp, "Test Task", "call type 1", "call id 1", name=fpv)
        comp.name = "test_value"
        self.assertFalse(task1 == task2)


class CallBackTaskTestCase(unittest.TestCase):

    def test_get_node_for_model_item_where_node_is_ms(self):
        ms = Mock()
        ms.get_vpath.return_value = '/ms'

        model_manager = Mock()

        def query_by_vpath(vpath):
            if vpath == ms.get_vpath():
                return ms
        model_manager.query_by_vpath.side_effect = query_by_vpath

        ms._manager = model_manager

        model_item = Mock()
        model_item._manager = model_manager
        model_item._model_item.get_node.return_value = None
        model_item._ref = None

        model_item.get_node.return_value = ms

        cb_task = CallbackTask(model_item, 'desc', lambda x: x)
        self.assertEquals(ms, cb_task.get_node_for_model_item())

    def test_can_have_dependency_for_validation(self):
        ms = Mock()
        ms.get_vpath.return_value = '/ms'

        model_manager = Mock()

        def query_by_vpath(vpath):
            if vpath == ms.get_vpath():
                return ms
        model_manager.query_by_vpath.side_effect = query_by_vpath

        ms._manager = model_manager

        model_item1 = Mock()
        model_item1._manager = model_manager
        model_item1._model_item.get_node.return_value = None
        model_item1._ref = None

        model_item2 = Mock()
        model_item2._manager = model_manager
        model_item2._model_item.get_node.return_value = None
        model_item2._ref = None

        model_item1.get_node.return_value = ms
        model_item2.get_node.return_value = ms

        task1 = CallbackTask(model_item1, 'desc', lambda x: x)
        task2 = CallbackTask(model_item2, 'desc', lambda x: x)

        self.assertTrue(can_have_dependency_for_validation(task1, task2))

    @patch('litp.core.task.get_task_model_item_node')
    @patch('litp.core.task.get_task_node')
    def test_can_have_dependency_in_ms_other_extended_group(self,
                                                            get_task_node,
                                                            get_task_model_item_node):
        ms = Mock()
        ms.get_vpath.return_value = '/ms'

        model_manager = Mock()

        def query_by_vpath(vpath):
            if vpath == ms.get_vpath():
                return ms
        model_manager.query_by_vpath.side_effect = query_by_vpath

        ms._manager = model_manager

        model_item1 = Mock()
        model_item1._manager = model_manager
        model_item1._model_item.get_node.return_value = None
        model_item1._ref = None

        model_item2 = Mock()
        model_item2._manager = model_manager
        model_item2._model_item.get_node.return_value = None
        model_item2._ref = None

        model_item1.get_node.return_value = ms
        model_item2.get_node.return_value = ms

        task1 = CallbackTask(model_item1, 'desc', lambda x: x)
        task2 = CallbackTask(model_item2, 'desc', lambda x: x)
        task1.group = deployment_plan_groups.MS_GROUP
        task2.group = deployment_plan_groups.MS_GROUP

        get_task_node.side_effect = lambda x: Mock(vpath='/foo') if x.group == deployment_plan_groups.MS_GROUP else None
        get_task_model_item_node.return_value = None

        self.assertTrue(can_have_dependency(task1, task2))

        get_task_node.side_effect = lambda x: Mock(vpath='/foo')
        get_task_model_item_node.return_value = None

        self.assertTrue(can_have_dependency(task1, task2))


    @patch('litp.core.task.get_task_model_item_node')
    @patch('litp.core.task.get_task_node')
    def test_can_have_dependency_in_cluster_group(self, get_task_node,
                                                  get_task_model_item_node):
        task1 = Mock()
        task1.group = deployment_plan_groups.CLUSTER_GROUP
        task1.requires = []
        task2 = Mock()
        task2.group = deployment_plan_groups.CLUSTER_GROUP
        task2.requires = []

        get_task_node.side_effect = lambda x: Mock(vpath='/foo') if x == task1 else Mock(vpath='/bar')

        self.assertFalse(can_have_dependency(task1, task2))
        # make sure it failed at 1st check
        self.assertFalse(get_task_model_item_node.called)


    @patch('litp.core.task.get_task_model_item_node')
    @patch('litp.core.task.get_task_node')
    def test_combined(self, get_task_node, get_task_model_item_node):
        # list pairs of variables for can_have_dependency_testing and expected
        # results
        # test variables:
        # 0: task node 1
        # 1: task node 2
        # 2: model item node 1
        # 3: model item node 2
        # 4: task 1 in MS/OTHER
        # 5: task 2 in MS/OTHER
        # expected result: if None, this is invalid tc and should be skipped
        test_vals_results = [
            ((1, 1, 1, 1, True, True), True),                 # 1
            ((1, 1, 1, 1, True, False), True),
            ((1, 1, 1, 1, False, False), True),

            ((2, 1, 1, 1, True, True), False),                # 4
            ((2, 1, 1, 1, True, False), False),
            ((2, 1, 1, 1, False, False), False),

            ((None, 1, 1, 1, True, True), True),              # 7
            ((None, 1, 1, 1, True, False), False),
            ((None, 1, 1, 1, False, False), False),

            # impossible to have a task with no task node but with model item
            # node
            ((None, None, 1, 1, True, True), None),           # 10
            ((None, None, 1, 1, True, False), None),
            ((None, None, 1, 1, False, False), None),

            ((1, 1, None, 1, True, True), True),              # 13
            ((1, 1, None, 1, True, False), True),
            ((1, 1, None, 1, False, False), True),

            ((2, 1, None, 1, True, True), False),             # 16
            ((2, 1, None, 1, True, False), False),
            ((2, 1, None, 1, False, False), False),

            ((None, 1, None, 1, True, True), True),           # 19
            ((None, 1, None, 1, True, False), False),
            ((None, 1, None, 1, False, False), False),

            # impossible to have a task with no task node but with model item
            # node
            ((None, None, None, 1, True, True), None),        # 22
            ((None, None, None, 1, True, False), None),
            ((None, None, None, 1, False, False), None),

            ((1, 1, None, None, True, True), True),           # 25
            ((1, 1, None, None, True, False), True),
            ((1, 1, None, None, False, False), True),

            ((2, 1, None, None, True, True), False),          # 28
            ((2, 1, None, None, True, False), False),
            ((2, 1, None, None, False, False), False),

            ((None, 1, None, None, True, True), True),        # 31
            ((None, 1, None, None, True, False), False),
            ((None, 1, None, None, False, False), False),

            ((None, None, None, None, True, True), True),     # 34
            ((None, None, None, None, True, False), True),
            ((None, None, None, None, False, False), True),
        ]
        for i, test_vals_result in enumerate(test_vals_results):
            test_vals, result = test_vals_result
            if result is None:
                continue  # skip invalid TCs
            msg = []
            task1 = falsevaluereturn
            task1.group = deployment_plan_groups.MS_GROUP if test_vals[4] else deployment_plan_groups.NODE_GROUP
            task2 = falsevaluereturn
            task2.group = deployment_plan_groups.MS_GROUP if test_vals[5] else deployment_plan_groups.CLUSTER_GROUP

            task_nodes = [test_vals[0], test_vals[1]]
            mitem_nodes = [test_vals[2], test_vals[3]]
            get_task_node.side_effect = lambda x: Mock(vpath=lambda: '/' + str(task_nodes.pop(0)))
            get_task_model_item_node.side_effect = lambda x: mitem_nodes.pop(0)

            if task_nodes[0] is None and task_nodes[1] is None:
                msg.append("no task nodes exist")
            elif task_nodes[0] is not None and task_nodes[1] is not None:
                msg.append("both task nodes exist")
            else:
                msg.append("only one task node exists")

            if mitem_nodes[0] is None and mitem_nodes[1] is None:
                msg.append("no model item nodes exist")
            elif mitem_nodes[0] is not None and mitem_nodes[1] is not None:
                msg.append("both model item nodes exist")
            else:
                msg.append("one model item node exists")

            if test_vals[4] and test_vals[5]:
                msg.append("both tasks in MS/OTHER group")
            elif test_vals[4] or test_vals[5]:
                msg.append("only one task in MS/OTHER group")
            else:
                msg.append("none task in MS/OTHER group")

            if result:
                msg.append('should be able to have dependency relationship')
            else:
                msg.append('dependency relationship should not be allowed')

            msg = ('TC %s: ' % (i + 1)) + '; '.join(msg)
            try:
                self.assertEquals(result, can_have_dependency(task1, task2), msg)
            except AssertionError, e:
                print e

    def test_cleanup_task(self):
        item = Mock(vpath='/node1')
        cleanup_task = CleanupTask(item)
        self.assertEqual(cleanup_task.description, 'Remove Item')
        self.assertEqual(cleanup_task.model_item.vpath, item.vpath)
        self.assertEqual(cleanup_task.state, 'Initial')


class TestSerializeDeserializeTaskArgsKwargs(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()

        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_item_types([
            ItemType(
                "root",
                nodes=Collection("node")
            ),
            ItemType(
                "node",
                items=Collection("item")
            ),
            ItemType(
                "item",
                name=Property("basic_string"),
            )
        ])

        self.model.create_root_item("root")
        node_mi = self.model.create_item("node", "/nodes/node1")
        item_mi = self.model.create_item("item", "/nodes/node1/items/item1")
        self.node = self.model.query_by_vpath(node_mi.vpath)
        self.item = self.model.query_by_vpath(item_mi.vpath)

    def test_serialize_deserialize_arg_value_to_object(self):
        value = "foo"
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(value, deserialized)

        value = FuturePropertyValue(self.item, "name")
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertTrue(isinstance(deserialized.query_item, QueryItem))
        self.assertEquals(value.query_item.vpath, deserialized.query_item.vpath)
        self.assertEquals(value.property_name, deserialized.property_name)

        self.model.remove_item(self.item.vpath)
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertFalse(isinstance(deserialized.query_item, QueryItem))
        self.assertEquals(value.query_item.vpath, deserialized.query_item)

        value = []
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)

        value = set()
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)

        value = {}
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)

        value = ["foo"]
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)

        value = set(["foo"])
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)

        value = {"foo": "bar"}
        serialized = serialize_arg_value_from_object(value)
        deserialized = deserialize_arg_value_to_object(serialized, self.model)
        self.assertEquals(type(value), type(deserialized))
        self.assertEquals(value, deserialized)
