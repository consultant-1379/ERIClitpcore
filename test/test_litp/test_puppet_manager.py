import unittest
import mock
import tempfile
import functools
import contextlib
import os
import itertools
from StringIO import StringIO
from collections import defaultdict

import cherrypy

from litp.core.task import ConfigTask, CleanupTask
from litp.core.plan import Plan
from litp.core.execution_manager import ExecutionManager
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.model_type import ItemType
from litp.core.model_type import Child
from litp.core.model_type import Property
from litp.core.model_type import Collection
from litp.core.puppet_manager import PuppetManager
from litp.core.plugin_manager import PluginManager
from litp.core.plugin_context_api import PluginApiContext
from litp.core.model_type import PropertyType
from litp.core import constants
from litp.core.exceptions import ServiceKilledException, McoFailed, FailedTasklessPuppetEvent
from mock import call, MagicMock
from litp.core.worker.celery_app import celery_app
from litp.data.db_storage import DbStorage
from litp.data.data_manager import DataManager
from litp.data.test_db_engine import get_engine

celery_app.conf.CELERY_ALWAYS_EAGER = True

def generate_n_config_tasks(tasks_count, node, model_manager):
    tasks = []
    for i, _ in enumerate(range(tasks_count), start=1):
        description = 'ConfigTasks node "{0}"'.format(node.hostname)
        call_type = str(i)
        call_id = "{0}_{0}".format(i)
        tasks.append(ConfigTask(node, node, description, call_type, call_id))
    return tasks


def set_tasks_state(state, *tasks):
    for task in tasks:
        task.state = state


def call_count(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        wrapper.call_count += 1
        return func(*args, **kwargs)
    wrapper.call_count = 0
    return wrapper


@contextlib.contextmanager
def mocked_fsync():
    try:
        _old_fsync = os.fsync
        os.fsync = lambda fd: None
        yield
    finally:
        os.fsync = _old_fsync


def give_results(results):
    for result in results:
        yield result


puppet_applying = {
        "ms1": {"data":
                    {"status": "idling",
                     "applying": True,
                     "action": "status"},
                "errors": "",
                },
        }


puppet_not_applying = {
        "ms1": {"data":
                    {"status": "idling",
                     "applying": False,
                     "action": "status"},
                "errors": "",
                },
        }


puppet_mixed_applying = {
        'node1': {'data': {'applying': False,
           'daemon_present': True,
           'disable_message': '',
           'enabled': True,
           'idling': False,
           'lastrun': 1429616319,
           'message': 'Currently applying a catalog; last completed run 1 minutes 05 seconds ago',
           'since_lastrun': 65,
           'status': 'applying a catalog'},
          'errors': ''},
         'node2': {'data': {'applying': True,
          'daemon_present': True,
           'disable_message': '',
           'enabled': True,
           'idling': False,
           'lastrun': 1429616313,
           'message': 'Currently applying a catalog; last completed run 1 minutes 08 seconds ago',
           'since_lastrun': 68,
           'status': 'applying a catalog'},
          'errors': ''}}


class MockFile(object):
    def __init__(self):
        self.filebuf = ""
        self.fileno = lambda: 3
        self.permissions = 0666
        self.name = ""
        self.group = ""
        self.user = ""

    def write(self, contents):
        self.filebuf += contents

    def close(self):
        pass

    def flush(self):
        pass

    def read(self):
        return self.filebuf

    def seek(self, size):
        pass

    def truncate(self):
        self.filebuf = ""


class MockTask(object):
    def __init__(self, state="Initial"):
        self.state = state
        self.call_type = None
        self.kwargs = None

class BasePuppetManagerTest(unittest.TestCase):
    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def _mock_mco_timeouts(self):
        self.manager.mco_processor._wait = mock.MagicMock()
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 3
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.0001 # seconds
        self.manager.mco_processor.MCO_CLI_TIMEOUT = 0.001  # seconds
        self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.1  # seconds

    def setUp(self):
        self.db_storage = DbStorage(get_engine())
        self.db_storage.reset()
        self.data_manager = DataManager(self.db_storage.create_session())

        self.model = ModelManager()
        self.data_manager.configure(self.model)
        self.model.data_manager = self.data_manager

        self.context_api = PluginApiContext(self.model)

        self.plugin_manager = PluginManager(self.model)

        self.manager = PuppetManager(self.model)

        self.execution_manager = ExecutionManager(
            self.model,
            None,
            self.plugin_manager)

        cherrypy.config.update({
            'db_storage': self.db_storage,
            'model_manager': self.model,
            'puppet_manager': self.manager,
            'execution_manager': self.execution_manager,
            'plugin_manager': self.plugin_manager,
            'dbase_root':'/pathdoesnotexist',
            'last_successful_plan_model':'NONEXISTENT_RESTORE_FILE',
        })

        self._files = dict()
        self.manager._open_file = self._mock_open
        self.manager._remove_file = self._mock_remove
        self.manager._exists = self._mock_exists
        self.manager._makedirs = lambda d: None
        self.manager._fchmod = self._mock_fchmod
        self.manager._fchown = self._mock_fchown
        self.manager.get_ms_hostname = self._mock_get_ms_hostname

        self.model.register_property_type(PropertyType("basic_string"))

        self.model.register_item_type(ItemType("root",
            nodes=Collection("node"),
            ms=Collection("node"),
        ))
        self.model.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            name=Property("basic_string", updatable_plugin=True),
            comp1=Child("component"),
            comp2=Child("another-component"),
        ))
        self.model.register_item_type(ItemType("component",
            packages=Collection("package"),
            res=Child("package"),
        ))
        self.model.register_item_type(ItemType("another-component",
            extend_item="component"
        ))

        self.model.register_item_type(ItemType("package",
            name=Property("basic_string"),
        ))

        self.model.create_root_item("root")
        self.model.create_item("node", "/ms", hostname="ms1")

        self.manager.mco_processor._run_puppet_command = self._mock_run_puppet_command

        self.manager._sleep = self._mock_sleep
        self.slept = 0

    def _convert_to_query_item(self, model_item):
        return QueryItem(self.model, model_item)

    def _mock_fchmod(self, file_instance, mode):
        self._files[file_instance.name].permissions = mode

    def _mock_fchown(self, file_instance):
        self._files[file_instance.name].group = PuppetManager.DEFAULT_GROUP
        self._files[file_instance.name].user = PuppetManager.CELERY_USER

    def _mock_run_puppet_command(self, hostnames, agent, action, action_kwargs):
        return dict(
                (hostname, {"errors": "", "data":{"idling":True, "present":0, "is_running": False}}) for hostname in hostnames
        )

    def _mock_open(self, filename, mode="w"):
        if filename not in self._files:
            self._files[filename] = MockFile()
            self._files[filename].name = filename
        return self._files[filename]

    def _mock_remove(self, filename):
        if filename in self._files:
            del self._files[filename]

    def _mock_exists(self, filename):
        return filename in self._files

    def _mock_sleep(self, seconds):
        self.slept += seconds

    def _mock_get_ms_hostname(self):
        return "ms_hostname"

