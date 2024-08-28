
import unittest
import cherrypy

from litp.core.execution_manager import CallbackTask
from litp.core.model_manager import ModelManager
from litp.core.model_manager import QueryItem
from litp.core.execution_manager import ConfigTask
from litp.core.execution_manager import ExecutionManager
from litp.core.plugin_manager import PluginManager
from litp.core.plugin import Plugin
from litp.core.puppet_manager import PuppetManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Collection
from litp.core.model_type import Property
from litp.core.model_type import Child
from litp.core.model_type import View
from litp.core.plan import Plan
from litp.core.litp_threadpool import Job
from litp.core.config import config
from litp.extensions.core_extension import CoreExtension
from litp.core.worker.celery_app import celery_app
from litp.plan_types.deployment_plan import deployment_plan_groups
from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.constants import CURRENT_PLAN_ID
from litp.core.constants import TASK_SUCCESS
from litp.data.test_db_engine import get_engine
from litp.core import scope
from contextlib import contextmanager
from mock import patch
from litp.plan_types.deployment_plan import deployment_plan_groups


celery_app.conf.CELERY_ALWAYS_EAGER = True


class MockJob(object):
    def __init__(self):
        self.processing = True
        self.executed_tasks = []

    def stop(self):
        self.processing = False


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

    def add_phase(self, task_list, phase_id):
        self.phase_ids.append(phase_id)
        self.phases.append(task_list)

    def wait_for_phase(self, nodes, timeout=600, poll_freq=60, poll_count=60):
        self._waited_for_phase = True
        for task in self.phases[self.phase_index]:
            task.state = "Success"
        self.phase_index += 1
        return not bool(self._error), self._error

    def apply_nodes(self):
        self._applied_configuration = True

    def disable_puppet_on_hosts(self, hostnames=None, task_state=TASK_SUCCESS):
        return


class MockPlugin(Plugin):
    def create_configuration(self, plugin_api_context):
        nodes = plugin_api_context.query("node")
        tasks = []
        for node in nodes:
            tasks.append(ConfigTask(node, node, "test", "type", "id"))
        return tasks


class ExecutionManagerOrderingTest(unittest.TestCase):
    def setUp(self):

        self.db_storage = DbStorage(get_engine())
        self.db_storage.reset()
        self.data_manager = DataManager(self.db_storage.create_session())

        self.model = ModelManager()
        self.data_manager.configure(self.model)
        self.model.data_manager = self.data_manager

        self.plugin_manager = PluginManager(self.model)
        self.plugin_manager.add_plugin("mock", "MockPlugin", "1.1",
            MockPlugin())
        self.puppet_manager = MockPuppetManager(self.model)
        self.execution = ExecutionManager(self.model,
                                        self.puppet_manager,
                                        self.plugin_manager)
        self.execution._phase_id = self.mock_phase_id

        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(ItemType("root",
            deployments=Collection("deployment"),
        ))
        self.model.register_item_type(ItemType("deployment",
            clusters=Collection("cluster-base"),
            ordered_clusters=View("basic_list",
                callable_method=CoreExtension.get_ordered_clusters),
        ))
        self.model.register_item_type(ItemType("cluster-base",
            nodes=Collection("node"),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            #comp1=Child("type_a", require="comp3"),
            #comp2=Child("type_a"),
            comps=Collection("type_a"),
            comp3=Child("type_b", require="comp2"),
            is_locked=Property("basic_string", default="false"),
        ))
        self.model.register_item_type(ItemType("type_b",
            res=Child("package"),
        ))

        self.model.register_item_type(ItemType("type_a",
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        self.model.create_root_item("root")

        cherrypy.config.update({
        'db_storage': self.db_storage,
        'model_manager': self.model,
        'puppet_manager': self.puppet_manager,
        'execution_manager': self.execution,
        'plugin_manager': self.plugin_manager,
        'dbase_root':'/pathdoesnotexist',
        'last_successful_plan_model':'NONEXISTENT_RESTORE_FILE',
        })

    def mock_phase_id(self, phase_index):
        return "%s" % (phase_index)

    def test_basic_run(self):
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster-base", "/deployments/d1/clusters/c1")
        self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/node1", hostname="node1")

        self.execution.create_plan()

        self.assertEquals(1, len(self.execution.plan.phases))

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

    @patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    def test_ordered_plan(self, get_worker, metrics, config_worker, worker):
        get_worker.return_value = ExecutionManagerOrderingTest.worker_context.__func__
        self.model.create_item("deployment", "/deployments/d1")
        self.model.create_item("cluster-base", "/deployments/d1/clusters/c1")
        node = self.model.create_item("node", "/deployments/d1/clusters/c1/nodes/node1", hostname="node1")

        self.node = QueryItem(self.model, node)
        self.execution.plan = Plan([], [])

        self.task1 = ConfigTask(self.node, self.node, "task1", "task", "1")
        self.task3 = ConfigTask(self.node, self.node, "task3", "task", "3")
        self.ordered_1 = ConfigTask(self.node, self.node, "ordered1", "ord", "1")
        self.ordered_2 = ConfigTask(self.node, self.node, "ordered2", "ord", "2")
        self.ordered_3 = ConfigTask(self.node, self.node, "ordered3", "ord", "3")

        self.execution.plan._phases = [
            [self.task1],
            [self.ordered_1, self.ordered_2, self.ordered_3],
            [self.task3],
        ]
        self.execution.plan.set_ready()

        self.execution.run_plan()

        self.assertEquals([
            [self.task1],
            [self.ordered_1, self.ordered_2, self.ordered_3],
            [self.task3],
        ], self.puppet_manager.phases)
