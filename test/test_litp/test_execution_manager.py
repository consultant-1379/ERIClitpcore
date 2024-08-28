import unittest
import time
from datetime import datetime
import ConfigParser
import logging
import StringIO
import cherrypy
import celery
from mock import Mock, MagicMock, patch, call, PropertyMock
from litp.core.plugin_info import PluginInfo
from litp.core.extension_info import ExtensionInfo
from litp.core.exceptions import DataIntegrityException, McoFailed
from litp.core.policies import LockPolicy
from celery.task.control import inspect as celery_inspect
from celery.result import AsyncResult


from litp.core.execution_manager import (
    ExecutionManager,
    CorruptedConfFileException,
)
from litp.core.task import (
    Task,
    CallbackTask,
    ConfigTask,
    OrderedTaskList,
    CleanupTask,
    RemoteExecutionTask,
)
from litp.core.plugin_context_api import PluginApiContext
from litp.core.validators import ValidationError
from litp.core.model_manager import ModelManager
from litp.core.model_manager import QueryItem
from litp.core.plugin_manager import PluginManager
from litp.core.plugin import Plugin
from litp.core.puppet_manager import PuppetManager
from litp.core.model_item import ModelItem
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Collection
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import Reference
from litp.core.model_type import View
from litp.core.exceptions import ViewError
from litp.core.model_type import RefCollection
from litp.core.plan import Plan, SnapshotPlan
from litp.core.callback_api import CallbackApi
from litp.core.lock_task_creator import LockTaskCreator
from litp.core.config import config
from litp.core.model_container import ModelItemContainer

from contextlib import contextmanager, nested

from litp.core.litp_threadpool import ThreadPoolSingleton
from litp.core.future_property_value import FuturePropertyValue
import litp.core.litp_threadpool
import litp.core.constants as constants
from litp.data.constants import SNAPSHOT_PLAN_MODEL_ID_PREFIX
from litp.core.exceptions import ConfigValueError, EmptyPlanException
from litp.core.exceptions import NoCredentialsException, NodeLockException
from litp.core.exceptions import NonUniqueTaskException, PluginError
from litp.core.exceptions import TaskValidationException
from litp.core.exceptions import CallbackExecutionException
import os
import json
from collections import defaultdict
from litp.plan_types.deployment_plan import deployment_plan_tags
from litp.extensions.core_extension import CoreExtension
from litp.core.worker.celery_app import celery_app
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.constants import CURRENT_PLAN_ID
from litp.data.test_db_engine import get_engine
from litp.core import scope


CALLBACK_TASK_TIMEOUT = float(3)
DELAY_TASK_IN_PROGRESS = 0.5 * CALLBACK_TASK_TIMEOUT
DELAY_TASK_COMPLETED = 1.25 * CALLBACK_TASK_TIMEOUT
celery_app.conf.CELERY_ALWAYS_EAGER = True

@contextmanager
def patch_method(module, methodname, new_method):
    """
    Monkey patching of a specified method from a specified module.
    'module' may be also a class or an instance.

    Example:
    >>> with patch(os, 'listdir', lambda d: ['a', 'b', 'c']):
    ...    print os.listdir('.')
    ...
    ['a', 'b', 'c']

    """
    old_method = getattr(module, methodname)
    setattr(module, methodname, new_method)

    try:
        yield
    finally:
        setattr(module, methodname, old_method)


class MockPlan(Plan):
    '''Mock Plan for plan comparisons, can be initialised with an explicit set
    of phases
    '''
    def __init__(self, phases, valid=False, state=Plan.INITIAL):
        self._phases = phases
        self.valid = valid
        self._state = state

    def is_running(self):
        return self._state == Plan.RUNNING

    def stop(self):
        self.processing = False


class Mockitem(object):
    def __init__(self, vPath):
        self.vpath = vPath

class MockPuppetManager(PuppetManager):
    def __init__(self, model_manager, error=None):
        super(MockPuppetManager, self).__init__(model_manager)
        self.phases = []
        self._waited_for_phase = False
        self._applied_configuration = False
        self._error = error
        self._write_templates = lambda hostnames: None
        self.children = {}
        self.parent = None
        self.phase_ids = []
        self.phase_index = 0

    def add_phase(self,task_list, phase_id):
        self.phase_ids.append(phase_id)
        self.phases.append(task_list)

    def wait_for_phase(self, nodes, timeout=600, poll_freq=60, poll_count=60):
        self._waited_for_phase = True
        for task in self.phases[self.phase_index]:
            task.state = "Success"
        self.phase_index += 1
        return not bool(self._error)

    def apply_nodes(self):
        self._applied_configuration = True

    def get_ms_hostname(self):
        return 'ms1'

    def disable_puppet_on_hosts(self, hostnames=None, task_state=constants.TASK_SUCCESS):
        return

# Test plugins

class TestPluginClass(Plugin):
    def create_configuration(self, api):
        nodes = api.query("node")
        return [RemoteExecutionTask(nodes, nodes[0], "RET Desc", "puppet", "stop")]


class TestPlugin(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            if node.is_initial():
                for callback_task_item in node.query("type_a"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method_wait, CALLBACK_TASK_TIMEOUT))
                for comp in node.query("type_b"):
                    configuration.append(
                            ConfigTask(node, comp, "Test Task", "foo::bar",
                             "call_type_b", param2="value2"))
                for comp in node.query("type_c"):
                    configuration.append(
                            ConfigTask(node, comp, "Test Task", "foo::bar",
                             "call_type_c", param2="value2"))

            elif node.is_for_removal():
                for comp in node.query("type_b"):
                    configuration.append(
                        ConfigTask(node, comp, "Test Task", "remove1",
                            "value1", param2="value2"))
                for comp in node.query("type_c"):
                    configuration.append(
                        ConfigTask(node, comp, "Test Task", "remove1",
                            "value1", param2="value2"))

        return configuration

    def callback_method(self, callback_api):
        return True, 'callback method successful'

    def callback_method_wait(self, callback_api, delay):
        #time.sleep(delay)
        return True, 'callback method successful'