class PuppetManagerTest(BasePuppetManagerTest):

    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file')
    def test_write_new_config_version(self, mock_write):
        # TORF-124437
        with mocked_fsync():
            version = self.manager.write_new_config_version()
        self.assertEqual(1, version)
        # Assert config_version is incremented on subsequent calls
        with mocked_fsync():
            version = self.manager.write_new_config_version()
        self.assertEqual(2, version)

    @mock.patch.object(PuppetManager, '_process_feedback', mock.Mock())
    @mock.patch('litp.core.puppet_manager.time.sleep', mock.Mock())
    @mock.patch.object(PuppetManager, '_is_puppet_alive')
    def test_wait_for_phase_dont_poll_processed_nodes(self, mock_is_pp_alive):
        manager = PuppetManager(mock.Mock())

        def mock_processed_nodes(hostnames):
            if mock_is_pp_alive.call_count == 1:
                manager._processed_nodes.add('ms1')
            elif mock_is_pp_alive.call_count == 2:
                manager._processed_nodes.add('node1')
            elif mock_is_pp_alive.call_count == 3:
                manager._processed_nodes.add('node2')

        mock_is_pp_alive.side_effect = mock_processed_nodes
        mock_phase = [
            mock.Mock(has_run=lambda:False, node=mock.Mock(hostname="ms1")),
            mock.Mock(has_run=lambda:False, node=mock.Mock(hostname="node1")),
            mock.Mock(has_run=lambda:False, node=mock.Mock(hostname="node2"))
        ]
        manager.wait_for_phase(mock_phase)
        expected = [mock.call(['node1', 'node2', 'ms1']),
                mock.call(['node1', 'node2']), mock.call(['node2'])]
        self.assertEqual(mock_is_pp_alive.call_args_list, expected)

    def test_manifest_file_permissions(self):
        # LITPCDS-9426: Keep permissions consistent
        with mocked_fsync():
            self.manager._write_file("/tmp/litpcds-9426_permissions.txt", "")
        f = self._files["/tmp/litpcds-9426_permissions.txt"]
        self.assertTrue(f.permissions == 0640)

    def test_manifest_file_group(self):
        # TORF-231269: Stricter permissions on puppet manifests
        with mocked_fsync():
            self.manager._write_file("/tmp/torf-231269_group.txt", "")
        f = self._files["/tmp/torf-231269_group.txt"]
        self.assertTrue(f.group == 'puppet')

    def test_manifest_file_user(self):
        with mocked_fsync():
            self.manager._write_file("/tmp/file.txt", "")
        f = self._files["/tmp/file.txt"]
        self.assertTrue(f.user == 'celery')

    def test_manifest_dir_and_file(self):
        expected_dir = '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins'
        self.assertEqual(self.manager.manifest_dir(), expected_dir)
        backup_dir = '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins.failed'
        self.assertEqual(self.manager.manifest_dir(
            manifest_dir="plugins.failed"), backup_dir)

    def test_sleep_if_not_killed(self):
        def mock_sleep2(seconds):
            self.slept += seconds
            # Mimic litpd service being killed while waiting for puppet
            if self.slept > 1:
                self.manager.killed = True

        self.manager._sleep = mock_sleep2
        # If service is killed while waiting for puppet, exit loop early
        self.assertRaises(ServiceKilledException, self.manager._sleep_if_not_killed, 5, self.manager._sleep)
        self.assertTrue(self.slept < 5)

    def test_sleep_if_not_killed_no_kill(self):
        self.manager._sleep_if_not_killed(5, sleep_method=self.manager._sleep)
        self.assertEqual(self.slept, 5)

    def test_puppet_run(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2
        err = "foo"

        returns = [
            {
                "a": {"errors": ""},
                "b": {"errors": err},
            },
            {
                "c": {"errors": err},
                "d": {"errors": ""},
            },
            {
                "e": {"errors": err},
            },
            {
                "b": {"errors": ""},
                "c": {"errors": err},
            },
            {
                "e": {"errors": err},
            },
            {
                "c": {"errors": ""},
                "e": {"errors": ""},
            }
        ]

        def side_effect(*args):
            return returns.pop(0)
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        self.manager.mco_processor.runonce_puppet(["a", "b", "c", "d", "e"])
        self.assertEquals(
            [
                mock.call(["a", "b"], "puppet", "runonce", None),
                mock.call(["c", "d"], "puppet", "runonce", None),
                mock.call(["e"], "puppet", "runonce", None),
                mock.call(["b", "c"], "puppet", "runonce", None),
                mock.call(["e"], "puppet", "runonce", None),
                mock.call(["c", "e"], "puppet", "runonce", None),
            ],
            self.manager.mco_processor._run_puppet_command.call_args_list
        )

    def test_puppet_start_check_running(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2

        returns = [
            {
                "ms1": {"data": {"status": "running", "action": "status"},
                        "errors": "",
                        },
            },
        ]

        def side_effect(*args):
            return returns.pop(0)
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        changed, ret = self.manager.mco_processor._start_puppet_check("ms1")

        self.assertEqual(ret["ms1"]["data"]["action"], "status")
        call_list = self.manager.mco_processor._run_puppet_command.call_args_list
        self.assertEqual(call_list[0],
                            mock.call(['ms1'],'service','status',{'service':'puppet'}))

    def test_puppet_stop_check_stopped(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2

        returns = [
            {
                "ms1": {"data": {"status": "stopped", "action": "status"},
                        "errors": "",
                        },
            },
        ]

        def side_effect(*args):
            return returns.pop(0)
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        changed, ret = self.manager.mco_processor._stop_puppet_check("ms1")

        self.assertEqual(ret["ms1"]["data"]["action"], "status")
        call_list = self.manager.mco_processor._run_puppet_command.call_args_list
        self.assertEqual(call_list[0],
                            mock.call(['ms1'],'service','status',{'service':'puppet'}))


    def test_puppet_start_check_stopped(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2
        err = "foo"

        returns = [
            {
                "ms1": {"data": {"status": "stopped", "action": "status"},
                        "errors": "",
                        },
            },
            {
                "ms1": {"data": {"status": "running", "action": "start"},
                        "errors": "",
                        },
            },
        ]

        def side_effect(*args):
            return returns.pop(0)
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        changed, ret = self.manager.mco_processor._start_puppet_check("ms1")

        self.assertEqual(ret["ms1"]["data"]["action"], "start")
        call_list = self.manager.mco_processor._run_puppet_command.call_args_list
        self.assertEqual(call_list[0],
                            mock.call(['ms1'],'service','status',{'service':'puppet'}))

    def test_puppet_stop_check_started(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2

        returns = [
            {
                "ms1": {"data": {"status": "running", "action": "status"},
                        "errors": "",
                        },
            },
            {
                "ms1": {"data": {"status": "stopped", "action": "stop"},
                        "errors": "",
                        },
            },
        ]

        def side_effect(*args):
            return returns.pop(0)
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        changed, ret = self.manager.mco_processor._stop_puppet_check("ms1")
        call_list = self.manager.mco_processor._run_puppet_command.call_args_list
        self.assertEqual(call_list[0],
                            mock.call(['ms1'],'service','status',{'service':'puppet'}))

        self.assertEqual(ret["ms1"]["data"]["action"], "stop")

    def test_get_resolv_domains(self):
        f = tempfile.NamedTemporaryFile()
        f.writelines(["domain testdomain1.com\n", "search testdomain2.com\n"])
        f.flush()

        domains = self.manager.mco_processor._get_resolv_domains(resolv_file=f.name)

        self.assertTrue('testdomain1.com' in domains)
        self.assertTrue('testdomain2.com' in domains)

        f.close()

    def test_check_agent_is_running(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2

        returns = [
                {
                    "a": {"errors": "", "data": {"is_running": False}},
                    "b": {"errors": "", "data": {"is_running": True}},
                    },
                {
                    "c": {"errors": "", "data": {"is_running": False}},
                    "d": {"errors": "", "data": {"is_running": False}},
                    },
                {
                    "e": {"errors": "", "data": {"is_running": True}},
                    },
                {
                    "b": {"errors": "", "data": {"is_running": False}},
                    "e": {"errors": "", "data": {"is_running": False}},
                    },
                ]

        def side_effect(*args):
            return returns.pop(0)

        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)

        self.manager._check_puppet_status(["a", "b", "c", "d", "e"])

        self.assertEquals(
            [
                mock.call(["a", "b"], "puppetlock", "is_running", None),
                mock.call(["c", "d"], "puppetlock", "is_running", None),
                mock.call(["e"], "puppetlock", "is_running", None),
                mock.call(["b", "e"], "puppetlock", "is_running", None),
            ],
            self.manager.mco_processor._run_puppet_command.call_args_list
        )

    @mock.patch('litp.core.puppet_manager.time.time')
    def test_check_timeout_on_puppet_applying(self, mocked_time):
        mocked_time.side_effect = itertools.count(872820840)
        return_values = itertools.repeat(
            { "a": {"errors": "", "data": {"is_running": True}}}
        )
        def _mco_return_values(*args):
            return return_values.next()
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=_mco_return_values)
        self.assertRaises(McoFailed, self.manager._check_puppet_status, ["a"])

        expected_rpc_call = mock.call(["a"], 'puppetlock', 'is_running', None)
        self.assertEquals(expected_rpc_call, self.manager.mco_processor._run_puppet_command.mock_calls[0])

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_litpcds_12791_massive_feedback(self):
        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1_comp = self.model.create_item("node", "/nodes/node1/comp1",
            hostname="node1")
        comp1 = self.model.create_item("component", "/nodes/node1/comp1")
        node1 = self._convert_to_query_item(node1)
        comp1 = self._convert_to_query_item(comp1)

        node_tasks = []
        for task_idx in xrange(4):
            task = ConfigTask(node1, comp1, "Task %04d" % task_idx, "foo", "bar")
            node_tasks.append(task)

        on_puppet_phase_start = mock.Mock()
        def _phase_start(tasks, phase_id):
            for task in tasks:
                task.state = constants.TASK_RUNNING
        on_puppet_phase_start.side_effect = _phase_start
        on_puppet_feedback = mock.Mock()
        #
        self.manager.attach_handler('puppet_phase_start', on_puppet_phase_start)
        self.manager.attach_handler('puppet_feedback', on_puppet_feedback)

        self.manager.add_phase(node_tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()
        self.assertTrue(all(t.state == constants.TASK_RUNNING for t in node_tasks))

        text_report = ",".join(
            'litp_feedback:task_{0}:tuuid_{1}=success'.format(
                node_task.unique_id, node_task.uuid
            ) for node_task in node_tasks
        )
        report_dict = self.manager._build_report(text_report)

        mocked_tasks_in_phase = MagicMock()
        mocked_tasks_in_phase.__iter__.return_value = iter(node_tasks)

        task_pairs = self.manager._get_tasks_states_pairs(mocked_tasks_in_phase, report_dict)
        expected_pairs = [(task, constants.TASK_SUCCESS) for task in node_tasks]
        self.assertEquals(expected_pairs, task_pairs)
        self.assertEquals(len(mocked_tasks_in_phase.__iter__.mock_calls), 1)

    def test_configtask_removal_selector(self):
        # A ConfigTask that was being applied by Puppet when the plan was
        # stopped should be taken out of node_tasks as it isn't
        # successfully applied
        stopped_task = MagicMock()
        stopped_task.state = constants.TASK_STOPPED
        self.assertTrue(self.manager.configtask_removal_selector(stopped_task))

        transient_task_without_model_item = MagicMock()
        transient_task_without_model_item.model_item = "/path/to/model_item"
        transient_task_without_model_item.state = constants.TASK_RUNNING
        self.assertFalse(self.manager.configtask_removal_selector(transient_task_without_model_item))
        transient_task_without_model_item.state = constants.TASK_FAILED
        self.assertFalse(self.manager.configtask_removal_selector(transient_task_without_model_item))
        transient_task_without_model_item.state = constants.TASK_SUCCESS
        self.assertTrue(self.manager.configtask_removal_selector(transient_task_without_model_item))

        transient_task_with_model_item = MagicMock()
        transient_task_with_model_item.state = constants.TASK_SUCCESS
        transient_task_with_model_item.persist = False
        self.assertTrue(self.manager.configtask_removal_selector(transient_task_with_model_item))
        transient_task_with_model_item.persist = True
        self.assertTrue(self.manager.configtask_removal_selector(transient_task_with_model_item))
        transient_task_with_model_item.model_item._model_item.is_removed = lambda : False
        self.model.query_descends = MagicMock()
        self.model.query_descends.return_value = []
        self.assertFalse(self.manager.configtask_removal_selector(transient_task_with_model_item))
        transient_task_with_model_item.model_item._model_item.is_removed = lambda : True
        self.model.query_descends = MagicMock()
        mock_item = MagicMock()
        mock_item.is_for_removal.return_value = True
        self.model.query_descends.return_value = [mock_item]
        self.assertFalse(self.manager.configtask_removal_selector(transient_task_with_model_item))
        mock_item.is_for_removal.return_value = False
        self.model.query_descends.return_value = [mock_item]
        self.assertTrue(self.manager.configtask_removal_selector(transient_task_with_model_item))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.time_taken_metrics')
    def test_feedback(self, metrics_ctx_mgr):
        metrics_ctx_mgr.__enter__ = mock.Mock()
        metrics_ctx_mgr.__exit__ = mock.Mock()
        self.plugin_manager = PluginManager(self.model)

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call")
        ]

        on_puppet_phase_start = mock.Mock()

        def _phase_start(tasks, phase_id):
            for task in tasks:
                task.state = constants.TASK_RUNNING

        on_puppet_phase_start.side_effect = _phase_start

        on_puppet_feedback = mock.Mock()

        self.manager.attach_handler('puppet_phase_start', on_puppet_phase_start)
        self.manager.attach_handler('puppet_feedback', on_puppet_feedback)

        self.manager.add_phase(tasks, 0)

        with mocked_fsync():
            self.manager.apply_nodes()

        self.assertEquals(constants.TASK_RUNNING, tasks[0].state)
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id}:tuuid_{task_uuid}=success,'.format(
                task_id=tasks[0].unique_id,
                task_uuid=tasks[0].uuid
            ), False)
        self.manager._puppet_feedback(feedback)
        self.manager._process_feedbacks(tasks)
        on_puppet_phase_start.assert_called_once_with(tasks, 0)
        on_puppet_feedback.assert_called_once_with([(tasks[0], 'Success')])

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.time_taken_metrics')
    def test_partial_feedback(self, metrics_ctx_mgr):
        metrics_ctx_mgr.__enter__ = mock.Mock()
        metrics_ctx_mgr.__exit__ = mock.Mock()
        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task 1", "call1",
                       "task_call"),
            ConfigTask(node1, node1.comp2, "Test Task 2", "call2",
                       "task_call")
        ]
        self.executionmanager.plan = Plan([tasks])
        self.executionmanager.plan.set_ready()
        self.executionmanager.plan.run()
        self.executionmanager.plan.current_phase = 0

        on_puppet_phase_start = mock.Mock()

        def _phase_start(tasks, phase_id):
            for task in tasks:
                task.state = constants.TASK_RUNNING

        on_puppet_phase_start.side_effect = _phase_start

        self.manager.attach_handler('puppet_phase_start', on_puppet_phase_start)
        self.manager.attach_handler('puppet_feedback', self.executionmanager.on_puppet_feedback)

        self.manager.add_phase(tasks, 0)

        with mocked_fsync():
            self.manager.apply_nodes()

        self.assertTrue(all(t.state == constants.TASK_RUNNING for t in tasks))

        # Feedback is received (and enqueued) for task1 *only*
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id}:tuuid_{task_uuid}=success,'.format(
                task_id=tasks[0].unique_id,
                task_uuid=tasks[0].uuid
            ), False)

        self.manager._puppet_feedback(feedback)
        mock_phase = [
            mock.Mock(has_run=lambda:False, node=mock.Mock(hostname="node1"))]
        self.manager.wait_for_phase(mock_phase)
        on_puppet_phase_start.assert_called_once_with(tasks, 0)
        self.assertEquals(constants.TASK_SUCCESS, tasks[0].state)
        self.assertEquals(constants.TASK_FAILED, tasks[1].state)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.time_taken_metrics')
    @mock.patch('litp.core.puppetdb_api.PuppetDbApi.check_for_feedback')
    def test_failed_taskless_event(self, mock_pdb_check, metrics_ctx_mgr):
        metrics_ctx_mgr.__enter__ = mock.Mock()
        metrics_ctx_mgr.__exit__ = mock.Mock()
        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)

        phase = []
        successful_task = ConfigTask(node1, node1, "I do not depend on any resource defined in mn_node.pp", "b", "1")
        successful_task.state = constants.TASK_RUNNING
        phase.append(successful_task)

        skipped_task = ConfigTask(node1, node1, "I depend on a resource defined in mn_node.pp",  "b", "2")
        skipped_task.state = constants.TASK_RUNNING
        phase.append(skipped_task)

        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)

        self.executionmanager.plan = Plan([phase])
        self.executionmanager.plan.set_ready()
        self.executionmanager.plan.run()
        self.executionmanager.plan.current_phase = 0

        self.manager.add_phase(phase, 0)
        self.manager.attach_handler('puppet_feedback', self.executionmanager.on_puppet_feedback)

        with mocked_fsync():
            self.manager.apply_nodes()

        # This task is actually successful (ie. there are successful events for
        # all its resources)
        report = 'litp_feedback:task_{task_id}:tuuid_{task_uuid}=success,'.format(
                task_id=successful_task.unique_id,
                task_uuid=successful_task.uuid
        )
        # The other is assumed to be an eventless task, when in fact it is
        # skipped because of the taskless resource failure
        report += 'litp_feedback:task_{task_id}:tuuid_{task_uuid}=success,'.format(
                task_id=skipped_task.unique_id,
                task_uuid=skipped_task.uuid
        )
        feedback = ("node1", self.manager.phase_config_version, report)
        mock_pdb_check.return_value = feedback
        mock_pdb_check.side_effect=FailedTasklessPuppetEvent

        self.manager.wait_for_phase(phase)

        self.assertEquals(constants.TASK_FAILED, successful_task.state)
        self.assertEquals(constants.TASK_FAILED, skipped_task.state)
        self.assertTrue(self.manager.phase_complete)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.time_taken_metrics')
    def test_feedback_with_uuid(self, metrics_ctx_mgr):
        metrics_ctx_mgr.__enter__ = mock.Mock()
        metrics_ctx_mgr.__exit__ = mock.Mock()
        self.plugin_manager = PluginManager(self.model)

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call")
        ]

        on_puppet_phase_start = mock.Mock()

        def _phase_start(tasks, phase_id):
            for task in tasks:
                task.state = constants.TASK_RUNNING

        on_puppet_phase_start.side_effect = _phase_start

        on_puppet_feedback = mock.Mock()

        self.manager.attach_handler('puppet_phase_start', on_puppet_phase_start)
        self.manager.attach_handler('puppet_feedback', on_puppet_feedback)

        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        self.assertEquals(constants.TASK_RUNNING, tasks[0].state)
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
                'litp_feedback:task_{task_id}:tuuid_{task_uuid}=success,'.format(
                    task_id=tasks[0].unique_id, task_uuid=tasks[0].uuid), False)
        self.manager._puppet_feedback(feedback)
        on_puppet_phase_start.assert_called_once_with(tasks, 0)
        self.manager._process_feedbacks(tasks)
        on_puppet_feedback.assert_called_once_with([(tasks[0], 'Success')])

    def test_format_puppet_report(self):
        import litp.core.puppet_manager as pm
        expected = ('litp_feedback:task_ms1_cobblerdata::add_system_node2='
            'success,litp_feedback:task_ms1_cobbler::udev_network_node2='
            'success,litp_feedback:task_ms1_cobbler::bootloader_node1=success')
        actual = pm.format_puppet_report('litp_feedback:task_ms1__cobblerdat'
            'a_3a_3aadd__system__node2:tuuid_94383bda-5771-402f-b567-aa3df03'
            '329ea=success,litp_feedback:task_ms1__cobbler_3a_3audev__networ'
            'k__node2:tuuid_8770cd96-16d3-4785-98b1-ee122f895f86=success,lit'
            'p_feedback:task_ms1__cobbler_3a_3abootloader__node1:tuuid_a7e38'
            'd18-5981-4151-8fce-01bb12b70461=success,')
        self.assertEquals(expected, actual)

    def test_feedback_format_ids(self):
        task_clean_id = "node1__colon_3a_3acolon___55_50_50_45_52_43_41_53_45"
        report = 'litp_feedback:task_' + task_clean_id + '=success'
        self.assertEquals(
            'litp_feedback:task_node1_colon::colon_'
            'UPPERCASE=success', self.manager._format_report_for_logs(report))

        massive_report = (
            "litp_feedback:task_node1__hosts_3a_3ahostentry"
            "__node1___7b_27comment_27_3a_20_27_43reated_20by_20_4c_"
            "49_54_50_2e_20_50lease_20do_20not_20edit_27_2c_20_27ip_"
            "27_3a_20_2710_2e46_2e86_2e95_27_2c_20_27ensure_27_3a_20_"
            "27present_27_2c_20_27name_27_3a_20u_27node1_27_7d,litp_"
            "feedback:task_node1__class__hosts=success,litp_feedback:"
            "task_node1__network_3a_3aconfig__lo___7b_27nozeroconf_27_"
            "3a_20_27yes_27_2c_20_27network_27_3a_20_27127_2e0_2e0_"
            "2e0_27_2c_20_27userctl_27_3a_20_27no_27_2c_20_27ipaddr_"
            "27_3a_20_27127_2e0_2e0_2e1_27_2c_20_27broadcast_27_3a_"
            "20_27127_2e255_2e255_2e255_27_2c_20_27netmask_27_3a_20_"
            "27255_2e0_2e0_2e0_27_2c_20_27bootproto_27_3a_20_27static"
            "_27_2c_20_27ensure_27_3a_20_27present_27_2c_20_27device_"
            "27_3a_20_27lo_27_2c_20_27onboot_27_3a_20_27yes_27_7d="
            "success,litp_feedback:task_node1__hosts_3a_3ahostentry__"
            "node4___7b_27comment_27_3a_20_27_43reated_20by_20_4c_49_54_"
            "50_2e_20_50lease_20do_20not_20edit_27_2c_20_27ip_27_3a_20_"
            "2710_2e46_2e86_2e97_27_2c_20_27ensure_27_3a_20_27present_27"
            "_2c_20_27name_27_3a_20u_27node4_27_7d=success,litp_feedback"
            ":task_node1__network_3a_3aconfig__eth1___7b_27nozeroconf_27"
            "_3a_20_27yes_27_2c_20_27userctl_27_3a_20_27no_27_2c_20_27"
            "ipaddr_27_3a_20_2710_2e46_2e86_2e95_27_2c_20_27onboot_27_3a"
            "_20_27yes_27_2c_20_27broadcast_27_3a_20_2710_2e46_2e87_2e"
            "255_27_2c_20_27netmask_27_3a_20_27255_2e255_2e248_2e0_27_2c"
            "_20_27bootproto_27_3a_20_27static_27_2c_20_27ensure_27_3a_"
            "20_27present_27_2c_20_27hwaddr_27_3a_20u_27_44_45_3a_41_44"
            "_3a_42_45_3a_45_46_3a5_43_3a52_27_2c_20_27gateway_27_3a_20"
            "u_2710_2e46_2e86_2e94_27_7d=success,litp_feedback:task_"
            "node1__hosts_3a_3ahostentry__ms1___7b_27comment_27_3a_20_"
            "27_43reated_20by_20_4c_49_54_50_2e_20_50lease_20do_20not_"
            "20edit_27_2c_20_27ip_27_3a_20u_2710_2e46_2e86_2e94_27_2c_"
            "20_27ensure_27_3a_20_27present_27_2c_20_27name_27_3a_20_27"
            "ms1_27_7d=success,litp_feedback:task_node1__hosts_3a_3ahost"
            "entry__node2___7b_27comment_27_3a_20_27_43reated_20by_20_4c"
            "_49_54_50_2e_20_50lease_20do_20not_20edit_27_2c_20_27ip").strip()

        self.assertEquals(
            'litp_feedback:task_node1_class_hosts=success,litp_feedback'
            ':task_node1_network::config_lo=success,litp_feedback:task_'
            'node1_hosts::hostentry_node4=success,litp_feedback:task_'
            'node1_network::config_eth1=success,litp_feedback:task_node1_'
            'hosts::hostentry_ms1=success',
            self.manager._format_report_for_logs(massive_report))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_task_not_in_puppet_feedback_event_if_successful(self):
        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)
        self.executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call"),
        ]
        self.manager.add_phase(tasks, 0)

        with mocked_fsync():
            self.manager.apply_nodes()

        tasks[0].state = constants.TASK_SUCCESS

        puppet_feedback_handler = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_handler)

        self.manager.process_report = mock.Mock(return_value=set(tasks))
        self.executionmanager.plan.find_tasks = mock.Mock(return_value=tasks)
        self.executionmanager.plan.current_phase = 0

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_node1__call1__task_call=fail,', False)
        self.manager._puppet_feedback(feedback)
        self.assertEquals(constants.TASK_SUCCESS, tasks[0].state)
        self.manager._process_feedbacks(tasks)
        puppet_feedback_handler.assert_called_once_with([])

    def test_ignore_feedback_from_different_run_id(self):
        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)
        self.executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call"),
        ]
        self.manager.add_phase(tasks, 0)

        self.assertEquals(constants.TASK_RUNNING, tasks[0].state)
        feedback = self.manager.Feedback("node1", "x",
            'litp_feedback:task_node1__call1__task_call=success,', False)
        self.manager._puppet_feedback(feedback)
        self.assertEquals(constants.TASK_RUNNING, tasks[0].state)
        self.assertFalse(self.manager.phase_complete)

    def test_ignore_feedback_completed_phase(self):
        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)
        self.executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call")
        ]
        self.manager.add_phase(tasks, 0)

        self.assertEquals(constants.TASK_RUNNING, tasks[0].state)
        self.manager.wait_for_phase(tasks, timeout=1)
        self.assertEquals(constants.TASK_FAILED, tasks[0].state)
        self.assertTrue(self.manager.phase_complete)
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id}=success,'.format(task_id=tasks[0].unique_id), False)
        self.manager._puppet_feedback(feedback)
        self.assertEquals(constants.TASK_FAILED, tasks[0].state)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.Mock())
    def test_feedback_multiple(self):
        puppet_feedback_listener = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_listener)

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("another-component", "/nodes/node1/comp2")
        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task", "call1",
                       "task_call"),
            ConfigTask(node1, node1.comp2, "Test Task", "call2",
                       "task_call_2"),
        ]
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()
        # puppet manager shouldn't touch a task in Initial state
        for task in tasks:
            task.state = constants.TASK_RUNNING

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
                'litp_feedback:task_{0}:tuuid_{1}=success,'.format(
                    tasks[0].unique_id, tasks[0].uuid
                ), False)

        self.manager._puppet_feedback(feedback)
        puppet_feedback_listener.assert_called_with([(tasks[0],
                                                    constants.TASK_SUCCESS)])

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
                ('litp_feedback:task_{0}:tuuid_{1}=success,'
                'litp_feedback:task_{2}:tuuid_{3}=success,').format(
                    tasks[0].unique_id, tasks[0].uuid,
                    tasks[1].unique_id, tasks[1].uuid
                ), False)
        self.manager._puppet_feedback(feedback)

        self.assertEqual(sorted(puppet_feedback_listener.call_args[0][0]),
                        sorted([(tasks[0], constants.TASK_SUCCESS),
                                (tasks[1], constants.TASK_SUCCESS)]))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.Mock())
    def test_feedback_failure_in_report(self):
        puppet_feedback_listener = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_listener)

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [ConfigTask(node1, node1.comp2, "Test Task", "call1", "task_call"),
                 ConfigTask(node1, node1.comp2, "Test Task", "call2", "task_call_2"), ]
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()
        self.manager.timestamp = 1
        for task in tasks:
            task.state = constants.TASK_RUNNING

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
                ('litp_feedback:task_{0}:tuuid_{1}=success,'
                'litp_feedback:task_{2}:tuuid_{3}=fail,').format(
                    tasks[0].unique_id, tasks[0].uuid,
                    tasks[1].unique_id, tasks[1].uuid
                ), False)

        self.manager._puppet_feedback(feedback)
        self.assertEqual(sorted(puppet_feedback_listener.call_args[0][0]),
                        sorted([(tasks[1], constants.TASK_FAILED),
                                (tasks[0], constants.TASK_SUCCESS)]))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.Mock())
    def test_feedback_updates_tasks_signals_end_of_phase(self):
        puppet_feedback_listener = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_listener)
        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        node2 = self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(node2)
        self.model.create_item("another-component", "/nodes/node2/comp2")

        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task", "task_call",
                       'call1'),
            ConfigTask(node2, node2.comp2, "Test Task", "task_call",
                       'call2'),
        ]

        self.manager.add_phase(tasks, 0)

        # apply configuration
        with mocked_fsync():
            self.manager.apply_nodes()

        # feedback resourcecall
        self.assertFalse(self.manager.phase_complete)
        def _update_task_state(*args):
            tasks[0].state = constants.TASK_SUCCESS
        puppet_feedback_listener.side_effect = _update_task_state
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id1}=success,'.format(task_id1=tasks[0].unique_id), False)
        self.manager._puppet_feedback(feedback)
        self.assertFalse(self.manager.phase_complete)
        def _update_task_state(*args):
            tasks[1].state = constants.TASK_SUCCESS
        puppet_feedback_listener.side_effect = _update_task_state
        feedback = self.manager.Feedback("node2", self.manager.phase_config_version,
            'litp_feedback:task_{task_id2}=success,litp_feedback:task_{task_id1}=success,'.format(
                task_id1=tasks[0].unique_id,
                task_id2=tasks[1].unique_id
            ), False)
        self.manager._puppet_feedback(feedback)

        # assert phase ended
        self.assertTrue(self.manager.phase_complete)
        self.assertTrue(self.manager.phase_successful)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.Mock())
    def test_puppet_error_feedback_before_error(self):
        puppet_feedback_listener = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_listener)
        self.model.create_item("node", "/nodes/node1",
            hostname="ms1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="ms1")[0])
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(self.model.query("node", hostname="node2")[0])
        self.model.create_item("another-component", "/nodes/node2/comp2")

        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task", "task_call", 'call1'),
            ConfigTask(node2, node2.comp2, "Test Task", "task_call", 'call2'),
        ]
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        feedback = self.manager.Feedback("node2", self.manager.phase_config_version,
                'litp_feedback:task_%s:tuuid_%s=success,' % (tasks[0].unique_id, tasks[0].uuid), False)

        self.manager._puppet_feedback(feedback)
        self.assertFalse(self.manager.phase_complete)
        self.assertFalse(self.manager.phase_successful)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.Mock())
    def test_puppet_error_feedback_before_error_duplicate_uid(self):
        puppet_feedback_listener = mock.Mock()
        self.manager.attach_handler('puppet_feedback', puppet_feedback_listener)
        self.model.create_item("node", "/nodes/node1",
            hostname="ms1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="ms1")[0])
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(self.model.query("node", hostname="node2")[0])
        self.model.create_item("another-component", "/nodes/node2/comp2")

        tasks = [
            ConfigTask(node1, node1.comp1, 'Create test \'Task n1\' on node "node1"', "task_call", 'call1'),
            ConfigTask(node1, node1.comp1, "Test Task n1_1", "task_call", 'call1'),
            ConfigTask(node2, node2.comp2, "Test Task n2", "task_call", 'call2'),
            ConfigTask(node2, node2.comp2, "Test Task n2_1", "task_call", 'call2')
        ]
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        feedback = self.manager.Feedback("node2", self.manager.phase_config_version,
                'litp_feedback:task_%s:tuuid_%s=success,' % (tasks[0].unique_id, tasks[0].uuid), False)

        self.manager._puppet_feedback(feedback)
        self.assertFalse(self.manager.phase_complete)
        self.assertFalse(self.manager.phase_successful)

    def test_wait_for_phase_sleep(self):
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="hostname"))]
        self.manager._sleep = self._mock_sleep
        self.manager.wait_for_phase(
                mock_phase, timeout=10, poll_freq=0, poll_count=1)
        self.assertEqual(10, self.slept)

    def test_wait_for_phase_no_timeout_argument(self):
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="hostname"))]
        self.manager._sleep = self._mock_sleep
        self.manager.phase_complete = True
        self.manager.phase_successful = True
        self.assertTrue(self.manager.wait_for_phase(mock_phase))
        self.manager.phase_successful = False
        self.assertFalse(self.manager.wait_for_phase(mock_phase))

    def test_wait_for_phase_timed_out(self):
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="hostname"))]
        self.manager._sleep = self._mock_sleep
        self.manager.phase_complete = False
        timeout_handler = mock.Mock()
        self.manager.attach_handler('puppet_timeout', timeout_handler)
        self.manager.phase_successful = True
        self.assertFalse(self.manager.wait_for_phase(mock_phase, 1))
        self.manager.phase_successful = False
        self.assertFalse(self.manager.wait_for_phase(mock_phase, 1))
        timeout_handler.assert_called_once_with(self.manager.phase_tasks)

    def _prepare_poll_check(self, returns):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.PUPPET_RUN_CONCURRENCY = 2
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.001
        self.manager.mco_processor.MCO_ACTION_CONCURRENCY = 2
        def side_effect(*args):
            return returns.pop()
        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=side_effect)
        self.manager._sleep = self._mock_sleep
        self.manager._is_puppet_alive = call_count(self.manager._is_puppet_alive)
        self.manager.phase_complete = False
        timeout_handler = mock.Mock()
        self.manager.attach_handler('puppet_timeout', timeout_handler)
        self.manager.phase_successful = True

    def test_wait_for_phase_poll_not_applying(self):
        returns = [
                puppet_not_applying,
                puppet_not_applying
        ]
        self._prepare_poll_check(returns)
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="ms1"))]
        self.assertFalse(self.manager.wait_for_phase(
            mock_phase, timeout=0, poll_freq=1, poll_count=2))
        self.assertFalse(self.manager.phase_successful)
        self.assertTrue(self.manager.phase_complete)
        self.assertEquals(2, self.manager._is_puppet_alive.call_count)

    def test_wait_for_phase_poll_race_condition(self):
        def _race_condition(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Race condition: phase gets set to to complete while
                # _is_puppet_alive is being executed.
                self.manager.phase_complete = True
                return func(*args, **kwargs)
            return wrapper

        returns = [
                puppet_not_applying,
        ]
        self._prepare_poll_check(returns)
        self.manager._is_puppet_alive = _race_condition(self.manager._is_puppet_alive)
        self.assertFalse(self.manager.phase_complete)
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="ms1"))]
        self.assertTrue(self.manager.wait_for_phase(mock_phase, timeout=0, poll_freq=1, poll_count=1))
        self.assertTrue(self.manager.phase_successful)
        self.assertTrue(self.manager.phase_complete)

    def test_wait_for_phase_poll_applying(self):
        returns = [
                puppet_applying,
                puppet_applying,
                puppet_applying,
                puppet_applying
        ]
        self._prepare_poll_check(returns)
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="ms1"))]
        self.assertFalse(self.manager.wait_for_phase(
            mock_phase, timeout=4, poll_freq=1, poll_count=2))
        self.assertFalse(self.manager.phase_successful)
        self.assertTrue(self.manager.phase_complete)
        self.assertEquals(4, self.manager._is_puppet_alive.call_count)

    def test_wait_for_phase_poll_mixed_applying_and_not_applying(self):
        returns = [
            puppet_not_applying,
            puppet_not_applying,
            puppet_not_applying,
            puppet_applying,
            puppet_not_applying,
            puppet_applying,
            puppet_not_applying
        ]
        self._prepare_poll_check(returns)
        mock_phase = [mock.Mock(has_run=lambda:False,
            node=mock.Mock(hostname="ms1"))]
        self.assertFalse(self.manager.wait_for_phase(
            mock_phase, timeout=0, poll_freq=1, poll_count=3))
        self.assertFalse(self.manager.phase_successful)
        self.assertTrue(self.manager.phase_complete)
        self.assertEquals(7, self.manager._is_puppet_alive.call_count)

    def test__is_puppet_applying_not_applying(self):
        returns = [
            puppet_not_applying
        ]
        self._prepare_poll_check(returns)
        self.assertFalse(self.manager._is_puppet_alive(['ms1']))

    def test__is_puppet_applying_ok(self):
        returns = [
            puppet_applying
        ]
        self._prepare_poll_check(returns)
        self.assertTrue(self.manager._is_puppet_alive(['ms1']))

    def test__is_puppet_applying_many_hosts(self):
        returns = [
            puppet_mixed_applying
        ]
        self._prepare_poll_check(returns)
        self.assertTrue(self.manager._is_puppet_alive(['node1', 'node2']))

    def test_run_plan_fails(self):
        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        node2 = self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(node2)
        self.model.create_item("another-component", "/nodes/node2/comp2")

        # setup configuration
        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", 'call1'),
            ConfigTask(node2, node2.comp2, "Test Task",
                       "task_call", 'call2'),
        ]
        self.manager.add_phase(tasks, 0)

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id1}=fail,'.format(
                task_id1=tasks[0].unique_id
            ), False)
        self.manager._puppet_feedback(feedback)
        self.assertFalse(self.manager.phase_complete)
        self.assertFalse(self.manager.phase_successful)

        feedback = self.manager.Feedback("node2", self.manager.phase_config_version,
            'litp_feedback:task_{task_id1}=fail,litp_feedback:task_{task_id2}=success,'.format(
                task_id1=tasks[0].unique_id,
                task_id2=tasks[1].unique_id
            ), False)

        self.manager._puppet_feedback(feedback)
        # assert phase ended
        # self.assertTrue(self.manager.phase_complete)

    def test_null_report_throws_no_exception(self):
        self.manager._hosts_in_phase = ["node1"]
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version, '', False)
        self.manager._puppet_feedback(feedback)

    def test_corrupt_report(self):
        self.manager._hosts_in_phase = ["node1"]
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        self.manager.node_tasks['node1'] = ConfigTask(
            node1, node1, "Test Task", "call1", "task_call")
        feedback = self.manager.Feedback("node1", self.manager.phase_config_version, '=', False)
        self.assertRaises(Exception, self.manager._process_feedback, feedback)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_new_node_template(self):
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(self.model.query("node", hostname="node2")[0])
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("another-component", "/nodes/node2/comp2")

        # setup configuration
        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", 'call1',
                       param1="value1",
                       require=[{'type': 'Class',
                                 'value': 'Yum::Permanentrepos'}]),
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", 'call2',
                       param1="value2"),
            ConfigTask(node2, node2.comp2, "Test Task",
                       "task_call", 'call2',
                       param2="value2"),
        ]
        tasks[0].state = constants.TASK_RUNNING
        tasks[1].state = constants.TASK_RUNNING
        tasks[2].state = constants.TASK_RUNNING
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        expected = """
class task_{task_id1}(){{
    task_call {{ "call1":
        tag => ["{task_uuid1}",],
        param1 => "value1",
        require => [Class["Yum::Permanentrepos"]]
    }}
}}

class task_{task_id2}(){{
    task_call {{ "call2":
        tag => ["{task_uuid2}",],
        param1 => "value2"
    }}
}}


node "node1" {{

    class {{'litp::mn_node':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{'task_{task_id1}':
    }}


    class {{'task_{task_id2}':
    }}


}}
""".format(
    task_id1=tasks[0].unique_id,
    task_uuid1='tuuid_' + tasks[0].uuid,
    task_id2=tasks[1].unique_id,
    task_uuid2='tuuid_' + tasks[1].uuid)

        actual = self._files['/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp'].filebuf

        self.assertEquals(actual, expected)

        self.assertEqual("""
class task_{task_id}(){{
    task_call {{ "call2":
        tag => ["{task_uuid3}",],
        param2 => "value2"
    }}
}}


node "node2" {{

    class {{'litp::mn_node':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{'task_{task_id}':
    }}


}}
""".format(
    task_id=tasks[2].unique_id,
    task_uuid3='tuuid_' + tasks[2].uuid),
                         self._files['/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node2.pp'].filebuf)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_old_apply(self):
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        self.model.create_item("component", "/nodes/node1/comp1")
        self.model.create_item("node", "/nodes/node2",
            hostname="node2")
        node2 = self._convert_to_query_item(self.model.query("node", hostname="node2")[0])
        self.model.create_item("another-component", "/nodes/node2/comp2")

        self.task1 = ConfigTask(node1, node1.comp1, "Test Task",
                                "task_call", 'call1')
        self.task1.state = constants.TASK_RUNNING
        self.task2 = ConfigTask(node2, node2.comp2, "Test Task",
                                "task_call", 'call2')
        self.task2.state = constants.TASK_RUNNING

        self.manager.add_phase([
            self.task1,
            self.task2,
        ], 0)

        with mocked_fsync():
            self.manager.apply_nodes()
        self.assertEqual(3, len(self._files))

    def test_ignore_feedback_from_other_puppet_runs(self):
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        self.model.create_item("component", "/nodes/node1/comp1")

        self.assertEqual("Initial", node1.comp1.get_state())

        self.manager.add_phase([
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", 'call1'),
        ], 0)

        feedback = self.manager.Feedback("node1", "x",
            'litp_feedback:task_node1__task__call__call1=success,', False)

        self.manager._puppet_feedback(feedback)
        self.assertEqual("Initial", node1.comp1.get_state())

    # FIXME
    def test_dont_overwrite_deconfigured_state_with_applied_from_last_run(self):
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        comp1 = self.model.create_item("component", "/nodes/node1/comp1")
        comp1.set_for_removal()
        comp1 = self._convert_to_query_item(comp1)

        self.manager.add_phase([
            ConfigTask(node1_qi, node1_qi.comp1, "Test Task", "task_call", 'call1'),
        ], 0)

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_node1__task__call__call1=success,', False)

        self.manager._puppet_feedback(feedback)
        self.assertEqual({'comp1': comp1}, node1_qi._children)

    def test_puppet_feedback_phase_complete_check(self):
        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)
        self.executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))
        self.executionmanager._log_phase_completion = mock.Mock()

        node1 = self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(node1)
        self.model.create_item("component", "/nodes/node1/comp1")
        comp2 = self.model.create_item("another-component", "/nodes/node1/comp2")

        tasks = [
            ConfigTask(node1, node1.comp2, "Test Task", "call1",
                       "task_call")
        ]
        self.manager.add_phase(tasks, 0)

        feedback = self.manager.Feedback("node1", self.manager.phase_config_version,
            'litp_feedback:task_{task_id}=success,'.format(task_id=tasks[0].unique_id), False
        )
        self.manager._puppet_feedback(feedback)

    def test_check_any_tasks_failed(self):
        self.assertTrue(
            self.manager._any_tasks_failed(
                [MockTask("Success"), MockTask("Failed")]
                ),
            msg="_any_tasks_failed() missed failed tasks"
            )

    def test_check_all_tasks_succeeded(self):
        self.assertFalse(
            self.manager._all_tasks_suceeded([]),
            msg="Check there can be no success with no tasks"
            )
        self.assertTrue(
            self.manager._all_tasks_suceeded(
                [MockTask("Success"), MockTask("Success"), MockTask("Success")]
                ),
            msg="Check all tasks success"
            )
        self.assertFalse(
            self.manager._all_tasks_suceeded(
                [MockTask("Success"), MockTask("Failed"), MockTask("Success")]
                ),
            msg="Check failed tasks gets noticed"
            )

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_ordered_phase(self):
        self.model.create_item("node", "/nodes/node1",
            hostname="node1")
        node1 = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        self.model.create_item("component", "/nodes/node1/comp1")

        # setup configuration
        tasks = [
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", call_id='call1',
                param1="value1", require=[{'type': 'Class',
                                           'value': 'Yum::Permanentrepos'}]),
            ConfigTask(node1, node1.comp1, "Test Task",
                       "task_call", call_id='call2',
                param1="value2"),
        ]
        tasks[1]._requires = set([tasks[0].unique_id])
        tasks[0].state = constants.TASK_RUNNING
        tasks[1].state = constants.TASK_RUNNING
        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        expected = """
class task_{task_id1}(){{
    task_call {{ "call1":
        tag => ["{task_uuid1}",],
        param1 => "value1",
        require => [Class["Yum::Permanentrepos"]]
    }}
}}

class task_{task_id2}(){{
    task_call {{ "call2":
        tag => ["{task_uuid2}",],
        param1 => "value2"
    }}
}}


node "node1" {{

    class {{'litp::mn_node':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{'task_{task_id1}':
    }}


    class {{'task_{task_id2}':
        require => [Class["task_{task_id1}"]]
    }}


}}
""".format(
        task_id1=tasks[0].unique_id,
        task_uuid1='tuuid_' + tasks[0].uuid,
        task_id2=tasks[1].unique_id,
        task_uuid2='tuuid_' + tasks[1].uuid)

        actual = self._files['/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp'].filebuf

        self.assertEquals(actual, expected)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_remove_task(self):
        self.model.create_item("node", "/nodes/node1",
                                    hostname="node1")
        node_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])

        tasks = [
            ConfigTask(node_qi, node_qi, "tbd2", "call_type", "1"),
            ConfigTask(node_qi, node_qi, "tbd1", "call_type", "2"),
            ConfigTask(node_qi, node_qi, "tbd1", "call_type", "3"),
            ConfigTask(node_qi, node_qi, "", "call_type", "4"),
        ]
        tasks[1]._requires = set([tasks[0].unique_id])
        tasks[1].requires.add(tasks[0])
        tasks[2]._requires = set([tasks[1].unique_id])
        tasks[2].requires.add(tasks[1])
        tasks[3]._requires = set([tasks[2].unique_id])
        tasks[3].requires.add(tasks[2])

        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        self.manager._rewrite_persisted_tasks(lambda task: task.description == "tbd1")
        remaining_tasks = self.manager.node_tasks["node1"]
        self.assertEquals([tasks[0], tasks[3]], remaining_tasks)

        self.assertFalse(any(tasks[1] in t.requires for t in remaining_tasks))
        self.assertFalse(any(tasks[2] in t.requires for t in remaining_tasks))

        self.assertTrue(remaining_tasks[0].unique_id in remaining_tasks[1]._requires)

        self.manager._rewrite_persisted_tasks(lambda task: task.description == "tbd2")
        remaining_tasks = self.manager.node_tasks["node1"]
        self.assertEquals(1, len(remaining_tasks))
        self.assertFalse(remaining_tasks[0]._requires)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_set_task_redundant_requires(self):
        self.model.create_item("node", "/nodes/node1",
                                    hostname="node1")
        node_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])

        tasks = [
            ConfigTask(node_qi, node_qi, "tbd1", "task_call", call_id="1"),
            ConfigTask(node_qi, node_qi, "tbd2", "task_call", call_id="2"),
            ConfigTask(node_qi, node_qi, "tbd3", "task_call", call_id="3"),
            ConfigTask(node_qi, node_qi, "tbd4", "task_call", call_id="4"),
        ]
        tasks[0]._requires = set([tasks[1].unique_id,tasks[2].unique_id,tasks[3].unique_id])
        tasks[1]._requires = set([tasks[2].unique_id])
        tasks[2]._requires = set([tasks[3].unique_id])

        self.manager.add_phase(tasks, 0)
        for task in tasks:
            task.state = constants.TASK_RUNNING
        with mocked_fsync():
            self.manager.apply_nodes()
        expected = """
class task_{task_id1}(){{
    task_call {{ "1":
        tag => ["{task_uuid1}",],

    }}
}}

class task_{task_id2}(){{
    task_call {{ "2":
        tag => ["{task_uuid2}",],

    }}
}}

class task_{task_id3}(){{
    task_call {{ "3":
        tag => ["{task_uuid3}",],

    }}
}}

class task_{task_id4}(){{
    task_call {{ "4":
        tag => ["{task_uuid4}",],

    }}
}}


node "node1" {{

    class {{'litp::mn_node':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{'task_{task_id1}':
        require => [Class["task_{task_id2}"]]
    }}


    class {{'task_{task_id2}':
        require => [Class["task_{task_id3}"]]
    }}


    class {{'task_{task_id3}':
        require => [Class["task_{task_id4}"]]
    }}


    class {{'task_{task_id4}':
    }}


}}
""".format(
        task_id1=tasks[0].unique_id,
        task_uuid1='tuuid_' + tasks[0].uuid,
        task_id2=tasks[1].unique_id,
        task_uuid2='tuuid_' + tasks[1].uuid,
        task_id3=tasks[2].unique_id,
        task_uuid3='tuuid_' + tasks[2].uuid,
        task_id4=tasks[3].unique_id,
        task_uuid4='tuuid_' + tasks[3].uuid)

        actual = self._files['/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp'].filebuf
        self.assertEquals(actual, expected)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_set_task_redundant_requires_2(self):
        self.model.create_item("node", "/nodes/node1",
                                    hostname="node1")
        node_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])

        tasks = [
            ConfigTask(node_qi, node_qi, "tbd1", "task_call", call_id="1"),
            ConfigTask(node_qi, node_qi, "tbd2", "task_call", call_id="2"),
            ConfigTask(node_qi, node_qi, "tbd3", "task_call", call_id="3"),
            ConfigTask(node_qi, node_qi, "tbd4", "task_call", call_id="4"),
        ]
        tasks[0]._requires = set([tasks[1].unique_id])
        tasks[1]._requires = set([tasks[2].unique_id])
        tasks[2]._requires = set([tasks[3].unique_id])

        self.manager.add_phase(tasks, 0)
        for task in tasks:
            task.state = constants.TASK_RUNNING
        with mocked_fsync():
            self.manager.apply_nodes()
        expected = """
class task_{task_id1}(){{
    task_call {{ "1":
        tag => ["{task_uuid1}",],

    }}
}}

class task_{task_id2}(){{
    task_call {{ "2":
        tag => ["{task_uuid2}",],

    }}
}}

class task_{task_id3}(){{
    task_call {{ "3":
        tag => ["{task_uuid3}",],

    }}
}}

class task_{task_id4}(){{
    task_call {{ "4":
        tag => ["{task_uuid4}",],

    }}
}}


node "node1" {{

    class {{'litp::mn_node':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{'task_{task_id1}':
        require => [Class["task_{task_id2}"]]
    }}


    class {{'task_{task_id2}':
        require => [Class["task_{task_id3}"]]
    }}


    class {{'task_{task_id3}':
        require => [Class["task_{task_id4}"]]
    }}


    class {{'task_{task_id4}':
    }}


}}
""".format(
        task_id1=tasks[0].unique_id,
        task_uuid1='tuuid_' + tasks[0].uuid,
        task_id2=tasks[1].unique_id,
        task_uuid2='tuuid_' + tasks[1].uuid,
        task_id3=tasks[2].unique_id,
        task_uuid3='tuuid_' + tasks[2].uuid,
        task_id4=tasks[3].unique_id,
        task_uuid4='tuuid_' + tasks[3].uuid)

        actual = self._files['/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp'].filebuf
        self.assertEquals(actual, expected)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_remove_task_redundant_requires(self):
        self.model.create_item("node", "/nodes/node1",
                                    hostname="node1")
        node_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])

        tasks = [
            ConfigTask(node_qi, node_qi, "tbd1", "call_type", "1"),
            ConfigTask(node_qi, node_qi, "tbd2", "call_type", "2"),
            ConfigTask(node_qi, node_qi, "tbd3", "call_type", "3"),
            ConfigTask(node_qi, node_qi, "tbd4", "call_type", "4"),
        ]
        tasks[0]._requires = set([tasks[1].unique_id,tasks[2].unique_id,tasks[3].unique_id])
        tasks[0].requires |= set([tasks[1], tasks[2], tasks[3]])
        tasks[1]._requires = set([tasks[2].unique_id])
        tasks[1].requires |= set([tasks[2]])
        tasks[2]._requires = set([tasks[3].unique_id])
        tasks[2].requires |= set([tasks[3]])

        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        self.manager._rewrite_persisted_tasks(lambda task: task.description == "tbd2")
        remaining_tasks = self.manager.node_tasks["node1"]
        self.assertEquals(3, len(remaining_tasks))
        self.assertTrue(remaining_tasks[1].unique_id in remaining_tasks[0]._requires)
        self.assertTrue(remaining_tasks[2].unique_id in remaining_tasks[0]._requires)
        self.assertFalse(any(tasks[1] in t.requires for t in remaining_tasks))

        self.manager._rewrite_persisted_tasks(lambda task: task.description == "tbd4")
        remaining_tasks = self.manager.node_tasks["node1"]
        self.assertEquals(2, len(remaining_tasks))
        self.assertTrue(remaining_tasks[1].unique_id in remaining_tasks[0]._requires)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.Mock())
    def test_fail_removal_task(self):
        original_node_tasks = self.manager.node_tasks
        self.model.create_item("node", "/nodes/node1",
                                    hostname="node1")
        self.model.create_item("component", "/nodes/node1/comp1")

        node_qi = self._convert_to_query_item(self.model.query("node", hostname="node1")[0])
        comp_qi = node_qi.comp1

        initial_task = ConfigTask(node_qi, comp_qi, "tbd1", "call_type", "3", action='setup')
        self.manager.add_phase([initial_task], 0)
        initial_task.model_item._model_item.set_applied()
        initial_task.state = constants.TASK_SUCCESS

        with mocked_fsync():
            self.manager.apply_nodes()
            self.manager.restore_backed_up_tasks()
            self.manager.cleanup([], set())
        self.assertTrue(initial_task in self.manager.node_tasks[node_qi.hostname])

        removal_task = ConfigTask(node_qi, comp_qi, "tbd1", "call_type", "3", action='teardown')
        self.manager.add_phase([removal_task], 0)
        removal_task.model_item._model_item.set_for_removal()
        removal_task.state = constants.TASK_FAILED

        with mocked_fsync():
            self.manager.apply_nodes()
        self.assertTrue(removal_task._id in self.manager._task_backup)
        self.assertEquals(initial_task._id, self.manager._task_backup[removal_task._id][0])
        self.assertTrue(removal_task in self.manager.node_tasks[node_qi.hostname])
        self.assertFalse(initial_task in self.manager.node_tasks[node_qi.hostname])

        with mocked_fsync():
            self.manager.restore_backed_up_tasks()
            self.manager.cleanup([], set())
        self.assertTrue(initial_task in self.manager.node_tasks[node_qi.hostname])
        self.assertFalse(removal_task in self.manager.node_tasks[node_qi.hostname])

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.Mock())
    def test_cleanup(self):
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        node_qi = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        self.model.create_item("component", "/nodes/node1/comp1")
        task1 = ConfigTask(node_qi, node_qi, "", "1", "1_1")
        task3 = ConfigTask(node_qi, node_qi, "", "1", "1_3")
        task4 = ConfigTask(node_qi, node_qi, "", "1", "1_4")
        task5 = ConfigTask(node_qi, node_qi.comp1, "", "1", "1_5")
        tasks = [task1, task3, task4, task5]

        self.manager.add_phase(tasks, 0)
        with mocked_fsync():
            self.manager.apply_nodes()
        task1.state = constants.TASK_SUCCESS
        task3.state = constants.TASK_STOPPED
        task4.state = constants.TASK_SUCCESS
        task4.model_item._model_item.set_removed()
        task5.state = constants.TASK_SUCCESS
        task5.model_item._model_item.set_removed()

        with mocked_fsync():
            self.manager.cleanup([], set())

        remaining = self.manager.node_tasks[node_qi.hostname]
        # TORF-151105: Removal of Failed tasks done at phase end instead
        self.assertEquals(0, len(remaining))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.Mock())
    def test_cleanup_removed_nodes(self):
        node1_mi = self.model.create_item("node", "/nodes/node1", hostname="node1")
        node1_comp1 = self.model.create_item("component", "/nodes/node1/comp1")
        node1 = QueryItem(self.model, node1_mi)

        node2_mi = self.model.create_item("node", "/nodes/node2", hostname="node2")
        node2 = QueryItem(self.model, node2_mi)

        task1 = ConfigTask(node1, node1, "configure", "1", "1_1")
        task2 = ConfigTask(node1, node1.comp1, "configure", "1", "1_1_1")
        task3 = ConfigTask(node2, node2, "configure", "2", "2_2")

        phase = [task1, task2, task3]
        self.manager.add_phase(phase, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        task1.state = constants.TASK_SUCCESS
        task2.state = constants.TASK_SUCCESS
        task3.state = constants.TASK_SUCCESS

        self.assertTrue(node1.hostname in self.manager.node_tasks)
        self.assertTrue(node2.hostname in self.manager.node_tasks)
        self.assertEqual(2, len(self.manager.node_tasks))

        # cleanup() with removed_nodes, check hostnames removed from node_tasks
        node1_mi.set_applied()
        node1.comp1._model_item.set_removed()
        node2_mi.set_removed()
        with mocked_fsync():
            with mock.patch.object(self.manager, 'apply_removal') as mock_apply_removal:
                self.manager.cleanup([], set())
                # apply_removal() is not run on node2
                self.assertEquals(
                    [mock.call(set(["node1"]))],
                    mock_apply_removal.mock_calls
                )

        self.assertTrue(node1.hostname in self.manager.node_tasks)
        self.assertFalse(node2.hostname in self.manager.node_tasks)
        self.assertEqual(1, len(self.manager.node_tasks))

    # TORF-201562
    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.Mock())
    def test_cleanup_for_removal_nodes(self):
        node1_mi = self.model.create_item("node", "/nodes/node1", hostname="node1")
        node1_comp1 = self.model.create_item("component", "/nodes/node1/comp1")
        node1 = QueryItem(self.model, node1_mi)

        node2_mi = self.model.create_item("node", "/nodes/node2", hostname="node2")
        node2_comp1 = self.model.create_item("component", "/nodes/node2/comp1")
        node2 = QueryItem(self.model, node2_mi)

        task1 = ConfigTask(node1, node1, "configure", "1", "1_1")
        task2 = ConfigTask(node1, node1.comp1, "configure", "1", "1_1_1")
        task3 = ConfigTask(node2, node2, "configure", "2", "2_2")

        phase = [task1, task2, task3]
        self.manager.add_phase(phase, 0)
        with mocked_fsync():
            self.manager.apply_nodes()

        task1.state = constants.TASK_SUCCESS
        task2.state = constants.TASK_SUCCESS
        task3.state = constants.TASK_SUCCESS

        # There are persisted tasks for both nodes
        self.assertEqual(
            set(n.hostname for n in (node1_mi, node2_mi)),
            set(self.manager.node_tasks.keys())
        )

        # We're considering the end of a plan's failed execution in which..
        # 1) Node1's comp1 child has successfully transitioned from FR to
        # Removed
        # 2) Node2 and its remaining progeny are still in the ForRemoval plan
        node1_mi.set_applied()
        node1.comp1._model_item.set_removed()
        node2_mi.set_for_removal()
        node2_mi.comp1.set_for_removal()
        with mocked_fsync():
            with mock.patch.object(self.manager, 'apply_removal') as mock_apply_removal:
                with mock.patch.object(self.manager, '_remove_file') as mock_remove_file:
                    # There are no cleanup tasks and the node on which a failure
                    # occurred is neither node1 nor node2
                    self.manager.cleanup([], set(("some_other_node",)))

                    # apply_removal() is not run on node2
                    self.assertEquals(
                        [mock.call(set(["node1", "some_other_node"]))],
                        mock_apply_removal.mock_calls
                    )
                    # Node2's manifest has *NOT* been removed
                    self.assertEquals(
                        [],
                        mock_remove_file.mock_calls
                    )

        self.assertTrue(node1.hostname in self.manager.node_tasks)
        # There are still persisted tasks for node2, seeing as it's still in
        # the FR state
        self.assertEqual(
            set(n.hostname for n in (node1_mi, node2_mi)),
            set(self.manager.node_tasks.keys())
        )

        # We're considering the end of a plan's successful execution in which..
        # 1) Node2 and its remaining progeny are noe Removed
        node2_mi.set_removed()
        node2_mi.comp1.set_removed()
        with mocked_fsync():
            with mock.patch.object(self.manager, 'apply_removal') as mock_apply_removal:
                with mock.patch.object(self.manager, '_remove_file') as mock_remove_file:
                    # There are no cleanup tasks and the node on which a failure
                    # occurred is neither node1 nor node2
                    self.manager.cleanup([], set())

                    # apply_removal() is not run on node2
                    self.assertEquals(
                        [mock.call(set())],
                        mock_apply_removal.mock_calls
                    )
                    # Node2"s manifest has been removed
                    self.assertEquals(
                        [mock.call('/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node2.pp')],
                        mock_remove_file.mock_calls
                    )

    def test_cleanup_removes_manifests(self):
        expected_node = '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/nodex.pp'

        # No manifest files written
        self.assertFalse(expected_node in self._files)

        self.model.create_item("node", "/nodes/nodex", hostname="nodex")
        node = self._convert_to_query_item(self.model.query_by_vpath("/nodes/nodex"))


        #n for n in self.model_manager.get_all_nodes() if n.is_removed()
        node._model_item.set_removed()
        with mocked_fsync():
            self.manager.cleanup([], set())

        # Check no manifests are left after cleanup
        self.assertFalse(expected_node in self._files)

    @contextlib.contextmanager
    def engine_context():
        yield cherrypy.config["db_storage"]._engine

    @contextlib.contextmanager
    def worker_context(engine):
        yield

    def init_metrics():
        pass

    def configure_worker(engine, **kwargs):
        pass

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.Mock())
    @mock.patch('litp.core.plugin_context_api.PluginApiContext.snapshot_action', return_value='create')
    @mock.patch('litp.core.worker.celery_app.engine_context', side_effect=engine_context)
    @mock.patch('litp.core.worker.celery_app.init_metrics', side_effect=init_metrics)
    @mock.patch('litp.core.worker.celery_app.configure_worker', side_effect=configure_worker)
    @mock.patch('litp.core.worker.celery_app._BaseLitpTask._get_worker_context')
    @mock.patch('litp.core.execution_manager.ExecutionManager.invalidate_restore_model', mock.Mock())
    @mock.patch('litp.core.execution_manager.ExecutionManager._is_node_reachable')
    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file')
    @mock.patch('litp.core.puppet_manager.PuppetMcoProcessor._run_puppet_command')
    def test_all_cleanup_plan(self,
            mocked_rpc_run, mocked_write_file, mocked_reachable_node,
            get_worker, config_worker, metrics, engine, action):

        get_worker.return_value = PuppetManagerTest.worker_context.__func__
        self.plugin_manager = PluginManager(self.model)
        self.manager = PuppetManager(self.model)
        self.manager._open_file = self._mock_open
        self.manager._fchmod = self._mock_fchmod
        self.manager._fchown = self._mock_fchown
        self.manager.get_ms_hostname = mock.Mock(return_value="ms")

        self.executionmanager = ExecutionManager(self.model, self.manager, self.plugin_manager)
        mocked_reachable_node.return_value = True

        cherrypy.config.update({
            'puppet_manager': self.manager,
            'execution_manager': self.executionmanager,
        })

        node_mi = self.model.create_item("node", "/nodes/node1", hostname="node1")
        node_mi.set_applied()

        self.model.create_item("component", "/nodes/node1/comp1")
        package_mi = self.model.create_item("package", "/nodes/node1/comp1/packages/p1")
        package_mi.set_updated()

        node_qi = self.context_api.query_by_vpath("/nodes/node1")
        package_qi = self.context_api.query_by_vpath("/nodes/node1/comp1/packages/p1")

        resource_task = ConfigTask(node_qi, package_qi, 'Apply item', 'notify',
                'foo')
        resource_task._id = "7524a133-3178-41fb-a59f-b6d9b5caa557"
        other_task = ConfigTask(node_qi, node_qi, 'Other task', 'notify',
                'bar')
        other_task._id = "7524a133-3178-41fb-a59f-b6d9b5caa558"

        puppet_not_applying = {
            'node1': {'errors':'', 'data': {'applying': False}},
        }

        puppet_not_running = {
            'node1': {'errors':'', 'data': {'is_running': False}},
        }
        puppet_agent_killed = {
            'node1': {'errors':'', 'data': {'status': 0,
                                            'out': 'Puppet agent not applying',
                                            'err': ""}}
        }
        clear_puppet_cache = {
            'ms' : {'errors': '', 'data':
                    {'status': 0,
                     'err': '',
                     'out': 'HTTP/1.1 204 No Content'}}
        }

        def rpc(*args):
            hostnames, agent, action, action_kwargs = args
            #print(agent, action)
            if (agent, action) in (
                        ('puppetlock', 'clean'),
                        ('puppet', 'disable'),
                        ('puppet', 'enable'),
                    ):
                return puppet_not_applying
            if (agent, action) in (
                        ('puppetlock', 'is_running'),
                    ):
                return puppet_not_running
            if (agent, action) in (
                        ('puppetagentkill', 'kill_puppet_agent'),
                    ):
                return puppet_agent_killed
            elif (agent, action) in (
                        ('puppet', 'runonce'),
                    ):
                feedback = self.manager.Feedback('node1',
                    self.manager.phase_config_version,
                    ','.join((
                        'litp_feedback:task_node1__notify__foo:tuuid_7524a133-3178-41fb-a59f-b6d9b5caa557=success',
                        'litp_feedback:task_node1__notify__bar:tuuid_7524a133-3178-41fb-a59f-b6d9b5caa558=success',
                    )), False)
                self.manager._puppet_feedback(feedback)
                return puppet_not_applying
            elif (agent, action) in (
                        ('rpcutil', 'get_data'),
                    ):
                return {
                    'node1': {'errors':'', 'data': {'present': False}},
                }
            elif (agent, action) in (('puppetcache', 'clean'),):
                return clear_puppet_cache

        mocked_rpc_run.side_effect = rpc

        manifests = defaultdict(StringIO)
        # real PuppetManager._write_file ~ truncate and write, as it
        # calls PuppetManager._open_file to do an open("w")
        def mocked_write(path, contents):
            manifests[path].truncate(0)
            manifests[path].write(contents)
        mocked_write_file.side_effect = mocked_write
        # First "run" a plan where the resource is applied
        self.executionmanager.plan = Plan([[resource_task,
            other_task]])
        self.executionmanager.plan.set_ready()
        with mocked_fsync():
            self.executionmanager.run_plan()
        self.assertTrue(self.executionmanager.plan.is_final())
        self.assertTrue(package_qi.is_applied())
        self.assertEquals('successful', self.executionmanager.plan.state)

        package_mi.set_for_removal()
        removal_task = CleanupTask(package_qi)

        node_manifest_path = '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp'
        self.assertTrue(node_manifest_path in manifests)
        manifests[node_manifest_path].seek(0)
        self.assertEquals(
            '''
class task_node1__notify__bar(){
    notify { "bar":
        tag => ["tuuid_7524a133-3178-41fb-a59f-b6d9b5caa558",],

    }
}

class task_node1__notify__foo(){
    notify { "foo":
        tag => ["tuuid_7524a133-3178-41fb-a59f-b6d9b5caa557",],

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__notify__bar':
    }


    class {'task_node1__notify__foo':
    }


}
'''         ,
            manifests[node_manifest_path].read()
        )

        mocked_rpc_run.reset_mock()
        mocked_write_file.reset_mock()
        del manifests[node_manifest_path]

        # Run a plan comprising only of a CleanupTask for that resource
        self.executionmanager.plan = Plan([], [removal_task], [])
        self.executionmanager.plan.set_ready()
        with mocked_fsync():
            self.executionmanager.run_plan()
        self.assertTrue(node_manifest_path in manifests)
        manifests[node_manifest_path].seek(0)

        # The resource definition has disappeared from the manifest
        self.assertEquals(
            '''
class task_node1__notify__bar(){
    notify { "bar":
        tag => ["tuuid_7524a133-3178-41fb-a59f-b6d9b5caa558",],

    }
}


node "node1" {

    class {'litp::mn_node':
        ms_hostname => "ms",
        cluster_type => "NON-CMW"
        }


    class {'task_node1__notify__bar':
    }


}
'''         ,
            manifests[node_manifest_path].read()
        )

        # But has a new catalog been compiled?
        self.assertEquals(
            [
                mock.call(['node1'], 'puppet', 'disable', None),
                mock.call(['node1'], 'puppetlock', 'clean', None),
                mock.call(['node1'], 'puppet', 'disable', None),
                mock.call(['ms'], 'puppetcache', 'clean', None),
                mock.call(['node1'], 'puppet', 'enable', None),
                mock.call(['node1'], 'puppet', 'runonce', None),
                mock.call(['node1'], 'puppet', 'enable', None),
                mock.call(['node1'], 'puppet', 'enable', None),
            ],
            mocked_rpc_run.mock_calls
        )

    def test_replace_persisted_task_based_on_call_type_call_id(self):
        node1_mitem = self.model.create_item("node", "/nodes/node1", hostname="node1")
        comp1_mitem = self.model.create_item("component", "/nodes/node1/comp1")
        self.model.set_all_applied()
        node1 = self._convert_to_query_item(node1_mitem)
        comp1 = self._convert_to_query_item(comp1_mitem)

        task1 = ConfigTask(node1, comp1, "", "foo1", "bar1", foobar="foobar1")
        task2 = ConfigTask(node1, comp1, "", "foo2", "bar2", foobar="foobar2")
        task3 = ConfigTask(node1, comp1, "", "foo3", "bar3", foobar="foobar2")
        persisted_tasks = [task1, task2, task3]

        self.manager.node_tasks = {
            node1.hostname: persisted_tasks
        }

        task = ConfigTask(node1, comp1, "", "foo2", "bar2", foobar="not_foobar2")
        phase_tasks = [task]

        self.manager.add_phase(phase_tasks, 0)

        persisted_tasks = [task1, task, task3]
        self.assertEquals(persisted_tasks, self.manager.node_tasks[node1.hostname])

    def test_replace_persisted_task_replaced_resource(self):
        node1_mitem = self.model.create_item("node", "/nodes/node1", hostname="node1")
        comp1_mitem = self.model.create_item("component", "/nodes/node1/comp1")
        self.model.set_all_applied()
        node1 = self._convert_to_query_item(node1_mitem)
        comp1 = self._convert_to_query_item(comp1_mitem)

        task1 = ConfigTask(node1, comp1, "", "foo1", "bar1")
        task2 = ConfigTask(node1, comp1, "", "foo2", "bar2")
        task3 = ConfigTask(node1, comp1, "", "foo3", "bar3")
        task4 = ConfigTask(node1, comp1, "", "foo4", "bar4")
        persisted_tasks = [task1, task2, task3, task4]

        self.manager.node_tasks = {
            node1.hostname: persisted_tasks
        }

        task = ConfigTask(node1, comp1, "", "foo", "bar")
        task.replaces.add(("foo2", "bar2"))
        task.replaces.add(("foo3", "bar3"))
        phase_tasks = [task]

        self.manager.add_phase(phase_tasks, 0)

        persisted_tasks = [task1, task4, task]
        self.assertEquals(persisted_tasks, self.manager.node_tasks[node1.hostname])

    def test_restore_replaced_persisted_tasks(self):
        node1_mitem = self.model.create_item("node", "/nodes/node1", hostname="node1")
        comp1_mitem = self.model.create_item("component", "/nodes/node1/comp1")
        self.model.set_all_applied()
        node1 = self._convert_to_query_item(node1_mitem)
        comp1 = self._convert_to_query_item(comp1_mitem)

        task1 = ConfigTask(node1, comp1, "", "foo1", "bar1")
        task2 = ConfigTask(node1, comp1, "", "foo2", "bar2")
        task3 = ConfigTask(node1, comp1, "", "foo3", "bar3")
        task4 = ConfigTask(node1, comp1, "", "foo4", "bar4")
        persisted_tasks = [task1, task2, task3, task4]

        self.manager.node_tasks = {
            node1.hostname: persisted_tasks
        }

        task = ConfigTask(node1, comp1, "", "foo", "bar")
        task.replaces.add(("foo2", "bar2"))
        task.replaces.add(("foo3", "bar3"))
        phase_tasks = [task]

        self.manager.add_phase(phase_tasks, 0)

        task.state = constants.TASK_FAILED

        with mocked_fsync():
            self.manager.restore_backed_up_tasks()
            self.manager.cleanup([], set())

        persisted_tasks = set([task1, task4, task2, task3])
        self.assertEquals(persisted_tasks, set(self.manager.node_tasks[node1.hostname]))


    def test_is_mco_status_error(self):
        host_result = {'errors': '', 'data':
            { 'status': 0,
              'err': '',
              'out': 'HTTP/1.1 204 No Content'}}

        self.assertEquals(False, self.manager._is_mco_status_error(host_result))

        host_result = {'errors': '', 'data':
            {'status': 77,
             'err': 'Not authorized',
             'out': ''}}
        self.assertTrue(True, self.manager._is_mco_status_error(host_result))

    def test_check_mco_agent_status_for_errors(self):

        def create_mco_result (status=0, errors= '', err='', out=''):
            return { 'ms': {'errors': errors, 'data':
            {'status': status,
             'err': err,
            'out': out }}}

        self.assertEqual(create_mco_result(), self.manager.\
                             _check_mco_agent_status_for_errors(["ms"],create_mco_result(),
                                                                'MCO action '
                                                                'clean in agent '
                                                                'puppetcache failed.'))

        host_result = create_mco_result(status=77, errors='',
                                        err='HTTP/1.1 401 Unauthorized')
        expected_host_result = create_mco_result(status=77,
                                                 errors='MCO action clean in '
                                                 'agent puppetcache failed.',
                                                 err= 'HTTP/1.1 401 Unauthorized')
        self.assertEqual(expected_host_result,
                         self.manager._check_mco_agent_status_for_errors(
                             ["ms"],
                             host_result,
                             "MCO action clean in agent puppetcache failed."))

    def test_clear_puppet_cache(self):

        def create_mco_result(status=0, errors='', err='', out=''):
            return {'ms': {'errors': errors, 'data':
                {'status': status,
                 'err': err,
                 'out': out}}}

        self.manager.mco_processor.clear_puppet_cache = mock.Mock()

        mco_result = create_mco_result (out='HTTP/1.1 204 No content')
        expected_result = create_mco_result (out='HTTP/1.1 204 No content')

        self.manager.mco_processor.clear_puppet_cache.return_value \
            = mco_result

        self.assertEquals(expected_result, self.manager._clear_puppet_cache(["ms"]))


        mco_result =  {'ms': { 'errors': 'No answer from node ms',
                      'data': {}}}
        expected_result = {'ms': { 'errors': 'No answer from node ms',
                      'data': {}}}

        self.manager.mco_processor.clear_puppet_cache.return_value \
            = mco_result
        self.assertEquals(expected_result, self.manager._clear_puppet_cache(["ms"]))

    @mock.patch('litp.core.puppet_manager.log')
    def test_stop_puppet_applying(self, mock_log):
        self.manager.mco_processor.stop_puppet_applying = mock.Mock()
        hostnames = ["ms", "node1"]
        mco_result = {}
        for hostname in set(hostnames):
            mco_result[hostname] = {'errors': '', 'data': {'status': 0,
                                         'out': 'Puppet agent not applying',
                                         'err': ""}}

        self.manager.mco_processor.stop_puppet_applying.return_value \
            = mco_result

        self.assertEquals(None, self.manager._stop_puppet_applying(["node1", "ms"]))
        mock_log.trace.info.assert_has_calls(
            [mock.call("Puppet agent not applying on host: {0}".format(hostnames[1])),
             mock.call("Puppet agent not applying on host: {0}".format(hostnames[0]))])


        mock_log.reset_mock()
        mco_result = {}
        for hostname in set(hostnames):
            mco_result[hostname] = {'errors': '', 'data': {'status': 0,
                                        'out': 'Puppet agent not applying',
                                        'err': ""}}

        mco_result[hostnames[1]]['data']['status'] = 1
        mco_result[hostnames[1]]['data']['out'] = "Puppet agent not terminated"
        self.manager.mco_processor.stop_puppet_applying.return_value \
            = mco_result

        self.assertRaises(McoFailed, self.manager._stop_puppet_applying, hostnames)
        mock_log.event.error.assert_has_calls(
            [mock.call("Mco action kill_puppet_agent failed on host: {0}"
                       .format(hostnames[1]))])


        expected_result = {}
        mco_result = {}
        for hostname in set(hostnames):
            mco_result[hostname] = {'errors': '', 'data': {'status': 0,
                                                           'out': 'Puppet agent not applying',
                                                           'err': ""}}
            expected_result[hostname] = {'errors': '', 'data': {'status': 0,
                                                           'out': 'Puppet agent not applying',
                                                           'err': ""}}

        mco_result[hostnames[1]]['data']['status'] = 1
        mco_result[hostnames[1]]['data']['out'] = "Puppet agent not terminated"

        expected_result[hostnames[1]]['data']['status'] = 1
        expected_result[hostnames[1]]['data']['out'] = "Puppet agent not terminated"
        expected_result[hostnames[1]]['errors'] = "MCO action kill_puppet_agent failed"
        self.manager.mco_processor.stop_puppet_applying.return_value \
            = mco_result

        try:
            self.manager._stop_puppet_applying(hostnames)
        except McoFailed as e:
            self.assertEquals(e.result, expected_result)

        mock_log.reset_mock()
        mco_result = {}
        for hostname in set(hostnames):
            mco_result[hostname] = {'errors': '', 'data': {'status': 0,
                                                           'out': 'Puppet agent not applying',
                                                           'err': ""}}

        mco_result[hostnames[1]]['data'] = {}
        mco_result[hostnames[1]]['errors'] = constants.BASE_RPC_NO_ANSWER
        self.manager.mco_processor.stop_puppet_applying.return_value \
            = mco_result
        self.assertRaises(McoFailed, self.manager._stop_puppet_applying,
                          hostnames)

        mock_log.event.error.assert_has_calls(
            [mock.call("Mco action kill_puppet_agent failed on host: {0}"
                       .format(hostnames[1]))])

        mock_log.reset_mock()
        expected_result = {}
        mco_result = {}
        for hostname in set(hostnames):
            mco_result[hostname] = {'errors': '', 'data': {'status': 0, ''
                                                            'out': 'Puppet agent not applying',
                                                           'err': ""}}
            expected_result[hostname] = {'errors': '', 'data': {'status': 0,
                                                                'out': 'Puppet agent not applying',
                                                                'err': ""}}
        mco_result[hostnames[1]]['data'] = {}
        mco_result[hostnames[1]]['errors'] = constants.BASE_RPC_NO_ANSWER

        expected_result[hostnames[1]]['data'] = {}
        expected_result[hostnames[1]]['errors'] = constants.BASE_RPC_NO_ANSWER
        self.manager.mco_processor.stop_puppet_applying.return_value = mco_result

        try:
            self.manager._stop_puppet_applying(hostnames)
        except McoFailed as e:
            self.assertEquals(e.result, expected_result)


