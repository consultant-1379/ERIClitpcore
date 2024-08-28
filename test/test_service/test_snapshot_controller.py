import cherrypy
import json
import os.path
import unittest

from litp.core import constants
from litp.data.constants import LAST_SUCCESSFUL_PLAN_MODEL_ID
from litp.extensions.core_extension import CoreExtension
from litp.core.execution_manager import ExecutionManager
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.plugin_manager import PluginManager
from litp.core.puppet_manager import PuppetManager
from litp.core.model_container import ModelItemContainer
from litp.core.model_type import ItemType, Collection, Property, PropertyType
from litp.core.plan import Plan
from litp.core.task import ConfigTask
from litp.service.controllers import SnapshotController
from litp.service.utils import human_readable_request_type

from base import Mock, MockPlan, MockTask
from mock import MagicMock, patch
from time import time


remove_snapshot_request_result = (
    '{"item-type-name": "plan", "_embedded": {"item": [{"item-type-name": '
    '"collection-of-phase", "_links": {"self": {"href": "/plans/plan/phases"},'
    ' "collection-of": {"href": "/item-types/phase"}}, "id": "phases"}]},'
    ' "_links": {"self": {"href": "/plans/plan"}, "item-type": {"href":'
    ' "/item-types/plan"}}, "id": "plan", "properties": {"state": "initial"}}')


def _invalid_request_json(snapshot_path, error_message):
    return (
        '{"messages": [{"_links": {"self": {"href": "' + snapshot_path + '"}},'
        ' "message": "' + error_message + '",'
        ' "type": "InvalidRequestError"}], "_links": {"self": {"href": "' + snapshot_path + '"}}}'
    )