class TestPlugin2(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            for comp in node.query("type_a"):
                configuration.append(ConfigTask(node, comp, "Test Task",
                                          "call2", "id_type_a"))
                configuration.append(ConfigTask(node, comp, "Test Task",
                                          "call3", "id_type_a"))
        return configuration

class TestPlugin3(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        return [ OrderedTaskList(nodes, []) ]

class TestPluginCallbackArgs(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            for callback_task_item in node.query("type_a"):
                configuration.append(
                        CallbackTask(callback_task_item, "Test Task",
                            self.callback_method_args, 2, 3, foo='bar',
                            bar='bat'))

    def callback_method_args(self, a, b, c, d):
        pass


class TestPluginMixedPhase(Plugin):

    def create_configuration(self, plugin_api_context):
        tasks = []

        nodes = plugin_api_context.query("node")
        for node in nodes:
            if node.is_initial():
                somethings = node.query("something")
                for thing in somethings:
                    tasks.append(
                        CallbackTask(
                            thing, "Test CallbackTask",
                            self.callback_method_wait,
                            CALLBACK_TASK_TIMEOUT
                        )
                    )

                for comp in node.query("type_c"):
                    tasks.append(
                            ConfigTask(node, comp, "Test Task", "foo::bar",
                             "call_type_c", param2="value2"))

        return tasks

    def callback_method_wait(self, callback_api, delay):
        #time.sleep(delay)
        return True, 'callback method successful'


class TestPluginRemoteExecutionTasks(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []

        model_item = plugin_api_context.query("type_a")[0]
        nodes = plugin_api_context.query("node")
        tasks.append(
            RemoteExecutionTask(
                nodes,
                model_item,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        return tasks

    def create_lock_tasks(self, plugin_api_context, node):
        # Whatever query item, just to be passed to ConfigTask
        comp = plugin_api_context.query("type_a")[0]
        lock_task = ConfigTask(node, comp, "Lock Task", "lock", "lock_id")
        unlock_task = ConfigTask(node, comp, "Unlock Task", "unlock", "id")
        return (lock_task, unlock_task)

    def callback_method(self, callback_api):
        return True, 'callback method successful'

    def callback_method_wait(self, callback_api, delay):
        #time.sleep(delay)
        return True, 'callback method successful'


class TestPluginLockTasksOnly(Plugin):
    def create_configuration(self, plugin_api_context):
        return []

    def create_lock_tasks(self, plugin_api_context, node):
        # Whatever query item, just to be passed to ConfigTask
        comp = plugin_api_context.query("type_a")[0]
        lock_task = ConfigTask(node, comp, "Lock Task", "lock", "lock_id")
        unlock_task = ConfigTask(node, comp, "Unlock Task", "unlock", "id")
        return (lock_task, unlock_task)


class TestPluginRemoteExecutionTasksNoLocking(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []

        model_item = plugin_api_context.query("type_a")[0]
        nodes = plugin_api_context.query("node")
        tasks.append(
            RemoteExecutionTask(
                nodes,
                model_item,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        return tasks

    def callback_method(self, callback_api):
        return True, 'callback method successful'

    def callback_method_wait(self, callback_api, delay):
        #time.sleep(delay)
        return True, 'callback method successful'


class TestPluginRemoteExecutionTasksManyTasks(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []

        model_item = plugin_api_context.query("type_a")[0]
        model_item_type_b = plugin_api_context.query("type_b")[0]
        nodes = plugin_api_context.query("node")
        cluster = plugin_api_context.query("cluster")[0]
        node1 = plugin_api_context.query("node", hostname="node1")[0]
        node2 = plugin_api_context.query("node", hostname="node2")[0]
        node3 = plugin_api_context.query("node", hostname="node3")[0]
        node1_something = node1.query('something')[0]
        node2_something = node2.query('something')[0]

        tasks.append(
            RemoteExecutionTask(
                nodes,
                model_item,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        tasks.append(
            ConfigTask(nodes[0], model_item, "Test Task", "foo1", "id"))

        tasks.append(
            CallbackTask(model_item, "Test CB Task", self.callback_method))

        tasks.append(
            OrderedTaskList(model_item,
                [ConfigTask(node1, model_item, "Test Task", "foo2", "id"),
                CallbackTask(model_item, "Test CB Task", self.callback_method)]))

        tasks.append(
            RemoteExecutionTask(
                nodes,
                cluster,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        tasks.append(
            ConfigTask(nodes[0], cluster, "Test Task", "foo3", "id"))

        tasks.append(
            CallbackTask(cluster, "Test CB Task", self.callback_method))

        tasks.append(
            OrderedTaskList(cluster,
                [CallbackTask(cluster, "Test CB Task", self.callback_method),
                CallbackTask(cluster, "Test CB Task", self.callback_method)]))

        tasks.append(
            CallbackTask(model_item_type_b, "Test CB Task", self.callback_method))

        tasks.append(
                ConfigTask(node1, node1_something, "Something task", "foo5", "id"))

        tasks.append(
                ConfigTask(node2, node2_something, "Something task", "foo6", "id"))

        return tasks

    def create_lock_tasks(self, plugin_api_context, node):
        # Whatever query item, just to be passed to ConfigTask
        comp = plugin_api_context.query("type_a")[0]
        lock_task = ConfigTask(node, comp, "Lock Task", "lock", "lock_id")
        unlock_task = ConfigTask(node, comp, "Unlock Task", "unlock", "id")
        return (lock_task, unlock_task)

    def callback_method(self, callback_api):
        return True, 'callback method successful'

    def callback_method_wait(self, callback_api, delay):
        #time.sleep(delay)
        return True, 'callback method successful'

class TestPluginWithDuplicatedConfigTasks(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []

        model_item = plugin_api_context.query("type_a")[0]
        model_item_type_b = plugin_api_context.query("type_b")[0]
        nodes = plugin_api_context.query("node")
        cluster = plugin_api_context.query("cluster")[0]
        node1 = plugin_api_context.query("node", hostname="node1")[0]
        node2 = plugin_api_context.query("node", hostname="node2")[0]
        node3 = plugin_api_context.query("node", hostname="node3")[0]
        node1_something = node1.query('something')[0]
        node2_something = node2.query('something')[0]

        tasks.append(
            ConfigTask(nodes[0], model_item, "Test Task", "foo1", "id"))

        tasks.append(
            OrderedTaskList(model_item,
                [ConfigTask(nodes[0], model_item, "Test Task", "foo1", "id")]))

        tasks.append(
            ConfigTask(nodes[0], cluster, "Test Task", "foo", "id"))

        tasks.append(
            OrderedTaskList(cluster,
                [ConfigTask(nodes[0], cluster, "Test Task", "foo", "id")]))

        tasks.append(
                ConfigTask(node1, node1_something, "Something task", "foo", "id"))

        tasks.append(
                ConfigTask(node2, node2_something, "Something task", "foo", "id"))

        return tasks

class TestPluginWithDuplicatedNonConfigTasks(Plugin):
    def create_configuration(self, plugin_api_context):
        tasks = []

        model_item = plugin_api_context.query("type_a")[0]
        model_item_type_b = plugin_api_context.query("type_b")[0]
        nodes = plugin_api_context.query("node")
        cluster = plugin_api_context.query("cluster")[0]
        node1 = plugin_api_context.query("node", hostname="node1")[0]
        node2 = plugin_api_context.query("node", hostname="node2")[0]
        node3 = plugin_api_context.query("node", hostname="node3")[0]
        node1_something = node1.query('something')[0]
        node2_something = node2.query('something')[0]

        tasks.append(
            RemoteExecutionTask(
                nodes,
                model_item,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        tasks.append(
            CallbackTask(model_item, "Test CB Task", self.callback_method))

        tasks.append(
            OrderedTaskList(model_item,
                [CallbackTask(model_item, "Test CB Task", self.callback_method)]))

        tasks.append(
            RemoteExecutionTask(
                nodes,
                cluster,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        tasks.append(
            CallbackTask(cluster, "Test CB Task", self.callback_method))

        tasks.append(
            OrderedTaskList(cluster,
                [CallbackTask(cluster, "Test CB Task", self.callback_method)]))

        tasks.append(
            CallbackTask(model_item_type_b, "Test CB Task", self.callback_method))

        return tasks

    def callback_method(self, callback_api):
        return True, 'callback method successful'


class TestPluginUncaughtExceptionCallback(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            if node.is_initial():
                for callback_task_item in node.query("type_a"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method_exception))
        return configuration

    def callback_method_exception(self, callback_api):
        return 6/0, 'callback method successful'

class TestPluginExceptionCallback(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            if node.is_initial():
                for callback_task_item in node.query("type_a"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method_exception))
                for callback_task_item in node.query("type_b"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method_exception))
                for callback_task_item in node.query("type_c"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method_exception))

        return configuration

    def callback_method_exception(self, callback_api):
        raise CallbackExecutionException("Oh no!")

class TestPluginExceptionCreateTasks(Plugin):
    def create_configuration(self, plugin_api_context):
        return 6/0

class TestPluginDiverseCallbackArgTypes(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            if node.is_initial():
                for callback_task_item in node.query("type_a"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method, 2, [], {'a': 2},
                                object()))
                for callback_task_item in node.query("type_b"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method, 2, [], {'a': 2},
                                object()))
                for callback_task_item in node.query("type_c"):
                    configuration.append(
                            CallbackTask(callback_task_item, "Test Task",
                                self.callback_method, 2, [], {'a': 2},
                                object()))

        return configuration

    def callback_method(self, callback_api):
        pass

class TestPluginQuery(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        configuration = []
        for node in nodes:
            for no, comp in enumerate(node.query("type_a")):
                configuration.append(
                        ConfigTask(node, comp, "Test Task", "baz::bat",
                            "value" + str(no), param2="value2"))
        return configuration

class TestPluginWithValidationError(Plugin):
    def validate_model(self, context):
        return [ValidationError('/nodes/arbitrary/path', error_message="item A is invalid")]

class TestPluginWithValidationException(Plugin):
    def validate_model(self, context):
        return [ValidationError(str(6/0), error_message="item A is invalid")]

class TestPluginInvalidCallbacks(Plugin):
    def method(self, api, param):
        pass

    def create_configuration(self, api):
        nodes = api.query("node")
        return [CallbackTask(node, "Invalid Task", self.method, object()) for \
            node in nodes]

def _function(invalid_api, invalid_arg):
    pass


class TestPluginInvalidFunctionCallback(Plugin):
    def create_configuration(self, api):
        nodes = api.query("node")
        return [CallbackTask(node, "Invalid Task", _function, "") for \
            node in nodes]

class NotAPlugin(object):
    def this_class_is_not_a_plugin(self, api):
        pass


class TestPluginInvalidMethodCallback(Plugin):

    def create_configuration(self, api):
        nodes = api.query("node")
        return [CallbackTask(node, "Invalid Task",
            NotAPlugin().this_class_is_not_a_plugin) for \
            node in nodes]


class TestPluginSetSecurityCredentials(Plugin):
    def get_security_credentials(self):
        return None


class PluginWithCredentials(Plugin):
    def get_security_credentials(self, plugin_api_context):
        return [('user', 'service')]


class _PluginWithCallRecording(Plugin):

    @classmethod
    def reset_call_recording(cls):
        cls._update_model_called = False
        cls._validate_model_called = False
        cls._create_configuration_called = False

    def create_configuration(self, plugin_api_context):
        self.__class__._create_configuration_called = True
        return []

    def validate_model(self, plugin_api_context):
        self.__class__._validate_model_called = True
        return []

    def update_model(self, plugin_api_context):
        node = plugin_api_context.query_by_vpath("/deployments/d1/clusters/c1/nodes/node1")
        node.name = "ChangedName"
        self.__class__._update_model_called = True

class PluginWithUpdateModelA(_PluginWithCallRecording): pass
class PluginWithUpdateModelB(_PluginWithCallRecording): pass
class PluginWithUpdateModelC(_PluginWithCallRecording): pass
class PluginWithUpdateModelD(_PluginWithCallRecording): pass

class PluginWithUpdateModelRaisingException(_PluginWithCallRecording):
    def update_model(self, plugin_api_context):
        super(PluginWithUpdateModelRaisingException, self). \
            update_model(plugin_api_context)
        raise Exception("Oops, cannot update model")


class TestSnapshotPlugin(Plugin):

    def create_snapshot_plan(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        tasks = []
        for node in nodes:
            tasks.append(
                CallbackTask(node, "A Snapshot Task", self.callback_method))

        return tasks

    def callback_method(self, callback_api):
        return True, 'callback method successful'


class TestSnapshotPluginWithInvalidTaskTypes(Plugin):

    def create_snapshot_plan(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        cluster = plugin_api_context.query("cluster")[0]
        tasks = []

        tasks.append(
            ConfigTask(nodes[0], cluster, "Test Task", "foo", "id"))

        tasks.append(
            RemoteExecutionTask(
                nodes,
                cluster,
                "Description",
                "agent",
                "action",
                kwarg1="val1"))

        tasks.append(
            OrderedTaskList(
                cluster,
                [CallbackTask(
                    cluster,"A Task in an OTL", self.callback_method)]))

        return tasks

    def callback_method(self, callback_api):
        return True, 'callback method successful'


class ExecutionManagerTest(unittest.TestCase):
    def setUp(self):

        self.db_storage = DbStorage(get_engine())
        self.db_storage.reset()
        self.data_manager = DataManager(self.db_storage.create_session())

        self.model = ModelManager()
        self.data_manager.configure(self.model)
        self.model.data_manager = self.data_manager

        config.update({"puppet_phase_timeout": 42})
        config.update({"puppet_poll_frequency": 60})
        config.update({"puppet_poll_count": 60})
        #self.model = ModelManager()
        self.api = PluginApiContext(self.model)
        self.plugin_manager = PluginManager(self.model)
        self.puppet_manager = MockPuppetManager(self.model)
        self.manager = ExecutionManager(self.model,
                                        self.puppet_manager,
                                        self.plugin_manager)
        self.manager._phase_id = self.mock_phase_id

        cherrypy.config.update({
        'db_storage': self.db_storage,
        'model_manager': self.model,
        'puppet_manager': self.puppet_manager,
        'execution_manager': self.manager,
        'plugin_manager': self.plugin_manager,
        'dbase_root':'/pathdoesnotexist',
        'last_successful_plan_model':'NONEXISTENT_RESTORE_FILE',
        })

        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))
        self.model.register_property_type(
                PropertyType('ha_manager', regex=r"^(cmw|vcs)$|^$")
        )

        self.model.register_item_type(ItemType("root",
            nodes=Collection("node"),
            ms=Child("ms"),
            snapshots=Collection("snapshot-base", max_count=1),
            deployments=Collection("deployment"),
            somethings=Collection("something"),
            packages=Collection("package")
        ))
        self.model.register_item_type(ItemType("deployment",
            clusters=Collection("cluster"),
            ordered_clusters=View("basic_list", callable_method=CoreExtension.get_ordered_clusters),
        ))
        # since cluster-base got introduced ModelItem.is_cluster() should check
        # that instead
        self.model.register_item_type(ItemType("cluster-base"))
        self.model.register_item_type(ItemType("network-interface"))

        self.model.register_item_type(ItemType("cluster",
                                               extend_item="cluster-base",
                                               nodes=Collection("node"),
                                               ha_manager=Property("ha_manager")))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string", updatable_plugin=False),
            another_property=Property("basic_string", updatable_plugin=True),
            future_view=View("basic_string", callable_method=ExecutionManagerTest.future_view_method),
            name=Property("basic_string", updatable_plugin=True),
            comp1=Child("type_a", require="comp3"),
            comp2=Child("type_c"),
            comp3=Child("type_b", require="comp2"),
            something=Reference("something"),
            eth0=Child("network-interface"),
            is_locked=Property("basic_string", default="false")
        ))
        self.model.register_item_type(ItemType("ms",
            extend_item="node"
        ))
        self.model.register_item_type(ItemType("something",
            name=Property("basic_string"),
        ))
        self.model.register_item_type(ItemType("type_a",
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("type_b",
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("type_c",
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        self.model.register_item_type(ItemType("snapshot-base",
                timestamp=Property('basic_string'),
                active=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            default='true')))

        self.model.create_root_item("root")
        self.model.create_item("ms", "/ms", hostname="ms1")

        class myReader(object):

            def read(self, file_path):
                return

            def get(self, file_path, key):
                return "test_value"

        self.old_safe = ConfigParser.SafeConfigParser
        ConfigParser.SafeConfigParser = myReader
        #db_storage = DbStorage(engine)

        self.plugin_api = PluginApiContext(self.model)

    def qi(self, model_item):
        return QueryItem(self.model, model_item)

    @staticmethod
    def future_view_method(model_manager, query_item):
        return "<prefix>" + query_item.name + "<suffix>"

    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def tearDown(self):
        ConfigParser.SafeConfigParser = self.old_safe

    def mock_phase_id(self, phase_index):
        return "%s" % (phase_index)

    def _add_plugin(self, plugin):
        name = plugin.__class__.__name__
        klass = "%s.%s" % (plugin.__class__.__module__,
            plugin.__class__.__name__)
        version = '1.0.0'

        self.plugin_manager.add_plugin(name, klass, version, plugin)

    def run_plan_async(self):
        return self.manager.run_plan()

    # This is required for the purpose of adding jobs to the threadpool
    def get_vpath(self):
        return '/execution'

    def _setup_model(self):
        """Creates and returns model items."""
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        node = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/node1",
                hostname="node", name="OriginalName",
                another_property="OriginalAnotherProperty")

        item1 = self.model.create_item("type_b", "/deployments/d1/clusters/c1/nodes/node1/comp3")
        item2 = self.model.create_item("type_c", "/deployments/d1/clusters/c1/nodes/node1/comp2")
        return node, item1, item2

    @contextmanager
    def engine_context():
        yield cherrypy.config["db_storage"]._engine

    @contextmanager
    def worker_context(engine):
        yield

    def init_metrics():
        pass

    def configure_worker(engine, **kwargs):
        pass

    ###### Test methods below this line
    @patch('litp.core.execution_manager.has_errors', Mock(return_value=True))
    @patch('litp.core.puppet_manager.PuppetManager.add_phase', Mock())
    @patch('litp.core.puppet_manager.PuppetManager._apply_nodes')
    def test_run_puppet_phase_return_value(self, mock_apply):
        # TORF-165226: return value of _run_puppet_phase, called by CeleryTask
        # must conform to expected format
        mm = ModelManager()
        pm = PuppetManager(mm)
        em = ExecutionManager(mm, pm, Mock())
        mock_apply.side_effect = McoFailed('Deliberate', {'ms1': 'foo'})
        res = em._run_puppet_phase(0, [])
        self.assertEqual(res, {'error': {'ms1': 'foo'}})
        mock_apply.side_effect = McoFailed('Deliberate2')
        res = em._run_puppet_phase(0, [])
        self.assertEqual(res, {'error': {}})

    @patch('litp.core.puppet_manager.PuppetManager.add_phase', Mock())
    @patch('litp.core.puppet_manager.PuppetManager._apply_nodes')
    def test_run_puppet_phase_return_value_with_has_mco_result(self, mock_apply):
        mm = ModelManager()
        pm = PuppetManager(mm)
        em = ExecutionManager(mm, pm, Mock())
        stop_puppet_applying_error = {'ms1':
                                          {'errors': 'Mco action kill_puppet_agent failed',
                                           'data': {'status': 1, 'err': '',
                                                    'out': 'Failed to terminate puppet agent with pid: 50184'}}}

        mock_apply.side_effect = McoFailed('Mco action kill_puppet_agent failed', stop_puppet_applying_error)
        res = em._run_puppet_phase(0, [])
        self.assertEqual(res, {'error': stop_puppet_applying_error})

    @patch('litp.core.execution_manager.time.sleep', Mock())
    @patch('litp.core.execution_manager.ExecutionManager._enqueue_ready_phases')
    def test_celery_task_exception_handling(self, mock_enque):
        # TORF-156510: Test async_result.result returning a dict with error
        self.manager.plan = Mock(
            _id=1, is_stopping=lambda: False, phases=[[], [], [], []])
        celery_task_errors = [
            Mock(result=None, failed=lambda: False),
            Mock(result=Exception('foo'), failed=lambda: True),
            Mock(result={'error': str(Exception('bar'))}, failed=lambda: False),
            Mock(result=None, failed=lambda: False)
        ]
        self.manager._fail_running_tasks = lambda a: None
        self.manager._update_item_states = Mock()

        def enqueue_mock_result(errors, last_phase_idx=-1):
            self.manager._active_phases[last_phase_idx] = celery_task_errors.pop()

        mock_enque.side_effect = enqueue_mock_result
        actual = self.manager._run_all_phases()
        # Assert we enqueued twice, on the 2nd task we encountered an error
        self.assertEquals(2, mock_enque.call_count)
        # Assert errors returned as expected
        expected = {'errors': {-1: {'error': 'bar'}}, 'error': 'bar'}
        self.assertEqual(actual, expected)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_plan_worker_expires_mutable_items(self, mock_get_context,
                            mock_configure_worker,
                            mock_init_metrics,
                            mock_engine_context):

        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        unused_node_item = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/n1", hostname="node1"
        )

        ms_mi = self.model.query('ms')[0]
        ms_qi = self.qi(ms_mi)
        tasks = [
            # Only a CallbackTask can change items, but that's irrelevant to
            # our instance expiry logic
            ConfigTask(ms_qi, ms_qi, "Test Task", "call1", call_id="type1")
        ]
        self.create_plugin(tasks, [])
        self.manager.create_plan()
        self.manager._run_plan_start()
        # Items of type "node" and "ms" have plugin-updatable properties
        self.assertEqual(
            set([unused_node_item.vpath, ms_mi.vpath]),
            self.manager.model_manager.get_plugin_updatable_items()
        )

        with patch.object(self.manager.data_manager.session, 'expire') as mock_expire:
            self.manager._run_all_phases()
            mock_expire.assert_has_calls([call(ms_mi), call(unused_node_item)],
                                         any_order=True)

    @patch('litp.core.execution_manager.time.sleep', Mock())
    @patch('litp.core.execution_manager.ExecutionManager._enqueue_ready_phases')
    def test_celery_task_exception_handling_2(self, mock_enque):
        # TORF-156510: Test async_result.failed() scenario
        self.manager.plan = Mock(_id=1, is_stopping=lambda: False, phases=[[]])

        def enqueue_mock_result(errors, last_phase_idx=-1):
            """
            If AsyncResult.failed() returns True, AsyncResult.result will
            contain the exception instance.
            """
            self.manager._active_phases[last_phase_idx] = \
                Mock(result=Exception('foo'), failed=lambda: True)

        mock_enque.side_effect = enqueue_mock_result
        self.manager._fail_running_tasks = lambda a: None
        self.manager._update_item_states = Mock()
        actual = self.manager._run_all_phases()
        # Assert errors returned as expected'error'
        expected = {'errors': {-1: Exception('foo')}, 'error': 'foo'}
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(actual['error'], expected['error'])
        self.assertEqual(len(actual['errors']), len(expected['errors']))

    def test_run_callback_phase_on_resume(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        n1 = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n1", hostname="node1")
        n2 = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n2", hostname="node2")

        self.plugin = TestPlugin()
        self.plugin.successful_task_cb = MagicMock()
        self.plugin.resume_task_cb = MagicMock()

        successful_task = CallbackTask(
            QueryItem(self.model, n1),
            "Callbacktask",
            self.plugin.successful_task_cb
        )
        successful_task.state = constants.TASK_SUCCESS

        # This task failed and has subsequently been reset to the Initial state
        resume_task = CallbackTask(
            QueryItem(self.model, n2),
            "Callbacktask",
            self.plugin.resume_task_cb
        )
        resume_task.state = constants.TASK_INITIAL

        resumption_phase = [successful_task, resume_task]
        self.manager.plan = MagicMock()
        self.manager.plan.phases = [resumption_phase]

        with patch.object(self.manager, '_process_callback_task') as mock_process_cb:
            mock_process_cb.return_value = ("success", None)
            self.manager._run_callback_phase(0, resumption_phase)

            # We do not re-run the successful task
            self.assertEquals(1, len(mock_process_cb.mock_calls))
            self.assertEquals(
                [call(resume_task)],
                mock_process_cb.mock_calls
            )

    @patch('litp.core.task.subprocess.Popen')
    def test_process_callback_task(self, Mock_popen):
        instance = Mock_popen.return_value
        instance.communicate.return_value = ("error2", None)

        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n1", hostname="node1")
        self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/n2", hostname="node2")

        plugin = TestPluginClass()
        remote_task = plugin.create_configuration(self.plugin_api)[0]
        self.manager.plan = MagicMock()
        expected_result = (None, {'error': 'error running RemoteExecutionTask'})
        result = self.manager._process_callback_task(remote_task)

        self.assertEquals(expected_result, result)

    def test_create_all_items_task_dict(self):
        item1 = MagicMock(hostname='hostname', vpath='/item1')
        item2 = MagicMock(hostname='hostname', vpath='/item2')
        item3 = MagicMock(hostname='hostname', vpath='/item3')
        item4 = MagicMock(hostname='hostname', vpath='/item4')

        task1 = ConfigTask(item1, item1, "Foo", "foo::bar", "call_type_foo")
        task2 = ConfigTask(item2, item2, "Bar", "baz::bal", "call_type_baz")

        task1.model_items.update([item3, item4])
        task2.model_items.add(item1)

        tasks = [task1, task2]

        item_tasks = litp.core.execution_manager.create_all_items_task_dict(tasks)
        self.assertEqual(len(item_tasks), 4)
        self.assertTrue('/item1' in item_tasks)
        self.assertEqual(item_tasks['/item1'], set([task1, task2]))
        self.assertTrue('/item2' in item_tasks)
        self.assertEqual(item_tasks['/item2'], set([task2]))
        self.assertTrue('/item3' in item_tasks)
        self.assertEqual(item_tasks['/item3'], set([task1]))
        self.assertTrue('/item4' in item_tasks)
        self.assertEqual(item_tasks['/item4'], set([task1]))

    def test_manager_vpath(self):
        self.assertEqual('/execution', self.manager.get_vpath())

    def test_create_plan_no_tasks_unicode_kwargs(self):
        node, item1, item2 = self._setup_model()
        node_q = self.api.query('node')[0]
        # Create 2 tasks only diff being their kwargs - one is unicode
        task = ConfigTask(node_q, node_q, "Test Task", "call1",
                "id_type_1", list=['one', 'two'])
        # Make these kwargs the same as task but in unicode, as hash
        # str(kwargs) will be different when compared to task
        similar_task = ConfigTask(node_q, node_q, "Test Task", "call1",
                "id_type_1", list=[u'one', u'two'])

        def mock_get_prev_successful_tasks():
            return [similar_task]
        self.manager._get_prev_successful_tasks = mock_get_prev_successful_tasks

        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_configuration(self, plugin_api_context):
                return [task]
        plugin = DummyPlugin()
        self._add_plugin(plugin)

        res = self.manager.create_plan('Deployment')
        # Assert unable to create plan with no tasks
        self.assertEqual([{'message':'no tasks were generated',
                           'error': 'DoNothingPlanError'}], res)

    def test_create_plan_no_tasks_order_of_kwargs(self):
        node, item1, item2 = self._setup_model()
        node_q = self.api.query('node')[0]
        # Create 2 tasks only diff being the order of their kwargs
        task = ConfigTask(node_q, node_q, "Test Task", "call1",
                "id_type_1", name="unique", something="different")
        # Make order of kwargs different to task, so when hash does
        # str(kwargs), the hash comparison will be different
        similar_task = ConfigTask(node_q, node_q, "Test Task", "call1",
                "id_type_1", something="different", name="unique")

        def mock_get_prev_successful_tasks():
            return [similar_task]
        self.manager._get_prev_successful_tasks = mock_get_prev_successful_tasks

        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_configuration(self, plugin_api_context):
                return [task]
        plugin = DummyPlugin()
        self._add_plugin(plugin)

        res = self.manager.create_plan('Deployment')
        # Assert unable to create plan with no tasks
        self.assertEqual([{'message':'no tasks were generated',
                           'error': 'DoNothingPlanError'}], res)

    def test_create_plan(self):
        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()

        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")
        node1 = self.qi(self.model.query("node")[0])

        self.assertFalse(self.manager.plan_exists())
        task1 = ConfigTask(node1, node1.comp1, "Test Task", "call2", "id_type_a")
        task2 = ConfigTask(node1, node1.comp1, "Test Task", "call3", "id_type_a",)
        task2.group = deployment_plan_groups.NODE_GROUP

        task3 = ConfigTask(node1, node1.comp3, "Test Task", "foo::bar", "call_type_b", param2="value2")
        task3.group = deployment_plan_groups.NODE_GROUP

        task4 = ConfigTask(node1, node1.comp2, "Test Task", "foo::bar", "call_type_c",
                           param2="value2")
        task4.group = deployment_plan_groups.NODE_GROUP

        task7 = CallbackTask(node1.comp1, "gfsfsd",
                self.plugin.callback_method_wait, CALLBACK_TASK_TIMEOUT)
        task7.group = deployment_plan_groups.NODE_GROUP

        task2.requires = set([task3, task4])

        plan = self.manager.create_plan()
        self.assertTrue(self.manager.plan_exists())
        self.assertEqual(Plan, type(plan))

    def test_plan_phases(self):
        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()

        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")
        node1 = self.api.query("node")[0]

        self.assertFalse(self.manager.plan_exists())

        task1 = ConfigTask(node1, node1.comp1, "Test Task", "call2", "id_type_a")
        task1.plugin_name = "TestPlugin2"
        task1._requires = set(['node1__foo_3a_3abar__call__type__b',
                               'node1__foo_3a_3abar__call__type__c'])
        task1.group = deployment_plan_groups.NODE_GROUP

        task2 = ConfigTask(node1, node1.comp1, "Test Task", "call3", "id_type_a")
        task2.group = deployment_plan_groups.NODE_GROUP
        task2.plugin_name = "TestPlugin2"
        task2._requires = set(['node1__foo_3a_3abar__call__type__b',
                               'node1__foo_3a_3abar__call__type__c'])

        task3 = ConfigTask(node1, node1.comp3, "Test Task", "foo::bar", "call_type_b",
                param2='value2')
        task3._requires = set(['node1__foo_3a_3abar__call__type__c'])

        task3.group = deployment_plan_groups.NODE_GROUP
        task3.plugin_name = "TestPlugin"

        task4 = ConfigTask(node1, node1.comp2, "Test Task", "foo::bar", "call_type_c",
                param2='value2')
        task4.plugin_name = "TestPlugin"
        task4.group = deployment_plan_groups.NODE_GROUP

        task5 = CallbackTask(node1.comp1, "Test Task",
                self.plugin.callback_method_wait, CALLBACK_TASK_TIMEOUT)
        task5.plugin_name = "TestPlugin"
        task5.group = deployment_plan_groups.NODE_GROUP

        self.manager.create_plan()
        self.assertEqual(2, len(self.manager.plan_phases()))
        self.assertEqual(
            set([task1, task2, task3, task4]),
            set(self.manager.plan_phases()[0])
            )

        self.assertEqual(
            set([task5]),
            set(self.manager.plan_phases()[1])
        )

    def test_plan_empty_ordered_task_list(self):
        plugin = TestPlugin3()
        self._add_plugin(plugin)

        self._setup_model()

        plan = self.manager.create_plan()
        self.assertFalse(isinstance(plan, Plan))

    def test_delete_plan(self):
        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()

        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()
        node1 = self.model.query("node")[0]
        self.manager.create_plan()

        self.assertTrue(isinstance(self.manager.plan, Plan))
        self.manager.delete_plan()
        self.assertEquals(None, self.manager.plan)


    #TODO make obsolete???
    def test_run_phase(self):
        self.plugin = TestPluginQuery()
        self._add_plugin(self.plugin)

        # add items
        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")

        self.manager.create_plan()

        self.assertEqual(1, len(self.manager.plan.phases))

        self.manager.plan.set_ready()
        self.manager._run_phase(0)

        self.assertTrue(self.puppet_manager._applied_configuration)
        self.assertTrue(self.puppet_manager._waited_for_phase)
        self.assertTrue(self.manager._is_phase_complete(0))

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_run_plan_failures(self, mock_get_context,
                                    mock_configure_worker,
                                    mock_init_metrics,
                                    mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self.plugin = TestPlugin()
        self.plugin3 = TestPlugin2()

        self.puppet_manager = MockPuppetManager(self.model, "an error")
        self.manager = ExecutionManager(self.model, self.puppet_manager, self.plugin_manager)
        self.manager._phase_id = self.mock_phase_id

        cherrypy.config.update({
            'puppet_manager': self.puppet_manager,
            'execution_manager': self.manager,
        })

        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin3)

        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")
        self.model.remove_item("/deployments/d1/clusters/c1/nodes/node1/comp3")

        self.manager.create_plan()
        self.assertEqual(4, len(self.manager.plan._tasks))
        self.manager.plan._tasks[1].state = "fail"
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            result = {'error':'puppet errors'}
            self.assertEqual(result['error'], self.manager.run_plan()['error'])
        self.assertTrue(self.puppet_manager._applied_configuration)
        self.assertTrue(self.puppet_manager._waited_for_phase)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_on_successful_plan_remove_all_removed(self, mock_get_context,
                                                        mock_configure_worker,
                                                        mock_init_metrics,
                                                        mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()
        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()
        self.model.create_item("ms", "/ms")

        self.manager.create_plan()
        self.model.set_all_applied()

        self.model.get_item("/deployments/d1/clusters/c1/nodes/node1/comp2").set_removed()

        self.manager.plan.set_ready()
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.assertEqual({'success': 'Plan Complete'},
                self.manager.run_plan())
            #self.manager.run_plan()
            self.assertEqual(None, self.model.get_item("/nodes/node1/comp2"))

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_stop_plan(self, mock_get_context,
                            mock_configure_worker,
                            mock_init_metrics,
                            mock_engine_context):

        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__

        self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])

        tasks = [ConfigTask(node_qi, node_qi, "Test Task", "call1",
            call_id="type1")]
        self.create_plugin(tasks,[])
        self.manager.create_plan()
        self.manager._run_plan_start()
        self.manager.stop_plan()
        self.manager._run_all_phases()
        self.manager._run_plan_complete(False)
        self.assertFalse(self.manager.plan.is_running())
        self.assertTrue(self.manager.plan.is_stopped())

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_children_cannot_be_removed(self, mock_get_context,
                                            mock_configure_worker,
                                            mock_init_metrics,
                                            mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        # It is also test against LITPCDS-11798
        self.model.register_item_type(ItemType("something_to_remove"))
        self.model.register_item_type(ItemType("service",
            extend_item="something",
            packages=RefCollection("package"),
            collection=Collection("something_to_remove")
        ))

        pkg = self.model.create_item("package", "/packages/my_service_package")
        srv = self.model.create_item("service","/somethings/my_service", name="srv")
        self.model.create_inherited("/packages/my_service_package",
                "/somethings/my_service/packages/service_package")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        node_srv = self.model.create_inherited("/somethings/my_service",
                "/nodes/node1/something")
        sth_to_remove = self.model.create_item("something_to_remove",
                "/somethings/my_service/collection/my_something_to_remove")
        collection = self.model.query_by_vpath("/somethings/my_service/collection")
        self.model.set_all_applied()

        self.model.remove_item(node_srv.vpath)
        self.model.remove_item(srv.vpath)
        self.model.remove_item(pkg.vpath)

        node_qi = self.qi([mi for mi in self.model.query('node') if not mi.is_ms()][0])
        tasks = [ ConfigTask(
                    node_qi, node_qi.something.packages.service_package,
                    "Package removal task", "package", call_id="foo")]
        self.create_plugin(tasks,[])
        self.manager.create_plan()
        self.manager._run_plan_start()
        self.manager._run_all_phases()
        self.manager._run_plan_complete(False)
        self.assertTrue(node_srv.is_for_removal())
        self.assertTrue(node_srv.packages.service_package.is_for_removal())

        # Items from 'collection' item should be removed, but the 'collection'
        # item itself should stay there if its parent hasn't been removed.
        self.assertEquals([], self.model.query(sth_to_remove.vpath))
        self.assertEquals(collection, self.model.query_by_vpath(collection.vpath))

    def test_invalid_plan(self):
        # 1. create a model
        self._setup_model()
        node_qi = self.api.query('node')[0]

        # 2. now create and add a throwaway plugin
        tasks = [
            ConfigTask(node_qi,
                node_qi,
                "Node Task", "node1", "task1"
                )
        ]
        mock_plugin = self.create_plugin(tasks, [])

        self.assertFalse(self.manager.plan_exists())
        self.manager.create_plan()
        self.assertTrue(self.manager.plan_exists())

        self.manager.model_changed()
        self.assertEqual(self.manager.plan_state(), Plan.INVALID)
        self.assertEqual(self.manager.run_plan(),
                {'error': 'Plan not in initial state'})

    def test_task_unique_id(self):
        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        node2 = self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(node2)

        task1 = ConfigTask(node1, node1, "Test Task", "call1", "type1")
        task2 = ConfigTask(node2, node2, "Test Task", "call1", "type2")
        self.assertEqual("node1__call1__type1", task1.unique_id)
        self.assertEqual("node2__call1__type2", task2.unique_id)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_run_plan_sets_items_to_applied(self, mock_get_context,
                                                mock_configure_worker,
                                                mock_init_metrics,
                                                mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__

        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()
        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()
        self.model.create_item("ms", "/ms")
        self.manager.create_plan()

        self.assertEqual("Initial",
                          self.model.get_item("/deployments/d1/clusters/c1/nodes/node1").get_state())
        self.assertEqual("Initial",
                         self.model.get_item("/deployments/d1/clusters/c1/nodes/node1/comp3").get_state())
        self.assertEqual("Initial",
                         self.model.get_item("/deployments/d1/clusters/c1/nodes/node1/comp2").get_state())
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            #self.manager.plan.valid = True
            self.assertEqual({'success': 'Plan Complete'},
                self.manager.run_plan())

        self.assertEqual("Applied",
                          self.model.get_item("/deployments/d1/clusters/c1/nodes/node1").get_state())
        self.assertEqual("Applied",
                         self.model.get_item("/deployments/d1/clusters/c1/nodes/node1/comp3").get_state())
        self.assertEqual("Applied",
                         self.model.get_item("/deployments/d1/clusters/c1/nodes/node1/comp2").get_state())
        self.assertEqual("Applied", self.model.get_item("/ms").get_state())

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_invalidate_restore_model_does_not_get_called_for_snapshots(self, mock_get_context,
                                                                            mock_configure_worker,
                                                                            mock_init_metrics,
                                                                            mock_engine_context,
                                                                            action):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._node_and_2_tasks(MagicMock(return_value=None))
        node_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node"))
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)

        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager.invalidate_restore_model = Mock()

        self.manager.create_snapshot_plan()
        self.assertTrue(self.manager.is_snapshot_plan)

        self.manager._run_phase = MagicMock(return_value={'error': 'an error'})
        self.manager.run_plan()

        self.assertFalse(self.manager.invalidate_restore_model.called)

        self.manager.create_plan()
        self.assertFalse(self.manager.is_snapshot_plan)
        self.manager.run_plan()

        self.assertTrue(self.manager.invalidate_restore_model.called)

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_set_applied_props_determinable_not_called_for_snapshots(self, mock_get_context,
                                                                        mock_configure_worker,
                                                                        mock_init_metrics,
                                                                        mock_engine_context,
                                                                        action):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._node_and_2_tasks(MagicMock(return_value=None))
        node_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node"))
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)

        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._set_applied_properties_determinable = Mock()

        self.manager.create_snapshot_plan()
        self.assertTrue(self.manager.is_snapshot_plan)
        self.manager._run_phase = MagicMock(return_value={'error': 'an error'})
        self.manager.run_plan()

        self.assertFalse(
            self.manager._set_applied_properties_determinable.called
        )

        self.manager.create_plan()
        self.assertFalse(self.manager.is_snapshot_plan)
        self.manager.run_plan()
        self.assertTrue(
            self.manager._set_applied_properties_determinable.called
        )

    def test_plugin_validation_error(self):
        self.plugin = TestPluginWithValidationError()
        self._add_plugin(self.plugin)

        self.assertEquals(
                [{'message':"item A is invalid",
                    'error': 'ValidationError',
                    'uri': '/nodes/arbitrary/path',}],
                self.manager.create_plan())

    def test_plugin_validation_exception(self):
        self.plugin = TestPluginWithValidationException()
        self._add_plugin(self.plugin)

        self.assertRaises(Exception, self.manager._validate_model)
        expected_result = [{
            'message': 'Model validation failed with: '
                'integer division or modulo by zero',
            'error': 'InternalServerError'
        }]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    def test_plugin_create_configuration_exception(self):
        self.plugin = TestPluginExceptionCreateTasks()
        self._add_plugin(self.plugin)

        expected_result = [{'message': 'See logs for details.',
            'error': 'InternalServerError'}]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    def test_plugin_diverse_callback_args(self):
        self.plugin = TestPluginDiverseCallbackArgTypes()
        self._add_plugin(self.plugin)

        self._setup_model()

        expected_result = [{'message': 'See logs for details.',
            'error': 'InternalServerError'}]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_plan_stopped_by_user(self, mock_get_context,
                                    mock_configure_worker,
                                    mock_init_metrics,
                                    mock_engine_context):
        self._add_plugin(TestPlugin())

        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._setup_model()
        self.manager.create_plan()

        self.run_plan_async()
        #time.sleep(DELAY_TASK_IN_PROGRESS)
        self.manager.stop_plan()

        # The plan will stop at the end of phase 1
        self.assertFalse(self.manager.plan.is_running())
        #time.sleep(DELAY_TASK_COMPLETED)

    def test_stop_plan_without_running(self):

        self._setup_model()

        node_qi = QueryItem(self.model, self.model.query('node')[0])

        task = ConfigTask(node_qi, node_qi, "irrelevant", "call1", "id1")
        self.create_plugin([task],[])
        self.manager.create_plan()

        self.assertEquals(
            {"error": "Plan not currently running"},
            self.manager.stop_plan()
            )

        self.assertFalse(self.manager.plan.is_running())

    def test_stop_plan_with_no_plan(self):
        self.puppet_manager = MockPuppetManager(self.model, "an error")
        self.manager._phase_id = self.mock_phase_id
        self.assertEqual(
            {"error": 'Plan does not exist'},
            self.manager.stop_plan()
            )


        self.plugin = TestPlugin()
        self.plugin2 = TestPlugin2()
        self._add_plugin(self.plugin)
        self._add_plugin(self.plugin2)

        self._setup_model()

        self.manager.create_plan()

        self.assertEqual(
            {"error": "Plan not currently running"},
            self.manager.stop_plan()
            )

        self.manager.plan.run()
        self.assertEqual(
            {"success": "Plan stopping"},
            self.manager.stop_plan()
            )

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_kill_plan(self, mock_get_context,
                            mock_configure_worker,
                            mock_init_metrics,
                            mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._add_plugin(TestPlugin())

        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")
        self.manager.create_plan()

        self.manager.plan.phases[1][0].callback = MagicMock(side_effect=Exception)
        self.manager.plan.phases[1][0].callback.__name__ = "cb"
        self.manager.plan.phases[1][0].callback.im_func.__name__ = ""
        self.manager.plan.phases[1][0].callback.im_class.__name__ = ""

        self.run_plan_async()
        self.manager.kill_plan()

        self.assertFalse(self.manager.plan.is_running())
        self.assertTrue(self.manager.puppet_manager.killed)
        self.assertTrue(self.manager.plan.has_failed())
        self.assertEquals(Plan.FAILED, self.manager.plan.state)

    def test_stop_running_phase_tasks(self):
        t1 = Mock()
        t1.state = constants.TASK_FAILED
        t2 = Mock()
        t2.state = constants.TASK_INITIAL
        t3 = Mock()
        t3.state = constants.TASK_SUCCESS
        t4 = Mock()
        t4.state = constants.TASK_RUNNING
        t5 = Mock()
        t5.state = constants.TASK_STOPPED
        tasks = [t1, t2, t3, t4, t5]
        self.manager._stop_running_phase_tasks(tasks)
        self.assertEqual(t1.state, constants.TASK_FAILED)
        self.assertEqual(t2.state, constants.TASK_INITIAL)
        self.assertEqual(t3.state, constants.TASK_SUCCESS)
        self.assertEqual(t4.state, constants.TASK_STOPPED)
        self.assertEqual(t5.state, constants.TASK_STOPPED)

    def test_kill_plan__running_tasks(self):
        # Mimic service being stopped during running tasks resulting
        # in stopped plan with running tasks (9895)
        self._add_plugin(TestPlugin())

        self._setup_model()

        def mock_plan_stop_and_complete():
            # Call existing plan.stop() implementation and after
            # call run_plan_complete(False) to mimic phase end
            old_plan_stop()
            self.manager._run_plan_complete(False)

        self.manager.create_plan()
        old_plan_stop = self.manager.plan.stop
        self.manager.plan.stop = mock_plan_stop_and_complete

        self.manager._run_plan_start()
        for task in self.manager.plan.phases[0]:
            task.state = constants.TASK_RUNNING

        self.manager.kill_plan()

        self.assertEqual(Plan.STOPPED, self.manager.plan._state)
        self.assertTrue(self.manager.puppet_manager.killed)
        for task in self.manager.plan.phases[0]:
            self.assertEqual(constants.TASK_STOPPED, task.state)

    def test_kill_plan__no_plan_exists(self):
        self.manager._stop_running_phase_tasks = Mock()

        self.assertEquals(None, self.manager.plan)
        self.manager.kill_plan()
        self.assertTrue(self.manager.puppet_manager.killed)
        self.assertFalse(self.manager._stop_running_phase_tasks.called)

    def test_kill_plan__plan_created_not_running(self):
        self._add_plugin(TestPlugin())

        self._setup_model()
        self.manager.create_plan()
        self.manager.kill_plan()

        self.assertFalse(self.manager.plan.is_running())
        self.assertTrue(self.manager.puppet_manager.killed)
        self.assertFalse(self.manager.plan.has_failed())
        self.assertEquals(Plan.INITIAL, self.manager.plan.state)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_kill_plan__successful_plan(self, mock_get_context,
                                            mock_configure_worker,
                                            mock_init_metrics,
                                            mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._add_plugin(TestPlugin())

        self._setup_model()
        self.manager.create_plan()
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.run_plan_async()

        self.manager.kill_plan()

        self.assertFalse(self.manager.plan.is_running())
        self.assertTrue(self.manager.puppet_manager.killed)
        self.assertFalse(self.manager.plan.has_failed())
        self.assertEquals(Plan.SUCCESSFUL, self.manager.plan.state)

    def testPlanStates(self):
        self._add_plugin(TestPlugin())
        self._setup_model()
        self.manager.create_plan()

        self.assertFalse(self.manager.is_plan_running())
        self.assertFalse(self.manager.is_plan_stopping())
        self.assertTrue(self.manager.can_create_plan())

        self.manager.plan.run()

        self.assertTrue(self.manager.is_plan_running())
        self.assertFalse(self.manager.is_plan_stopping())
        self.assertFalse(self.manager.can_create_plan())

        self.manager.plan.stop()

        self.assertFalse(self.manager.is_plan_running())
        self.assertTrue(self.manager.is_plan_stopping())
        self.assertFalse(self.manager.can_create_plan())

    def _tiny_model_and_couple_of_tasks(self):
        # While _setup_model() does create a MS, it's still a pretty tiny model
        self._setup_model()
        node1_qi = self.qi(self.model.query("node")[0])
        t1 = ConfigTask(node1_qi, node1_qi.comp2, "irrelevant", "call1", "id1")
        t2 = ConfigTask(node1_qi, node1_qi.comp2, "irrelevant", "call2", "id2")
        t3 = ConfigTask(node1_qi, node1_qi.comp3, "irrelevant", "call3", "id3")
        t4 = ConfigTask(node1_qi, node1_qi.comp2, "irrelevant", "call4", "id4")
        return t1, t2, t3, t4

    def test_failed_tasks_in_phase(self):
        ts1, tf2, ts3, t4 = self._tiny_model_and_couple_of_tasks()
        ts1.state = ts3.state = constants.TASK_SUCCESS
        tf2.state = constants.TASK_FAILED
        mock_plan = MagicMock()
        mock_plan.get_phase.return_value = [ts1, tf2, ts3]
        self.manager.plan = mock_plan
        mock_plan.find_tasks.return_value = set([tf2])
        self.assertEquals([tf2], list(self.manager._failed_tasks_in_phase(0)))

    def test_update_item_states_best_case(self):
        # no failures
        tasks = [t1, t2, t3, t4] = self._tiny_model_and_couple_of_tasks()
        comp2_qi = self.qi(self.model.query("type_c")[0])
        comp3_qi = self.qi(self.model.query("type_b")[0])
        mock_plan = MagicMock()
        mock_plan.get_tasks.return_value = tasks
        mock_plan.get_phase.return_value = tasks
        self.manager._running_snapshot_phase = Mock(return_value=False)
        self.manager.plan = mock_plan
        mock_plan.find_tasks.return_value = set([t1, t2, t4])
        self.assertEquals("Initial", comp2_qi.get_state())
        self.assertEquals("Initial", comp3_qi.get_state())

        t1.state = constants.TASK_SUCCESS
        self.manager._update_item_states([t1])
        comp2_qi = self.qi(self.model.query_by_vpath(comp2_qi.vpath))
        self.assertEquals("Initial", comp2_qi.get_state())
        self.assertEqual(None, comp2_qi._model_item._previous_state)
        comp3_qi = self.qi(self.model.query_by_vpath(comp3_qi.vpath))
        self.assertEquals("Initial", comp3_qi.get_state())
        self.assertEqual(None, comp3_qi._model_item._previous_state)

        t2.state = t4.state = constants.TASK_SUCCESS
        self.manager._update_item_states([t2, t4])
        comp2_qi = self.qi(self.model.query_by_vpath(comp2_qi.vpath))
        self.assertEquals("Applied", comp2_qi.get_state())
        self.assertEqual(ModelItem.Initial, comp2_qi._model_item._previous_state)
        comp3_qi = self.qi(self.model.query_by_vpath(comp3_qi.vpath))
        self.assertEquals("Initial", comp3_qi.get_state())
        self.assertEqual(None, comp3_qi._model_item._previous_state)

        mock_plan.find_tasks.return_value = set([t3])
        t3.state = constants.TASK_SUCCESS
        self.manager._update_item_states([t3])
        comp2_qi = self.qi(self.model.query_by_vpath(comp2_qi.vpath))
        self.assertEquals("Applied", comp2_qi.get_state())
        self.assertEqual(ModelItem.Initial, comp2_qi._model_item._previous_state)
        comp3_qi = self.qi(self.model.query_by_vpath(comp3_qi.vpath))
        self.assertEquals("Applied", comp3_qi.get_state())
        self.assertEqual(ModelItem.Initial, comp3_qi._model_item._previous_state)

    def test_update_item_states_with_failures(self):
        # oh yes, there are failures
        tasks = [t1, t2, t3, t4] = self._tiny_model_and_couple_of_tasks()
        t1.state = t4.state = constants.TASK_SUCCESS
        t2.state = constants.TASK_FAILED
        comp2_qi = self.qi(self.model.query("type_c")[0])
        comp3_qi = self.qi(self.model.query("type_b")[0])

        mock_plan = MagicMock()
        mock_plan.get_tasks.return_value = tasks
        mock_plan.get_phase.return_value = tasks
        mock_plan.current_phase.return_value = 0
        def find_tasks(**kwargs):
            if kwargs.get('model_item').vpath == comp2_qi.vpath:
                return set([t1, t2, t4])
            elif kwargs.get('model_item').vpath == comp3_qi.vpath:
                return set([t3])
            return set()
        mock_plan.find_tasks.side_effect = find_tasks

        self.manager.plan = mock_plan
        self.assertEquals("Initial", comp2_qi.get_state())
        self.assertEquals("Initial", comp3_qi.get_state())

        self.manager._update_item_states([t1, t2, t4])
        comp2_qi = self.qi(self.model.query_by_vpath(comp2_qi.vpath))
        self.assertEquals("Initial", comp2_qi.get_state())
        self.assertEqual(None, comp2_qi._model_item._previous_state)
        comp3_qi = self.qi(self.model.query_by_vpath(comp3_qi.vpath))
        self.assertEquals("Initial", comp3_qi.get_state())
        self.assertEqual(None, comp3_qi._model_item._previous_state)

        t3.state = constants.TASK_SUCCESS
        self.manager._update_item_states([t3])
        comp2_qi = self.qi(self.model.query_by_vpath(comp2_qi.vpath))
        self.assertEquals("Initial", comp2_qi.get_state())
        self.assertEqual(None, comp2_qi._model_item._previous_state)
        comp3_qi = self.qi(self.model.query_by_vpath(comp3_qi.vpath))
        self.assertEquals("Applied", comp3_qi.get_state())
        self.assertEqual(ModelItem.Initial, comp3_qi._model_item._previous_state)

    def test_update_item_states_for_snapshot_plan(self):
        # snapshot plans should not transition anything but
        # snapshot model items.
        self._setup_model()
        node1_qi = self.qi(self.model.query("node")[0])
        node1_qi._model_item.set_for_removal()
        t1 = Mock()
        t1.state = constants.TASK_SUCCESS
        t1.all_model_items = set([node1_qi])
        t1.requires = set()

        snap_item = self.model.create_item("snapshot-base", "/snapshots/snapshot")
        snap_item.set_for_removal()
        snap_qi = self.qi(self.model.query("snapshot-base")[0])

        snap_plan = Mock(spec=SnapshotPlan)
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)

        t2 = Mock()
        t2.state = constants.TASK_SUCCESS
        t2.all_model_items = set([snap_qi])
        t2.requires = set()

        def find_tasks(**kwargs):
            if kwargs.get('model_item').vpath == node1_qi.vpath:
                return set([t1])
            elif kwargs.get('model_item').vpath == snap_qi.vpath:
                return set([t2])
            return set()
        snap_plan.find_tasks.side_effect = find_tasks

        self.manager.plan = snap_plan
        self.manager._update_item_states([t1, t2])
        self.assertEquals(ModelItem.ForRemoval, node1_qi.get_state())
        self.assertEquals(ModelItem.Initial, node1_qi._model_item._previous_state)
        self.assertEquals(ModelItem.Removed, snap_qi.get_state())
        self.assertEquals(ModelItem.Initial, snap_qi._model_item._previous_state)


    def test_item_applied_when_all_tasks_successful(self):
        tasks = [t1, t2, t3, t4] = self._tiny_model_and_couple_of_tasks()
        comp2 = self.model.query("type_c")[0]
        comp3 = self.model.query("type_b")[0]

        self.manager.plan = mock_plan = MagicMock()
        mock_plan.get_tasks.return_value = tasks
        mock_plan.current_phase.return_value = 0
        mock_plan.get_snapshot_phase.return_value = None
        # 1. first sanity checks
        self.assertEquals('Initial', comp2.get_state())
        self.assertEquals('Initial', comp3.get_state())

        # 2. check item remains initial
        t1.state = t2.state = constants.TASK_SUCCESS
        def find_tasks(**kwargs):
            if kwargs.get('state') == constants.TASK_SUCCESS:
                # find all successful tasks for that model item
                return set([t1, t2])
            else:
                # find any tasks for that model item
                return set([t1, t2, t4])
        mock_plan.find_tasks.side_effect= find_tasks
        self.manager._update_item_states([t1, t2])
        comp2 = self.model.query_by_vpath(comp2.vpath)
        self.assertEquals('Initial', comp2.get_state())

        # 3. check item now applied state
        t4.state = constants.TASK_SUCCESS
        def find_tasks(**kwargs):
            if kwargs.get('state') == constants.TASK_SUCCESS:
                # find all successful tasks for that model item
                return set([t4])
            else:
                # find any tasks for that model item
                return set([t1, t2, t4])
        mock_plan.find_tasks.side_effect= find_tasks
        self.manager._update_item_states([t4])
        comp2 = self.model.query_by_vpath(comp2.vpath)
        self.assertEquals('Applied', comp2.get_state())

    def test_on_puppet_feedback_while_plan_runs(self):
        mock_plan = MagicMock()
        mock_plan.running = True
        mock_plan.current_phase = 0
        mock_plan.timestamp = 0
        self.manager.plan = mock_plan
        self.manager._puppet_report = MagicMock(return_value=None)
        self.manager.on_puppet_feedback([])
        self.manager._puppet_report.assert_has_calls([])

    def test_on_puppet_feedback_raise_exception(self):
        self.model.create_item("node", "/nodes/node1", hostname="node")
        node_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))
        task1 = ConfigTask(node_qi, node_qi, "task", "call1", "id1")
        self.assertRaises(RuntimeError,
                self.manager.on_puppet_feedback, [(task1,'blah')])

    def test_check_callback_tasks_invalid_param(self):
        self.plugin = TestPluginInvalidCallbacks()
        self._add_plugin(self.plugin)

        self._setup_model()

        expected_result = [{'message': 'See logs for details.',
            'error': 'InternalServerError'}]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    def test_check_callback_tasks_invalid_function(self):
        self.plugin = TestPluginInvalidFunctionCallback()
        self._add_plugin(self.plugin)

        self._setup_model()

        expected_result = [{'message': 'See logs for details.',
            'error': 'InternalServerError'}]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    def test_check_callback_tasks_invalid_plugin_class(self):
        self.plugin = TestPluginInvalidMethodCallback()
        self._add_plugin(self.plugin)

        self._setup_model()

        expected_result = [{'message': 'See logs for details.',
            'error': 'InternalServerError'}]
        result = self.manager.create_plan()
        self.assertEquals(expected_result, result)

    def test_sec_creds_empty(self):
        self.assertEqual(None, self.manager._get_security_credentials())

    @patch.object(CallbackApi, 'get_password', return_value=None)
    def test_sec_creds_no_password(self, mock_api):
        plugin = PluginWithCredentials()
        self._add_plugin(plugin)
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            credentials = self.manager._get_security_credentials
            self.assertRaises(NoCredentialsException, credentials)

    def test_sec_creds_password_found(self):
        plugin = PluginWithCredentials()
        self._add_plugin(plugin)
        temp = CallbackApi.get_password
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            mock_cb_api.get_password.return_value = 'password'
            credentials = self.manager._get_security_credentials()
            self.assertEqual(None, credentials)

    @patch.object(CallbackApi, 'get_password', side_effect=Exception)
    def test_corrupted_litp_shadow(self, cb_api):
        plugin = PluginWithCredentials()
        self._add_plugin(plugin)
        self.assertRaises(CorruptedConfFileException,
                          self.manager._get_security_credentials)
        self.assertEqual([{'message': 'Error accessing credentials',
                           'error': 'CredentialsNotFoundError'}],
                         self.manager._has_errors_before_create_plan("")
                         )
    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_uncaught_exception_in_callback(self, mock_get_context,
                                                mock_configure_worker,
                                                mock_init_metrics,
                                                mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._add_plugin(TestPluginUncaughtExceptionCallback())

        self._setup_model()
        self.model.create_item("type_a", "/deployments/d1/clusters/c1/nodes/node1/comp1")

        self.manager.create_plan()

        result = self.run_plan_async()

        self.assertTrue("error" in result)

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_callbackexecution_exception_for_some_reason(self, mock_get_context,
                                                            mock_configure_worker,
                                                            mock_init_metrics,
                                                            mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._add_plugin(TestPluginExceptionCallback())

        self._setup_model()
        self.manager.create_plan()

        result = self.run_plan_async()

        self.assertTrue("error" in result)

    def test_wait_puppet_phase_with_failed_tasks_already(self):

        def racy_wait_for_pp(puppet_phase):
            # Force tasks to be in failed state
            for t in puppet_phase:
                t.state = constants.TASK_FAILED
            result = self.manager._wait_for_puppet_manager2(puppet_phase)
            return result

        self.manager._wait_for_puppet_manager2 = self.manager._wait_for_puppet_manager
        self.manager._wait_for_puppet_manager = racy_wait_for_pp

        self._add_plugin(TestPluginMixedPhase())
        self._setup_model()
        self.model.create_item("ms", "/ms")
        self.model.create_item("something", "/somethings/thingy", name="thingamajig")
        self.model.create_inherited("/somethings/thingy", "/deployments/d1/clusters/c1/nodes/node1/something")
        plan = self.manager.create_plan()

        self.assertEquals(2, len(plan.phases))
        self.assertEquals(1, len(plan.phases[0]))
        self.assertEquals(1, len([t for t in plan.phases[1] if isinstance(t, ConfigTask)]))
        self.assertEquals(1, len([t for t in plan.phases[0] if isinstance(t, CallbackTask)]))

        pp_result = self.manager._run_phase(1)
        self.assertEquals('puppet errors', pp_result['error'])

    def test_callbackexecution_exception_log_message(self):
        self._add_plugin(TestPluginExceptionCallback())

        self._setup_model()
        self.manager.create_plan()

        logger = logging.getLogger()
        logger.level = logging.DEBUG
        sio = StringIO.StringIO()
        stream_handler = logging.StreamHandler(sio)
        logger.addHandler(stream_handler)

        task = None
        for phase in self.manager.plan.phases:
            for _task in phase:
                if _task.model_item.get_vpath() == "/deployments/d1/clusters/c1/nodes/node1/comp2":
                    task = _task
                    break
            else:
                continue
            break

        if not task:
            self.fail("task not found")
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.manager._process_callback_task(task)
            # Assert that the log.error returned is correct
            sio.seek(0)
            log_err_msg = sio.readlines()
            exp_err_msg = ("CallbackExecutionException running task: "
                    "Test Task;"
                    " (Exception message: 'Oh no!')\n")
            self.assertTrue(exp_err_msg in log_err_msg)
            # Assert that the log.info returned is correct
            sio.seek(1)
            log_info_msg = sio.readlines()
            exp_info_msg = ("CallbackExecutionException running task: "
                "<CallbackTask /deployments/d1/clusters/c1/nodes/node1/comp2 - callback_method_exception:"
                "  [Running]>; (Exception message: 'Oh no!')\n")
            self.assertTrue(exp_info_msg in log_info_msg)

    def test_wait_for_puppet_manager_timeout_from_config_file(self):
        """ Make sure timeout and poll values for a puppet phase are taken from
        a config file.

        """
        config.update({"puppet_phase_timeout": 66})
        config.update({"puppet_poll_frequency": 67})
        config.update({"puppet_poll_count": 68})
        mock_puppet_manger = MagicMock()
        mock_task = MagicMock()
        mock_task.has_run.side_effect = lambda: False
        mock_task.state = constants.TASK_SUCCESS
        self.manager.puppet_manager = mock_puppet_manger
        self.manager._wait_for_puppet_manager([mock_task])
        mock_puppet_manger.wait_for_phase.assert_called_once_with(
                [mock_task], timeout=66, poll_freq=67, poll_count=68)

    def test_task_collection_calls_correct_plan(self):
        self._add_plugin(TestPlugin())
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_b", "/nodes/node1/comp3")
        self.manager._create_plugin_tasks = MagicMock()
        self.manager.create_plan()
        self.manager._create_plugin_tasks.assert_has_calls([call('create_configuration')])

    def create_plugin(self, config_tasks=None, snapshot_tasks=None):
        mock_plugin_class = MagicMock()
        mock_plugin_class.__name__ = "MagicMock"
        mock_plugin_class.__module__ = "mock"
        mock_plugin = mock_plugin_class.return_value
        mock_plugin.__class__ = mock_plugin_class
        if config_tasks is not None:
            mock_plugin.create_configuration.return_value = config_tasks
        if snapshot_tasks is not None:
            mock_plugin.create_snapshot_plan.return_value = snapshot_tasks
        mock_plugin.create_lock_tasks.return_value = tuple()
        self._add_plugin(mock_plugin)
        return mock_plugin

    def test_task_collection_calls_correct_snapshot(self):
        _, _, cb_task = self._node_and_2_tasks(TestSnapshotPlugin().callback_method)
        self.create_plugin([], [cb_task])
        self.manager.create_snapshot_plan()
        self.assertTrue(self.manager.is_snapshot_plan)
        self.assertEquals(self.manager.plan._phases[0], [cb_task]),

    def test_create_snapshot_returns_err(self):
        self.manager.snapshot_status = MagicMock(return_value='exists')
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.assertEqual([{'message':
                            'no tasks were generated. No snapshot tasks added '
                            'because Deployment Snapshot with timestamp  exists',
                           'error':
                            'DoNothingPlanError'}],
                         self.manager.create_snapshot_plan())

    def test_empty_plan_combinations(self):
        # create a dummy plugin
        config_tasks=[]
        snapshot_tasks = []
        self.create_plugin(config_tasks, snapshot_tasks)
        # first, empty plan should raise an exception
        self.assertRaises(EmptyPlanException, self.manager._create_plan, 'Deployment')
        self.assertRaises(EmptyPlanException, self.manager._create_plan, 'create_snapshot')
        # non-empty standard tasks works
        _, task, cb_task = self._node_and_2_tasks(TestSnapshotPlugin().callback_method)
        del config_tasks[:]
        del snapshot_tasks[:]
        config_tasks.append(task)
        result = self.manager._create_plan('Deployment')
        self.assertEquals(Plan([[task]], []), result)
        # also with only snapshot task
        del config_tasks[:]
        del snapshot_tasks[:]
        snapshot_tasks.append(cb_task)
        self.assertRaises(EmptyPlanException, self.manager._create_plan, 'Deployment')
        self.assertEquals(Plan([], [cb_task]),
                          self.manager._create_plan('create_snapshot'))

    def test_empty_plan_when_tasks_equal_successful_tasks_in_prev_plan_raise_exception(self):
        config_tasks = []
        snapshot_tasks = []
        self.create_plugin(config_tasks, snapshot_tasks)
        self.model.create_item("node", "/nodes/node1", hostname="node")
        self.model.create_item("type_b", "/nodes/node1/comp3")
        node_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))
        node_child_qi = node_qi.comp3

        task1 = ConfigTask(node_qi, node_qi, "task", "call1", "id1")
        task1.group = deployment_plan_groups.NODE_GROUP
        task1.requires.add(node_child_qi) # query item
        task1_dependency = ConfigTask(node_qi, node_child_qi,
                                      "task", "call2", "id2")
        task1_dependency.group = deployment_plan_groups.NODE_GROUP
        task1.requires.add(task1_dependency)
        config_tasks.append(task1)
        config_tasks.append(task1_dependency)

        old_task1 = ConfigTask(node_qi, node_qi, "task", "call1", "id1")
        old_task1.state = 'Success'
        old_task1.group = deployment_plan_groups.NODE_GROUP
        old_task1_dependency = ConfigTask(node_qi, node_child_qi,
                                          "task", "call2", "id2")
        old_task1_dependency.state = 'Success'
        old_task1_dependency.group = deployment_plan_groups.NODE_GROUP
        old_task1.requires.add(node_child_qi)
        old_task1.requires.add(old_task1_dependency)
        self.manager._get_prev_successful_tasks = Mock(
            return_value=[old_task1])
        self.assertRaises(EmptyPlanException,
                          self.manager._create_plan, 'Deployment')

    def test_empty_plan_when_only_lock_tasks_generated(self):
        # LITPCDS-8553 (part of).
        # Set up a model that will create lock tasks
        self._create_sample_model_for_locking_template(
                       TestPluginLockTasksOnly())

        cluster_qi = self.qi(self.model.query('cluster')[0])
        nodes = cluster_qi.query('node')
        for node in nodes:
            node._model_item.set_applied()
        cluster_qi._model_item.set_applied()

        # Add a plugin that will create one ConfigTask for each node
        config_tasks = []
        snapshot_tasks = []
        self.create_plugin(config_tasks, snapshot_tasks)
        for node in nodes:
            task = ConfigTask(node, node, "task", "call1", "id1")
            task.group = deployment_plan_groups.NODE_GROUP
            config_tasks.append(task)

        # This will create a plan with config tasks and lock tasks.
        plan = self.manager._create_plan('Deployment')

        # For each node, we get three phases with a single task in
        # each - "lock", "call1", "unlock".

        self.assertEquals(9, len(plan.phases))

        for phase in plan.phases:
            self.assertEquals(1, len(phase))

        for i in (0, 3, 6):
            self.assertEquals('lock', plan.phases[i][0].call_type)
            self.assertEquals('call1', plan.phases[i+1][0].call_type)
            self.assertEquals('unlock', plan.phases[i+2][0].call_type)

        # Now - if we tell execution manager that we have already executed
        # all of the config tasks, the next create_plan should raise
        # an exception, despite the existence of lock tasks.

        self.manager._get_prev_successful_tasks = Mock(
            return_value=list(config_tasks))

        self.assertRaises(EmptyPlanException,
                          self.manager._create_plan, 'Deployment')

    def test__get_tasks_to_ignore(self):
        node = QueryItem(self.model, self.model.create_item("node", "/nodes/node1", hostname="node1"))
        item = QueryItem(self.model, self.model.create_item("type_b", "/nodes/node1/comp3"))
        task = ConfigTask(node, item, "", "foo", "bar")
        self.manager.puppet_manager.node_tasks = { node.hostname: [task] }

        item._model_item.state = ModelItem.Initial
        task.state = constants.TASK_SUCCESS
        self.assertTrue(task in self.manager._get_prev_successful_tasks())

        item._model_item.state = ModelItem.ForRemoval
        task.state = constants.TASK_SUCCESS
        self.assertTrue(task in self.manager._get_prev_successful_tasks())

        item._model_item.state = ModelItem.Initial
        task.state = constants.TASK_INITIAL
        self.assertFalse(task in self.manager._get_prev_successful_tasks())

        item._model_item.state = ModelItem.Initial
        task.state = constants.TASK_FAILED
        self.assertFalse(task in self.manager._get_prev_successful_tasks())

        item._model_item.state = ModelItem.ForRemoval
        task.state = constants.TASK_RUNNING
        self.assertFalse(task in self.manager._get_prev_successful_tasks())

        item._model_item.state = ModelItem.Initial
        task.state = constants.TASK_STOPPED
        self.assertFalse(task in self.manager._get_prev_successful_tasks())


    def test_create_plan_for_bootpxe_and_wait_for_node_tasks(self):
        class BootpxePlugin(object):
            def _exec_pxeboot_request(self):
                pass

        class BootmgrPlugin(object):
            def _wait_for_node(self):
                pass
            def _disable_netboot(self):
                pass
            def _remove_from_cobbler(self):
                pass

        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        node1_qi = self.qi(self.model.query("node", hostname="node1")[0])
        node2_qi = self.qi(self.model.query("node", hostname="node2")[0])

        bootpxe_task = CallbackTask(node1_qi, "bootpxe", BootpxePlugin()._exec_pxeboot_request,
                                    tag_name=deployment_plan_tags.BOOT_TAG)
        bootpxe_task.plugin_name = 'bootpxe'
        bootpxe_task.group = deployment_plan_groups.NODE_GROUP

        wait_task = CallbackTask(node1_qi, "bootpxe", BootmgrPlugin()._wait_for_node)
        wait_task.plugin_name = 'bootmgr_plugin'
        wait_task.group = deployment_plan_groups.NODE_GROUP

        netboot_task = CallbackTask(node1_qi, "bootpxe", BootmgrPlugin()._disable_netboot)
        netboot_task.plugin_name = 'bootmgr_plugin'
        netboot_task.group = deployment_plan_groups.NODE_GROUP
        cobbler_task = CallbackTask(node1_qi, "bootpxe", BootmgrPlugin()._remove_from_cobbler)
        cobbler_task.plugin_name = 'bootmgr_plugin'
        cobbler_task.group = deployment_plan_groups.NODE_GROUP

        boot_task_other_node = CallbackTask(node2_qi, "bootpxe", BootmgrPlugin()._wait_for_node)
        boot_task_other_node.plugin_name = 'bootmgr_plugin'
        boot_task_other_node.group = deployment_plan_groups.NODE_GROUP

        self.manager._create_plugin_tasks = Mock(return_value=[wait_task,
                                                               netboot_task,
                                                               bootpxe_task,
                                                               cobbler_task,
                                                               boot_task_other_node])
        self.manager._create_snapshot_tasks = Mock(return_value=[])
        plan = self.manager._create_plan('Deployment')
        self.assertEquals(2, len(plan.phases))
        self.assertEquals(5, len(plan.get_tasks()))
        self.assertTrue(bootpxe_task in plan.phases[0])
        self.assertTrue(boot_task_other_node in plan.phases[0])

        self.assertTrue(wait_task in plan.phases[1])
        self.assertTrue(netboot_task in plan.phases[1])
        self.assertTrue(cobbler_task in plan.phases[1])

    def test_snapshot_task_creation_all_exists(self):
        _, task, _ = self._node_and_2_tasks(MagicMock(return_value=None))
        task.plugin_name = 'Plugin'
        task.group = deployment_plan_groups.NODE_GROUP
        mock_obj = MagicMock(return_value=[task])
        self.manager._create_plugin_tasks = mock_obj
        self.manager._create_removal_tasks = mock_obj
        self.assertFalse(isinstance(self.manager.create_plan(), SnapshotPlan))
        # now it shouldn't create a plan, even if snapshot tasks exist
        empty_mock_obj = MagicMock(return_value=[])
        self.manager._create_plugin_tasks = empty_mock_obj
        self.manager._create_removal_tasks = empty_mock_obj
        # not good to compare the error strings within the list, as they
        # might change
        self.assertEquals(list, type(self.manager.create_plan()))
        # any of cleanup of normal tasks will trigger snapshot tasks
        # Note: 7683 removed automatic snapshot task generation on create_plan
        self.manager._create_plugin_tasks = mock_obj
        self.assertFalse(isinstance(self.manager.create_plan(), SnapshotPlan))

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @patch('litp.core.execution_manager.time.time', return_value=69.96)
    def test_create_update_snapshot_called(self, time,
                                                action,
                                                mock_get_context,
                                                mock_configure_worker,
                                                mock_init_metrics,
                                                mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        task.plugin_name = 'Plugin'
        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager.create_snapshot_plan()
        self.manager._run_phase = MagicMock(return_value={'error': 'an error'})
        self.manager._update_ss_timestamp = MagicMock()
        self.manager.run_plan()
        # called with None (timestamp = ""), error existed
        self.manager._update_ss_timestamp.assert_called_with('')

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    @patch('litp.core.execution_manager.time.time', return_value=69.96)
    def test_create_update_snapshot_called_2(self, time,
                                                mock_get_context,
                                                mock_configure_worker,
                                                mock_init_metrics,
                                                mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        node, _, _ = self._node_and_2_tasks(MagicMock(return_value=None))
        node = self._convert_to_query_item(node)
        self.manager._update_ss_timestamp = MagicMock()
        self.manager._run_phase = MagicMock(return_value=[])
        task = ConfigTask(node, node, "irrelevant2", "call2", "id2")
        task.is_snapshot_task = True
        plan = SnapshotPlan([], [task])
        self.manager._create_plan = MagicMock(return_value=plan)
        self.model.set_snapshot_applied = MagicMock()
        self.model.create_snapshot_item('snapshot')
        self.manager.create_plan()
        self.manager.run_plan()
        self.manager._update_ss_timestamp.assert_called_with(
            str(time.return_value))

    def test_create_snapshot(self):
        self.assertEquals([], self.model.query('snapshot-base'))
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.assertEquals(1, len(self.model.query('snapshot-base')))
        self.assertEquals(None, self.model.query('snapshot-base')[0].timestamp)
        self.manager.model_manager.create_snapshot_item('snapshot')
        # only created once
        self.assertEquals(1, len(self.model.query('snapshot-base')))

    def test_snapshot_states(self):
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.assertEquals('Initial', self.model.query('snapshot-base')[0].get_state())
        self.manager._update_ss_timestamp(None)
        self.assertEquals('Initial', self.model.query('snapshot-base')[0].get_state())

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_snapshot_statues_after_plan(self, mock_get_context,
                                            mock_configure_worker,
                                            mock_init_metrics,
                                            mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__

        _, ctask, task = self._node_and_2_tasks(MagicMock(return_value=None))
        ctask.plugin_name = 'Plugin'
        ctask.group = deployment_plan_groups.NODE_GROUP
        plan = SnapshotPlan([[ctask]], [task])
        task.is_snapshot_task = True
        self.manager._create_plan = MagicMock(return_value=plan)
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.manager.create_plan()
        self.manager._run_phase = MagicMock(return_value={'error': 'an error'})
        self.manager.run_plan()
        self.assertEquals('Initial', self.model.query('snapshot-base')[0].get_state())

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_snapshot_timestamp_after_plan(self, mock_get_context,
                                                mock_configure_worker,
                                                mock_init_metrics,
                                                mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        cb = MagicMock(return_value=None)
        cb.__name__ = ""
        cb.im_func.__name__ = ""
        cb.im_class.__name__ = ""
        _, ctask, task = self._node_and_2_tasks(cb)
        ctask.plugin_name = 'Plugin'
        ctask.group = deployment_plan_groups.NODE_GROUP
        plan = SnapshotPlan([[ctask]], [task])
        task.is_snapshot_task = True
        self.manager._create_plan = MagicMock(return_value=plan)
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.manager.create_plan()
        self.manager._run_phase = MagicMock(return_value={'error': 'an error'})
        plan.snapshot_type = 'create'
        self.manager.run_plan()
        # no previous snapshot, run create and remove and get a failed task
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        plan.snapshot_type = 'remove'
        plan._state = plan.INITIAL
        self.manager.run_plan()
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        # now assume we have a successful snapshot instead
        # remove_snapshot will mark snapshot status failed if any task failed
        self.manager._update_ss_timestamp("1411567963.2958429")
        plan._state = plan.INITIAL
        self.manager.run_plan()
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        # same applies to create_snapshot
        self.manager._update_ss_timestamp("1411567963.2958429")
        plan.snapshot_type = 'create'
        plan._state = plan.INITIAL
        self.manager.run_plan()
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        # but restore_snapshot won't
        self.manager._update_ss_timestamp("1411567963.2958429")
        plan.snapshot_type = 'restore'
        plan._state = plan.INITIAL
        self.manager.run_plan()
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))

    def _node_and_2_tasks(self, cb):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/c1")
        node = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/node",hostname="node")
        node_qi = self.qi(self.model.query('node')[0])
        config_task = ConfigTask(node_qi, node_qi, "irrelevant", "call1", "id1")
        cb_task = CallbackTask(node_qi, 'Snapshot', cb)
        return node, config_task, cb_task

    def test_snapshot_task_needed_no_item(self):
        self.assertEquals([], self.model.query('snapshot-base'))
        self.assertTrue(self.manager._snapshot_tasks_needed('create_snapshot'))

    def test_snapshot_task_needed_no_timestamp(self):
        # we assume the snapshot plan failed for a reason
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp='')
        self.assertFalse(self.manager._snapshot_tasks_needed('create_snapshot'))
        # plan not started yet
        self.manager._update_ss_timestamp(None)
        self.assertTrue(self.manager._snapshot_tasks_needed('create_snapshot'))

    def test_snapshot_task_needed_timestamp(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.assertFalse(self.manager._snapshot_tasks_needed('create_snapshot'))

    @patch('litp.core.execution_manager.time.time')
    def test_update_ss_timestamp_values(self, mock_time):
        mock_time.return_value = 69.69
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=str(time.time()))
        mock_time.return_value = 70.0
        self.assertFalse(self.manager._snapshot_tasks_needed('create_snapshot'))
        self.manager._update_ss_timestamp(str(mock_time()))
        self.assertEquals("70.0", self.model.query('snapshot-base')[0].timestamp)
        mock_time.return_value = 69.68
        self.assertFalse(self.manager._snapshot_tasks_needed('create_snapshot'))

    def test_snapshot_status_no_snapshot(self):
        self.assertEquals([], self.model.query('snapshot-base'))
        self.assertEquals('no_snapshot', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_plan_and_failure(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        self.manager._snapshot_tasks_failure = MagicMock(return_value=True)
        self.manager.plan = MagicMock()
        self.manager.plan.is_active.return_value = False
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_plan_failed_plan_successful_snapshot(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        self.manager._snapshot_tasks_failure = MagicMock(return_value=False)
        self.manager.plan = MagicMock()
        self.manager.plan.__class__ = SnapshotPlan
        self.manager.plan.is_active.return_value = False
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_with_timestamp(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.manager.plan_has_tasks = MagicMock(return_value=False)
        # weird to have no tasks but snapshot tasks have failed. Anyways...
        self.manager._snapshot_tasks_failure = MagicMock(return_value=True)
        self.assertEquals('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.manager._snapshot_tasks_failure = MagicMock(return_value=False)
        self.assertEquals('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        # this other situation would make more sense
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        self.manager.plan = MagicMock(autospec=True)
        self.manager.plan.__class__ = SnapshotPlan
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_no_timestamp(self):
        # failed snapshot
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp='')
        self.manager.plan_has_tasks = MagicMock(return_value=False)
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        # the plan didn't start running yet
        self.manager._update_ss_timestamp(None)
        self.assertEquals('not_started_yet', self.manager.snapshot_status('snapshot'))
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        mock_plan = MagicMock()
        mock_plan.is_active.return_value = True
        self.manager.plan = mock_plan
        self.manager._update_ss_timestamp('')
        self.manager._snapshot_tasks_failure = MagicMock(return_value=False)
        # but if the plan exists and we still don't know if snapshot tasks failed, then it is in progress
        self.assertEquals('in_progress', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_with_failed_restore(self):
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        mock_plan = MagicMock(autospec=True)
        mock_plan.__class__ = SnapshotPlan
        mock_plan.is_active.return_value = True
        mock_plan.snapshot_type = 'restore'
        self.manager.plan = mock_plan
        self.manager._snapshot_tasks_failure = MagicMock(return_value=True)
        # a failure in a restore plan does not make the snapshot failed
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))
        mock_plan.is_active.return_value = False
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))
        # but it does for create|remove
        mock_plan.snapshot_type = 'create'
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))
        mock_plan.snapshot_type = 'remove'
        self.assertEquals('failed', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_plan_previous_plan(self):
        # check what it returns if a snapshot exists and
        # either a plan with snapshots exists or not
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.assertEquals('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        self.manager.plan = MagicMock(autospec=True)
        self.assertEquals('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.manager.plan.__class__ = SnapshotPlan
        self.assertEquals('exists', self.manager.snapshot_status('snapshot'))
        self.manager.plan.is_snapshot_plan = False
        self.manager.plan_has_tasks.return_value = False
        self.assertEquals('exists_previous_plan', self.manager.snapshot_status('snapshot'))

    def test_snapshot_status_several_snapshots(self):
        # create_snapshot -> suceeds
        # create_snapshot -n backup -> fails
        # status for the first one should be exists_previous_plan
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp=time.time())
        self.model.set_snapshot_applied('snapshot')
        self.model.get_item('/snapshots/snapshot').delete_property('active')
        self.assertEqual(None, self.model.get_item('/snapshots/snapshot').active)
        self.model.create_item("snapshot-base", "/snapshots/backup", timestamp='')
        self.manager.plan_has_tasks = MagicMock(return_value=True)
        self.manager.plan = MagicMock(autospec=True)
        self.manager.plan.__class__ = SnapshotPlan
        self.manager.plan.is_active.return_value = False
        self.manager._snapshot_tasks_failure = MagicMock(return_value=True)
        # plqn finished and snapshot phase failed
        self.assertEqual('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.assertEqual('failed', self.manager.snapshot_status('backup'))
        # plan is ongoing
        self.manager.plan.is_active.return_value = True
        self.assertEqual('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.assertEqual('in_progress', self.manager.snapshot_status('backup'))
        # plan finished and snapshot phase was ok
        self.manager.plan.is_active.return_value = False
        self.manager._snapshot_tasks_failure = MagicMock(return_value=False)
        self.model.get_item('/snapshots/backup').set_property('timestamp', str(time.time()))
        self.assertEqual('exists_previous_plan', self.manager.snapshot_status('snapshot'))
        self.assertEqual('exists', self.manager.snapshot_status('backup'))

    def test_snapshot_tasks_failure(self):
        fn = MagicMock(return_value=None)
        fn.__name__ = "cb"
        fn.im_func.__name__ = ""
        fn.im_class.__name__ = ""
        _, standard_task, snapshot_task = self._node_and_2_tasks(fn)
        standard_task.plugin_name = 'Plugin'
        standard_task.group =deployment_plan_groups.NODE_GROUP
        plan = SnapshotPlan([[standard_task]], [snapshot_task])
        snapshot_task.is_snapshot_task = True
        self.manager._create_plan = MagicMock(return_value=plan)
        self.manager.create_plan()
        self.manager._failed_tasks_in_phase = MagicMock(return_value=[])
        self.assertFalse(self.manager._snapshot_tasks_failure())
        snapshot_task.state = constants.TASK_FAILED
        self.assertTrue(self.manager._snapshot_tasks_failure())

    def test_empty_plan_err(self):
        # without snapshot
        msg = 'no tasks were generated'
        self.assertEquals(msg, self.manager._get_empty_plan_err('Deployment'))
        self.assertEquals(msg, self.manager._get_empty_plan_err('snapshot'))
        # now create snapshot
        self.model.create_item("snapshot-base", "/snapshots/snapshot", timestamp='')
        self.assertEquals(msg + '. No snapshot tasks added because failed Deployment Snapshot exists',
                          self.manager._get_empty_plan_err('snapshot'))
        self.assertEquals(msg, self.manager._get_empty_plan_err('Deployment'))
        # and put a timestamp
        mock_ts = MagicMock(return_value=69.69)
        with patch('time.time', mock_ts):
            self.manager._update_ss_timestamp(str(time.time()))
            self.assertEquals(msg + \
                '. No snapshot tasks added because Deployment Snapshot with timestamp %s exists' \
                % datetime.fromtimestamp(time.time()).ctime(),
                          self.manager._get_empty_plan_err('snapshot'))
            self.assertEquals(msg, self.manager._get_empty_plan_err('Deployment'))

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_items_not_applied_after_snapshot_plan(self, mock_get_context,
                                                        mock_configure_worker,
                                                        mock_init_metrics,
                                                        mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        node, item1, item2 = self._setup_model()
        node_qi = self.qi(node)
        self.assertFalse(item1.is_applied())
        self.assertFalse(item2.is_applied())
        # setup plugin
        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_snapshot_plan(self, plugin_api_context):
                return [CallbackTask(node_qi, 'Snapshot', plugin.callback)]
        plugin = DummyPlugin()
        self._add_plugin(plugin)
        # now create and run plan
        self.model.create_snapshot_item('snapshot')
        self.manager.create_plan('create_snapshot')
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.manager.run_plan()
        self.assertFalse(item1.is_applied())
        self.assertFalse(item2.is_applied())

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_items_applied_after_snapshot_plan(self, mock_get_context,
                                                    mock_configure_worker,
                                                    mock_init_metrics,
                                                    mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        _, item1, item2 = self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])
        # setup plugin
        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_configuration(self, plugin_api_context):
                return [ ConfigTask(node_qi, node_qi, "irrelevant", "call1", "id1") ]
            def create_snapshot_plan(self, plugin_api_context):
                return [CallbackTask(node_qi, 'Snapshot', plugin.callback)]
        plugin = DummyPlugin()
        self._add_plugin(plugin)
        # now create and run plan
        self.manager.create_plan('Deployment')
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.manager.run_plan()
        # finally check states
        item1 = self.model.get_item(item1.vpath)
        self.assertTrue(item1.is_applied())
        item2 = self.model.get_item(item2.vpath)
        self.assertTrue(item2.is_applied())

    def test_unlock_task_not_generated_in_snapshot_plan(self):
        node, item1, item2 = self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])
        # lock node, to create unlock task
        node.set_property('is_locked', "true")
        # setup dummy plugin with locking tasks
        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_configuration(self, plugin_api_context):
                return [ ConfigTask(node_qi, node_qi, "irrelevant", "call1", "id1") ]
            def create_snapshot_plan(self, plugin_api_context):
                return [CallbackTask(node_qi, 'Snapshot', self.callback)]
            def create_lock_tasks(self, api, node):
                return (CallbackTask(node, "Lock node %s" % node.item_id, self.cb_lock_unlock),
                        CallbackTask(node, "Unlock node %s" % node.item_id, self.cb_unlock_failed),
                )
            def cb_lock_unlock(self):
                pass

            def cb_unlock_failed(self):
                raise CallbackExecutionException("Failed deliberately")

        plugin = DummyPlugin()
        self._add_plugin(plugin)

        # Test litp_create_plan
        self.manager.create_plan('Deployment')
        self.assertEqual(self.manager.plan.phases[0][0].description, 'Unlock node node1')

        # Test litp_create_snapshot
        self.manager.create_plan('create_snapshot')

        self.assertEqual(self.manager.plan.phases[0][0].description, 'Snapshot')
        self.assertEqual(1, len(self.manager.plan.phases))

        # Test litp remove_snapshot
        with patch_method(self.manager, 'snapshot_status', lambda x: 'failed'):
            # Test litp remove_snapshot
            self.manager.create_plan('remove_snapshot')
            self.assertEqual(self.manager.plan.phases[0][0].description,
                             'Snapshot')
            self.assertEqual(1, len(self.manager.plan.phases))

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_future_property_value_updatable_plugin(self, mock_get_context,
                                                        mock_configure_worker,
                                                        mock_init_metrics,
                                                        mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        node, item1, item2 = self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])
        future_property_value = FuturePropertyValue(node_qi, "name")
        future_property_view = FuturePropertyValue(node_qi, "future_view")
        # Create a dummy plugin with a callback task which updates the 'name'
        # property before a config task using the future property is executed.
        class DummyPlugin(Plugin):
            def update_prop_cb(self, callback_api, *args):
                callback_api.query("node")[0].name = "UpdatedName"
                callback_api.query("node")[0].another_property = "UpdatedAnotherProperty"
            def create_configuration(self, plugin_api_context):
                update_prop_task = CallbackTask(node_qi, 'Snapshot', self.update_prop_cb)
                use_update_prop_task = ConfigTask(node_qi, node_qi, "Future Property Task", "call1", "id1",
                            name=future_property_value, another_property=node_qi.another_property, future_view=future_property_view)
                use_update_prop_task.requires.add(update_prop_task)
                return [update_prop_task, use_update_prop_task]
        plugin = DummyPlugin()
        self._add_plugin(plugin)
        # now create and run plan
        self.manager.create_plan('Deployment')

        self.assertEqual(self.manager.plan.phases[1][0].model_item.name, "OriginalName")
        self.assertEqual(self.manager.plan.phases[1][0].model_item.future_view, "<prefix>OriginalName<suffix>")
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.manager.run_plan()
        # Assert updated FutureValueProperty was used in plan
        self.assertEqual(self.manager.plan.phases[1][0].kwargs["name"], "UpdatedName")
        # Assert that without the use of FuturePropertyValue, the original value is used in the plan
        self.assertEqual(self.manager.plan.phases[1][0].kwargs["another_property"], "OriginalAnotherProperty")
        self.assertEqual(node_qi.another_property, "UpdatedAnotherProperty")
        # Assert that a FuturePropertyValue that is a View behaves correctly
        self.assertEqual(node_qi.future_view, "<prefix>UpdatedName<suffix>")

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_future_property_value_list_and_dict(self, mock_get_context,
                                                    mock_configure_worker,
                                                    mock_init_metrics,
                                                    mock_engine_context):
        mock_get_context.return_value = ExecutionManagerTest.worker_context.__func__
        node, item1, item2 = self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])
        future_property_value = FuturePropertyValue(node_qi, "name")
        future_value_list = [future_property_value, 'test']
        future_value_dict = {'normal':'string', 'test':future_property_value}
        future_value_nested = {'normal':'string', 'test':future_value_list, 'test2':future_value_dict}
        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                callback_api.query("node")[0].name = "NewName"
            def create_configuration(self, plugin_api_context):
                cb_task = CallbackTask(node_qi, 'Snapshot', self.callback)
                cf_task = ConfigTask(node_qi, node_qi, "Future Property Task", "call1", "id1",
                    test_nested=future_value_nested)
                cf_task.requires.add(cb_task)
                return [cb_task, cf_task]
        plugin = DummyPlugin()
        self._add_plugin(plugin)
        # now create and run plan
        self.manager.create_plan('Deployment')
        with patch('litp.core.base_plugin_api._SecurityApi') as mock_cb_api:
            mock_cb_api._get_keyset_and_passwd.return_value = 'ola', 'kease'
            self.manager.run_plan()
        self.assertEqual(self.manager.plan.phases[1][0].kwargs["test_nested"],
            {'normal':'string', 'test':["NewName", 'test'],
                'test2':{'normal':'string', 'test':'NewName'}})

    def test_future_property_value_not_updatable_plugin(self):
        self._setup_model()
        node_qi = self.model.query('node')[0]
        future_property_value = FuturePropertyValue(node_qi, "hostname")
        class DummyPlugin(Plugin):
            def callback(self, callback_api, *args):
                pass
            def create_configuration(self, plugin_api_context):
                return [ ConfigTask(node_qi, node_qi, "Future Property Task", "call1", "id1",
                    hostname=future_property_value)]
            def create_snapshot_plan(self, plugin_api_context):
                return [CallbackTask(node_qi, 'Snapshot', self.callback)]
        plugin = DummyPlugin()
        self._add_plugin(plugin)
        # Assert that create a plan returns an error, as FuturePropertyValue requires the Propety
        # to be updatable_plugin=True for it to work
        self.assertEqual([{'message': 'See logs for details.', 'error': 'InternalServerError'}],
                self.manager.create_plan('Deployment'))

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', return_value='snapshot')
    @patch('litp.core.rpc_commands.PuppetMcoProcessor.enable_puppet', return_value=None)
    def test_snapshot_task_failure_sets_timestamp_to_empty_string(self, action, name, mco_processor):
        task = Mock()
        task.callback.side_effect = CallbackExecutionException
        task._callback_name = 'test_callback'
        task.all_model_items = set()

        plan = MagicMock()
        plan.__class__ = SnapshotPlan

        plan.phases = [[task]]
        plan.is_stopping.return_value = False
        plan.get_phase.return_value = [task]

        model_manager = Mock()
        model_manager.get_all_nodes.return_value = []
        snapshot_item = model_manager.get_item.return_value
        snapshot_item.vpath = '/snapshots/snapshot'

        puppet_manager = Mock()
        puppet_manager.node_tasks.keys = lambda: ["a", "b"]

        self.manager = ExecutionManager(
            model_manager, puppet_manager, MagicMock())
        self.manager.plan = plan

        def extract_tasks(phase, task_type):
            if task_type is CallbackTask:
                return [task]
            return []
        plan.filter_tasks = Mock(side_effect=extract_tasks)

        self.manager.current_snapshot_object = MagicMock(return_value=snapshot_item)
        self.model.create_snapshot_item('snapshot')
        self.manager._run_plan_phase(0)
        model_manager.get_item.assert_called_with("/snapshots/snapshot")
        snapshot_item.set_property.assert_called_with('timestamp', '')

    def _create_sample_model_for_locking_template(self, plugin):
        self._add_plugin(plugin)

        self.model.create_item("node", "/ms")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("something", "/somethings/something1",
                name="something1")
        self.model.create_item("something", "/somethings/something2",
                name="something2")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1",
                ha_manager="cmw")
        self.model.create_item("node", "/deployments/d1/clusters/cluster1/nodes/node1",
                hostname="node1")
        self.model.create_item("node", "/deployments/d1/clusters/cluster1/nodes/node2",
                hostname="node2")
        self.model.create_item("node", "/deployments/d1/clusters/cluster1/nodes/node3",
                hostname="node3")
        self.model.create_item("type_a",
                "/deployments/d1/clusters/cluster1/nodes/node1/comp1")
        self.model.create_item("type_b",
                "/deployments/d1/clusters/cluster1/nodes/node2/comp2")
        self.model.create_item("type_b",
                "/deployments/d1/clusters/cluster1/nodes/node3/comp3")
        self.model.create_inherited("/somethings/something1",
                "/deployments/d1/clusters/cluster1/nodes/node1/something")
        self.model.create_inherited("/somethings/something2",
                "/deployments/d1/clusters/cluster1/nodes/node2/something")

    def _create_sample_model_for_locking(self):
        self._create_sample_model_for_locking_template(
               TestPluginRemoteExecutionTasks())

    def _create_sample_model_for_locking_no_lock_tasks(self):
        self._create_sample_model_for_locking_template(
                TestPluginRemoteExecutionTasksNoLocking())

    def _create_sample_model_for_locking_many_tasks(self):
        self._create_sample_model_for_locking_template(
                TestPluginRemoteExecutionTasksManyTasks())

    def _create_sample_model_for_duplicated_config_tasks_validation(self):
        plugin = TestPluginWithDuplicatedConfigTasks()
        self._create_sample_model_for_locking_template(plugin)
        return plugin

    def _create_sample_model_for_duplicated_non_config_tasks_validation(self):
        plugin = TestPluginWithDuplicatedNonConfigTasks()
        self._create_sample_model_for_locking_template(plugin)
        return plugin

    def test_create_lock_tasks(self):
        # self._create_sample_model_for_locking_no_lock_tasks()
        self._create_sample_model_for_locking()
        cluster_qi = self.qi(self.model.query('cluster')[0])
        node_qis = cluster_qi.query('node')

        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals({}, lock_tasks)
        self.assertEquals(1, len(tasks))

        node_qis[0]._model_item.set_applied()
        node_qis[1]._model_item.set_applied()
        cluster_qi._model_item.set_applied()
        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals(2, len(lock_tasks))

    def test_create_many_lock_tasks_for_same_node(self):
        self._create_sample_model_for_locking()
        self._add_plugin(TestPluginLockTasksOnly())
        cluster_qi = self.qi(self.model.query('cluster')[0])
        node_qis = cluster_qi.query('node')

        self.manager._create_plugin_tasks('create_configuration')
        node_qis[0]._model_item.set_applied()
        node_qis[1]._model_item.set_applied()
        cluster_qi._model_item.set_applied()
        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        self.assertRaises(NodeLockException,
                          lock_task_creator.create_lock_tasks)

    def test_create_lock_tasks_variety_of_tasks(self):
        self._create_sample_model_for_locking_many_tasks()
        cluster_qi = self.qi(self.model.query('cluster')[0])
        node_qis = cluster_qi.query('node')

        tasks = self.manager._create_plugin_tasks('create_configuration')
        tasks = self.manager._rewrite_ordered_task_lists(tasks)
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals({}, lock_tasks)

        node_qis[0]._model_item.set_applied()
        node_qis[1]._model_item.set_applied()
        cluster_qi._model_item.set_applied()
        tasks = self.manager._create_plugin_tasks('create_configuration')
        tasks = self.manager._rewrite_ordered_task_lists(tasks)
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals(2, len(lock_tasks))
        self.assertNotEquals({}, lock_tasks)
        self.assertEquals(lock_tasks.values()[0][0].lock_type, Task.TYPE_LOCK)
        self.assertEquals(lock_tasks.values()[0][1].lock_type, Task.TYPE_UNLOCK)
        self.assertTrue(node_qis[0].get_vpath() in lock_tasks)
        self.assertTrue(node_qis[1].get_vpath() in lock_tasks)

    def test_create_lock_tasks_no_lock_tasks_from_plugin(self):
        self._create_sample_model_for_locking_no_lock_tasks()
        # self._create_sample_model_for_locking()
        node_qis = self.api.query('node')

        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals({}, lock_tasks)
        self.assertEquals(1, len(tasks))

        node_qis[0]._model_item.set_applied()
        node_qis[1]._model_item.set_applied()
        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals({}, lock_tasks)
        self.assertEquals(1, len(tasks))
        self.assertEquals(set(node_qis), tasks[0].nodes)  # Task 1

    def test_create_lock_tasks_if_cluster_initial(self):
        self._create_sample_model_for_locking()
        cluster_qi = self.qi(self.model.query('cluster')[0])
        node_qis = cluster_qi.query('node')
        for node_qi in node_qis:
            node_qi._model_item.set_applied()
        cluster_qi._model_item.set_initial()

        tasks = self.manager._create_plugin_tasks('create_configuration')
        lock_task_creator = LockTaskCreator(
            self.manager.model_manager,
            self.manager.plugin_manager,
            PluginApiContext(self.manager.model_manager),
            self.manager._get_nodes_to_be_locked(tasks))
        lock_tasks = lock_task_creator.create_lock_tasks()
        self.assertEquals({}, lock_tasks)


    def test__check_duplicated_config_tasks(self):
        plugin = self._create_sample_model_for_duplicated_config_tasks_validation()
        tasks = plugin.create_configuration(
                PluginApiContext(self.manager.model_manager))

        self.assertRaises(NonUniqueTaskException,
                self.manager._check_duplicated_tasks, plugin, tasks)

    def test__check_duplicated_non_config_tasks(self):
        plugin = self._create_sample_model_for_duplicated_non_config_tasks_validation()
        tasks = plugin.create_configuration(
                PluginApiContext(self.manager.model_manager))

        try:
            self.manager._check_duplicated_tasks(plugin, tasks)
        except PluginError as e:
            self.fail(str(e))

    def test_delete_snapshot_plan(self):
        self.manager.snapshot_status = MagicMock(return_value='exists')
        self.model.create_snapshot_item('snapshot')
        result = self.manager.restore_snapshot_plan()
        self.assertTrue(constants.DO_NOTHING_PLAN_ERROR, result[0]["error"])
        snapshot_qi = self.qi(self.model.get_item('/snapshots/snapshot'))
        task1 = CallbackTask(snapshot_qi, "", None)
        task2 = CallbackTask(snapshot_qi, "", None)
        self.manager.snapshot_status = MagicMock(return_value='exists')
        self.manager._create_plugin_tasks = MagicMock(return_value=
                                                [task1, task2])
        result = self.manager.restore_snapshot_plan()
        self.assertTrue(isinstance(result, SnapshotPlan))
        self.assertTrue("initial", result.state)
        self.assertTrue(2, len(result._tasks))

        self.manager.snapshot_status = MagicMock(
                                    return_value='exists_previous_plan')
        result = self.manager.restore_snapshot_plan()
        self.assertTrue(isinstance(result, SnapshotPlan))
        self.assertTrue("initial", result.state)
        self.assertTrue(2, len(result._tasks))

    def test_validate_callback_method(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        node = self.model.query('node')[0]
        node_qi = self.qi(node)

        plugin = TestPlugin()
        self._add_plugin(plugin)

        task = CallbackTask(node_qi, "", plugin.callback_method)
        self.manager._validate_tasks(plugin, [task])

        task = CallbackTask(node_qi, "", self.test_validate_callback_method)
        self.assertRaises(TaskValidationException, self.manager._validate_tasks, plugin, [task])

    def test_check_task_requires_datatype(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms = self.model.query_by_vpath("/ms")
        ms_qi = self.qi(ms)

        plugin = TestPlugin()

        task1 = CallbackTask(ms_qi, "", None)
        task2 = CallbackTask(ms_qi, "", None)
        task3 = CallbackTask(ms_qi, "", None)
        task_list = OrderedTaskList(ms, [task2])
        tasks = [task1, task_list, task3]

        task1.requires.add("")
        task2.requires.clear()
        task3.requires.clear()
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

        task1.requires.clear()
        task2.requires.add("")
        task3.requires.clear()
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

        task1.requires.clear()
        task2.requires.clear()
        task3.requires.add("")
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

    def test_check_task_replaces_datatype(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms = self.qi(self.model.query_by_vpath("/ms"))

        plugin = TestPlugin()

        task1 = ConfigTask(ms, ms, "", "foo1", "bar1")
        task2 = ConfigTask(ms, ms, "", "foo2", "bar2")
        task3 = ConfigTask(ms, ms, "", "foo3", "bar3")
        task_list = OrderedTaskList(ms, [task2])
        tasks = [task1, task_list, task3]

        task1.replaces.add("")
        task2.replaces.clear()
        task3.replaces.clear()
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

        task1.replaces.clear()
        task2.replaces.add("")
        task3.replaces.clear()
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

        task1.replaces.clear()
        task2.replaces.clear()
        task3.replaces.add("")
        self.assertRaises(TaskValidationException,
            self.manager._check_task_attributes_datatype, plugin, tasks)

    def test_check_task_replaces_itself_same_plan(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms = self.qi(self.model.query_by_vpath("/ms"))

        task1 = ConfigTask(ms, ms, "", "foo1", "bar1")
        task1.replaces.add(("foo1", "bar1"))
        tasks = [task1]
        try:
            self.manager._validate_task_replaces(tasks)
        except TaskValidationException:
            self.fail()

    def test_check_task_replaces_other_task_same_plan(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms = self.qi(self.model.query_by_vpath("/ms"))

        task1 = ConfigTask(ms, ms, "", "foo1", "bar1")
        task2 = ConfigTask(ms, ms, "", "foo2", "bar2")
        task2.replaces.add(("foo1", "bar1"))
        tasks = [task1, task2]

        self.assertRaises(TaskValidationException,
            self.manager._validate_task_replaces, tasks)

    def test_check_multiple_tasks_replaces_one(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms = self.qi(self.model.query_by_vpath("/ms"))

        task1 = ConfigTask(ms, ms, "", "foo1", "bar1")
        task1.replaces.add(("foo", "bar"))
        task2 = ConfigTask(ms, ms, "", "foo2", "bar2")
        task2.replaces.add(("foo", "bar"))
        tasks = [task1, task2]

        self.assertRaises(TaskValidationException,
            self.manager._validate_task_replaces, tasks)

    def test_get_task_node(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        self.model.create_item("type_a", "/nodes/node1/comp1")

        node1_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))
        node2_qi = self.qi(self.model.query_by_vpath("/nodes/node2"))

        task = ConfigTask(node1_qi, node1_qi.comp1, "", "1", "2")
        task_node = self.manager._get_task_node(task)
        self.assertEquals(task_node._model_item, node1_qi._model_item)

        task = CallbackTask(node1_qi.comp1, "", None)
        task_node = self.manager._get_task_node(task)
        self.assertEquals(task_node._model_item, node1_qi._model_item)

        node_collection = self.qi(self.model.query_by_vpath("/nodes"))
        task = RemoteExecutionTask([node1_qi], node_collection, "", "agent", "action")
        task_node = self.manager._get_task_node(task)
        self.assertEquals(task_node._model_item, node1_qi._model_item)

        task = RemoteExecutionTask([node1_qi, node2_qi], node_collection, "", "agent", "action")
        self.assertRaises(ValueError, self.manager._get_task_node, task)

        self.assertRaises(ValueError, self.manager._get_task_node, "")

    def test_setup_task_group(self):
        # If a task matches many groups, the assigned group should be the one
        # appearing first in the list
        task = Mock(tag_name=None)
        ruleset = [{'group_name': 'A-TEAM'}, {'group_name': 'B-TEAM'}]
        with nested(
                patch('litp.core.execution_manager.DEPLOYMENT_PLAN_RULESET', ruleset),
                patch('litp.core.execution_manager.ExecutionManager._task_matches_criteria', return_value=True)):
            self.manager._setup_task_group(task)
            self.assertEquals(task.group, 'A-TEAM')

        # If the task does not match any group, the unmatched group is
        # assigned to the task
        task = Mock(tag_name=None, group=None)
        ruleset = [{'group_name': 'A-TEAM'},
                   {'group_name': 'B-TEAM'}]
        with nested(
                patch('litp.core.execution_manager.ExecutionManager._task_matches_criteria', return_value=False),
                patch('litp.core.execution_manager.ExecutionManager.unmatched_group_name', return_value='D-TEAM'),
                patch('litp.core.execution_manager.DEPLOYMENT_PLAN_RULESET', ruleset))\
             as (task_matches_criteria, unmatched_group_name, ruleset):
                self.manager._setup_task_group(task)
                self.assertEquals(task.group, 'D-TEAM')
                unmatched_group_name.assert_called_once()

    def test_setup_task_group_with_task_tag_name(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        self.model.create_item("type_a", "/ms/comp1")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        ms = self.qi(self.model.query_by_vpath("/ms"))
        node1 = self.qi(self.model.query_by_vpath("/nodes/node1"))
        cluster1 = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/cluster1"))
        somethings = self.qi(self.model.query_by_vpath("/somethings"))

        # Tag name does not exist in the deployment plan ruleset
        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        task.tag_name = "dummy_tag_name"
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = ConfigTask(node1, node1.comp1, "", "call_type1", "call_id1_1")
        task.tag_name = "dummy_tag_name"
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = CallbackTask(node1.comp1, "", None)
        task.tag_name = "dummy_tag_name"
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        # MS_TAG is MS_GROUP tag name
        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        task.tag_name = deployment_plan_tags.MS_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = ConfigTask(ms, ms.comp1, "", "1", "1_1")
        task.tag_name = deployment_plan_tags.MS_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = CallbackTask(ms.comp1, "", None)
        task.tag_name = deployment_plan_tags.MS_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        # BOOT_TAG is BOOT_GROUP tag name
        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        task.tag_name = deployment_plan_tags.BOOT_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.BOOT_GROUP, task.group)

        task = ConfigTask(node1, node1.comp1, "", "1", "1_1")
        task.tag_name = deployment_plan_tags.BOOT_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.BOOT_GROUP, task.group)

        task = CallbackTask(node1.comp1, "", None)
        task.tag_name = deployment_plan_tags.BOOT_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.BOOT_GROUP, task.group)

        # NODE_TAG is NODE_GROUP tag name
        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        task.tag_name = deployment_plan_tags.NODE_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        task = ConfigTask(node1, node1.comp1, "", "1", "1_1")
        task.tag_name = deployment_plan_tags.NODE_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        task = CallbackTask(node1.comp1, "", None)
        task.tag_name = deployment_plan_tags.NODE_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        # CLUSTER_TAG is CLUSTER_GROUP tag name
        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        task.tag_name = deployment_plan_tags.CLUSTER_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.CLUSTER_GROUP, task.group)

        task = ConfigTask(node1, node1.comp1, "", "1", "1_1")
        task.tag_name = deployment_plan_tags.CLUSTER_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.CLUSTER_GROUP, task.group)

        task = CallbackTask(cluster1, "", None)
        task.tag_name = deployment_plan_tags.CLUSTER_TAG
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.CLUSTER_GROUP, task.group)

    def test_setup_task_group_with_no_task_tag_name(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        self.model.create_item("type_a", "/ms/comp1")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        ms = self.api.query_by_vpath("/ms")
        node1 = self.api.query_by_vpath("/nodes/node1")
        cluster1= self.api.query_by_vpath("/deployments/d1/clusters/cluster1")
        somethings = self.api.query_by_vpath("/somethings")

        task = ConfigTask(node1, node1.comp1, "", "1", "1_1")
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        task = ConfigTask(ms, ms.comp1, "", "1", "1_1")
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = RemoteExecutionTask([node1], node1, "", "agent", "action")
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        task = RemoteExecutionTask([ms], ms, "", "agent", "action")
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = CallbackTask(ms.comp1, "", None)
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.MS_GROUP, task.group)

        task = CallbackTask(node1.comp1, "", None)
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.NODE_GROUP, task.group)

        task = CallbackTask(cluster1, "", None)
        self.manager._setup_task_group(task)
        self.assertEquals(deployment_plan_groups.CLUSTER_GROUP, task.group)

    def test_task_matches_criteria(self):
        # Task definition
        class MockTaskNested(object):
            def __init__(self):
                self.attr = True
                self.action = lambda: True

        class MockTask(object):
            def __init__(self):
                self.attr = True
                self.action = lambda: True
                self.nested = MockTaskNested()

        # Criteria dictionary pairs
        pair_type = ('task_type', 'MockTask')
        pair_simple = ('attr', True)
        pair_simple_brackets = ('attr()', True)
        pair_action = ('action', True)
        pair_action_brackets = ('action()', True)
        pair_nested_simple = ('nested.attr', True)
        pair_nested_simple_brackets = ('nested().attr()', True)
        pair_nested_action = ('nested.action', True)
        pair_nested_action_brackets = ('nested().action()', True)
        pair_nested_action_brackets_false = ('nested.action', False)
        pair_invalid = ('invalid', True)

        # Criteria dictionaries
        crit_all = dict([
            pair_type, pair_simple, pair_action,
            pair_nested_simple, pair_nested_action])
        crit_with_invalid = dict([
            pair_type, pair_simple, pair_action,
            pair_nested_simple, pair_nested_action,
            pair_invalid])
        crit_with_brackets = dict([
            pair_type, pair_simple_brackets, pair_action_brackets,
            pair_nested_simple_brackets, pair_nested_action_brackets])
        crit_with_false = dict([
            pair_type, pair_simple_brackets, pair_action_brackets,
            pair_nested_simple_brackets, pair_nested_action_brackets_false])

        # 1. Empty criteria list
        self.assertFalse(self.manager._task_matches_criteria(MockTask(), []))

        # 2. Empty criteria dict
        self.assertFalse(self.manager._task_matches_criteria(MockTask(), {}))
        self.assertFalse(self.manager._task_matches_criteria(MockTask(), [{}]))
        # TODO Check that the warning was registered to the log

        # 3. One non empty criteria dict
        # 3.1. All criteria fields match
        self.assertTrue(self.manager._task_matches_criteria(
            MockTask(), crit_all))
        self.assertTrue(self.manager._task_matches_criteria(
            MockTask(), crit_with_brackets))
        # 3.2. One field does not match
        self.assertFalse(self.manager._task_matches_criteria(
            MockTask(), crit_with_false))
        self.assertFalse(self.manager._task_matches_criteria(
            MockTask(), [crit_with_false]))
        self.assertFalse(self.manager._task_matches_criteria(
            MockTask(), crit_with_invalid))
        self.assertFalse(self.manager._task_matches_criteria(
            MockTask(), [crit_with_invalid]))

        # 4. Many non empty criteria
        # 4.1. None of the criteria matches
        self.assertFalse(self.manager._task_matches_criteria(
            MockTask(), [crit_with_false, crit_with_invalid]))
        # 4.2. First criteria matches
        self.assertTrue(self.manager._task_matches_criteria(
            MockTask(), [crit_with_brackets, crit_with_false]))
        # 4.3. Second criteria matches
        self.assertTrue(self.manager._task_matches_criteria(
            MockTask(), [crit_with_false, crit_with_brackets]))

    def _create_model_for_validate_tests(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("type_a", "/ms/comp1")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        self.model.create_item("type_a", "/nodes/node2/comp1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")

    def test_validate_task_dependencies(self):
        self._create_model_for_validate_tests()

        ms = self.api.query_by_vpath("/ms")
        node1 = self.api.query_by_vpath("/nodes/node1")
        node2 = self.api.query_by_vpath("/nodes/node2")
        cluster1 = self.api.query_by_vpath("/deployments/d1/clusters/cluster1")
        somethings = self.api.query_by_vpath("/somethings")

        other_task = CallbackTask(node1.comp1, "", None)
        other_task.group = deployment_plan_groups.NODE_GROUP

        task = CallbackTask(node1.comp1, "", None)
        task.group = deployment_plan_groups.NODE_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

        task = CallbackTask(node2.comp1, "", None)
        task.group = deployment_plan_groups.NODE_GROUP
        task.requires = set([other_task])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies, [task])

        task = CallbackTask(ms.comp1, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies, [task])

        task = CallbackTask(cluster1, "", None)
        task.group = deployment_plan_groups.CLUSTER_GROUP
        task.requires = set([other_task])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies, [task])

        task = CallbackTask(somethings, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies, [task])

        other_task = CallbackTask(ms.comp1, "", None)
        other_task.group = deployment_plan_groups.MS_GROUP
        task = CallbackTask(ms.comp1, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

        other_task = CallbackTask(ms.comp1, "", None)
        other_task.group = deployment_plan_groups.MS_GROUP
        task = CallbackTask(ms.comp1, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

        other_task = ConfigTask(ms, somethings, "cfg task", "cfg::task", "0101")
        other_task.group = deployment_plan_groups.MS_GROUP
        task = CallbackTask(ms.comp1, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

        other_task = CallbackTask(cluster1, "", None)
        other_task.group = deployment_plan_groups.CLUSTER_GROUP
        task = CallbackTask(cluster1, "", None)
        task.group = deployment_plan_groups.CLUSTER_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

        other_task = CallbackTask(somethings, "", None)
        other_task.group = deployment_plan_groups.MS_GROUP
        task = CallbackTask(somethings, "", None)
        task.group = deployment_plan_groups.MS_GROUP
        task.requires = set([other_task])
        self.manager._validate_task_dependencies([task])

    def test_validate_call_typ_call_id_dependency(self):
        self._create_model_for_validate_tests()
        node1 = self.qi(self.model.query_by_vpath("/nodes/node1"))
        task = CallbackTask(node1.comp1, "", None)
        task.requires.add(("call_type", "call_id"))
        task.group = "NODE"

        # Happy case: there is a matching ConfigTask, in the same group
        other_task = ConfigTask(node1, node1.comp1, "", "call_type", "call_id")
        other_task.group = "NODE"
        try:
            self.manager._validate_task_dependencies([task, other_task])
        except TaskValidationException:
            self.fail()

        # Happy case: there is no matching ConfigTask
        other_task = ConfigTask(node1, node1.comp1, "", "foo", "bar")
        other_task.group = "NODE"
        try:
            self.manager._validate_task_dependencies([task, other_task])
        except TaskValidationException:
            self.fail()

        # Unhappy case: there is a matching ConfigTask, but it's in a different
        # group
        other_task = ConfigTask(node1, node1.comp1, "", "call_type", "call_id")
        other_task.group = "CLUSTER"
        self.assertRaises(TaskValidationException, self.manager._validate_task_dependencies, [
            task, other_task
        ])

        # Unhappy case: there are 2 matching ConfigTasks, and one is in a
        # different group
        another_task = ConfigTask(node1, node1.comp1, "", "call_type", "call_id")
        another_task.group = "NODE"
        self.assertRaises(TaskValidationException, self.manager._validate_task_dependencies, [
            task, other_task, another_task
        ])

        # Happy case: there are 2 matching ConfigTasks, both in the same group
        # as the task that has the requires attribute set
        other_task.group = "NODE"
        try:
            self.manager._validate_task_dependencies([task, other_task, another_task])
        except TaskValidationException:
            self.fail()


    def test_validate_query_item_dependencies(self):
        self._create_model_for_validate_tests()

        ms = self.api.query_by_vpath("/ms")
        node1 = self.api.query_by_vpath("/nodes/node1")
        node2 = self.api.query_by_vpath("/nodes/node2")
        cluster1 = self.api.query_by_vpath("/deployments/d1/clusters/cluster1")

        task_node1 = CallbackTask(node1.comp1, "", None)
        task_node1.group = deployment_plan_groups.NODE_GROUP
        task_node2 = CallbackTask(node2, "", None)
        task_node2.group = deployment_plan_groups.NODE_GROUP
        task_ms = CallbackTask(ms, "", None)
        task_ms.group = deployment_plan_groups.MS_GROUP
        task_cluster1 = CallbackTask(cluster1, "", None)
        task_cluster1.group = deployment_plan_groups.CLUSTER_GROUP

        task_node1.requires = set([node1])
        self.manager._validate_task_dependencies([task_node1])

        task_node1.requires = set([node2])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_node1, task_node2])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_node2, task_node1, task_ms, task_cluster1])

        task_node1.requires = set([ms])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_node1, task_ms])

        task_node1.requires = set([cluster1])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_node1, task_cluster1])

        task_ms.requires = set([ms])
        self.manager._validate_task_dependencies([task_ms])

        task_ms.requires = set([cluster1])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_ms, task_cluster1])

        task_ms.requires = set([node1])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_ms, task_node1])

        task_cluster1.requires = set([cluster1])
        self.manager._validate_task_dependencies([task_cluster1])

        task_cluster1.requires = set([""])
        self.assertRaises(TaskValidationException,
                          self.manager._validate_task_dependencies,
                          [task_cluster1])

    def test_validate_task_group(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("something", "/somethings/something1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        node_item = self.model.create_item("node",
                "/deployments/d1/clusters/cluster1/nodes/node1")
        inherited_item_1 = self.model.create_inherited("/somethings/something1",
                "/deployments/d1/clusters/cluster1/nodes/node1/something")
        inherited_item_ms = self.model.create_inherited("/somethings/something1",
                "/ms/something")

        plugin = TestPlugin()
        ms_qi = QueryItem(self.manager.model_manager, self.model.query_by_vpath("/ms"))
        node_qi = QueryItem(self.manager.model_manager, node_item)
        inherited_qi = QueryItem(self.manager.model_manager, inherited_item_1)
        inherited_qi_ms = QueryItem(self.manager.model_manager, inherited_item_ms)

        # Test ConfigTasks are passing regardless of the group and vpath
        task = ConfigTask(ms_qi, inherited_qi_ms, "callback task", "call_type", "call_id")
        task.group = deployment_plan_groups.NODE_GROUP
        try:
            self.manager._validate_task_group([task])
        except TaskValidationException:
            self.fail("TaskValidationException should not be raised.")

        # Test Callback tasks are validated - Positive Case
        task = CallbackTask(inherited_qi, "callback task", plugin.callback_method)
        task.group = deployment_plan_groups.NODE_GROUP
        try:
            self.manager._validate_task_group([task])
        except TaskValidationException:
            self.fail("TaskValidationException should not be raised.")

        # Test Callback tasks are validated - Negative Case
        task = CallbackTask(inherited_qi_ms, "callback task", plugin.callback_method)
        task.group = deployment_plan_groups.NODE_GROUP
        self.assertRaises(TaskValidationException, self.manager._validate_task_group, [task])

        # Test Callback tasks are validated - task group should not be validated
        task = CallbackTask(inherited_qi_ms, "callback task", plugin.callback_method)
        task.group = deployment_plan_groups.MS_GROUP
        try:
            self.manager._validate_task_group([task])
        except TaskValidationException:
            self.fail("TaskValidationException should not be raised.")

        # Test RemoteExecutionTask tasks are validated - Positive Case
        task = RemoteExecutionTask(
                [node_qi], inherited_qi,"RemoteExecutionTask", "agent", "action")
        task.group = deployment_plan_groups.NODE_GROUP
        try:
            self.manager._validate_task_group([task])
        except TaskValidationException:
            self.fail("TaskValidationException should not be raised.")

        # Test RemoteExecutionTask tasks are validated - Negative Case
        task = RemoteExecutionTask(
                [ms_qi], inherited_item_ms, "RemoteExecutionTask", "agent", "action")
        task.group = deployment_plan_groups.NODE_GROUP
        self.assertRaises(TaskValidationException, self.manager._validate_task_group, [task])

    def test_get_all_nodes(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        self.model.create_item("type_a", "/ms/comp1")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        self.model.create_item("type_a", "/nodes/node2/comp1")
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        ms_qi = self.qi(self.model.query_by_vpath("/ms"))
        node1_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))
        node2_qi = self.qi(self.model.query_by_vpath("/nodes/node2"))
        cluster1_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/cluster1"))

        self.assertRaises(ValueError, self.manager._get_all_nodes, [""])

        task = ConfigTask(node1_qi, node1_qi.comp1, "", "1", "1_1")
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(
            set([node1_qi._model_item.vpath]),
            set([node.vpath for node in nodes])
        )

        task = ConfigTask(ms_qi, ms_qi.comp1, "", "1", "1_1")
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(
            set([ms_qi._model_item.vpath]),
            set([node.vpath for node in nodes])
        )

        task = CallbackTask(node1_qi.comp1, "", None)
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(
            set([node1_qi._model_item.vpath]),
            set([node.vpath for node in nodes])
        )

        task = CallbackTask(ms_qi.comp1, "", None)
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(
            set([ms_qi._model_item.vpath]),
            set([node.vpath for node in nodes])
        )

        task = CallbackTask(cluster1_qi, "", None)
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(set(), nodes)

        task = RemoteExecutionTask([node1_qi, node2_qi], ms_qi, "", "agent", "action")
        nodes = self.manager._get_all_nodes([task])
        self.assertEquals(
            set([node1_qi._model_item.vpath, node2_qi._model_item.vpath]),
            set([node.vpath for node in nodes])
        )

    def test_get_nodes_to_be_locked(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        self.model.create_item("node", "/deployments/d1/clusters/cluster1/nodes/node1", hostname="node1")
        self.model.create_item("ms", "/ms", hostname="ms")

        cluster_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/cluster1"))
        cluster_mi = cluster_qi._model_item

        node1_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/cluster1/nodes/node1"))
        node1_mi = node1_qi._model_item

        task1 = CallbackTask(node1_qi, "", None)

        tasks = [task1]
        nodes = self.manager._get_nodes_to_be_locked(tasks)
        self.assertEquals(set(), nodes)

        node1_mi.set_applied()
        cluster_mi.set_property("ha_manager", None)
        nodes = self.manager._get_nodes_to_be_locked(tasks)
        self.assertEquals(set(), nodes)

        node1_mi.set_initial()
        cluster_mi.set_property("ha_manager", "cmw")
        nodes = self.manager._get_nodes_to_be_locked(tasks)
        self.assertEquals(set(), nodes)

        node1_mi.set_applied()
        cluster_mi.set_applied()
        nodes = self.manager._get_nodes_to_be_locked(tasks)
        self.assertEquals(set([node1_mi]), nodes)

        nodes = self.manager.\
             _get_nodes_to_be_locked(tasks,
                                     [LockPolicy(LockPolicy.INITIAL_LOCKS)])
        self.assertEquals(set(), nodes)

        # Make the cluster a 2-node cluster
        self.model.create_item("node", "/deployments/d1/clusters/cluster1/nodes/node2", hostname="node2")
        node2_qi = self.qi(self.model.query_by_vpath("/deployments/d1/clusters/cluster1/nodes/node2"))
        node2_mi = node2_qi._model_item

        task2 = CallbackTask(node2_qi, "", None)
        tasks.append(task2)

        node2_mi.set_applied()
        nodes = self.manager._get_nodes_to_be_locked(tasks)
        self.assertEquals(set([node1_mi, node2_mi]), nodes)


        node1_mi.set_initial()
        node2_mi.set_initial()
        nodes = self.manager.\
            _get_nodes_to_be_locked(tasks,
                                    [LockPolicy(LockPolicy.INITIAL_LOCKS)])
        self.assertEquals(set([node1_mi, node2_mi]), nodes)

        node1_mi.set_applied()
        node2_mi.set_applied()
        nodes = self.manager._get_nodes_to_be_locked(tasks,
                                                     [LockPolicy(LockPolicy.NO_LOCKS)])
        self.assertEquals(set(), nodes)

        node1_mi.set_initial()
        node2_mi.set_initial()
        nodes = self.manager.\
            _get_nodes_to_be_locked(tasks, [LockPolicy(LockPolicy.NO_LOCKS),
                                            LockPolicy(
                                                 LockPolicy.INITIAL_LOCKS)])
        self.assertEquals(set(), nodes)

        node1_mi.set_applied()
        node2_mi.set_applied()
        nodes = self.manager.\
            _get_nodes_to_be_locked(tasks,
                                    [LockPolicy(LockPolicy.CREATE_LOCKS,
                                                ["cluster2"]),
                                     LockPolicy(LockPolicy.INITIAL_LOCKS)])
        self.assertEquals(set([node1_mi, node2_mi]), nodes)


    def test_get_nodes_to_be_locked_skips_ms(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        ms_qi = self.qi(self.model.query_by_vpath("/ms"))
        ms_qi._model_item.set_applied()
        task = CallbackTask(ms_qi, "", None)
        nodes = self.manager._get_nodes_to_be_locked([task])
        self.assertEquals(set(), nodes)

    def test_is_node_to_be_locked(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster", "/deployments/d1/clusters/cluster1")
        self.model.create_item("node",
            "/deployments/d1/clusters/cluster1/nodes/node1", hostname="node1")
        self.model.create_item("node",
            "/deployments/d1/clusters/cluster1/nodes/node2", hostname="node2")

        cluster_qi = self.qi(
            self.model.query_by_vpath("/deployments/d1/clusters/cluster1"))
        node1_qi = self.qi(
            self.model.query_by_vpath(
                "/deployments/d1/clusters/cluster1/nodes/node1"))
        node1_mi = node1_qi._model_item
        node2_qi = self.qi(self.model.query_by_vpath(
                   "/deployments/d1/clusters/cluster1/nodes/node2"))
        node2_mi = node2_qi._model_item

        #Cluster does not have ha_manager attr
        result = self.manager._is_node_to_be_locked(node1_mi)
        self.assertEquals(False, result)

        #No lock policy and cluster is initial
        cluster_qi._model_item.set_property("ha_manager", "cmw")
        result = self.manager._is_node_to_be_locked(node1_mi)
        self.assertEquals(False, result)

        # Cluster is initial, node2 applied and no lock policy
        node2_mi.set_applied()
        result = self.manager._is_node_to_be_locked(node2_mi)
        self.assertEquals(False, result)

        # Cluster is initial, node2 applied and
        # Lock policy create locks
        result = self.manager._is_node_to_be_locked(node2_mi,
                        LockPolicy(LockPolicy.CREATE_LOCKS))
        self.assertEquals(False, result)

        #Node in state initial and no lock policy
        cluster_qi._model_item.set_applied()
        result = self.manager._is_node_to_be_locked(node1_mi)
        self.assertEquals(False, result)

        #Node in state initial and lock policy
        #initial locks
        result = self.manager._is_node_to_be_locked(node1_mi,
                        LockPolicy(LockPolicy.INITIAL_LOCKS))
        self.assertEquals(True, result)

        #Node in state initial and lock policy
        #create locks
        result = self.manager._is_node_to_be_locked(node1_mi,
                        LockPolicy(LockPolicy.CREATE_LOCKS))
        self.assertEquals(False, result)

        #Node in state initial and lock policy
        #no locks
        result = self.manager._is_node_to_be_locked(node1_mi,
                        LockPolicy(LockPolicy.NO_LOCKS))
        self.assertEquals(False, result)

        node1_mi.set_applied()

        #Node applied and lock policy no_locks
        result = self.manager._is_node_to_be_locked(node1_mi,
                        LockPolicy(LockPolicy.NO_LOCKS))
        self.assertEquals(False, result)

        #Node applied, lock policy create locks and
        #matching cluster "not to lock" specifed in cluster list
        result = self.manager._is_node_to_be_locked(node1_mi,
                            LockPolicy(LockPolicy.CREATE_LOCKS, ["cluster1"]))
        self.assertEquals(False, result)

        # Node applied, lock policy create locks and
        # non matching cluster "not to lock" specified in cluster list
        result = self.manager._is_node_to_be_locked(node1_mi,
                    LockPolicy(LockPolicy.CREATE_LOCKS, ["cluster2"]))
        self.assertEquals(True, result)

        #Node applied and lock policy initial locks
        result = self.manager._is_node_to_be_locked(node1_mi,
                            LockPolicy(LockPolicy.INITIAL_LOCKS))
        self.assertEquals(True, result)

        #Node applied and lock policy create locks, no cluster
        #list
        result = self.manager._is_node_to_be_locked(node1_mi,
                        LockPolicy(LockPolicy.CREATE_LOCKS))
        self.assertEquals(True, result)

        #Node applied and no lock policy
        result = self.manager._is_node_to_be_locked(node1_mi)
        self.assertEquals(True, result)

    def test_add_node_left_locked(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster",
                               "/deployments/d1/clusters/cluster1")
        self.model.create_item("node",
            "/deployments/d1/clusters/cluster1/nodes/node1", hostname="node1")

        cluster_qi = self.qi(
            self.model.query_by_vpath("/deployments/d1/clusters/cluster1"))
        node_qi = self.qi(
            self.model.query_by_vpath(
                "/deployments/d1/clusters/cluster1/nodes/node1"))
        node_mi = node_qi._model_item

        # No lock policies, no nodes left locked
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=None)
        self.manager._add_node_left_locked([], nodes_to_be_locked)
        self.assertEquals(set([]), nodes_to_be_locked)

        # No lock policies, node1 left locked
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked([], nodes_to_be_locked)
        self.assertEquals(set([node_mi]), nodes_to_be_locked)

        # Lock policy = no locks, node1 left locked
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked([LockPolicy(LockPolicy.NO_LOCKS)],
                                           nodes_to_be_locked)
        self.assertEquals(set(), nodes_to_be_locked)

        #Lock policy = create_locks, node 1 left locked
        #no cluster specified
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked(
            [LockPolicy(LockPolicy.CREATE_LOCKS)],
            nodes_to_be_locked)
        self.assertEquals(set([node_mi]), nodes_to_be_locked)

        # Lock policy = create_locks, node 1 left locked
        # matching cluster specified
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked(
            [LockPolicy(LockPolicy.CREATE_LOCKS,
                        ["cluster1", "cluster2"])],
                        nodes_to_be_locked)
        self.assertEquals(set([]), nodes_to_be_locked)

        # Lock policy = create_locks node 1 left locked,
        # no matching cluster specified
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked(
            [LockPolicy(LockPolicy.CREATE_LOCKS,
                        ["cluster2"])],
                        nodes_to_be_locked)
        self.assertEquals(set([node_mi]), nodes_to_be_locked)

        #Lock policy = initial locks, node 1 left locked,
        nodes_to_be_locked = set()
        self.manager.model_manager._node_left_locked = \
            MagicMock(return_value=node_mi)
        self.manager._add_node_left_locked(
            [LockPolicy(LockPolicy.INITIAL_LOCKS)],
            nodes_to_be_locked)
        self.assertEquals(set([]), nodes_to_be_locked)


    def test_get_tasks_from_ordered_task_list(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        node1_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))

        task1 = CallbackTask(node1_qi.comp1, "", None)
        task2 = CallbackTask(node1_qi.comp1, "", None)
        task2.requires = set([node1_qi])
        task3 = CallbackTask(node1_qi.comp1, "", None)
        task3.requires = set([node1_qi])
        otl = OrderedTaskList(node1_qi.comp1, [task1, task2, task3])

        tasks = self.manager._get_tasks_from_ordered_task_list(otl)
        self.assertEquals(3, len(tasks))

        # ugly hacks below because of QueryItem comparison is broken
        # so we need to compare ModelItems instead
        def uh(s):
            return set([req if isinstance(req, Task) else req._model_item for req in s])

        self.assertEquals(set(), uh(task1.requires))
        self.assertEquals(set([task1, node1_qi._model_item]), uh(task2.requires))
        self.assertEquals(set([task2, node1_qi._model_item]), uh(task3.requires))

    def test_rewrite_ordered_task_lists(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("type_a", "/nodes/node1/comp1")
        node1 = self.qi(self.model.query_by_vpath("/nodes/node1"))

        task1 = CallbackTask(node1.comp1, "", None)
        task2 = CallbackTask(node1.comp1, "", None)
        task3 = CallbackTask(node1.comp1, "", None)
        otl = OrderedTaskList(node1.comp1, [task1, task2, task3])

        task0 = CallbackTask(node1.comp1, "", None)

        tasks = self.manager._rewrite_ordered_task_lists([task0, otl])
        self.assertEquals(set([task0, task1, task2, task3]), set(tasks))

    def test_split_remote_execution_tasks(self):
        self.model.create_item("ms", "/ms", hostname="ms")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        ms_qi = self.qi(self.model.query_by_vpath("/ms"))
        node1_qi = self.qi(self.model.query_by_vpath("/nodes/node1"))
        node2_qi = self.qi(self.model.query_by_vpath("/nodes/node2"))

        task1 = CallbackTask(ms_qi, "", None)
        task2 = ConfigTask(ms_qi, ms_qi, "", "1", "1_1")
        tasks = self.manager._split_remote_execution_tasks([task1, task2], [])
        self.assertEquals([task1, task2], tasks)

        task = RemoteExecutionTask([ms_qi], ms_qi, "", "agent", "action")
        tasks = self.manager._split_remote_execution_tasks([task], [])
        self.assertEquals([task], tasks)

        task = RemoteExecutionTask([node1_qi, node2_qi, ms_qi], ms_qi, "", "agent", "action")
        tasks = self.manager._split_remote_execution_tasks([task], [])
        self.assertEquals(2, len(tasks))
        ms_tasks = [t for t in tasks if len(t.nodes) == 1 and list(t.nodes)[0]._model_item == ms_qi._model_item]
        self.assertEquals(1, len(ms_tasks))
        self.assertEquals(1, len(ms_tasks[0].nodes))
        self.assertEquals(ms_qi._model_item, list(ms_tasks[0].nodes)[0]._model_item)
        node_tasks = [t for t in tasks if not (len(t.nodes) == 1 and list(t.nodes)[0]._model_item == ms_qi._model_item)]
        self.assertEquals(1, len(node_tasks))
        self.assertEquals(2, len(node_tasks[0].nodes))
        self.assertEquals(set([node1_qi._model_item, node2_qi._model_item]), set([node._model_item for node in node_tasks[0].nodes]))

        task = RemoteExecutionTask([node1_qi, node2_qi, ms_qi], ms_qi, "", "agent", "action")
        tasks = self.manager._split_remote_execution_tasks([task], [node1_qi._model_item])
        self.assertEquals(3, len(tasks))
        ms_tasks = [t for t in tasks if len(t.nodes) == 1 and list(t.nodes)[0]._model_item == ms_qi._model_item]
        self.assertEquals(1, len(ms_tasks))
        self.assertEquals(1, len(ms_tasks[0].nodes))
        self.assertEquals(ms_qi._model_item, list(ms_tasks[0].nodes)[0]._model_item)
        node1_tasks = [t for t in tasks if len(t.nodes) == 1 and list(t.nodes)[0]._model_item == node1_qi._model_item]
        self.assertEquals(1, len(node1_tasks))
        self.assertEquals(1, len(node1_tasks[0].nodes))
        self.assertEquals(node1_qi._model_item, list(node1_tasks[0].nodes)[0]._model_item)
        node2_tasks = [t for t in tasks if len(t.nodes) == 1 and list(t.nodes)[0]._model_item == node2_qi._model_item]
        self.assertEquals(1, len(node2_tasks))
        self.assertEquals(1, len(node2_tasks[0].nodes))
        self.assertEquals(node2_qi._model_item, list(node2_tasks[0].nodes)[0]._model_item)

    def test_for_removal_items_not_deleted_after_removesnapshot(self):
        self._create_sample_model_for_locking_no_lock_tasks()
        self.manager.model_manager.create_snapshot_item('snapshot')
        self.manager._update_ss_timestamp('234564845646')
        self.model.set_all_applied(['snapshot-base'])

        self.assertTrue(self.model.query('snapshot-base')[0].is_initial())

        self.model.get_item('/deployments/d1/clusters/cluster1/nodes/node1/comp1').set_for_removal()
        self.assertTrue(self.model.get_item('/deployments/d1/clusters/cluster1/nodes/node1/comp1').is_for_removal())
        # we have a valid snapshot and a for_removal item
        # now, when we create a remove_snapshot plan we should only have
        # tasks to remove the snapshot item and not the other
        self.model.get_item('/snapshots/snapshot').set_for_removal()
        actual_plan = self.manager.delete_snapshot_plan()
        expected = [CleanupTask(self.api.query('snapshot-base')[0])]
        self.assertEqual(Plan([], cleanup_tasks=expected).get_tasks(),
                         actual_plan.get_tasks())

    def test_exception_in_create_plan_gets_formatted(self):
        self.manager._create_plan = MagicMock(side_effect=PluginError(['one', 'two']))
        self.assertEqual([{'message': 'one', 'error': 'InternalServerError'},
                          {'message': 'two', 'error': 'InternalServerError'}],
                         self.manager.create_plan())
        self.manager._create_plan = MagicMock(side_effect=PluginError('one'))
        self.assertEqual([{'message': 'one', 'error': 'InternalServerError'}],
                         self.manager.create_plan())
        self.manager._create_plan = MagicMock(side_effect=EmptyPlanException())
        self.assertEqual([{'message': 'no tasks were generated', 'error': 'DoNothingPlanError'}],
                         self.manager.create_plan())
        self.manager._create_plan = MagicMock(side_effect=Exception('duuh'))
        self.assertEqual([{'message': 'See logs for details.', 'error': 'InternalServerError'}],
                         self.manager.create_plan())

    @patch('litp.core.execution_manager.ExecutionManager._backup_model_for_snapshot')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', MagicMock(return_value="snapshot"))
    def test_backup_snapshot_model_called_at_create(self, mock_backup):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_phase = MagicMock(return_value=None)
        self.manager._run_all_phases = MagicMock(return_value=None)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "restore")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertFalse(mock_backup.called)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "remove")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertFalse(mock_backup.called)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "create")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertTrue(mock_backup.called)

    @patch('litp.core.execution_manager.ExecutionManager._backup_model_for_snapshot')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', MagicMock(return_value="named"))
    def test_backup_snapshot_model_called_for_named_snapshot(self, mock_backup):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_phase = MagicMock(return_value=None)
        self.manager._run_all_phases = MagicMock(return_value=None)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "create")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertTrue(mock_backup.called)

    @patch('litp.core.execution_manager.ExecutionManager._backup_model_for_snapshot')
    def test_backup_snapshot_model_is_called_failed_snapshot(self, mock_backup):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks= MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_all_phases = MagicMock(return_value='error')

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "create")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertTrue(mock_backup.called)

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', MagicMock(return_value="snapshot"))
    @patch('litp.core.execution_manager.ExecutionManager.invalidate_snapshot_model')
    def test_invalidate_snapshot_model_called_at_remove(self, mock_invalidate):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks = MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_phase = MagicMock(return_value=None)
        self.manager._run_all_phases = MagicMock(return_value=None)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "restore")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertFalse(mock_invalidate.called)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "create")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertFalse(mock_invalidate.called)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "remove")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertTrue(mock_invalidate.called)

    @patch('litp.core.execution_manager.ExecutionManager.invalidate_snapshot_model')
    def test_invalidate_snapshot_model_not_called_failed_snapshot(self,
            mock_invalidate):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks = MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_all_phases = MagicMock(return_value='error')

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "remove")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertFalse(mock_invalidate.called)

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', MagicMock(return_value="a_name"))
    @patch('litp.core.execution_manager.ExecutionManager.invalidate_snapshot_model')
    def test_invalidate_snapshot_model_called_for_named_snapshot(self,
            mock_invalidate):
        self._node_and_2_tasks(MagicMock(return_value=None))
        node = self.model.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        node_qi = self.qi(node)
        task = CallbackTask(node_qi, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks = MagicMock(return_value=[task])
        self.manager.model_manager.create_snapshot_item = MagicMock()
        self.manager._run_all_phases = MagicMock(return_value=None)

        with patch.object(PluginApiContext, 'snapshot_action',
                          MagicMock(return_value = "remove")):
            self.manager.create_snapshot_plan()
            self.manager.run_plan()
            self.assertTrue(mock_invalidate.called)

    @patch('litp.data.model_data_manager.ModelDataManager.create_backup')
    def test_backup_model_for_snapshot(self, create_backup):
        self._node_and_2_tasks(MagicMock(return_value=None))
        self.model.create_item(
                 'snapshot-base', '/snapshots/snapshot', timestamp='123')
        node = self.api.query_by_vpath("/deployments/d1/clusters/c1/nodes/node")
        task = CallbackTask(node, "irrelevant2", TestSnapshotPlugin().callback_method)
        self.manager._create_plugin_tasks = MagicMock(return_value=[task])

        self.manager.create_plan()
        self.assertTrue(self.manager.plan)

        self.manager._backup_model_for_snapshot()
        self.assertTrue(create_backup.called)
        save_args, save_kwargs = create_backup.call_args
        self.assertEqual(
            SNAPSHOT_PLAN_MODEL_ID_PREFIX + 'snapshot',
            save_args[0]
        )

    def _create_vcs_cluster_without_node_upgrade_ordering(self):
        self.model.register_item_type(
            ItemType(
                "vcs-cluster",
                extend_item="cluster",
                item_description="vcs-cluster like item type",
                )
            )
        self.model.create_item("vcs-cluster",
                "/deployments/d1/clusters/vcs_cluster")
        self.model.create_item("node",
                "/deployments/d1/clusters/vcs_cluster/nodes/node1",
                hostname="vcs_node1")
        self.model.create_item("node",
                "/deployments/d1/clusters/vcs_cluster/nodes/node2",
                hostname="vcs_node2")

    def _create_vcs_cluster_with_node_upgrade_ordering_viewerror(self):
        def dummy_get_node_upgrade_ordering(api_context, cluster):
            raise ViewError('test ViewError')
        self.model.register_item_type(
            ItemType(
                "vcs-cluster",
                extend_item="cluster",
                item_description="vcs-cluster like item type",
                node_upgrade_ordering=View(
                    "basic_list",
                    dummy_get_node_upgrade_ordering,
                    view_description="A comma seperated list of the node "
                    "ordering for upgrade."),
                )
            )
        self.model.create_item("vcs-cluster",
                "/deployments/d1/clusters/vcs_cluster")
        self.model.create_item("node",
                "/deployments/d1/clusters/vcs_cluster/nodes/node1",
                hostname="vcs_node1")
        self.model.create_item("node",
                "/deployments/d1/clusters/vcs_cluster/nodes/node2",
                hostname="vcs_node2")

    def _prepare_task_mocking_and_get_task(self):
        vpath = "/deployments/d1/clusters/vcs_cluster/nodes/node2"
        node_qi = self.qi(self.model.query_by_vpath(vpath))
        node_qi._model_item.set_updated()

        task = ConfigTask(node_qi, node_qi, "", "", "")
        task.group = deployment_plan_groups.NODE_GROUP
        self.manager._create_plugin_tasks = MagicMock(return_value=[task])
        self.manager._create_lock_tasks = MagicMock(
            return_value={vpath: [task, task]})
        return task

    def test_puppet_manager_get_nodes_no_node_upgrade_ordering_view(self):
        self._setup_model()
        self._create_vcs_cluster_without_node_upgrade_ordering()
        task = self._prepare_task_mocking_and_get_task()
        plan = self.manager.create_plan()
        self.assertEquals(task, plan.phases[1][0])

    def test_puppet_manager_get_nodes_view_error(self):
        self._setup_model()
        self._create_vcs_cluster_with_node_upgrade_ordering_viewerror()
        task = self._prepare_task_mocking_and_get_task()
        expected = [{'message': 'test ViewError',
                'error': 'InternalServerError'}]
        self.assertEquals(expected, self.manager.create_plan())

    def test_exception_raised_during_plugin_validate_model(self):
        self._setup_model()

        class ExceptionPlugin(Plugin):
            def validate_model(self, plugin_api_context):
                raise PluginError("deliberate exception raised by plugin")

        plugin = ExceptionPlugin()
        self._add_plugin(plugin)

        self.manager.create_plan()

    def test_good_model_update(self):
        self._setup_model()

        PluginWithUpdateModelA.reset_call_recording()
        PluginWithUpdateModelB.reset_call_recording()
        PluginWithUpdateModelC.reset_call_recording()
        PluginWithUpdateModelD.reset_call_recording()

        plugin_a = PluginWithUpdateModelA()
        plugin_b = PluginWithUpdateModelB()
        plugin_c = PluginWithUpdateModelC()
        plugin_d = PluginWithUpdateModelD()

        for plugin in (plugin_a, plugin_b, plugin_c, plugin_d):
            self._add_plugin(plugin)

        res = self.manager.create_plan()

        self.assertEqual([{'message':'no tasks were generated',
                           'error': 'DoNothingPlanError'}], res)

        # Assert that all plugin methods are called for all plugins
        for plugin in (plugin_a, plugin_b, plugin_c, plugin_d):
            self.assertTrue(plugin._update_model_called)
            self.assertTrue(plugin._validate_model_called)
            self.assertTrue(plugin._create_configuration_called)
        node = self.model.get_item('/deployments/d1/clusters/c1/nodes/node1')
        self.assertEquals(node.name,"ChangedName")

    def test_model_update_exception(self):
        self._setup_model()

        PluginWithUpdateModelA.reset_call_recording()
        PluginWithUpdateModelB.reset_call_recording()
        PluginWithUpdateModelRaisingException.reset_call_recording()
        PluginWithUpdateModelD.reset_call_recording()

        plugin_a = PluginWithUpdateModelA()
        plugin_b = PluginWithUpdateModelB()
        plugin_c = PluginWithUpdateModelRaisingException()
        plugin_d = PluginWithUpdateModelD()

        for plugin in (plugin_a, plugin_b, plugin_c, plugin_d):
            self._add_plugin(plugin)

        res = self.manager.create_plan()

        self.assertEqual(res, [{
            'message': 'Model update failed with: Oops, cannot update model',
            'error': 'InternalServerError'}])

        # The update_model() method is called on all plugins in an
        # arbitrary order, and we stop on the first exception. So all
        # we can assert is that the method was called on the plugin that
        # raised the exception...
        self.assertTrue(plugin_c._update_model_called)

        # ... and that the subsequent methods are not called on any plugins.
        for plugin in (plugin_a, plugin_b, plugin_c, plugin_d):
            self.assertFalse(plugin._validate_model_called)
            self.assertFalse(plugin._create_configuration_called)

    def test_not_generating_replacement_configtask(self):
        node_mitem, item_mitem, _ = self._setup_model()
        self.model.set_all_applied()

        node = self.qi(self.model.query_by_vpath(node_mitem.vpath))
        item = self.qi(self.model.query_by_vpath(item_mitem.vpath))

        persisted_tasks = [ConfigTask(node, item, "", "foo", "bar")]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        self.model.remove_item(item.vpath)

        plugin_tasks = [ConfigTask(node, item, "", "foo", "bar")]
        replacement_tasks = self.manager._create_removal_tasks(plugin_tasks)

        self.assertEquals(0, len(replacement_tasks))

    def test_no_replacement_task_but_generates_cleanup_task(self):
        # LITPCDS-12624
        node_mitem, item_mitem, _ = self._setup_model()
        self.model.set_all_applied()

        node = self.api.query_by_vpath(node_mitem.vpath)
        item = self.api.query_by_vpath(item_mitem.vpath)
        item2 = self.api.query_by_vpath('/deployments/d1/clusters/c1/nodes/node1/comp2')

        persisted_tasks = [ConfigTask(node, item, "", "foo", "bar")]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        self.model.remove_item(item.vpath)

        # Plugin returns a ConfigTask for the same puppet resource, but on a
        # different vpath on the same node. No replacement task needed, but
        # requires a cleanup task to remove original item
        plugin_tasks = [ConfigTask(node, item2, "", "foo", "bar")]
        cleanup_tasks = self.manager._create_removal_tasks(plugin_tasks)

        self.assertEquals(1, len(cleanup_tasks))
        self.assertTrue(isinstance(cleanup_tasks[0], CleanupTask))
        self.assertEqual(cleanup_tasks[0].model_item, item)

        # If plugin returns a ConfigTask for the same resource on a different
        # node, a replacement task is required and no clean up task is needed
        node2 = Mock(vpath="/nodes/node2")
        plugin_tasks = [ConfigTask(node2, item2, "", "foo", "bar")]
        replacement_tasks = self.manager._create_removal_tasks(plugin_tasks)
        self.assertEquals(1, len(replacement_tasks))
        self.assertTrue(isinstance(replacement_tasks[0], ConfigTask))

    def test_node_deconfigure_tasks_no_plugin_tasks(self):
        self._setup_model()

        node2 = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node2",
            hostname="othernode", name="bleep",
            another_property="bloop"
        )
        self.model.create_item("type_c", "/deployments/d1/clusters/c1/nodes/node2/comp2")
        self.model.set_all_applied()

        cluster_qi = self.api.query_by_vpath("/deployments/d1/clusters/c1")
        node_qis = [self.qi(node) for node in self.model.query("node") if not node.is_ms()]

        persisted_tasks = [
            ConfigTask(node_qi, cluster_qi, "cluster task", "foo", "%s_resource" % node_qi.hostname) for
                node_qi in node_qis
        ]
        persisted_tasks += [
            ConfigTask(node_qi, node_qi.comp2, "node task", "bar", "%s_resource" % node_qi.hostname) for
                node_qi in node_qis
        ]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        # This would cause both nodes to be ForRemoval
        # self.model.remove_item(cluster_qi.vpath)
        self.model.remove_item(node2.vpath)

        plugin_tasks = []
        removal_tasks = self.manager._create_removal_tasks(plugin_tasks)
        # No replacement tasks are generated for node2, since its being in the
        # ForRemoval state means that Puppet would be unable to perform a
        # catalog run on it anyway
        self.assertEquals(2, len(removal_tasks))
        self.assertTrue(all(isinstance(removal_task, CleanupTask) for removal_task in removal_tasks))
        self.assertEquals(
            [
                CleanupTask(self._convert_to_query_item(node2)),
                CleanupTask(self._convert_to_query_item(node2.comp2))
            ],
            removal_tasks
        )

    def test_node_deconfigure_multiple_plugin_tasks_for_fr_node(self):
        self._setup_model()

        node2 = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node2",
            hostname="othernode", name="bleep",
            another_property="bloop"
        )
        node2_qi = self.qi(node2)
        self.model.create_item("type_c", "/deployments/d1/clusters/c1/nodes/node2/comp2")
        self.model.set_all_applied()

        node_qis = [self.qi(node) for node in self.model.query("node") if not node.is_ms()]

        persisted_tasks = [
            ConfigTask(node_qi, node_qi.comp2, "node task", "bar", "%s_resource" % node_qi.hostname) for
                node_qi in node_qis
        ]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        # This would cause both nodes to be ForRemoval
        # self.model.remove_item(cluster_qi.vpath)
        self.model.remove_item(node2.vpath)

        # We have 2 plugin-generated ConfigTasks for the same item
        plugin_tasks = [
            ConfigTask(node2_qi, node2_qi.comp2, "Deconfig task on node", "foo", "%s_resource" % node2_qi.hostname),
            ConfigTask(node2_qi, node2_qi.comp2, "Deconfig task on node", "bar", "%s_resource" % node2_qi.hostname),
        ]
        removal_tasks = self.manager._create_removal_tasks(plugin_tasks)
        # No replacement tasks are generated for node2, since its being in the
        # ForRemoval state means that Puppet would be unable to perform a
        # catalog run on it anyway
        self.assertEquals(2, len(removal_tasks))
        self.assertTrue(all(isinstance(removal_task, CleanupTask) for removal_task in removal_tasks))
        self.assertEquals(
            [
                CleanupTask(self._convert_to_query_item(node2)),
                # There's only one CleanupTask for node2.comp2, even though
                # there were several removal tasks generated by plugins
                CleanupTask(self._convert_to_query_item(node2.comp2))
            ],
            removal_tasks
        )

    def test_node_deconfigure_tasks_with_plugin_tasks(self):
        self._setup_model()

        node2 = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node2",
            hostname="othernode", name="bleep",
            another_property="bloop"
        )
        self.model.create_item("type_c", "/deployments/d1/clusters/c1/nodes/node2/comp2")
        self.model.set_all_applied()

        cluster_qi = self.api.query_by_vpath("/deployments/d1/clusters/c1")
        node_qis = [self.qi(node) for node in self.model.query("node") if not node.is_ms()]

        persisted_tasks = [
            ConfigTask(node_qi, cluster_qi, "cluster task", "foo", "%s_resource" % node_qi.hostname) for
                node_qi in node_qis
        ]
        persisted_tasks += [
            ConfigTask(node_qi, node_qi.comp2, "node task", "bar", "%s_resource" % node_qi.hostname) for
                node_qi in node_qis
        ]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        # This would cause both nodes to be ForRemoval
        # self.model.remove_item(cluster_qi.vpath)
        self.model.remove_item(node2.vpath)
        node2_qi = self._convert_to_query_item(node2)

        plugin_tasks = [
            ConfigTask(
                node2_qi,
                node2_qi.comp2,
                "Plugin-generated deconfigure task",
                "foo",
                "%s_resource" % node2_qi.hostname,
                ensure='absent'
            )
        ]
        removal_tasks = self.manager._create_removal_tasks(plugin_tasks)

        # The plugin generated task is filtered out
        self.assertEquals(2, len(removal_tasks))
        self.assertTrue(all(isinstance(removal_task, CleanupTask) for removal_task in removal_tasks))
        self.assertEquals(
            [
                CleanupTask(node2_qi),
                CleanupTask(node2_qi.comp2)
            ],
            removal_tasks
        )

    def test_generating_cleanuptask(self):
        node_mitem, item_mitem, _ = self._setup_model()
        self.model.set_all_applied()

        node = self.model.query_by_vpath(node_mitem.vpath)
        item = self.model.query_by_vpath(item_mitem.vpath)

        persisted_tasks = []
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        self.model.remove_item(item.vpath)

        plugin_tasks = []
        replacement_tasks = self.manager._create_removal_tasks(plugin_tasks)

        self.assertEquals(1, len(replacement_tasks))
        self.assertTrue(isinstance(replacement_tasks[0], CleanupTask))

    def test_generating_replacement_configtask(self):
        node_mitem, item_mitem, _ = self._setup_model()
        self.model.set_all_applied()

        node = self.api.query_by_vpath(node_mitem.vpath)
        item = self.api.query_by_vpath(item_mitem.vpath)

        persisted_tasks = [
            ConfigTask(node, item, "", "foo1", "bar1"),
            ConfigTask(node, item, "", "foo2", "bar2")
        ]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        self.model.remove_item(item.vpath)

        plugin_tasks = []
        replacement_tasks = self.manager._create_removal_tasks(plugin_tasks)

        self.assertEquals(1, len(replacement_tasks))
        replacement_task = replacement_tasks[0]
        self.assertTrue(isinstance(replacement_task, ConfigTask))
        self.assertEquals(set([("foo1", "bar1"), ("foo2", "bar2")]), replacement_task.replaces)
        #LITPCDS-11234
        self.manager.create_plan()
        self.assertEqual(self.manager.plan.phases[0][0].description,
                '''Remove Item\'s resource from node "node" puppet manifest''')

    def test_generating_cleanuptask_instead_replacement_configtask_in_special_cases(self):
        node_mitem, _, _ = self._setup_model()
        self.model.create_item("network-interface", node_mitem.vpath + "/eth0")
        self.model.set_all_applied()

        node = self.qi(self.model.query_by_vpath(node_mitem.vpath))
        item = self.qi(self.model.query_by_vpath(node_mitem.vpath + "/eth0"))

        persisted_tasks = [
            ConfigTask(node, item, "", "foo1", "bar1"),
            ConfigTask(node, item, "", "foo2", "bar2")
        ]
        self.puppet_manager.all_tasks = Mock(return_value=persisted_tasks)

        self.model.remove_item(item.vpath)

        plugin_tasks = []
        replacement_tasks = self.manager._create_removal_tasks(plugin_tasks)

        self.assertEquals(1, len(replacement_tasks))
        replacement_task = replacement_tasks[0]
        self.assertTrue(isinstance(replacement_task, CleanupTask))

    def test_on_puppet_timeout_log_message(self):
        self._setup_model()
        node1 = self.qi(self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node0", hostname="node1"))
        node2 = self.qi(self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node2", hostname="node2"))
        node3 = self.qi(self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node3", hostname="node3"))
        node4 = self.qi(self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node4", hostname="node4"))
        task1 = ConfigTask(node1, node1, '', '', '')
        task2 = ConfigTask(node2, node2, '', '', '')
        task3 = ConfigTask(node3, node3, '', '', '')
        task_initial = ConfigTask(node4, node4, '', '', '')
        task_initial.state = constants.TASK_INITIAL
        with patch('litp.core.execution_manager.log.trace.info') as info:
            # 1 node involved
            task1.state = constants.TASK_RUNNING
            self.manager.on_puppet_timeout([
                task1, task_initial])
            info.assert_called_with('Failing running tasks due to '
                    'Puppet timeout on node(s) node1')

            # 2 nodes involved
            task1.state = constants.TASK_RUNNING
            task2.state = constants.TASK_RUNNING
            self.manager.on_puppet_timeout(
                    [task1, task_initial, task2])
            info.assert_called_with('Failing running tasks due to '
                    'Puppet timeout on node(s) node1 and node2')

            # 3 nodes involved
            task1.state = constants.TASK_RUNNING
            task2.state = constants.TASK_RUNNING
            task3.state = constants.TASK_RUNNING
            self.manager.on_puppet_timeout(
                    [task1, task_initial, task2, task3])
            info.assert_called_with('Failing running tasks due to '
                    'Puppet timeout on node(s) node1, node2 and node3')

    def test_create_snapshot_plan_invalid_task_types(self):
        self._setup_model()
        plugin = TestSnapshotPluginWithInvalidTaskTypes()
        self._add_plugin(plugin)
        result = self.manager.create_snapshot_plan()
        self.assertFalse(isinstance(result, SnapshotPlan))
        # plugin deliberately returns tasks where no tasks are of valid type,
        # hence no tasks generated as they are all filtered out (LITPCDS-11688)
        self.assertEqual(
            [{
                'message': 'no tasks were generated',
                'error': 'DoNothingPlanError'
            }],
            result)

    def test_handle_task_validation_exception_messages(self):
        exception_with_messages = TaskValidationException('Foo', ['a', 'b', 'c'])
        exception_with_empty_messages = TaskValidationException('Foo', [])
        exception_without_messages = TaskValidationException('Foo')

        manager = ExecutionManager(MagicMock(), Mock(), Mock())
        manager._has_errors_before_create_plan = Mock(return_value=None)

        expected_error = [{'message': 'Foo', 'error': 'InternalServerError'}]

        manager._create_plan = Mock(side_effect=exception_with_messages)
        result = manager.create_plan()
        self.assertEqual(result, expected_error)

        manager._create_plan = Mock(side_effect=exception_with_empty_messages)
        result = manager.create_plan()
        self.assertEqual(result, expected_error)

        manager._create_plan = Mock(side_effect=exception_without_messages)
        result = manager.create_plan()
        self.assertEqual(result, expected_error)

    def test_call_type_call_id_in_tasks(self):
        manager = ExecutionManager(Mock(), Mock(), Mock())
        node1 = Mock(vpath='/node1')
        plugin_tasks = [
            ConfigTask(node1, Mock(), "", "foo1", "bar1"),
            ConfigTask(node1, Mock(), "", "foo2", "bar2")
        ]
        # Matching call_types and call_ids
        persisted_task = ConfigTask(node1, Mock(), "", "foo1", "bar1")
        self.assertTrue(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        persisted_task = ConfigTask(node1, Mock(), "", "foo2", "bar2")
        self.assertTrue(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        # Mismatching call_types and call_ids
        persisted_task = ConfigTask(node1, Mock(), "", "foo2", "bar1")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        persisted_task = ConfigTask(node1, Mock(), "", "foo1", "bar2")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        persisted_task = ConfigTask(node1, Mock(), "", "foo2", "bar3")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        persisted_task = ConfigTask(node1, Mock(), "", "foo3", "bar3")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        # Plugin tasks from a different node
        node2 = Mock(vpath='/node2')
        persisted_task = ConfigTask(node2, Mock(), "", "foo1", "bar1")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        persisted_task = ConfigTask(node2, Mock(), "", "foo2", "bar2")
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

        # Pass in callback tasks
        plugin_tasks = [
            CallbackTask(node1, 'Callback 1', Mock()),
            CallbackTask(node1, 'Callback 2', Mock())
        ]
        self.assertFalse(manager.call_type_and_id_in_tasks(
            persisted_task, plugin_tasks))

    def test_fix_plan_invalidate_if_initial_and_plugins_changed(self):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        saved_plugins = [
            PluginInfo("p1", "litp.p1", "1")
        ]
        installed_plugins = []

        plan = Mock()
        plan.mark_invalid = Mock()

        data_manager.get_plugins = Mock(return_value=saved_plugins)
        data_manager.get_extensions = Mock(return_value=[])
        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=installed_plugins)
        plugin_manager.get_extension_info = Mock(return_value=[])

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        plan.is_initial = Mock(return_value=True)
        scope.plan = data_manager.get_plan
        execution_manager.fix_plan_at_service_startup()
        self.assertTrue(plan.mark_invalid.called)

        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=False)
        plan.mark_invalid = Mock()
        scope.plan = data_manager.get_plan

        execution_manager.fix_plan_at_service_startup()
        self.assertFalse(plan.mark_invalid.called)

    def test_fix_plan_invalidate_if_initial_and_extensions_changed(self):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        saved_extensions = [
            ExtensionInfo("e1", "litp.e1", "1")
        ]
        installed_extensions = []

        plan = Mock()
        plan.mark_invalid = Mock()

        data_manager.get_plugins = Mock(return_value=[])
        data_manager.get_extensions = Mock(return_value=saved_extensions)
        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=[])
        plugin_manager.get_extension_info = Mock(return_value=installed_extensions)

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        plan.is_initial = Mock(return_value=True)
        execution_manager.fix_plan_at_service_startup()
        self.assertTrue(plan.mark_invalid.called)
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=False)
        plan.mark_invalid = Mock()
        scope.plan = data_manager.get_plan

        execution_manager.fix_plan_at_service_startup()
        self.assertFalse(plan.mark_invalid.called)

    def test_fix_plan_dont_invalidate_if_initial_and_extensions_plugins_not_changed(self):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        saved_extensions = [
            ExtensionInfo("e1", "litp.e1", "1")
        ]
        installed_extensions = [
            {
                "name": "e1",
                "class": "litp.e1",
                "version": "1"
            }
        ]
        saved_plugins = [
            PluginInfo("p1", "litp.p1", "1")
        ]
        installed_plugins = [
            {
                "name": "p1",
                "class": "litp.p1",
                "version": "1"
            }
        ]

        plan = Mock()
        plan.is_initial = Mock(return_value=True)
        plan.mark_invalid = Mock()
        plan.get_tasks = Mock(return_value=[])

        data_manager.get_plugins = Mock(return_value=saved_plugins)
        data_manager.get_extensions = Mock(return_value=saved_extensions)
        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=installed_plugins)
        plugin_manager.get_extension_info = Mock(return_value=installed_extensions)

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        execution_manager.fix_plan_at_service_startup()

        self.assertFalse(plan.mark_invalid.called)

    def test_fix_plan_exception_if_unknown_plugin(self):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        cb = Mock()
        qitem = Mock()
        task = CallbackTask(qitem, "", cb)
        task._plugin_class = "cb"

        plan = Mock()
        plan.is_initial = Mock(return_value=True)
        plan.mark_invalid = Mock()
        plan.get_tasks = Mock(return_value=[task])

        data_manager.get_plugins = Mock(return_value=[])
        data_manager.get_extensions = Mock(return_value=[])
        data_manager.get_plan = Mock(return_value=plan)

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=[])
        plugin_manager.get_extension_info = Mock(return_value=[])
        plugin_manager.get_plugin = Mock(return_value=None)

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        self.assertRaises(DataIntegrityException, execution_manager.fix_plan_at_service_startup)

    def test_fix_plan_invalidate_if_unknown_callback(self):
        class Plugin:
            pass

        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        cb = Mock()
        qitem = Mock()
        task = CallbackTask(qitem, "", cb)
        task._plugin_class = "cb"

        plan = Mock()
        plan.is_initial = Mock(return_value=True)
        plan.mark_invalid = Mock()
        plan.get_tasks = Mock(return_value=[task])

        data_manager.get_plugins = Mock(return_value=[])
        data_manager.get_extensions = Mock(return_value=[])
        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=[])
        plugin_manager.get_extension_info = Mock(return_value=[])
        plugin_manager.get_plugin = Mock(return_value=Plugin())

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        execution_manager.fix_plan_at_service_startup()

        self.assertTrue(plan.mark_invalid.called)

    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_fix_plan_end_if_active_invalid_celery_task(
            self, mock_execution_manager):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[])

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        execution_manager.fix_plan_at_service_startup()

        self.assertTrue(plan.end.called)

    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=True)
    def test_fix_plan_end_if_active_valid_celery_task(
            self, mock_execution_manager):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[])

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan

        execution_manager.fix_plan_at_service_startup()

        self.assertFalse(plan.end.called)

    @patch.object(celery_inspect, 'active')
    @patch.object(AsyncResult, 'id', new_callable=PropertyMock)
    @patch.object(AsyncResult, 'ready')
    def test_fix_plan_end_if_active_valid_celery_lean_task(
            self, mock_ready, mock_id, mock_active):
        task_id = u'bc73abad-f88e-481a-b78e-97feea878c34'
        mock_ready.return_value = False
        mock_id.return_value = task_id
        mock_active.return_value = {
            u'litpTask@ms1': [],
            u'litpDefault@ms1': [],
            u'litpPlan@ms1': [
                {u'args': u'[]',
                u'time_start': 97979.554220356003,
                u'name': u'litp.core.worker.tasks.run_plan',
                u'delivery_info': {u'priority': None,
                u'redelivered': False,
                u'routing_key': u'litp_plan',
                u'exchange': u'litp_plan'},
                u'hostname': u'litpPlan@ms1',
                u'acknowledged': True,
                u'kwargs': u'{}',
                u'id': task_id,
                u'worker_pid': 18646
                }]
        }

        data_manager = Mock()

        model_manager = MagicMock()
        model_manager.data_manager = data_manager
        model_manager.get_item('/ms').hostname = 'ms1'

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[])
        plan.celery_task_id = u'bc73abad-f88e-481a-b78e-97feea878c34'

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        # lean task does not instanciate puppet_manger or plugin_manger
        puppet_manager = None
        plugin_manager = None
        execution_manager = ExecutionManager(model_manager, puppet_manager, plugin_manager)
        execution_manager.plan = plan

        execution_manager.fix_plan_at_service_startup()

        self.assertFalse(plan.end.called)

    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_fix_plan_tasks_state_if_active_invalid_celery_task(
            self, mock_execution_manager):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        task = Mock()
        task.state = constants.TASK_RUNNING

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[task])

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.fix_plan_at_service_startup()

        self.assertEquals(constants.TASK_FAILED, task.state)
        self.assertTrue(execution_manager._set_applied_properties_determinable.called)

    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_fix_plan_tasks_state_if_active_valid_celerytask(
            self, mock_execution_manager):
        data_manager = Mock()

        model_manager = Mock()
        model_manager.data_manager = data_manager

        task = Mock()
        task.state = constants.TASK_RUNNING

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[task])

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.fix_plan_at_service_startup()

        self.assertEquals(constants.TASK_FAILED, task.state)
        self.assertTrue(execution_manager._set_applied_properties_determinable.called)

    def test_enable_puppet_is_run_before_plan_end(self):
        self._setup_model()
        node_qi = self.qi(self.model.query('node')[0])
        tasks = [ConfigTask(node_qi, node_qi, "Test Task", "call1",
            call_id="type1")]
        self.create_plugin(tasks,[])
        self.manager.create_plan()
        with patch.object(self.manager, '_enable_puppet') as _enable_puppet:
            mock_plan = MagicMock()
            mock_plan.get_tasks.return_value = tasks
            mock_plan.get_phase.return_value = tasks
            self.manager.plan = mock_plan
            self.manager.plan.end = Mock()
            _enable_puppet.side_effect = lambda check_reachable: self.assertFalse(
                    self.manager.plan.end.called,
                    'manager.plan.end() called before _enable_puppet()')
            self.manager._run_plan_start()
            self.manager._run_all_phases()

            self.manager.plan._state = 'Running'
            self.manager._run_plan_complete(True)
            self.assertTrue(_enable_puppet.called)
            self.assertTrue(self.manager.plan.end.called)

    def test_enable_puppet_not_run_on_FR_nodes(self):
        self._setup_model()
        puppet_manager = Mock()
        puppet_manager.node_tasks.keys = lambda: ["ms1", "node1"]
        puppet_manager.mco_processor = Mock()
        puppet_manager.mco_processor.enable_puppet = Mock()

        node_qi = self.qi(self.model.query('node')[0])
        ms_qi = self.qi(self.model.query('ms')[0])

        self.manager = ExecutionManager(self.manager.model_manager, puppet_manager, Mock())
        node_qi._model_item.set_for_removal()

        self.manager._enable_puppet()
        self.assertEqual(
            [call([ms_qi.hostname], timeout=30)],
            puppet_manager.mco_processor.enable_puppet.mock_calls
        )

    @patch.object(celery_inspect, 'active')
    @patch.object(AsyncResult, 'id', new_callable=PropertyMock)
    @patch.object(AsyncResult, 'ready')
    def test_celery_task_is_valid(self, mock_ready, mock_id, mock_active):
        task_id = u'bc73abad-f88e-481a-b78e-97feea878c34'
        mock_ready.return_value = False
        mock_id.return_value = task_id
        mock_active.return_value = {
            u'litpTask@ms1': [],
            u'litpDefault@ms1': [],
            u'litpPlan@ms1': [
                {u'args': u'[]',
                u'time_start': 97979.554220356003,
                u'name': u'litp.core.worker.tasks.run_plan',
                u'delivery_info': {u'priority': None,
                u'redelivered': False,
                u'routing_key': u'litp_plan',
                u'exchange': u'litp_plan'},
                u'hostname': u'litpPlan@ms1',
                u'acknowledged': True,
                u'kwargs': u'{}',
                u'id': task_id,
                u'worker_pid': 18646
                }]
        }

        plan = MagicMock()
        plan.celery_task_id = task_id
        self.assertTrue(self.manager.celery_task_is_valid(plan))

        plan.celery_task_id = 'Totally-different-id'
        self.assertFalse(self.manager.celery_task_is_valid(plan))

        plan.celery_task_id = task_id
        mock_ready.return_value = True
        self.assertFalse(self.manager.celery_task_is_valid(plan))

        plan.celery_task_id = task_id
        mock_ready.return_value = False
        mock_id.return_value = 'Different-celery-task-id-in-AsyncResult'
        self.assertFalse(self.manager.celery_task_is_valid(plan))

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_plan_running( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = u'fde7:a76a:7711::/48'
        mock_ready.return_value = True
        mock_status.return_value = 'Failed'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.celery_task_id = task_id
        plan.is_running = Mock(return_value=True)

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.monitor_plan()

        self.assertTrue(execution_manager._fix_plan.called)

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_plan_and_celery_running( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = u'fd96:36fd:1267::/48'
        mock_ready.return_value = False
        mock_status.return_value = 'Started'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.celery_task_id = task_id
        plan.is_running = Mock(return_value=True)

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.monitor_plan()

        self.assertFalse(execution_manager._fix_plan.called)

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_plan_and_celery_not_running( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = u'fd96:36fd:1267::/48'
        mock_ready.return_value = True
        mock_status.return_value = 'Success'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.celery_task_id = task_id
        plan.is_running = Mock(return_value=False)

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.monitor_plan()

        self.assertFalse(execution_manager._fix_plan.called)

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_plan_running_celery_success( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = u'fd96:36fd:1267::/48'
        mock_ready.return_value = True
        mock_status.return_value = 'Success'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.celery_task_id = task_id
        plan.is_running = Mock(return_value=True)

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.monitor_plan()

        self.assertTrue(execution_manager._fix_plan.called)

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_no_plan( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = u'fd87:8206:6e94::/48'
        mock_ready.return_value = True
        mock_status.return_value = 'Success'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = None

        execution_manager.monitor_plan()

        self.assertFalse(execution_manager._fix_plan.called)

    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'ready')
    @patch.object(ExecutionManager, '_fix_plan')
    @patch.object(ExecutionManager, 'celery_task_is_valid', return_value=False)
    def test_monitor_plan_not_started_yet( self, celery_task_is_valid, _fix_plan, mock_ready, mock_status):
        task_id = None
        mock_ready.return_value = True
        mock_status.return_value = 'Initial'

        data_manager = Mock()
        model_manager = Mock()
        model_manager.data_manager = data_manager

        plan = Mock()
        plan.celery_task_id = task_id
        plan.is_running = Mock(return_value=False)

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        plugin_manager = Mock()

        execution_manager = ExecutionManager(model_manager, Mock(), plugin_manager)
        execution_manager.plan = plan
        execution_manager._set_applied_properties_determinable = Mock()

        execution_manager.monitor_plan()

        self.assertFalse(execution_manager._fix_plan.called)

    @patch.object(celery_inspect, 'active')
    @patch.object(AsyncResult, 'status')
    @patch.object(AsyncResult, 'id', new_callable=PropertyMock)
    @patch.object(AsyncResult, 'ready')
    def test_monitor_plan_lean_task(
            self, mock_ready, mock_id, mock_status, mock_active):
        task_id = u'bc73abad-f88e-481a-b78e-97feea878c34'
        mock_ready.return_value = True
        mock_status.return_value = 'Initial'
        mock_id.return_value = task_id
        mock_active.return_value = {
            u'litpTask@ms1': [],
            u'litpDefault@ms1': [],
            u'litpPlan@ms1': [
                {u'args': u'[]',
                u'time_start': 97979.554220356003,
                u'name': u'litp.core.worker.tasks.run_plan',
                u'delivery_info': {u'priority': None,
                u'redelivered': False,
                u'routing_key': u'litp_plan',
                u'exchange': u'litp_plan'},
                u'hostname': u'litpPlan@ms1',
                u'acknowledged': True,
                u'kwargs': u'{}',
                u'id': task_id,
                u'worker_pid': 18646
                }]
        }

        data_manager = Mock()

        model_manager = MagicMock()
        model_manager.data_manager = data_manager
        model_manager.get_item('/ms').hostname = 'ms1'

        plan = Mock()
        plan.end = Mock()
        plan.is_initial = Mock(return_value=False)
        plan.is_active = Mock(return_value=True)
        plan.get_tasks = Mock(return_value=[])
        plan.celery_task_id = u'bc73abad-f88e-481a-b78e-97feea878c34'

        data_manager.get_plan = Mock(return_value=plan)
        scope.plan = data_manager.get_plan

        # lean task does not instanciate puppet_manger or plugin_manger
        puppet_manager = None
        plugin_manager = None
        execution_manager = ExecutionManager(model_manager, puppet_manager, plugin_manager)
        execution_manager.plan = plan

        execution_manager.monitor_plan()

        self.assertTrue(plan.end.called)

    def test_task_filtering_for_removal_node(self):
        tasks = []
        self._setup_model()
        node1_qi = self.api.query_by_vpath('/deployments/d1/clusters/c1/nodes/node1')

        node2 = self.model.create_item(
            "node", "/deployments/d1/clusters/c1/nodes/node2",
            hostname="othernode", name="bleep",
            another_property="bloop"
        )
        node2_qi = self.api.query_by_vpath('/deployments/d1/clusters/c1/nodes/node2')

        self.model.create_item("type_c", "/deployments/d1/clusters/c1/nodes/node2/comp2")
        self.model.set_all_applied()

        cluster_qi = self.api.query_by_vpath("/deployments/d1/clusters/c1")
        node_qis = [self.qi(node) for node in self.model.query("node") if not node.is_ms()]

        # This would cause both nodes to be ForRemoval
        # self.model.remove_item(cluster_qi.vpath)
        self.model.remove_item(node2.vpath)

        self.plugin = TestPlugin()

        plugin_tasks = []
        plugin_tasks += [
            ConfigTask(
                node_qi, node_qi, "Configtask for %s" % node_qi.item_id,
                "foo", "%s_resource" % node_qi.hostname
            ) for node_qi in node_qis
        ]
        plugin_tasks += [
            CallbackTask(
                node_qi, "CallbackTask for %s" % node_qi.item_id,
                self.plugin.callback_method,
            ) for node_qi in node_qis
        ]

        expected = [
            ConfigTask(
                node1_qi, node1_qi, "Configure configtask for node1", "foo",
                "node_resource"
            ),
            CallbackTask(node1_qi, "CallbackTask for node1", self.plugin.callback_method),
            CallbackTask(node2_qi, "CallbackTask for node2", self.plugin.callback_method),
        ]

        filtered_tasks = self.manager._filter_faulty_node_configtasks(plugin_tasks)
        self.assertEqual(set(expected), set(filtered_tasks))

    @patch('litp.core.execution_manager.ExecutionManager._enqueue_ready_phases')
    def test_update_item_states_called(self, mock_enque):
        # TORF-156510: Test async_result.result returning a dict with error
        self.manager.plan = Mock(
            _id=1, is_stopping=lambda: False, phases=[[]])
        self.manager._fail_running_tasks = lambda a: None
        self.manager._update_item_states = Mock()

        def enqueue_mock_result(errors, last_phase_idx=-1):
            self.manager._active_phases[last_phase_idx] = \
                Mock(result=None, failed=lambda: True)

        mock_enque.side_effect = enqueue_mock_result
        self.manager._run_all_phases()
        self.assertEquals(1, self.manager._update_item_states.call_count)

    def test_reboot_plan_tasks(self):
        # Set up a model that will create lock tasks
        self._create_sample_model_for_locking_template(
                       TestPluginLockTasksOnly())
        self.model.set_all_applied()
        mock_reboot_tasks = [CallbackTask(QueryItem(self.model, self.model.query('node')[0]),
                                          "something",
                                          MagicMock())]
        with patch.object(self.manager, '_get_core_plugin') as gcp:
            crt = MagicMock()
            crt.create_reboot_tasks.return_value = mock_reboot_tasks
            gcp.return_value = crt
            plan = self.manager._create_plan('Reboot')
            self.assertEqual(3, len(plan.phases))
            self.assertEqual(mock_reboot_tasks, plan.phases[1])

            for phase in plan.phases:
                self.assertEqual(1, len(phase))

    def test_reboot_plan_validation(self):
        with patch.object(self.manager, '_get_core_plugin') as gcp:
            crt = MagicMock()
            crt.validate_reboot_plan.return_value = [ValidationError(
                item_path='path',
                error_message="Path not found",
                error_type=constants.INVALID_LOCATION_ERROR
            )]
            gcp.return_value = crt
            self.assertEqual([{'message': 'Path not found',
                               'uri': 'path',
                               'error': 'InvalidLocationError'}],
                             self.manager._create_plan_with_type('Reboot'))

    def test_reboot_plan_no_ssreset_and_not_set_all_applied(self):
        self.manager.puppet_manager = MagicMock()
        self.manager.plan = MagicMock()
        ssa = MagicMock()
        saa = MagicMock()
        rpa = MagicMock()
        self.manager.model_manager.set_snapshot_applied = ssa
        self.manager.model_manager.set_all_applied = saa
        self.manager._reset_phase_atts = rpa

        self.manager._clear_plan(True)
        # set_snapshot_applied and set_all_applied were not called, but the
        # whole method ran because _reset_phase_atts was
        ssa.assert_has_calls([])
        saa.assert_has_calls([])
        rpa.assert_called_once()


class ConfigTaskTest(unittest.TestCase):
    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(ItemType("root",
            nodes=Collection("node"),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            components=Collection("component"),
            other_component=Child("component_mod"),
        ))

        self.model.register_item_type(ItemType("component",
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))
        self.model.register_item_type(ItemType("component_mod",
            extend_item="component"))


        self.model.create_root_item("root")
        self.node1 = self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.node1 = self._convert_to_query_item(self.node1)
        self.node2 = self.model.create_item("node", "/nodes/node2", hostname="node2")
        self.node2 = self._convert_to_query_item(self.node2)
        self.model.create_item("component", "/nodes/node1/components/component")
        self.model.create_item("component_mod", "/nodes/node1/other_component")
        self.model.create_item("component", "/nodes/node2/components/component")
        self.model.create_item("component_mod", "/nodes/node2/other_component")

        self.reference_task = ConfigTask(
                self.node1,
                self.node1.components.component,
                "Irrelevant",
                "alpha::bravo", "foo",
                foo='bar', bar=[2,3])

        self.task_no_kwargs = ConfigTask(self.node1,
                self.node1.components.component, "blah", "alpha::bravo",
                "foo")

    def test_equality_self(self):
        self.assertEquals(self.reference_task, self.reference_task)
        self.assertEquals(hash(self.reference_task),
                hash(self.reference_task))

    def test_equality_diff_node(self):
        task_different_node = ConfigTask(
                self.node2,
                self.node2.components.component,
                "XXX", "XXX", "XXX")
        self.assertNotEquals(self.reference_task, task_different_node)
        self.assertNotEquals(task_different_node, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_different_node))

    def test_equality_diff_item(self):
        task_diff_item = ConfigTask(
                self.node1,
                self.node1.other_component,
                "XXX", "XXX", "XXX")
        self.assertNotEquals(self.reference_task, task_diff_item)
        self.assertNotEquals(task_diff_item, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_item))

    def test_equality_diff_resource_type(self):
        task_diff_resource_type = ConfigTask(
                self.node1,
                self.node1.components.component,
                "blah",
                "alpha::charlie",
                "XXX")
        self.assertNotEquals(self.reference_task, task_diff_resource_type)
        self.assertNotEquals(task_diff_resource_type, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_resource_type))

    def test_equality_diff_id(self):
        task_diff_id = ConfigTask(self.node1,
                self.node1.components.component, "blah", "alpha::bravo",
                "GRUNK")
        self.assertNotEquals(self.reference_task, task_diff_id)
        self.assertNotEquals(task_diff_id, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_id))

    def test_equality_diff_deconfigure(self):
        task_diff_deconfigure = ConfigTask(self.node1,
                self.node1.components.component,
                "blah",
                "alpha::bravo",
                "foo")
        self.assertNotEquals(self.reference_task, task_diff_deconfigure)
        self.assertNotEquals(task_diff_deconfigure, self.reference_task)

    def test_equality_diff_kwargs(self):
        self.assertNotEquals(self.reference_task, self.task_no_kwargs)
        self.assertNotEquals(self.task_no_kwargs, self.reference_task)

        task_diff_kwargs = ConfigTask(self.node1,
                self.node1.components.component,
                "blah",
                "alpha::bravo",
                "foo",
                baz='foo')
        self.assertNotEquals(self.reference_task, task_diff_kwargs)
        self.assertNotEquals(task_diff_kwargs, self.reference_task)

    def test_equality_identical(self):
        task_identical = ConfigTask(self.node1,
                self.node1.components.component,
                "Irrelevant",
                "alpha::bravo",
                "foo",
                foo='bar', bar=[2,3])
        self.assertEquals(self.reference_task, task_identical)
        self.assertEquals(task_identical, self.reference_task)
        self.assertEquals(hash(self.reference_task),
                hash(task_identical))

    def test_task_vpath(self):
        self.assertEquals('/nodes/node1/components/component',
                self.reference_task.item_vpath)

    def test_task_node(self):
        self.assertEquals(self.node1, self.reference_task.get_node())

    def test_task_unique_id(self):
        # We're testing clean_classname here
        self.assertEquals(self.reference_task.unique_id,
                self.reference_task.unique_id)

        task_upper_case = ConfigTask(self.node1,
                self.node1.components.component,
                "blah",
                "FOO::BAR",
                "BAZ",
                foo='bar', bar=[2,3])

        self.assertEquals(task_upper_case.unique_id,
                task_upper_case.unique_id)

    def test_format_parameters(self):
        self.assertEquals(
                {
                    "description": "Irrelevant",
                    "call_id": "foo",
                    "call_type": "alpha::bravo",
                    "node": {
                        "type": "node",
                        "id": "node1",
                        "uri": "/item-types/node",
                        },
                    "model_item": {
                        "type": "component",
                        "id": "component",
                        "uri": "/item-types/component",
                        },
                    "kwargs": "{'foo': 'bar', 'bar': [2, 3]}"
                },
                self.reference_task.format_parameters()
                )

        self.assertEquals(
                {
                    "description": "blah",
                    "call_id": "foo",
                    "call_type": "alpha::bravo",
                    "node": {
                        "type": "node",
                        "id": "node1",
                        "uri": "/item-types/node",
                        },
                    "model_item": {
                        "type": "component",
                        "id": "component",
                        "uri": "/item-types/component",
                        },
                    "kwargs": ""
                },
                self.task_no_kwargs.format_parameters()
                )

    def test_has_run(self):
        self.assertFalse(self.reference_task.has_run())
        self.reference_task.state = 'foo'
        # TODO This is nonsensical!!
        self.assertTrue(self.reference_task.has_run())


class CallbackTaskTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(ItemType("root",
            nodes=Collection("node"),
            ms=Child('node'),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            component=Child("component"),
            other_component=Child("component_mod"),
        ))
        self.model.register_item_type(ItemType("component",
            res=Child("package"),
        ))

        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        self.model.register_item_type(ItemType("component_mod",
            extend_item="component"))

        #
        self.model.create_root_item("root")
        self.model.create_item("node", "/ms", hostname='ms1')
        self.node1 = self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.node2 = self.model.create_item("node", "/nodes/node2", hostname="node2")

        self.model.create_item("component", "/nodes/node1/component")
        self.model.create_item("component", "/nodes/node1/other_component")
        self.model.create_item("component", "/nodes/node2/component")
        self.model.create_item("component", "/nodes/node2/other_component")

        self.plugin = TestPlugin()
        self.node1_component_query_item = QueryItem(self.model, self.node1.component)
        self.node2_component_query_item = QueryItem(self.model, self.node2.component)

        self.reference_task = CallbackTask(
                self.node1_component_query_item,
                "Irrelevant",
                self.plugin.callback_method,
                'foo', 'bar',
                foo='bar', bar=[2,3])

        self.task_no_pos_args = CallbackTask(
                self.node1_component_query_item,
                "Irrelevant",
                self.plugin.callback_method,
                foo='bar', bar=[2,3])

        self.task_no_kwargs = CallbackTask(
                self.node1_component_query_item,
                "Irrelevant",
                self.plugin.callback_method,
                'foo', 'bar',
                )

        self.task_no_args = CallbackTask(
                self.node1_component_query_item,
                "Irrelevant",
                self.plugin.callback_method)


    def test_equality_self(self):
        self.assertEquals(self.reference_task, self.reference_task)
        self.assertEquals(hash(self.reference_task),
                hash(self.reference_task))

    def test_equality_diff_item(self):
        task_diff_item = CallbackTask(self.node2_component_query_item,
                "blah",
                self.plugin.callback_method,
                "foo", "bar",
                foo='bar', bar=[2,3])

        self.assertNotEquals(self.reference_task, task_diff_item)
        self.assertNotEquals(task_diff_item, self.reference_task)
        self.assertNotEquals(hash(self.reference_task), hash(task_diff_item))

    def test_equality_diff_callback(self):
        task_diff_callback = CallbackTask(self.node2_component_query_item,
                "blah",
                self.plugin.callback_method_wait,
                "foo", "bar",
                foo='bar', bar=[2,3])

        self.assertNotEquals(self.reference_task, task_diff_callback)
        self.assertNotEquals(task_diff_callback, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_callback))

    def test_equality_diff_args(self):
        self.assertNotEquals(self.reference_task, self.task_no_pos_args)
        self.assertNotEquals(self.task_no_pos_args, self.reference_task)

        self.assertNotEquals(self.reference_task, self.task_no_args)
        self.assertNotEquals(self.task_no_args, self.reference_task)

        task_diff_args = CallbackTask(self.node2_component_query_item,
                "blah",
                self.plugin.callback_method_wait,
                123, 456,
                foo='bar', bar=[2,3])

        self.assertNotEquals(self.reference_task, task_diff_args)
        self.assertNotEquals(task_diff_args, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_args))
        self.assertNotEquals(hash(self.reference_task),
                hash(self.task_no_args))
        self.assertNotEquals(hash(self.reference_task),
                hash(self.task_no_pos_args))

    def test_equality_diff_kwargs(self):
        self.assertNotEquals(self.reference_task, self.task_no_kwargs)
        self.assertNotEquals(self.task_no_kwargs, self.reference_task)

        task_diff_kwargs = CallbackTask(self.node2_component_query_item,
                "blah",
                self.plugin.callback_method_wait,
                "foo", "bar",
                foo='blah', baz=[100])

        self.assertNotEquals(self.reference_task, task_diff_kwargs)
        self.assertNotEquals(task_diff_kwargs, self.reference_task)
        self.assertNotEquals(hash(self.reference_task),
                hash(task_diff_kwargs))

    def test_equality_identical(self):
        task_identical = CallbackTask(self.node1_component_query_item,
                "blah",
                self.plugin.callback_method,
                "foo", "bar",
                foo='bar', bar=[2,3])

        self.assertEquals(self.reference_task, task_identical)
        self.assertEquals(task_identical, self.reference_task)
        self.assertEquals(hash(self.reference_task), hash(task_identical))

    def test_repr(self):
        self.assertEquals(
                "<CallbackTask /nodes/node1/component - callback_method: ('foo', 'bar') [Initial]>",
                repr(self.reference_task))

        self.assertEquals(
                "<CallbackTask /nodes/node1/component - callback_method:  [Initial]>",
                repr(self.task_no_args))

    def test_task_vpath(self):
        self.assertEquals('/nodes/node1/component',
                self.reference_task.item_vpath)

    def test_task_call_type(self):
        self.assertEquals('callback_method', self.reference_task.call_type)
        self.assertEquals('test_execution_manager.TestPlugin',
            self.reference_task.plugin_class)

    def test_task_unique_id(self):
        # We're testing clean_classname here
        self.assertEquals(self.reference_task.unique_id,
                self.reference_task.unique_id)

    def test_has_run(self):
        self.assertFalse(self.reference_task.has_run())
        self.reference_task.state = 'foo'
        # TODO This is nonsensical!!
        self.assertTrue(self.reference_task.has_run())

    def test_format_parameters(self):
        self.assertEquals(
                {
                    "description": "Irrelevant",
                    "call_type": "callback_method",
                    "model_item": {
                        "type": "component",
                        "id": "component",
                        "uri": "/item-types/component",
                        },
                    "kwargs": "{'foo': 'bar', 'bar': [2, 3]}"
                },
                self.reference_task.format_parameters()
                )

        self.assertEquals(
                {
                    "description": "Irrelevant",
                    "call_type": "callback_method",
                    "model_item": {
                        "type": "component",
                        "id": "component",
                        "uri": "/item-types/component",
                        },
                    "kwargs": ""
                },
                self.task_no_kwargs.format_parameters()
                )


    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', return_value='snapshot')
    @patch('litp.core.rpc_commands.PuppetMcoProcessor.enable_puppet', return_value=None)
    def test_snapshot_timestamp_updated_twice(self, action, name, mco_processor):
        task1 = Mock()
        task1.callback.side_effect = CallbackExecutionException
        task1.all_model_items = set()

        plan = MagicMock()
        plan.__class__ = SnapshotPlan

        plan.phases = [[task1], [task1], [task1]]
        plan.is_stopping.return_value = False

        model_manager = Mock()
        model_manager.get_all_nodes.return_value = []
        snapshot_item = model_manager.get_item.return_value
        snapshot_item.vpath = '/snapshots/snapshot'
        snapshot_item.is_for_removal.return_value = False
        snapshot_item.is_removed.return_value = False
        puppet_manager = Mock()
        puppet_manager.node_tasks.keys = lambda: ["a", "b"]

        self.manager = ExecutionManager(model_manager, puppet_manager, Mock())
        self.manager.plan = plan
        self.manager._backup_model_for_snapshot = MagicMock(return_value=True)
        self.manager._run_phase = MagicMock(return_value=False)
        self.manager._update_ss_timestamp = MagicMock()
        self.manager.current_snapshot_object = MagicMock(return_value=snapshot_item)
        self.model.create_snapshot_item('snapshot')
        self.manager._run_plan_phase(0)
        self.manager._run_plan_phase(1)
        self.manager._run_plan_phase(2)
        self.assertEquals(self.manager._update_ss_timestamp.call_count, 2)

    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='remove')
    @patch('litp.core.plugin_context_api.PluginApiContext.snapshot_name', return_value='snapshot')
    @patch('litp.core.rpc_commands.PuppetMcoProcessor.enable_puppet', return_value=None)
    def test_snapshot_timestamp_updated_once(self, action, name, mco_processor):
        # remove_snapshot should call update_timestamp failed once, but should
        # not call update_timestamp_successful at all
        task1 = Mock()
        task1.callback.side_effect = CallbackExecutionException
        task1.all_model_items = set()

        plan = MagicMock()
        plan.__class__ = SnapshotPlan

        plan.phases = [[task1], [task1], [task1]]
        plan.is_stopping.return_value = False

        model_manager = Mock()
        model_manager.get_all_nodes.return_value = []
        snapshot_item = model_manager.get_item.return_value
        snapshot_item.vpath = '/snapshots/snapshot'
        snapshot_item.is_for_removal.return_value = False
        snapshot_item.is_removed.return_value = True
        puppet_manager = Mock()
        puppet_manager.node_tasks.keys = lambda: ["a", "b"]

        self.manager = ExecutionManager(model_manager, puppet_manager, Mock())
        self.manager.plan = plan
        self.manager._backup_model_for_snapshot = MagicMock(return_value=True)
        self.manager._run_phase = MagicMock(return_value=False)
        self.manager._update_ss_timestamp_failed = MagicMock()
        self.manager._update_ss_timestamp_successful = MagicMock()
        self.manager.current_snapshot_object = MagicMock(return_value=snapshot_item)
        self.manager.invalidate_snapshot_model = MagicMock()
        self.model.create_snapshot_item('snapshot')
        self.manager._run_plan_phase(0)
        self.manager._run_plan_phase(1)
        self.manager._run_plan_phase(2)
        self.assertEquals(self.manager._update_ss_timestamp_failed.call_count, 1)
        self.assertEquals(self.manager._update_ss_timestamp_successful.call_count, 0)