class PuppetManagerApplyRemovalTest(BasePuppetManagerTest):
    def setUp(self):
        super(PuppetManagerApplyRemovalTest, self).setUp()

        self.model.create_item("node", "/nodes/ms", hostname="ms")
        self.model.create_item("node", "/nodes/node1", hostname="node1")

        self.manager.mco_processor.puppetlock_clean = mock.Mock()
        self.manager.mco_processor.disable_puppet = mock.Mock()
        self.manager.mco_processor.enable_puppet = mock.Mock()
        self.manager.mco_processor.runonce_puppet = mock.Mock()

        self.manager.mco_processor.puppetlock_is_running = mock.Mock()
        self.manager.mco_processor.puppetlock_is_running.return_value = {
            'node1': {
                'errors': [],
                'data': {'is_running': True}
            }
        }

        self.manager._write_file = mock.Mock()

        self.ms = self._convert_to_query_item(self.model.query_by_vpath("/nodes/ms"))
        self.node1 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        self.model.create_item("another-component", "/nodes/node1/comp2")

        self.deconfigure_task = ConfigTask(self.node1, self.node1.comp2,
                "Deconfigure Task", "call1", "task_call", ensure="absent")

        self.node1.comp2._model_item.set_for_removal()
        self.deconfigure_task.state = constants.TASK_RUNNING
        self.manager.node_tasks = {
            'node1': [self.deconfigure_task]
        }

        # Initially, we have an Aplied "deconfigure" ConfigTask with something
        # like "ensure => absent"
        with mocked_fsync():
            self.manager.add_phase([self.deconfigure_task], 0)
            self.manager.apply_nodes()

        self.manager.mco_processor.puppetlock_is_running.return_value = {
            'node1': {
                'errors': [],
                'data': {'is_running': False}
            }
        }
        deconfigure_task_manifest='''
class task_node1__call1__task__call(){{
    call1 {{ "task_call":
        tag => ["tuuid_{uuid}",],
        ensure => "absent"
    }}
}}


node "node1" {{

    class {{\'litp::mn_node\':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


    class {{\'task_node1__call1__task__call\':
    }}


}}\n'''.format(uuid=self.deconfigure_task.uuid)

        node1_manifest_calls = self._find_manifest_write_calls_for_node(
            "node1",
            self.manager._write_file.mock_calls
        )
        self.assertEquals(1, len(node1_manifest_calls))
        self.assertEquals(
            mock.call(
                '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp',
                deconfigure_task_manifest
            ),
            node1_manifest_calls[0]
        )
        self.manager._write_file.reset_mock()
        self.manager.mco_processor.puppetlock_clean.reset_mock()
        self.manager.mco_processor.disable_puppet.reset_mock()
        self.manager.mco_processor.enable_puppet.reset_mock()
        self.manager.mco_processor.puppetlock_is_running.reset_mock()
        self.manager.mco_processor.runonce_puppet.reset_mock()

    @staticmethod
    def _find_manifest_write_calls_for_node(hostname, mock_calls):
        matches = []
        for mock_call in mock_calls:
            positional_args = mock_call[1]
            if positional_args[0].endswith(hostname + ".pp"):
                matches.append(mock_call)
        return matches

    def _reset_mocks_and_node_tasks(self, pre_cleanup_node_tasks):
        self.manager.mco_processor.puppetlock_clean.reset_mock()
        self.manager.mco_processor.disable_puppet.reset_mock()
        self.manager.mco_processor.enable_puppet.disable_puppet.reset_mock()
        self.manager.mco_processor.runonce_puppet.disable_puppet.reset_mock()
        self.manager.node_tasks = dict(pre_cleanup_node_tasks)

    def test_deconfigure_task_removal(self):
        self.deconfigure_task.state = constants.TASK_SUCCESS
        self.node1.comp2._model_item.set_removed()

        # The deconfigure task is applied, let's deconfigure it
        with mocked_fsync():
            self.manager.cleanup([], set())

        cleanedup_manifest='''

node "node1" {{

    class {{\'litp::mn_node\':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


}}\n'''.format(uuid=self.deconfigure_task.uuid)

        node1_manifest_calls = self._find_manifest_write_calls_for_node(
            "node1",
            self.manager._write_file.mock_calls
        )

        self.assertEquals(1, len(node1_manifest_calls))
        self.assertEquals(
            mock.call(
            '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp',
            cleanedup_manifest
        ),
            node1_manifest_calls[0]
        )

        self.manager.mco_processor.puppetlock_clean.assert_called_once_with(['node1'])
        self.manager.mco_processor.disable_puppet.assert_called_once_with(['node1'])
        self.manager.mco_processor.puppetlock_is_running.assert_called_once_with(['node1'])
        self.manager.mco_processor.enable_puppet.assert_called_once_with(['node1'])
        self.manager.mco_processor.runonce_puppet.assert_called_once_with(['node1'])

    def test_mco_error_during_cleanup(self):
        self.deconfigure_task.state = constants.TASK_SUCCESS
        self.node1.comp2._model_item.set_removed()
        pre_cleanup_node_tasks = dict(self.manager.node_tasks)

        self.manager.mco_processor.puppetlock_clean.return_value = {
            'node1': {'errors': "OH NO!!!!!"}
        }
        # The deconfigure task is applied, let's deconfigure it
        with mocked_fsync():
            with mock.patch('litp.core.puppet_manager.log') as mock_logger:
                self.manager.cleanup([], set())
                self.assertEquals(
                    [mock.call(
                        ("An error occurred during LITP's Puppet clean-up "
                            "before the manifests were written.")
                    )],
                    mock_logger.event.error.mock_calls
                )

        self.manager.mco_processor.puppetlock_clean.assert_called_once_with(['node1'])
        self.assertEquals([], self.manager.mco_processor.disable_puppet.mock_calls)
        self.assertEquals([], self.manager.mco_processor.puppetlock_is_running.mock_calls)
        # The MCo error occurred before the manifest was overwritten
        node1_manifest_calls = self._find_manifest_write_calls_for_node(
            "node1",
            self.manager._write_file.mock_calls
        )
        self.assertEquals(0, len(node1_manifest_calls))
        self.assertEquals([], self.manager.mco_processor.enable_puppet.disable_puppet.mock_calls)
        self.assertEquals([], self.manager.mco_processor.runonce_puppet.disable_puppet.mock_calls)

        # Reset
        self._reset_mocks_and_node_tasks(pre_cleanup_node_tasks)
        self.manager.mco_processor.puppetlock_clean = mock.Mock()

        cleanedup_manifest='''

node "node1" {{

    class {{\'litp::mn_node\':
        ms_hostname => "ms_hostname",
        cluster_type => "NON-CMW"
        }}


}}\n'''.format(uuid=self.deconfigure_task.uuid)


        # The MCo error occurred *after* the manifest was overwritten
        self.manager.mco_processor.enable_puppet.return_value = {
            'node1': {'errors': "..."}
        }

        with mocked_fsync():
            with mock.patch('litp.core.puppet_manager.log') as mock_logger:
                self.manager.cleanup([], set())
                self.assertEquals(
                    [mock.call(
                        ("An error occurred during LITP's Puppet clean-up "
                            "after the manifests were written.")
                    )],
                    mock_logger.event.error.mock_calls
                )

        self.manager.mco_processor.puppetlock_clean.assert_called_once_with(['node1'])
        self.manager.mco_processor.disable_puppet.assert_called_once_with(['node1'])
        self.manager.mco_processor.puppetlock_is_running.assert_called_once_with(['node1'])

        node1_manifest_calls = self._find_manifest_write_calls_for_node(
            "node1",
            self.manager._write_file.mock_calls
        )
        self.assertEquals(1, len(node1_manifest_calls))
        self.assertEquals(
            mock.call(
                '/opt/ericsson/nms/litp/etc/puppet/manifests/plugins/node1.pp',
                cleanedup_manifest
            ),
            node1_manifest_calls[0]
        )
        self.assertEquals([], self.manager.mco_processor.enable_puppet.disable_puppet.mock_calls)
        self.assertEquals([], self.manager.mco_processor.runonce_puppet.disable_puppet.mock_calls)

    def test_is_running_during_cleanup(self):
        self.deconfigure_task.state = constants.TASK_SUCCESS
        self.node1.comp2._model_item.set_removed()
        pre_cleanup_node_tasks = dict(self.manager.node_tasks)

        self.manager.mco_processor.puppetlock_is_running.side_effect = \
                McoFailed("Puppet won't stop running")

        # The configure task is applied, let's deconfigure it
        with mocked_fsync():
            with mock.patch('litp.core.puppet_manager.log') as mock_logger:
                self.manager.apply_removal(['node1'])
                self.assertEquals(
                    [mock.call(
                        ("An error occurred during LITP checking puppet status"
                            " before the manifests were written.")
                    )],
                    mock_logger.event.error.mock_calls
                )

        self.assertEquals([call(['node1'])], self.manager.mco_processor.puppetlock_clean.mock_calls)
        self.assertEquals([call(['node1'])], self.manager.mco_processor.disable_puppet.mock_calls)
        self.assertEquals([call(['node1'])], self.manager.mco_processor.puppetlock_is_running.mock_calls)
        # We don't go any further
        # The MCo error occurred before the manifest was overwritten
        node1_manifest_calls = self._find_manifest_write_calls_for_node(
            "node1",
            self.manager._write_file.mock_calls
        )
        self.assertEquals(0, len(node1_manifest_calls))
        self.assertEquals([], self.manager.mco_processor.enable_puppet.mock_calls)
        self.assertEquals([], self.manager.mco_processor.runonce_puppet.mock_calls)

