import unittest

from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.constants import CURRENT_PLAN_ID
from litp.core.model_manager import ModelManager
from litp.core.model_manager import QueryItem
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Collection
from litp.core.model_item import ModelItem
from litp.core.model_item import CollectionItem
from litp.core.task import Task
from litp.core.task import ConfigTask
from litp.core.task import CallbackTask
from litp.core.task import RemoteExecutionTask
from litp.core.task import CleanupTask
from litp.core.constants import TASK_SUCCESS
from litp.core.plan import SnapshotPlan
from litp.core.plan import Plan
from litp.core.persisted_task import PersistedTask
from litp.core.extension_info import ExtensionInfo
from litp.core.plugin_info import PluginInfo
from litp.data.test_db_engine import get_engine


class TestDataManager(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDataManager, self).__init__(*args, **kwargs)
        self.storage = DbStorage(get_engine())
        self.storage.reset()

    def _create_managers(self):
        model_manager = ModelManager()
        model_manager.register_property_types([
            PropertyType("basic_string")
        ])
        model_manager.register_item_types([
            ItemType(
                "root",
                nodes=Collection("node")
            ),
            ItemType(
                "node",
                hostname=Property("basic_string"),
                item=Child("item")
            ),
            ItemType(
                "item"
            )
        ])

        session = self.storage.create_session()
        data_manager = DataManager(session)
        data_manager.configure(model_manager)
        model_manager._data_manager = data_manager
        self._data_managers.append(data_manager)
        return (data_manager, model_manager)

    def setUp(self):
        self._data_managers = []
        self.data_manager, self.model_manager = self._create_managers()

    def tearDown(self):
        for data_manager in self._data_managers:
            data_manager.close()
        self.storage.reset()

    def test_task(self):
        data_manager1, model_manager1 = self._create_managers()

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        dep0 = ConfigTask(node1, item1, "description", "foo0", "bar0")
        data_manager1.add_task(dep0)

        dep1 = ConfigTask(node1, item1, "description", "foo1", "bar1")
        dep2 = ConfigTask(node1, item1, "description", "foo2", "bar2")
        dep3 = ConfigTask(node1, item1, "description", "foo3", "bar3")

        persisted_task = PersistedTask("foo", dep1, 0)
        data_manager1.add_persisted_task(persisted_task)
        persisted_task = PersistedTask("foo", dep3, 1)
        data_manager1.add_persisted_task(persisted_task)

        plan = Plan([[dep2, dep3]])
        plan._id = CURRENT_PLAN_ID
        plan.populate_plan_tasks()
        data_manager1.add_plan(plan)

        task1 = ConfigTask(node1, item1, "description", None, None)
        task1.model_items.update(set([node1, item1]))
        task1.requires.update(set([dep0, dep1, dep2, dep3, item1, ("foo", "bar")]))
        task1._requires = set(["foo", "bar"])
        task1.state = TASK_SUCCESS
        task1.persist = False
        data_manager1.add_task(task1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()

        task2 = data_manager2.get_task(task1._id)
        self.assertTrue(task2 is not None)
        task2.initialize_from_db(data_manager2, model_manager2)

        self.assertEquals(task2._id, task1._id)

        self.assertTrue(isinstance(task2.model_item, QueryItem))
        self.assertEquals(task1.model_item.vpath, task2.model_item.vpath)

        self.assertEquals("description", task1.description)
        self.assertEquals(task1.description, task2.description)

        self.assertEquals(TASK_SUCCESS, task1.state)
        self.assertEquals(task1.state, task2.state)

        self.assertEquals(False, task1.persist)
        self.assertEquals(task1.persist, task2.persist)

        self.assertEquals(
            set(["/node", "/node/item"]),
            set([item.vpath for item in task1.model_items])
        )
        self.assertTrue(all([
            isinstance(item, QueryItem) for item in task2.model_items
        ]))
        self.assertEquals(
            set([item.vpath for item in task1.model_items]),
            set([item.vpath for item in task2.model_items])
        )

        self.assertEquals(
            set(["/node/item"]),
            set([dep.vpath for dep in task1.requires if isinstance(dep, QueryItem)])
        )
        self.assertEquals(
            set([dep.vpath for dep in task1.requires if isinstance(dep, QueryItem)]),
            set([dep.vpath for dep in task2.requires if isinstance(dep, QueryItem)])
        )
        self.assertEquals(
            set([dep0.unique_id, dep1.unique_id, dep2.unique_id, dep3.unique_id]),
            set([dep.unique_id for dep in task1.requires if isinstance(dep, Task)])
        )
        self.assertEquals(
            set([dep1.unique_id, dep2.unique_id, dep3.unique_id]),
            set([dep.unique_id for dep in task2.requires if isinstance(dep, Task)])
        )
        self.assertEquals(
            set([("foo", "bar")]),
            set([dep for dep in task1.requires if isinstance(dep, tuple)])
        )
        self.assertEquals(
            set([dep for dep in task1.requires if isinstance(dep, tuple)]),
            set([dep for dep in task2.requires if isinstance(dep, tuple)])
        )

        self.assertEquals(set(["foo", "bar"]), task1._requires)
        self.assertEquals(task1._requires, task2._requires)

    def test_config_task(self):
        data_manager1, model_manager1 = self._create_managers()

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        task1 = ConfigTask(node1, item1, "description", "foo", "bar", x="X", y="Y")
        task1.replaces.update(set([("foo1", "bar1"), ("foo2", "bar2")]))

        data_manager1.add_task(task1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()

        task2 = data_manager2.get_task(task1._id)
        self.assertTrue(task2 is not None)
        task2.initialize_from_db(data_manager2, model_manager2)

        self.assertEquals("/node", task1._node_vpath)
        self.assertEquals(task1._node_vpath, task2._node_vpath)

        self.assertTrue(isinstance(task2.node, QueryItem))
        self.assertEquals(task1.node.vpath, task2.node.vpath)

        self.assertEquals("foo", task1._call_type)
        self.assertEquals(task1._call_type, task2._call_type)

        self.assertEquals("bar", task1._call_id)
        self.assertEquals(task1._call_id, task2._call_id)

        self.assertEquals(
            set([("foo1", "bar1"), ("foo2", "bar2")]),
            task1.replaces
        )
        self.assertEquals(
            task1.replaces,
            task2.replaces
        )

        self.assertEquals({"x": "X", "y": "Y"}, task1._kwargs)
        self.assertEquals(task1._kwargs, task2._kwargs)

    def test_callback_task(self):
        data_manager1, model_manager1 = self._create_managers()

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        class Plugin():
            def cb(self):
                pass

        cb = Plugin().cb
        task1 = CallbackTask(item1, "description", cb, "a", "b", x="X", y="Y")

        data_manager1.add_task(task1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()

        task2 = data_manager2.get_task(task1._id)
        self.assertTrue(task2 is not None)
        task2.initialize_from_db(data_manager2, model_manager2)

        self.assertEquals("test_data_manager.Plugin", task1._plugin_class)
        self.assertEquals(task1._plugin_class, task2._plugin_class)

        self.assertEquals(task1._plugin_class, task2._plugin_class)
        self.assertEquals(task1._callback_name, task2._callback_name)

        self.assertEquals(["a", "b"], task1._args)
        self.assertEquals(task1._args, task2._args)

        self.assertEquals({"x": "X", "y": "Y"}, task1._kwargs)
        self.assertEquals(task1._kwargs, task2._kwargs)

    def test_remote_execution_task(self):
        data_manager1, model_manager1 = self._create_managers()

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node1", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        node_mi2 = ModelItem(model_manager1, model_manager1.item_types["node"], "node2", "/")
        data_manager1.model.add(node_mi2)
        node2 = QueryItem(model_manager1, node_mi2)

        task1 = RemoteExecutionTask([node1, node2], item1, "description", "agent", "action")

        data_manager1.add_task(task1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()

        task2 = data_manager2.get_task(task1._id)
        self.assertTrue(task2 is not None)
        task2.initialize_from_db(data_manager2, model_manager2)

        self.assertEquals("agent", task1.agent)
        self.assertEquals(task1.agent, task2.agent)

        self.assertEquals("action", task1.action)
        self.assertEquals(task1.action, task2.action)

        self.assertEquals(
            set(["/node1", "/node2"]),
            set([item.vpath for item in task1.nodes])
        )
        self.assertTrue(all([
            isinstance(item, QueryItem) for item in task2.nodes
        ]))
        self.assertEquals(
            set([item.vpath for item in task1.nodes]),
            set([item.vpath for item in task2.nodes])
        )

    def test_plan(self):
        data_manager1, model_manager1 = self._create_managers()

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node1", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        task1 = ConfigTask(node1, item1, "", "foo", "bar")
        task2 = ConfigTask(node1, item1, "", "foo", "bar")

        plan1 = Plan([[task1, task2]])
        plan1._id = "foobar"
        plan1.populate_plan_tasks()
        data_manager1.add_plan(plan1)
        data_manager1.commit()
        task1_id = task1._id

        data_manager2, _ = self._create_managers()

        plan2 = data_manager2.get_plan("foobar")
        self.assertTrue(plan2 is not None)

        self.assertEquals(plan1._id, plan2._id)
        self.assertEquals(
            set([plan_task.task_id for plan_task in plan1._plan_tasks]),
            set([plan_task.task_id for plan_task in plan2._plan_tasks])
        )

    def test_snapshot_plan(self):
        data_manager1, model_manager1 = self._create_managers()

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node1", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        task1 = ConfigTask(node1, item1, "", "foo", "bar")
        task2 = ConfigTask(node1, item1, "", "foo", "bar")

        plan1 = SnapshotPlan([[task1, task2]])
        plan1._id = "foobar"
        data_manager1.add_plan(plan1)
        data_manager1.commit()
        task1_id = task1._id

        data_manager2, _ = self._create_managers()

        plan2 = data_manager2.get_plan("foobar")
        self.assertTrue(plan2 is not None)

        self.assertEquals(plan1._id, plan2._id)
        self.assertEquals(
            set([plan_task.task_id for plan_task in plan1._plan_tasks]),
            set([plan_task.task_id for plan_task in plan2._plan_tasks])
        )

    def test_basics(self):
        node_mi = ModelItem(self.model_manager, self.model_manager.item_types["node"], "node", "/")
        node = QueryItem(self.model_manager, node_mi)

        item_mi = ModelItem(self.model_manager, self.model_manager.item_types["item"], "item", "/node")
        item = QueryItem(self.model_manager, item_mi)

        task1 = ConfigTask(node, item, "", "foo", "bar")
        task2 = ConfigTask(node, item, "", "foo", "bar")

        plan = Plan([[task1, task2]])
        plan._id = "foobar"
        plan.populate_plan_tasks()
        self.data_manager.add_plan(plan)
        self.data_manager.commit()

        task1_id = task1._id
        task2_id = task2._id

        plan = self.data_manager.get_plan("foobar")
        self.assertTrue(plan is not None)
        self.data_manager.delete_plan(plan)
        self.data_manager.commit()

        self.assertTrue(self.data_manager.get_task(task1_id) is not None)
        self.assertTrue(self.data_manager.get_task(task2_id) is not None)

    def test_persisted_tasks(self):
        data_manager1, model_manager1 = self._create_managers()

        item_mi1 = ModelItem(model_manager1, model_manager1.item_types["item"], "item", "/node")
        data_manager1.model.add(item_mi1)
        item1 = QueryItem(model_manager1, item_mi1)

        node_mi1 = ModelItem(model_manager1, model_manager1.item_types["node"], "node1", "/")
        data_manager1.model.add(node_mi1)
        node1 = QueryItem(model_manager1, node_mi1)

        task1 = ConfigTask(node1, item1, "", "foo", "bar")
        data_manager1.add_task(task1)

        persisted_task1 = PersistedTask("foobar", task1, 123)
        data_manager1.add_persisted_task(persisted_task1)
        data_manager1.commit()

        data_manager2, model_manager2 = self._create_managers()

        persisted_task2 = data_manager2.get_persisted_tasks()[0]
        self.assertTrue(persisted_task2 is not None)

        self.assertEquals("foobar", persisted_task1.hostname)
        self.assertEquals(persisted_task1.hostname, persisted_task2.hostname)

        self.assertEquals(task1._id, persisted_task1.task_id)
        self.assertEquals(persisted_task1.task_id, persisted_task2.task_id)

        self.assertEquals(123, persisted_task1.task_seq_id)
        self.assertEquals(persisted_task1.task_seq_id, persisted_task2.task_seq_id)

        persisted_task1 = PersistedTask("foobar", None, 321)
        persisted_task1.task_id = task1._id
        data_manager1.update_persisted_tasks("foobar", [persisted_task1])
        data_manager1.commit()

        data_manager2.session.expire_all()

        persisted_task2 = data_manager2.get_persisted_tasks()[0]
        self.assertTrue(persisted_task2 is not None)

        self.assertEquals("foobar", persisted_task1.hostname)
        self.assertEquals(persisted_task1.hostname, persisted_task2.hostname)

        self.assertEquals(task1._id, persisted_task1.task_id)
        self.assertEquals(persisted_task1.task_id, persisted_task2.task_id)

        self.assertEquals(321, persisted_task1.task_seq_id)
        self.assertEquals(persisted_task1.task_seq_id, persisted_task2.task_seq_id)

    def test_extensions(self):
        data_manager1, _ = self._create_managers()

        extension1 = ExtensionInfo("name", "classpath", "version")
        data_manager1.add_extension(extension1)
        data_manager1.commit()

        data_manager2, _ = self._create_managers()

        extension2 = data_manager2.get_extensions()[0]
        self.assertTrue(extension2 is not None)

        self.assertEquals("name", extension1.name)
        self.assertEquals(extension1.name, extension2.name)

        self.assertEquals("classpath", extension1.classpath)
        self.assertEquals(extension1.classpath, extension2.classpath)

        self.assertEquals("version", extension1.version)
        self.assertEquals(extension1.version, extension2.version)

        data_manager2.delete_extension(extension2)
        data_manager2.commit()

        self.assertEquals(0, len([e for e in data_manager1.get_extensions()]))

    def test_plugins(self):
        data_manager1, _ = self._create_managers()

        plugin1 = PluginInfo("name", "classpath", "version")
        data_manager1.add_plugin(plugin1)
        data_manager1.commit()

        data_manager2, _ = self._create_managers()

        plugin2 = data_manager2.get_plugins()[0]
        self.assertTrue(plugin2 is not None)

        self.assertEquals("name", plugin1.name)
        self.assertEquals(plugin1.name, plugin2.name)

        self.assertEquals("classpath", plugin1.classpath)
        self.assertEquals(plugin1.classpath, plugin2.classpath)

        self.assertEquals("version", plugin1.version)
        self.assertEquals(plugin1.version, plugin2.version)

        data_manager2.delete_plugin(plugin2)
        data_manager2.commit()

        self.assertEquals(0, len([p for p in data_manager1.get_plugins()]))