class TestSnapshotController(unittest.TestCase):

    def setUp(self):
        self.snapshot_controller = SnapshotController()
        self.snapshot_controller._discard_snapshot = lambda: None
        self.snapshot_controller._save_snapshot = lambda: None
        self.swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.body = Mock()
        cherrypy.request.body.fp = Mock()
        cherrypy.request.body.fp.read = lambda: '{}'
        cherrypy.request.path_info = ''
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        model_manager = ModelManager()
        puppet_manager = PuppetManager(model_manager)
        puppet_manager._write_templates = MagicMock()
        self.plugin_manager = plugin_manager = PluginManager(model_manager)
        model_manager.register_property_type(PropertyType("basic_string"))
        model_manager.register_property_type(PropertyType("basic_boolean", regex=r"^(true|false)$"))
        model_manager.register_property_type(PropertyType('timestamp', regex=r"^([0-9]+\.[0-9]+)|None|.*$"))
        model_manager.register_property_type(self._hostname_property_type_from_core_extension())
        model_manager.register_item_type(ItemType("node",
            hostname=Property("basic_string"),
            is_locked=Property("basic_string", default="false"),
        ))
        model_manager.register_item_type(ItemType("snapshot-base",
                timestamp=Property('timestamp',
                            prop_description='Snapshot creation timestamp.',
                            required=False,
                            updatable_rest=False),
                active=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            default='true'),
                force=Property('basic_boolean',
                            required=False,
                            updatable_rest=False,
                            updatable_plugin=False,
                            default='false')
        ))
        model_manager.register_item_type(ItemType("root",
            nodes=Collection("node"),
            snapshots=Collection("snapshot-base", max_count=1),
        ))

        model_manager.create_root_item("root")

        plugin_manager.get_plugins = lambda arg: []
        plugin_manager.get_extensions = lambda arg: []
        execution_manager = ExecutionManager(
            model_manager, puppet_manager, plugin_manager
            )
        model_container = ModelItemContainer(
            model_manager, plugin_manager, execution_manager)
        cherrypy.config = {
            'execution_manager': execution_manager,
            'model_manager': model_manager,
            'model_container': model_container,
            'dbase_root': '/var/lib/litp/core/model/'
        }
        self.model_manager = model_manager

    def tearDown(self):
        cherrypy.request = self.swp
        execution_manager = cherrypy.config.get('execution_manager')
        execution_manager.plan = None

    def _hostname_property_type_from_core_extension(self):
        core_extension = CoreExtension()
        property_type = [p for p in core_extension.define_property_types()
                if p.property_type_id == 'hostname'][0]
        return property_type

    def _setup_plan(self):
        execution_manager = cherrypy.config.get('execution_manager')
        execution_manager.plan = Plan([], [])

    def _check_default_response(self, response):
        self.assertTrue('messages' in response)
        self.assertTrue('data' in response)
        self.assertTrue(isinstance(response['data'], dict))
        self.assertTrue('id' in response['data'])
        self.assertTrue('state' in response['data'])
        self.assertTrue('properties' in response['data'])
        self.assertTrue(isinstance(response['data']['properties'], dict))
        self.assertTrue('links' in response['data'])
        self.assertTrue(isinstance(response['data']['links'], dict))
        self.assertTrue('uri' in response['data']['links'])
        self.assertTrue('children' in response['data']['links'])
        self.assertTrue('type' in response['data'])
        self.assertTrue(isinstance(response['data']['type'], dict))
        self.assertEquals(len(response['messages']), 0)

    def _check_method_not_allowed(self, response):
        self.assertTrue('messages' in response)
        self.assertEquals(len(response['messages']), 1)
        err_message = response['messages'][0]
        self.assertTrue(isinstance(err_message, dict))
        self.assertTrue('message' in err_message)
        self.assertEquals(
            err_message['message'],
            '%s method on path not allowed'
            % human_readable_request_type(cherrypy.request.method))
        self.assertTrue('type' in err_message)
        self.assertEquals(
            err_message['type'], constants.METHOD_NOT_ALLOWED_ERROR
        )
        self.assertTrue('_links' in err_message)
        self.assertEquals(err_message['_links']['self']['href'], cherrypy.request.path_info)

    def _add_plugin(self, plugin):
        name = plugin.__class__.__name__
        klass = "%s.%s" % (plugin.__class__.__module__,
            plugin.__class__.__name__)
        version = '1.0.0'

        self.plugin_manager.add_plugin(name, klass, version, plugin)

    def create_plugin(self, config_tasks=None, snapshot_tasks=None):
        mock_plugin = MagicMock()
        if config_tasks is not None:
            mock_plugin.create_configuration.return_value = config_tasks
        if snapshot_tasks is not None:
            mock_plugin.create_snapshot_plan.return_value = snapshot_tasks
        self._add_plugin(mock_plugin)
        return mock_plugin

    def test_create_run_plan_executed(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = MagicMock(
            return_value='{"type": "snapshot-base", "id": "snapshot", "name": "trololo"}'
                                                  )
        exman = self.snapshot_controller.execution_manager
        exman.can_create_plan = MagicMock(return_value=True)
        exman.create_snapshot_plan = MagicMock(return_value=[])
        exman.run_plan_background = MagicMock()
        self.snapshot_controller.create_snapshot("snapshot")
        exman.create_snapshot_plan.assert_called_with()
        exman.run_plan_background.assert_called_with()

    def test_snapshot_not_run_if_invalid_json(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = MagicMock(return_value="{'invalid': 'invalid'}")
        err_str = '{"messages": [{"_links": {"self": {"href": "/plans/plan"}}, '\
                  '"message": "Create snapshot failed: Payload is not valid JSON: '\
                  '{\'invalid\': \'invalid\'}", "type": "InvalidRequestError"}],'\
                  ' "_links": {"self": {"href": "/snapshots"}}}'
        self.assertEqual(err_str, self.snapshot_controller.create_snapshot("snapshot"))

    def test_create_snapshot_manually_works(self):
        data = {
            'id': "snapshot",
            'type': 'snapshot-base',
            'properties': {}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        exman = self.snapshot_controller.execution_manager
        exman.can_create_plan = MagicMock(return_value=True)
        exman.create_snapshot_plan = MagicMock(return_value=MockPlan())
        exman.run_plan_background = MagicMock()
        response = json.loads(self.snapshot_controller.create_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 201)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_restore_snapshot_manually_works(self):
        data = {'properties': {'force': 'false'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 200)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_remove_put_snapshot_works(self):
        data = {'properties': {'action': 'remove', 'force':'false'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 200)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_remove_put_snapshot_force_works(self):
        data = {'properties': {'action': 'remove', 'force':'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 200)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_force_restore_snapshot_manually_works(self):
        data = {'properties': {'force': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 200)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_restore_snapshot_without_force_throws_error(self):
        data = {'properties': {'no_force': 'false'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 422)
        self.assertEquals(response['messages'][0]['message'],"Property 'force' must be specified")
        self.assertEqual(response["_links"]["self"]["href"], "/snapshots/snapshot")

    def test_restore_snapshot_with_invalid_force_value_throws_error(self):
        data = {'properties': {'force': 'hello'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 422)
        self.assertEquals(response['messages'][0]['message'],"Invalid value for force specified: 'hello'")
        self.assertEqual(response["_links"]["self"]["href"], "/snapshots/snapshot")

    def test_restore_snapshot_with_force_works(self):
        data = {'properties': {'force': 'False'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 200)
        self.assertEqual(response["_links"]["self"]["href"], "/plans/plan")

    def test_restore_snapshot_without_properties_throws_error(self):
        data = {'properties': {}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        snap_plan = MockPlan()
        snap_plan.is_snapshot_plan = MagicMock(return_value=True)
        snap_plan.is_active = MagicMock(return_value=False)
        snap_plan.get_snapshot_phase = MagicMock(return_value=0)
        snap_plan._phases = [[MockTask()]]

        exman = self.snapshot_controller.execution_manager

        exman.plan = snap_plan
        exman.can_create_plan = MagicMock(return_value=True)
        exman.restore_snapshot_plan = MagicMock(return_value=snap_plan)
        exman.run_plan_background = MagicMock()
        exman.snapshot_status = MagicMock(return_value="exists_previous_plan")
        response = json.loads(self.snapshot_controller.restore_or_remove_snapshot("snapshot"))
        self.assertEquals(cherrypy.response.status, 422)
        self.assertEquals(response['messages'][0]['message'],"Properties must be specified for update")
        self.assertEqual(response["_links"]["self"]["href"], "/snapshots/snapshot")

    def test_no_runplan_with_errs(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        data = {'type': 'snapshot-base','properties': {'force': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        exman = self.snapshot_controller.execution_manager
        exman.can_create_plan = MagicMock(return_value=True)
        exman.create_snapshot_plan = MagicMock(
            return_value=[{
                'error': constants.METHOD_NOT_ALLOWED_ERROR,
                'message': 'Create snapshot failed: '
            }])
        self.snapshot_controller.execution_manager.run_plan_background = MagicMock()
        self.snapshot_controller.create_snapshot("snapshot")
        exman.create_snapshot_plan.assert_called_with()
        self.snapshot_controller.execution_manager.run_plan_background.assert_has_calls([])

    def test_runplan_returns_errors(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        data = {'type': 'snapshot-base','properties': {'force': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        exman = self.snapshot_controller.execution_manager
        exman.can_create_plan = MagicMock(return_value=True)
        exman.create_snapshot_plan = MagicMock(return_value=[])
        self.snapshot_controller.execution_manager.run_plan_background = MagicMock(
            return_value={'error': constants.METHOD_NOT_ALLOWED_ERROR,
                          'message': 'nooooo'}
        )

        result = self.snapshot_controller.create_snapshot("snapshot")

        self.assertEquals(
            '{"messages": [{"_links": {"self": {"href": "/plans/plan"}},'
            ' "message": "Create snapshot failed: MethodNotAllowedError",'
            ' "type": "InvalidRequestError"}],'
            ' "_links": {"self": {"href": "/snapshots"}}}', result)

    def test_snapshot_state_consistent_errors(self):
        cherrypy.request.method = 'DELETE'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.execution_manager
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot1')
        self.snapshot_controller.model_manager.set_snapshot_applied('snapshot1')
        self.snapshot_controller.execution_manager.can_create_plan = MagicMock(return_value=True)
        self.snapshot_controller.execution_manager.delete_snapshot_plan = MagicMock(return_value=MockPlan())
        self.snapshot_controller.execution_manager.run_plan_background = MagicMock(return_value={'error': constants.METHOD_NOT_ALLOWED_ERROR,
                                                                             'message': 'nooooo'})
        # if plan fails the state is the same as before starting
        self.assertEquals("Applied", self.snapshot_controller.model_manager.get_item('/snapshots/snapshot1').get_state())
        self.snapshot_controller.execution_manager._update_ss_timestamp_successful()
        self.snapshot_controller.delete_snapshot('snapshot1')


        self.assertEquals("Applied", self.snapshot_controller.model_manager.get_item('/snapshots/snapshot1').get_state())
        # and make sure the snapshot item has been set to for removal in the middle
        self.snapshot_controller.model_manager.set_snapshot_for_removal = MagicMock()
        self.snapshot_controller.execution_manager._update_ss_timestamp_successful()
        self.snapshot_controller.delete_snapshot('snapshot1')
        self.snapshot_controller.model_manager.set_snapshot_for_removal.assert_called_with('snapshot1')


    def test_create_snapshot_not_run_if_item_exists(self):
        # simulate we run create_plan and it creates the snapshot item
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        # now we run create_snapshot, should not return an error
        self.assertEqual(
                        '{"messages": [{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "no tasks were generated. No snapshot tasks added because failed Deployment Snapshot exists", '
                        '"type": "DoNothingPlanError"}], "_links": {"self": {"href": "/snapshots/snapshot"}}}',
                         self.snapshot_controller._validate_and_create_snapshot_item('snapshot', 'snapshot-base'))
        self.assertFalse(self.snapshot_controller.model_manager.create_snapshot_item.called)
        with patch.object(self.snapshot_controller.model_manager, "backup_exists", MagicMock(return_value=True)) as m:
            result = self.snapshot_controller._validate_and_create_snapshot_item('test_named', 'snapshot-base')
        self.assertEqual('{"messages": [], "_links": {"self": {"href": "/snapshots/test_named"}}}',
                         result)
        self.assertTrue(self.snapshot_controller.model_manager.create_snapshot_item.called)

    def test_validate_delete_snapshot(self):
        response = [{'message':
        "no tasks were generated. No remove snapshot tasks added because Deployment Snapshot does not exist.",
        'error': 'DoNothingPlanError'}]
        self.assertEqual(self.snapshot_controller.execution_manager._validate_delete_snapshot('snapshot', True), response)

    def test_validate_create_snapshot(self):
        # simulate we run create_plan and it creates the snapshot item
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        # now we run create_snapshot, should not return an error
        self.assertEqual(
                        '{"messages": [{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "no tasks were generated. No snapshot tasks added because failed Deployment Snapshot exists", '
                        '"type": "DoNothingPlanError"}], "_links": {"self": {"href": "/snapshots/snapshot"}}}',
                         self.snapshot_controller._validate_and_create_snapshot_item('snapshot', 'snapshot-base'))
        self.assertEqual(
                        '{"messages": [{"_links": {"self": {"href": "/snapshots/snapshot"}}, "message": "Item type not registered: snapshot-ace", '
                        '"type": "InvalidTypeError"}, '
                        '{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "\'snapshot-ace\' is not an allowed type for collection of item type \'snapshot-base\'", '
                        '"type": "InvalidTypeError"}, '
                        '{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "no tasks were generated. No snapshot tasks added because failed Deployment Snapshot exists", '
                        '"type": "DoNothingPlanError"}], '
                        '"_links": {"self": {"href": "/snapshots/snapshot"}}}',
                        self.snapshot_controller._validate_and_create_snapshot_item('snapshot', 'snapshot-ace'))
        self.assertEqual(
                        '{"messages": [{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "\'node\' is not an allowed type for collection of item type \'snapshot-base\'", '
                        '"type": "InvalidTypeError"}, '
                        '{"_links": {"self": {"href": "/snapshots/snapshot"}}, '
                        '"message": "no tasks were generated. No snapshot tasks added because failed Deployment Snapshot exists", '
                        '"type": "DoNothingPlanError"}], '
                        '"_links": {"self": {"href": "/snapshots/snapshot"}}}',
                        self.snapshot_controller._validate_and_create_snapshot_item('snapshot', 'node'))

    def test_create_plan_and_get_errors(self):
        def create_plan_method_list():
            return [{"error": "some_constant", "message": "some message"}]
        def create_plan_method_plan():
            return Plan([], [])
        def create_plan_method_wat():
            return 'i shouldnt even be here'

        # returns the error
        self.assertEquals(([{'message': 'some message', 'error': 'some_constant'}],
                           None,
                           {}),
            self.snapshot_controller._create_plan_and_return_errors(create_plan_method_list, 'create')
                          )
        # returns the processing of the plan (even if it's empty like this)
        self.assertEquals(([],
                           201,
                           {u'_links': {u'self': {u'href': u'/plans/plan'}}, u'messages': [{u'type': u'InvalidLocationError', u'message': u'Plan does not exist', u'_links': {u'self': {u'href': u'/plans/'}}}]}),
            self.snapshot_controller._create_plan_and_return_errors(create_plan_method_plan, 'create')
                          )
        # kind of edge case
        self.assertEquals(([{'message': 'No plan created', 'uri': '/snapshots/', 'error': 'InvalidRequestError'}],
                           None,
                           {}),
                           self.snapshot_controller._create_plan_and_return_errors(create_plan_method_wat, 'create')
                          )

    def test_create_snapshot(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        data = {'type': 'snapshot-base'}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        # first, error in create_plan
        self.snapshot_controller._create_plan_and_return_errors = \
                                            MagicMock(return_value=(
                                                [{'message': 'some message',
                                                  'error': constants.METHOD_NOT_ALLOWED_ERROR
                                                 }],
                                                None,
                                                {}
                                            ))
        self.snapshot_controller._run_plan_and_return_errors = \
                                            MagicMock(return_value=([], 201))

        result = self.snapshot_controller.create_snapshot("snapshot")
        self.assertEquals(
            '{"messages": [{"message": "Create snapshot failed: some message",'
            ' "type": "MethodNotAllowedError"}], '
            '"_links": {"self": {"href": "/snapshots/snapshot"}}}',
            result)
        self.snapshot_controller.model_manager.remove_snapshot_item('snapshot')
        # now, no errors
        self.snapshot_controller._create_plan_and_return_errors = \
                                            MagicMock(return_value=([], 201, {}))
        result = self.snapshot_controller.create_snapshot("snapshot")
        self.assertEquals('{}', result)

        # and now error in run_plan
        self.snapshot_controller.model_manager.remove_snapshot_item('snapshot')
        self.snapshot_controller._create_plan_and_return_errors = \
                                            MagicMock(return_value=([], 201, {}))
        self.snapshot_controller._run_plan_and_return_errors = MagicMock(
            return_value=(
                [{'message': 'some message',
                  'error': constants.METHOD_NOT_ALLOWED_ERROR
                  }],
                None))

        result = self.snapshot_controller.create_snapshot("snapshot")

        self.assertEquals(
            '{"messages": [{"message": "Create snapshot failed: some message",'
            ' "type": "MethodNotAllowedError"}], "_links": {"self": {"href": "/snapshots"}}}',
            result)

    def test_cant_create_snapshot_without_last_successful(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = MagicMock(
            return_value='{"type": "snapshot-base", "id": "snapshot", "name": "trololo"}'
        )

        with patch.object(self.snapshot_controller.model_manager, "backup_exists", MagicMock(return_value=False)) as m:
            result = self.snapshot_controller.create_snapshot("trololo")
            m.assert_any_call(LAST_SUCCESSFUL_PLAN_MODEL_ID)
        self.assertEqual(cherrypy.response.status, 422)
        expected = {u'_links': {u'self': {u'href': u'/snapshots/trololo'}},
                    u'messages': [
                        {u'message': u'Cannot create named backup snapshot: It would not be possible to restore the deployment to a known good state because the last deployment plan was not successfully executed.',
                        u'type': u'ValidationError'}]}
        response = json.loads(result)
        self.assertEqual(expected, response)

    def test_no_type_in_create_snapshot(self):
        # check that if json doesn't have mandatory fields
        # litp doesn't throw an error (LITPCDS-10159)
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = MagicMock(
            return_value="{}"
        )

        result = self.snapshot_controller.create_snapshot("trololo")

        self.assertEqual(None,
                         self.snapshot_controller.model_manager.get_item('/snapshots/snapshot'))
        self.assertEqual(
            '{"messages": [{"_links": {"self": {"href": "/snapshots/trololo"}},'
            ' "message": "item-type not specified in request body",'
            ' "type": "InvalidRequestError"}], "_links": {"self": {"href": "/snapshots/trololo"}}}',
            result
        )

    def test_no_snapshot_after_failed_create_snapshot(self):
        # check that if create_snapshot fails at create_plan stage
        # there is no snapshot item afterwards
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = MagicMock(
            return_value='{"type": "snapshot-base"}'
                                                  )
        with patch.object(self.snapshot_controller.model_manager, "backup_exists", MagicMock(return_value=True)) as m:
            result = self.snapshot_controller.create_snapshot("trololo")
            m.assert_any_call(LAST_SUCCESSFUL_PLAN_MODEL_ID)

        self.assertEqual(None,
                         self.snapshot_controller.model_manager.get_item('/snapshots/snapshot'))
        self.assertEqual(
            '{"messages": [{"message": "no tasks were generated. No snapshot tasks added because failed Deployment Snapshot exists", '
            '"type": "DoNothingPlanError"}], '
            '"_links": {"self": {"href": "/snapshots/trololo"}}}',
            result
        )
        # now make sure the item was created in the middle and run_plan was not called
        self.snapshot_controller.model_manager.create_snapshot_item = MagicMock()
        self.snapshot_controller._run_plan_and_return_errors = MagicMock()
        with patch.object(self.snapshot_controller.model_manager, "backup_exists", MagicMock(return_value=True)) as m:
            result = self.snapshot_controller.create_snapshot("trololo")
            m.assert_any_call(LAST_SUCCESSFUL_PLAN_MODEL_ID)
        self.snapshot_controller.model_manager.create_snapshot_item.assert_called_once_with('trololo')
        self.snapshot_controller._run_plan_and_return_errors.assert_has_calls([])

    def test_delete_snapshot_fails(self):
        cherrypy.request.method = 'DELETE'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        self.snapshot_controller.execution_manager.delete_snapshot = MagicMock(
            return_value=[{'error': constants.INTERNAL_SERVER_ERROR,
                           'message': 'oops'}]
        )
        result = self.snapshot_controller.delete_snapshot('snapshot')
        expected = (
            '{"messages": [{"message": "Remove snapshot failed: oops",'
            ' "type": "InternalServerError"}],'
            ' "_links": {"self": {"href": "/snapshots/snapshot"}}}'
        )
        self.assertEqual(expected, result)

    def test_litp_snapshot_exists(self):
        self.assertEqual([], self.snapshot_controller._litp_snapshot_exists())
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.assertEqual(1, len(self.snapshot_controller._litp_snapshot_exists()))
        self.snapshot_controller.model_manager.create_snapshot_item('backup')
        self.assertEqual(1, len(self.snapshot_controller._litp_snapshot_exists()))

    def test_named_snapshots_exist(self):
        self.assertEqual([], self.snapshot_controller._named_snapshots_exist())
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.assertEqual([], self.snapshot_controller._named_snapshots_exist())
        self.snapshot_controller.model_manager.create_snapshot_item('backup')
        self.assertEqual(1, len(self.snapshot_controller._named_snapshots_exist()))
        self.snapshot_controller.model_manager.create_snapshot_item('backup2')
        self.assertEqual(2, len(self.snapshot_controller._named_snapshots_exist()))

    def test_no_stop_plan_after_restore(self):
        # running plan with snapshot tasks
        self.snapshot_controller.execution_manager.plan = MagicMock()
        self.snapshot_controller.execution_manager.plan.is_snapshot_plan = True
        self.snapshot_controller.execution_manager.plan.is_active.return_value = True
        self.snapshot_controller.execution_manager.plan_has_tasks = MagicMock(return_value=True)
        # snapshot item created and sucessful (applied)
        self.snapshot_controller.model_manager.create_snapshot_item('snapshot')
        self.snapshot_controller.execution_manager._update_ss_timestamp_successful()
        ss_obj = self.snapshot_controller.model_manager.get_item('/snapshots/snapshot')
        self.snapshot_controller.model_manager.set_snapshot_applied(ss_obj.item_id)
        self.assertEqual(None, self.snapshot_controller.stop_plan_validator())
        # now assume we created a snapshot and we are restoring it
        self.snapshot_controller.execution_manager.plan.snapshot_type = 'restore'
        self.assertEqual({'error': 'Cannot stop plan when restore is ongoing'},
                         self.snapshot_controller.stop_plan_validator())

    def test_restore_errors_come_from_named_or_deployment_snapshots(self):
        self.snapshot_controller.model_manager.create_item('snapshot-base' , "/snapshots/" + constants.UPGRADE_SNAPSHOT_NAME, item_id="snapshot1", active="false")
        self.snapshot_controller.execution_manager.plan = MagicMock()
        self.snapshot_controller.execution_manager.plan.is_snapshot_plan = True
        self.snapshot_controller.execution_manager.plan.is_active.return_value = True
        self.snapshot_controller.execution_manager.plan_has_tasks = MagicMock(return_value=True)
        self.snapshot_controller.model_manager.create_snapshot_item("snapshot1")
        self.snapshot_controller.model_manager.snapshot_status = MagicMock(
            return_value='Failed')
        self.snapshot_controller.model_manager.set_snapshot_applied("snapshot1")
        message = {'messages': [{
            'message': ('Restore snapshot failed: Cannot restore a Deployment'
                        ' Snapshot if a Named Backup Snapshot exists.'),
            'type': 'ValidationError'}], '_links': {'self': {'href': 'snapshot'}}}
        self.assertEqual(self.snapshot_controller._validate_restore_snapshot(constants.UPGRADE_SNAPSHOT_NAME),
        message)

    def _setup_exclude_node_test(self, data=None):
        def mock_run_plan_and_return_errors(*args, **kwargs):
            self.snapshot_controller.model_manager.set_all_applied()
            return [], 201
        def mock_node_model_item(hostname, is_ms):
            mock_node_mi = MagicMock(hostname=hostname)
            mock_node_mi.is_ms = MagicMock(return_value=is_ms)
            return mock_node_mi

        if data is None:
            data = {
                'type': 'snapshot-base',
            }
        self.snapshot_controller._run_plan_and_return_errors = \
            mock_run_plan_and_return_errors
        exman = self.snapshot_controller.execution_manager
        exman.can_create_plan = MagicMock(return_value=True)
        exman.create_snapshot_plan = MagicMock(return_value=[])
        exman.run_plan_background = MagicMock()
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        model_manager = self.snapshot_controller.model_manager
        node_set = set([
            mock_node_model_item(hostname='ms1', is_ms=True),
            mock_node_model_item(hostname='node1', is_ms=False),
            mock_node_model_item(hostname='node2', is_ms=False),
            ])
        model_manager.get_all_nodes = MagicMock(return_value=node_set)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_no_exclude_nodes(self, mock_backup_exists):
        self._setup_exclude_node_test()
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)

        result = self.snapshot_controller.create_snapshot(snapshot_name)

        self.assertEqual('Applied', model_manager.get_item(snapshot_path).state)
        self.assertEqual('{}', result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'node1,node2'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)

        result = self.snapshot_controller.create_snapshot(snapshot_name)

        self.assertEqual('Applied', model_manager.get_item(snapshot_path).state)
        self.assertEqual('{}', result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_are_set(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'node1,node2'
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        model_manager = self.snapshot_controller.model_manager
        exman = self.snapshot_controller.execution_manager

        def check_exclude_nodes_pupulated(*args, **kwargs):
            hostnames = [qi._model_item.hostname for qi in exman.exclude_nodes]
            self.assertEquals(set(['node1', 'node2']), set(hostnames))
            return [], 201, '{}'

        self.snapshot_controller._create_plan_and_return_errors = \
            check_exclude_nodes_pupulated

        result = self.snapshot_controller.create_snapshot(
            snapshot_name,exclude_nodes=exclude_nodes)

        self.assertEquals(set(), exman.exclude_nodes)
        self.assertEqual('Applied', model_manager.get_item(snapshot_path).state)
        self.assertEqual('{}', result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_always_cleaned(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'node1,node2'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        exman = self.snapshot_controller.execution_manager

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual('Applied', model_manager.get_item(snapshot_path).state)
        self.assertEqual('{}', result)
        self.assertEquals(set(), exman.exclude_nodes)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_nonexistent_nodes(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'fake-node'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        error_message = 'Nonexistent hostnames in exclude_nodes: fake-node'
        expected = _invalid_request_json(snapshot_path, error_message)

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual(None, model_manager.get_item(snapshot_path))
        self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_with_named_snapshot_only(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'node1'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        error_message = 'Use exclude_nodes with named snapshot only'
        expected = _invalid_request_json(snapshot_path, error_message)

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual(None, model_manager.get_item(snapshot_path))
        self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_empty_string(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = ''
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        error_message = 'exclude_nodes cannot be an empty string'
        expected = _invalid_request_json(snapshot_path, error_message)

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual(None, model_manager.get_item(snapshot_path))
        self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_invalid_format(self, mock_backup_exists):
        invalid_exclude_nodes_format_list = [
            '-',
            'a',
            '1',
            ',node1',
            'node1,',
            '_node1',
            'node1_',
            'node1,,node2',
            ',node1,node2',
            'node1,node2,',
            'node1,node2,  ',
            ]

        for exclude_nodes in invalid_exclude_nodes_format_list:
            self._setup_exclude_node_test()
            model_manager = self.snapshot_controller.model_manager
            snapshot_name = 'named_snapshot'
            snapshot_path = '/snapshots/{0}'.format(snapshot_name)
            error_message = 'exclude_nodes malformed'
            expected = _invalid_request_json(snapshot_path, error_message)

            result = self.snapshot_controller.create_snapshot(
                snapshot_name, exclude_nodes=exclude_nodes)

            self.assertEqual(None, model_manager.get_item(snapshot_path))
            self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_ms_in_the_list(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'ms1,node1'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        error_message = 'exclude_nodes cannot contain MS'
        expected = _invalid_request_json(snapshot_path, error_message)

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual(None, model_manager.get_item(snapshot_path))
        self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_create_snapshot_exclude_nodes_duplicate_entries(self, mock_backup_exists):
        self._setup_exclude_node_test()
        exclude_nodes = 'node1,node2,node1'
        model_manager = self.snapshot_controller.model_manager
        snapshot_name = 'named_snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        error_message = 'exclude_nodes contains duplicate entries: node1'
        expected = _invalid_request_json(snapshot_path, error_message)

        result = self.snapshot_controller.create_snapshot(
            snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual(None, model_manager.get_item(snapshot_path))
        self.assertEqual(expected, result)

    def _setup_remove_snapshot_request(self):
        data = {'properties': {
                    'force': False,
                    'action': 'remove'
                    }
                }
        cherrypy.request.method = 'PUT'
        cherrypy.request.body.fp.read = lambda: json.dumps(data)

    def _setup_remove_snapshot_with_exclude_nodes(self, name='snapshot'):
        self._setup_exclude_node_test()

        # 1. Create snapshot in the model
        model_manager = self.snapshot_controller.model_manager
        snapshot_path = '/snapshots/{0}'.format(name)
        self.snapshot_controller.create_snapshot(name)
        self.assertEqual('Applied', model_manager.get_item(snapshot_path).state)

        # 2. Configure proper mocking for remove_snapshot requests
        self._setup_remove_snapshot_request()

    def _run_remove_snapshot_test(
            self, exclude_nodes, expected_error_message, snapshot_name=None):
        if snapshot_name is None:
            snapshot_name = 'named_snapshot'
        self._setup_remove_snapshot_with_exclude_nodes(name=snapshot_name)
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        expected = _invalid_request_json(snapshot_path, expected_error_message)

        result = self.snapshot_controller.restore_or_remove_snapshot(
                snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual('Applied', self.model_manager.get_item(snapshot_path).state)
        self.assertEqual(expected, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_no_exclude_nodes(self, mock_backup_exists):
        snapshot_name = 'snapshot'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        self._setup_remove_snapshot_with_exclude_nodes(name=snapshot_name)

        result = self.snapshot_controller.restore_or_remove_snapshot(snapshot_name)
        self.assertEqual('ForRemoval', self.model_manager.get_item(snapshot_path).state)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes(self, mock_backup_exists):
        snapshot_name = 'named_snapshot'
        exclude_nodes = 'node1,node2'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        self._setup_remove_snapshot_with_exclude_nodes(name=snapshot_name)

        result = self.snapshot_controller.restore_or_remove_snapshot(
                snapshot_name, exclude_nodes=exclude_nodes)
        self.assertEqual('ForRemoval', self.model_manager.get_item(snapshot_path).state)
        self.assertEqual(remove_snapshot_request_result, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_are_set(self, mock_backup_exists):
        snapshot_name = 'named_snapshot'
        exclude_nodes = 'node1,node2'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        self._setup_remove_snapshot_with_exclude_nodes(name=snapshot_name)
        exman = self.snapshot_controller.execution_manager

        exman_old_delete_snapshot = exman.delete_snapshot

        def check_exclude_nodes_pupulated(*args, **kwargs):
            exman_old_delete_snapshot(*args, **kwargs)
            hostnames = [qi._model_item.hostname for qi in exman.exclude_nodes]
            self.assertEquals(set(['node1', 'node2']), set(hostnames))
            return [], 201, '{}'

        exman.delete_snapshot = check_exclude_nodes_pupulated

        result = self.snapshot_controller.restore_or_remove_snapshot(
                snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEquals(set(), exman.exclude_nodes)
        self.assertEqual('ForRemoval', self.model_manager.get_item(snapshot_path).state)
        self.assertEqual(remove_snapshot_request_result, result)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_always_cleaned(self, mock_backup_exists):
        snapshot_name = 'named_snapshot'
        exclude_nodes = 'node1,node2'
        snapshot_path = '/snapshots/{0}'.format(snapshot_name)
        self._setup_remove_snapshot_with_exclude_nodes(name=snapshot_name)
        exman = self.snapshot_controller.execution_manager

        result = self.snapshot_controller.restore_or_remove_snapshot(
                snapshot_name, exclude_nodes=exclude_nodes)

        self.assertEqual('ForRemoval', self.model_manager.get_item(snapshot_path).state)
        self.assertEqual(remove_snapshot_request_result, result)
        self.assertEquals(set(), exman.exclude_nodes)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_nonexistent_nodes(self, mock_backup_exists):
        expected_error_message = 'Nonexistent hostnames in exclude_nodes: fake-node'
        exclude_nodes = 'fake-node'
        self._run_remove_snapshot_test(exclude_nodes, expected_error_message)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_with_named_snapshot_only(self, mock_backup_exists):
        expected_error_message = 'Use exclude_nodes with named snapshot only'
        exclude_nodes = 'node1'
        snapshot_name = 'snapshot'
        self._run_remove_snapshot_test(exclude_nodes, expected_error_message, snapshot_name)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_empty_string(self, mock_backup_exists):
        expected_error_message = 'exclude_nodes cannot be an empty string'
        exclude_nodes = ''
        self._run_remove_snapshot_test(exclude_nodes, expected_error_message)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_ms_in_the_list(self, mock_backup_exists):
        expected_error_message = 'exclude_nodes cannot contain MS'
        exclude_nodes = 'ms1,node1'
        self._run_remove_snapshot_test(exclude_nodes, expected_error_message)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_duplicate_entries(self, mock_backup_exists):
        expected_error_message = 'exclude_nodes contains duplicate entries: node1'
        exclude_nodes = 'node1,node2,node1'
        self._run_remove_snapshot_test(exclude_nodes, expected_error_message)

    @patch.object(ModelManager, "backup_exists", return_value=True)
    def test_remove_snapshot_exclude_nodes_invalid_format(self, mock_backup_exists):
        expected_error_message = 'exclude_nodes malformed'
        invalid_exclude_nodes_format_list = [
            '-',
            'a',
            '1',
            ',node1',
            'node1,',
            '_node1',
            'node1_',
            'node1,,node2',
            ',node1,node2',
            'node1,node2,',
            'node1,node2,  ',
            ]

        for exclude_nodes in invalid_exclude_nodes_format_list:
            self._run_remove_snapshot_test(exclude_nodes, expected_error_message)