class PuppetManagerApplyNodesTest(BasePuppetManagerTest):
    def setUp(self):
        super(PuppetManagerApplyNodesTest, self).setUp()

        self.model.create_item("node", "/nodes/ms", hostname="ms")
        self.model.create_item("node", "/nodes/node1", hostname="node1")
        self.model.create_item("node", "/nodes/node2", hostname="node2")
        self.model.create_item("node", "/nodes/node3", hostname="node3")

        self.manager.mco_processor.disable_puppet_orig = \
            self.manager.mco_processor.disable_puppet
        self.manager.mco_processor.enable_puppet_orig = \
            self.manager.mco_processor.enable_puppet
        self.manager.mco_processor.stop_puppet_applying_orig = \
            self.manager.mco_processor.stop_puppet_applying
        self.manager.mco_processor.runonce_puppet_orig = \
            self.manager.mco_processor.runonce_puppet
        self.manager.mco_processor.puppetlock_clean_orig = \
            self.manager.mco_processor.puppetlock_clean
        self.manager.mco_processor.clear_puppet_cache_orig = \
            self.manager.mco_processor.clear_puppet_cache

        self.manager.mco_processor.stop_puppet_applying = mock.Mock()
        self.manager.mco_processor.runonce_puppet = mock.Mock()
        self.manager.mco_processor.disable_puppet = mock.Mock()
        self.manager.mco_processor.enable_puppet = mock.Mock()
        self.manager.mco_processor.clear_puppet_cache = mock.Mock()
        self.manager.get_ms_hostname = mock.Mock(return_value="ms")

        self.ms = self._convert_to_query_item(self.model.query_by_vpath("/nodes/ms"))
        self.node1 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node1"))
        self.node2 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node2"))
        self.node3 = self._convert_to_query_item(self.model.query_by_vpath("/nodes/node3"))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status',
                mock.MagicMock())
    def test_no_ms(self):
        task0 = ConfigTask(self.ms, self.ms, "", "0", "0_1")
        task0.state = constants.TASK_SUCCESS
        task1 = ConfigTask(self.node1, self.node1, "", "1", "1_1")
        task1.state = constants.TASK_RUNNING
        task2 = ConfigTask(self.node2, self.node2, "", "2", "2_1")
        task2.state = constants.TASK_RUNNING
        task3 = ConfigTask(self.node3, self.node3, "", "3", "3_1")
        task3.state = constants.TASK_SUCCESS

        self.manager.mco_processor.stop_puppet_applying.return_value = \
            {'node1': {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}},
             'node2': {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}}
             }

        self.manager.mco_processor.clear_puppet_cache.return_value = {
            self.manager.get_ms_hostname(): {'errors': '', 'data':
                {'status': 0,
                 'err': '',
                 'out': 'HTTP/1.1 204 No Content'}}
        }

        self.manager.node_tasks = {
            self.ms.hostname: [task0],
            self.node1.hostname: [task1],
            self.node2.hostname: [task2],
            self.node3.hostname: [task3],
        }
        with mocked_fsync():
            self.manager.add_phase([task1, task2], 0)
            self.manager.apply_nodes()

        self.assertEquals(1, self.manager.mco_processor.disable_puppet.call_count)
        self.assertEquals(set([self.node1.hostname, self.node2.hostname]), set(self.manager.mco_processor.disable_puppet.call_args_list[0][0][0]))
        self.assertEquals(1, self.manager.mco_processor.enable_puppet.call_count)
        self.assertEquals(set([self.node1.hostname, self.node2.hostname]), set(self.manager.mco_processor.enable_puppet.call_args_list[0][0][0]))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_no_nodes(self):
        self.manager.mco_processor.stop_puppet_applying.return_value = \
            {self.ms.hostname: {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}}
            }

        self.manager.mco_processor.clear_puppet_cache.return_value = {
            self.ms.hostname: {'errors': '', 'data':
                {'status': 0,
                 'err': '',
                 'out': 'HTTP/1.1 204 No Content'}}
        }

        task0 = ConfigTask(self.ms, self.ms, "", "0", "0_1")
        task0.state = constants.TASK_RUNNING
        task1 = ConfigTask(self.node1, self.node1, "", "1", "1_1")
        task1.state = constants.TASK_SUCCESS
        task2 = ConfigTask(self.node2, self.node2, "", "2", "2_1")
        task2.state = constants.TASK_SUCCESS
        task3 = ConfigTask(self.node3, self.node3, "", "3", "3_1")
        task3.state = constants.TASK_SUCCESS

        self.manager.node_tasks = {
            self.ms.hostname: [task0],
            self.node1.hostname: [task1],
            self.node2.hostname: [task2],
            self.node3.hostname: [task3],
        }
        with mocked_fsync():
            self.manager.add_phase([task0], 0)
            self.manager.apply_nodes()

        self.assertEquals(1, self.manager.mco_processor.disable_puppet.call_count)
        self.assertEquals(set([self.ms.hostname]), set(self.manager.mco_processor.disable_puppet.call_args_list[0][0][0]))
        self.assertEquals(1, self.manager.mco_processor.enable_puppet.call_count)
        self.assertEquals(set([self.ms.hostname]), set(self.manager.mco_processor.enable_puppet.call_args_list[0][0][0]))

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    def test_nodes_and_ms(self):
        task0 = ConfigTask(self.ms, self.ms, "", "0", "0_1")
        task0.state = constants.TASK_RUNNING
        task1 = ConfigTask(self.node1, self.node1, "", "1", "1_1")
        task1.state = constants.TASK_RUNNING
        task2 = ConfigTask(self.node2, self.node2, "", "2", "2_1")
        task2.state = constants.TASK_RUNNING
        task3 = ConfigTask(self.node3, self.node3, "", "3", "3_1")
        task3.state = constants.TASK_SUCCESS

        self.manager.mco_processor.stop_puppet_applying.return_value = \
            {'node1': {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}},
             'ms':  {'errors': '', 'data': {'status': 0,
                                            'out': 'Puppet agent not applying',
                                            'err': ""}},
             'node2': {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}}
            }

        self.manager.mco_processor.clear_puppet_cache.return_value = {
            self.ms.hostname: {'errors': '', 'data':
                {'status': 0,
                 'err': '',
                 'out': 'HTTP/1.1 204 No Content'}}
        }

        self.manager.node_tasks = {
            self.ms.hostname: [task0],
            self.node1.hostname: [task1],
            self.node2.hostname: [task2],
            self.node3.hostname: [task3],
        }
        with mocked_fsync():
            self.manager.add_phase([task0, task1, task2], 0)
            self.manager.apply_nodes()

        self.assertEquals(1, self.manager.mco_processor.disable_puppet.call_count)
        self.assertEquals(set([self.ms.hostname, self.node1.hostname, self.node2.hostname]), set(self.manager.mco_processor.disable_puppet.call_args_list[0][0][0]))
        self.assertEquals(2, self.manager.mco_processor.enable_puppet.call_count)
        self.assertEquals(set([self.node1.hostname, self.node2.hostname]), set(self.manager.mco_processor.enable_puppet.call_args_list[0][0][0]))
        self.assertEquals(set([self.ms.hostname]), set(self.manager.mco_processor.enable_puppet.call_args_list[1][0][0]))

    def test_run_puppet_retry(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.01
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.01

        _mocked_results = [
            {
                "foo": {
                    "errors": "oops"
                }
            },
            {
                "foo": {
                    "errors": "oops"
                }
            },
            {
                "foo": {
                    "errors": ""
                }
            }
        ]

        def _mock_run_puppet_command(*args, **kwargs):
            return _mocked_results.pop(0)

        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=_mock_run_puppet_command)
        self.manager.mco_processor.run_puppet(["foo"], "puppet", "bar")

        self.assertEquals(3, self.manager.mco_processor._run_puppet_command.call_count)

    def test_disable_puppet_if_disabled_already(self):
        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 0.01
        self.manager.mco_processor.MCO_ACTION_WAIT_BETWEEN_RETRIES = 0.01

        _mocked_results = [
            {
                "foo": {
                    "errors": "Could not disable Puppet: Already disabled"
                }
            }
        ]

        def _mock_run_puppet_command(*args, **kwargs):
            return _mocked_results.pop(0)

        self.manager.mco_processor._run_puppet_command = mock.Mock(side_effect=_mock_run_puppet_command)
        self.manager.mco_processor.run_puppet(["foo"], "puppet", "disable")

        self.assertEquals(1, self.manager.mco_processor._run_puppet_command.call_count)

    @mock.patch('litp.core.puppet_manager.PuppetManager._sleep', mock.Mock())
    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file', mock.Mock())
    @mock.patch('litp.core.puppet_manager.PuppetManager.PUPPET_RUN_TOTAL_TIMEOUT', 0.0001)
    @mock.patch('litp.core.puppet_manager.PuppetManager.PUPPET_RUN_WAIT_BETWEEN_RETRIES', 0.01)
    @mock.patch('litp.core.puppet_manager.PuppetMcoProcessor.MCO_ACTION_WAIT_BETWEEN_RETRIES', 0.01)
    def test_puppet_phase_completes_with_running_tasks(self):
        del self.manager
        self.manager = PuppetManager(self.model)
        self.manager._open_file = self._mock_open
        self.manager._fchmod = self._mock_fchmod
        self.manager._fchown = self._mock_fchown
        self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.00001

        self.plugin_manager = PluginManager(self.model)
        self.executionmanager = ExecutionManager(
            self.model,
            self.manager,
            self.plugin_manager
        )
        self.executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))

        self.manager.get_ms_hostname = mock.Mock(return_value="ms")

        rpc_failure_dict = {
            self.node1.hostname: {'errors':'Puppet runonce failed', 'data': ''},
            self.node2.hostname: {'errors':'', 'data': ''},
            self.node3.hostname: {'errors':'', 'data': ''},
        }

        rpc_success_dict = {
            self.node1.hostname: {'errors':'', 'data': ''},
            self.node2.hostname: {'errors':'', 'data': ''},
            self.node3.hostname: {'errors':'', 'data': ''},
        }

        rpc_not_running = {
            self.node1.hostname: {'errors':'', 'data': {'is_running': False}},
            self.node2.hostname: {'errors':'', 'data': {'is_running': False}},
            self.node3.hostname: {'errors':'', 'data': {'is_running': False}},
        }
        clear_puppet_cache = {
          self.ms.hostname:  {'errors': '', 'data':
              {'status': 0,
               'err': '',
               'out': 'HTTP/1.1 204 No Content'}}
        }

        stop_puppet_applying = {
            self.node1.hostname: {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}},
            self.node2.hostname: {'errors': '', 'data': {'status': 0,
                                            'out': 'Puppet agent not applying',
                                            'err': ""}},
            self.node3.hostname: {'errors': '', 'data': {'status': 0,
                                              'out': 'Puppet agent not applying',
                                              'err': ""}},
        }

        def fail_puppet_runonce(hostnames, agent, action, action_kwargs):
            if ('puppet', 'runonce') == (agent, action):
                return rpc_failure_dict
            elif ('puppet', 'status') == (agent, action):
                return {
                    self.node1.hostname: {'errors':'', 'data': {'applying': False}},
                    self.node2.hostname: {'errors':'', 'data': {'applying': False}},
                    self.node3.hostname: {'errors':'', 'data': {'applying': False}},
                }
            elif ('puppetlock', 'is_running') == (agent, action):
                # No lock file, we're ready to write manifests
                return rpc_not_running
            elif ('puppetagentkill', 'kill_puppet_agent') == (agent, action):
                return stop_puppet_applying
            elif ('puppetcache', 'clean') == (agent, action):
                return clear_puppet_cache
            else:
                return rpc_success_dict

        mock_puppet_rpc = mock.Mock(side_effect=fail_puppet_runonce)
        self.manager.mco_processor._run_puppet_command = mock_puppet_rpc

        task1 = ConfigTask(self.node1, self.node1, "", "1", "1_1")
        task1.state = constants.TASK_RUNNING
        task2 = ConfigTask(self.node2, self.node2, "", "2", "2_1")
        task2.state = constants.TASK_RUNNING
        task3 = ConfigTask(self.node3, self.node3, "", "3", "3_1")
        task3.state = constants.TASK_RUNNING

        self.manager.node_tasks = {
            self.node1.hostname: [task1],
            self.node2.hostname: [task2],
            self.node3.hostname: [task3],
        }
        with mocked_fsync():
            self.executionmanager._run_puppet_phase(0, [task1, task2, task3])
            self.executionmanager._wait_for_puppet_manager([task1, task2, task3])

        for task in (task1, task2, task3):
            self.assertTrue(task.has_run())
            self.assertEquals(constants.TASK_FAILED, task.state)

    @mock.patch('litp.core.puppet_manager.PuppetManager.PUPPET_LOCK_TIMEOUT', 0.1)
    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file', mock.Mock())
    def test_torf_168190_unreachable_node_during_status_check(self):
        # This will require two batches with concurrency set to 3
        all_node_hostnames = ['node1', 'node2', 'node3', 'node4']
        self.manager.mco_processor.MCO_CLI_TIMEOUT = 0.001  # seconds
        self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.01  # seconds
        self.manager.mco_processor.smart_sleep = mock.Mock()

        self.manager.PUPPET_RUN_WAIT_BETWEEN_RETRIES = 4

        # The MCo processor will raise a timeout exception after this delay
        #self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.02

        def mco_puppet_status_node_unreachable(hostnames, agent, action, action_kwargs):
            return_dict = {}
            for hostname in set(hostnames) ^ set(['node3']):
                return_dict[hostname] = {
                    'errors': '',
                    'data': {'is_running': False},
                }
            return_dict['node3'] = {
                'data': {},
                'errors': "{0} {1}".format(constants.BASE_RPC_NO_ANSWER, 'node3')
            }
            return return_dict

        self.manager.mco_processor._run_puppet_command = mock.Mock(
            side_effect=mco_puppet_status_node_unreachable
        )
        # The Puppet manager's _check_pupet_status *does* not raise a McoFailed
        # exception, since the logic used in the MCo processor ensures that it
        # sees a fully populated dictionary encompassing all the nodes,
        # including the unreachable node, with the latter being marked as
        # unreachable.
        try:
            self.manager._check_puppet_status(all_node_hostnames)
        except McoFailed as mco_exception:
            self.fail()

    @mock.patch('litp.core.puppet_manager.PuppetManager.PUPPET_LOCK_TIMEOUT', 0.1)
    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file', mock.Mock())
    def test_torf_168190_agent_wont_stop_running_on_one_node(self):
        # This will require two batches with concurrency set to 3
        all_node_hostnames = ['node1', 'node2', 'node3', 'node4']
        self.manager.mco_processor.MCO_CLI_TIMEOUT = 0.001  # seconds
        self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.01  # seconds
        self.manager.mco_processor.smart_sleep = mock.Mock()

        # The MCo processor will raise a timeout exception after this delay
        #self.manager.mco_processor.PUPPET_RUN_TOTAL_TIMEOUT = 0.02

        def mco_puppet_status_node_unreachable(hostnames, agent, action, action_kwargs):
            return_dict = {}
            for hostname in set(hostnames) ^ set(['node3']):
                return_dict[hostname] = {
                    'errors': '',
                    'data': {'is_running': False},
                }
            return_dict['node3'] = {
                'data': {'is_running': True},
                'errors': '',
            }
            return return_dict

        self.manager.mco_processor._run_puppet_command = mock.Mock(
            side_effect=mco_puppet_status_node_unreachable
        )
        self.assertRaises(McoFailed, self.manager._check_puppet_status, all_node_hostnames, )

        # We only see the node on which the agent won't stop in the dictionary
        # attached to the exception
        try:
            self.manager._check_puppet_status(all_node_hostnames)
        except McoFailed as mco_exception:
            return_value = mco_exception.result
            self.assertEquals(
                {'node3': {'data': {'is_running': True}, 'errors': 'Puppet agent lock file present'}},
                return_value
            )

    @mock.patch('litp.core.puppet_manager.PuppetManager._write_file', mock.Mock())
    def test_litpcds_11610_break_apply_nodes_on_mco_error(self):

        def execute_test_and_check_result(manager, no_times_ok_response,
                                          methods_not_called, methods_called):
            executionmanager = ExecutionManager(self.model, manager, mock.Mock())
            executionmanager.plan = mock.Mock(is_stopping=mock.Mock(return_value=False))
            self._mock_mco_timeouts()
            MAX_TRIES = 15

            results = []
            ok_response = {'node1': {'errors': ''},
                           'node2': {'errors': ''},
                           'node3': {'errors': ''}}
            stop_puppet_applying_ok = {
                'node1': {'errors': '', 'data': {'status': 0,
                                                 'out': 'Puppet agent not applying',
                                                 'err': ""}},
                'node2': {'errors': '', 'data': {'status': 0,
                                                 'out': 'Puppet agent not applying',
                                                 'err': ""}},
                'node3': {'errors': '', 'data': {'status': 0,
                                                 'out': 'Puppet agent not applying',
                                                 'err': ""}},
            }
            stop_puppet_applying_error = {
                'node1': {'errors': '', 'data': {'status': 0,
                                                 'out': 'Puppet agent not applying',
                                                 'err': ""}},
                'node2': {'errors': 'Node not reachable', 'data': {'status': 0,
                                                                   'out': 'Puppet agent not applying',
                                                                   'err': ""}},
                'node3': {'errors': '', 'data': {'status': 0,
                                                 'out': 'Puppet agent not applying',
                                                 'err': ""}},
            }
            error_response = {'node1': {'data': '', 'errors': ''},
                              'node2': {'data': {'status': 'running'}, 'errors': 'Ugly error'},
                              'node3': {'data': '', 'errors': ''}}

            clear_puppet_cache_ok = {
                self.manager.get_ms_hostname(): {'errors': '', 'data':
                    {'status': 0,
                     'err': '',
                     'out': 'HTTP/1.1 204 No Content'}}
            }

            clear_puppet_cache_error = {
                self.manager.get_ms_hostname(): {'errors': '', 'data':
                    {'status': 1,
                     'err': 'Unauthorized access',
                     'out': ''}}
            }

            for i in range(no_times_ok_response):
                if i == 1:
                    results.append(stop_puppet_applying_ok)
                elif i == 3:
                    results.append(clear_puppet_cache_ok)
                else:
                    results.append(ok_response)
            for i in range(MAX_TRIES):
                if no_times_ok_response == 1:
                    results.append(stop_puppet_applying_error)
                elif no_times_ok_response == 3:
                    results.append(clear_puppet_cache_error)
                else:
                    results.append(error_response)

            manager.mco_processor._run_puppet_command = mock.Mock(
                side_effect=give_results(results))

            manager.emit = mock.Mock(side_effect=manager.emit)

            tasks_node1 = generate_n_config_tasks(2, self.node1, self.model)
            tasks_node2 = generate_n_config_tasks(2, self.node2, self.model)
            tasks_node3 = generate_n_config_tasks(2, self.node3, self.model)

            # Tasks are set to Running on add_phase
            self.manager.add_phase(tasks_node1 + tasks_node2 + tasks_node3, 0)
            set_tasks_state(constants.TASK_SUCCESS, *tasks_node3)
            manager.apply_nodes()

            for method in methods_called:
                self.assertTrue(method.called)
            for method in methods_not_called:
                self.assertFalse(method.called)

            # ExecutionManager.on_mco_error should have been called and failed
            # all running tasks.
            for task in tasks_node1 + tasks_node2:
                self.assertEquals(task.state, constants.TASK_FAILED)

            # But don't change successful tasks to failed
            for task in tasks_node3:
                self.assertEquals(task.state, constants.TASK_SUCCESS)

            manager.emit.assert_called_with('on_mco_error', manager.phase_tasks)

        manager = self.manager
        manager.mco_processor.stop_puppet_applying = \
            mock.Mock(side_effect=manager.mco_processor.stop_puppet_applying_orig)
        manager.mco_processor.disable_puppet = \
            mock.Mock(side_effect=manager.mco_processor.disable_puppet_orig)
        manager.mco_processor.puppetlock_clean = \
            mock.Mock(side_effect=manager.mco_processor.puppetlock_clean_orig)
        manager.mco_processor.runonce_puppet = \
            mock.Mock(side_effect=manager.mco_processor.runonce_puppet_orig)
        manager._write_templates = mock.Mock()
        manager.mco_processor.clear_puppet_cache = mock.Mock(side_effect=
                                                             manager.mco_processor.
                                                             clear_puppet_cache_orig)
        manager.mco_processor.enable_puppet = mock.Mock(side_effect=
                                                      manager.mco_processor.
                                                      enable_puppet_orig)

        # Test 1, verfiy that if disable puppet fails, stop_puppet_applying is
        # not called
        methods_called = [manager.mco_processor.disable_puppet]
        methods_not_called = [manager.mco_processor.stop_puppet_applying]
        num_ok_response = 0

        execute_test_and_check_result(manager, num_ok_response,
                                      methods_not_called, methods_called)

        # Test2, verify that if stop_puppet_applying fails that
        # puppetlock_clean is not called
        methods_called.append(manager.mco_processor.stop_puppet_applying)
        methods_not_called = [manager.mco_processor.puppetlock_clean]
        num_ok_response += 1

        execute_test_and_check_result(manager, num_ok_response,
                                      methods_not_called, methods_called)

        # Test3, verify that if puppetlock_clean fails that
        # write_templates is not called
        methods_called.append(manager.mco_processor.puppetlock_clean)
        methods_not_called = [manager._write_templates]
        num_ok_response += 1

        execute_test_and_check_result(manager, num_ok_response,
                                      methods_not_called, methods_called)

        # Test4, verify that if clear_puppet_cache fails that
        # enable_puppet is not called
        methods_called.append(manager.mco_processor.clear_puppet_cache)
        methods_not_called = [manager.mco_processor.enable_puppet]
        num_ok_response += 1

        execute_test_and_check_result(manager, num_ok_response,
                                      methods_not_called, methods_called)

        # Test5, verify that if enable_puppet fails that runonce_puppet
        # is not called
        methods_called.append(manager.mco_processor.enable_puppet)
        methods_not_called = [manager.mco_processor.runonce_puppet]
        num_ok_response += 1


        # Test6, verify that if runonce fails that on_mco_error is emitted
        methods_called.append(manager.mco_processor.runonce_puppet)
        methods_not_called = []
        num_ok_response += 1

        execute_test_and_check_result(manager, num_ok_response,
                                      methods_not_called, methods_called)

    def test_already_applying_manifest_passes_check_mco_result(self):
        # LITPCDS-12468
        pp_manager = PuppetManager(ModelManager())
        pp_manager.emit = mock.Mock()

        # Already applying manifest, no exception raised or event emitted
        applying_result = {
                'ms1': {
                    'errors': 'ms1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    },
                'node1': {
                    'errors': 'node1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    }
                }
        pp_manager.check_mco_result(applying_result)
        self.assertFalse(pp_manager.emit.called)

        # Already applying, but error on node1 also. Raises exception and
        # emits event 'mco_error'.
        error_result = {
                'ms1': {
                    'errors': 'ms1: Puppet is currently applying a catalog, cannot run now',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'Puppet is currently applying a catalog, cannot run now'
                        }
                    },
                'node1': {
                    'errors': 'cannot reach node1',
                    'data': {
                        'initiated_at': 0,
                        'summary': 'cannot reach node1',
                        }
                    }
                }
        self.assertRaises(McoFailed, pp_manager.check_mco_result, error_result)

    @mock.patch('litp.core.puppet_manager.PuppetManager._check_puppet_status', mock.MagicMock())
    @mock.patch('litp.core.puppet_manager.metrics', mock.MagicMock())
    def test_apply_nodes(self):
        # TORF-147920: Increment config_version prior to writing manifest
        self.manager.mco_processor.stop_puppet_applying.return_value = {
            'node1': {'errors': '', 'data': {'status': 0,
                                             'out': 'Puppet agent not applying',
                                             'err': ""}},
            'ms':  {'errors': '', 'data': {'status': 0,
                                           'out': 'Puppet agent not applying',
                                           'err': ""}}}

        self.manager.mco_processor.clear_puppet_cache.return_value = {
            self.manager.get_ms_hostname(): {'errors': '', 'data':
                {'status': 0,
                 'err': '',
                 'out': 'HTTP/1.1 204 No Content'}}
        }

        task0 = ConfigTask(self.ms, self.ms, "a", "0", "0_1")
        task0.state = constants.TASK_RUNNING
        task1 = ConfigTask(self.node1, self.node1, "b", "1", "1_1")
        task1.state = constants.TASK_RUNNING

        self.manager.node_tasks = {
            self.ms.hostname: [task0],
            self.node1.hostname: [task1],
        }

        with mocked_fsync():
            self.manager.add_phase([task0, task1], 0)
            self.manager.apply_nodes()

        config_version1 = self.manager.phase_config_version
        self.assertEquals(int, type(self.manager.phase_config_version))

        with mocked_fsync():
            self.manager.add_phase([task0, task1], 0)
            self.manager.apply_nodes()

        # Assert that when write_templates is called again,
        # the config_version is incremented
        self.assertEquals(self.manager.phase_config_version, int(config_version1) + 1)
