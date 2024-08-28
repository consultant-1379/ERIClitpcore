import cherrypy
import json
import unittest

from litp.core import constants
from litp.extensions.core_extension import CoreExtension
from litp.core.execution_manager import ExecutionManager, ExecutionManagerNextGen
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.plugin_manager import PluginManager
from litp.core.puppet_manager import PuppetManager
from litp.core.model_container import ModelItemContainer
from litp.core.model_type import ItemType, Collection, Property, PropertyType, View, Child
from litp.core.plan import Plan
from litp.core.task import ConfigTask
from litp.service.controllers import PlanController
from litp.service.utils import human_readable_request_type
from litp.service.utils import set_db_availability

from base import Mock, MockPlan, MockTask
from mock import MagicMock, patch, PropertyMock
from time import time


class TestPlanController(unittest.TestCase):

    def setUp(self):
        self.plan_controller = PlanController()
        self.plan_controller._discard_snapshot = lambda: None
        self.plan_controller._save_snapshot = lambda: None
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
                            default='true')
        ))
        model_manager.register_item_type(ItemType("root",
            ms=Child("node"),
            deployments=Collection("deployment"),
            snapshots=Collection("snapshot-base", max_count=1),
        ))
        model_manager.register_item_type(ItemType("deployment",
            clusters=Collection("cluster-base"),
            ordered_clusters=View("basic_list", callable_method=CoreExtension.get_ordered_clusters),
        ))
        model_manager.register_item_type(ItemType("cluster-base",
            nodes=Collection("node"),
        ))

        model_manager.create_root_item("root")
        model_manager.create_item("node", "/ms")

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
            'db_available': True,
        }

    def tearDown(self):
        cherrypy.request = self.swp
        execution_manager = cherrypy.config.get('execution_manager')
        execution_manager.plan = None

    def _setup_plan(self):
        execution_manager = cherrypy.config.get('execution_manager')
        execution_manager.plan = Plan([], [])
        execution_manager.plan.set_ready()

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

    def test_method_not_allowed(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(self.plan_controller.list_plans())
        self._check_method_not_allowed(response)

    def test_list_plans_no_plan(self):
        response = json.loads(self.plan_controller.list_plans())
        self.assertEqual(response['_links']['self']['href'], '/plans')
        self.assertEqual(response['_links']['collection-of']['href'],
                         '/item-types/plan')
        self.assertEqual(response['id'], 'plans')

    def test_list_plans_when_plan_exists(self):
        cherrypy.config['execution_manager'].plan = MockPlan()
        response = json.loads(self.plan_controller.list_plans())

        self.assertEqual(response['_links']['self']['href'], '/plans')
        self.assertEqual(response['_links']['collection-of']['href'],
                         '/item-types/plan')
        self.assertEqual(
            response['_embedded']['item'][0]['item-type-name'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['item-type']['href'],
            '/item-types/plan')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'plan')
        self.assertEqual(response['id'], 'plans')

    def test_get_plan_wrong_plan_id(self):
        plan_id = 'some plan'

        # check the response when there is no plan
        response = json.loads(self.plan_controller.get_plan(plan_id))
        self.assertEquals(len(response['messages']), 1)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Item not found' in message_list
        )

        # let's create a plan and check again the response with a wrong
        # plan id
        cherrypy.config['execution_manager'].plan = MockPlan()
        response = json.loads(self.plan_controller.get_plan(plan_id))
        self.assertEquals(len(response['messages']), 1)
        self.assertEquals(
            response['messages'][0]['message'],
            'Item not found'
        )

    def test_get_plan_valid_plan_id(self):
        plan_id = 'plan'
        # check the response when there is no plan
        response = json.loads(self.plan_controller.get_plan(plan_id))
        self.assertEquals(len(response['messages']), 1)
        self.assertEquals(
            response['messages'][0]['message'],
            'Plan does not exist'
        )

        # let's check the response when there is a plan
        cherrypy.config['execution_manager'].plan = MockPlan()
        response = json.loads(self.plan_controller.get_plan(plan_id))

        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'phases')
        self.assertEqual(response['id'], 'plan')

    def test_create_plan_with_get_request(self):
        cherrypy.request.method = 'GET'
        response = json.loads(self.plan_controller.create_plan())
        self._check_method_not_allowed(response)

    def test_create_plan_no_params(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 2)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Create plan failed: '
                        'Invalid value for argument ID :None' in message_list)
        self.assertTrue('Create plan failed: '
            'Must specify type as \'plan\' or \'reboot_plan\'' in message_list)
        self.assertEquals(response['messages'][0]['_links']['self']['href'],
                          '/plans')
        self.assertEquals(
            response['messages'][0]['type'], constants.INVALID_REQUEST_ERROR
        )

    def test_create_plan_no_lock_tasks_true(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "no-lock-tasks":"true"}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: no tasks were generated")
        self.assertEquals(err['type'], constants.DO_NOTHING_PLAN_ERROR)

    def test_create_plan_no_lock_tasks_false(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "no-lock-tasks": "false"}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: no tasks were generated")
        self.assertEquals(err['type'], constants.DO_NOTHING_PLAN_ERROR)

    def test_create_plan_no_lock_tasks_invalid(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "no-lock-tasks": "invalid"}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: Invalid value for no-lock-tasks specified: 'invalid'")
        self.assertEquals(err['type'], constants.INVALID_REQUEST_ERROR)

    def test_create_plan_no_lock_tasks_list(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "no-lock-tasks": "true", "no-lock-tasks-list": ["svc_cluster"]}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: no tasks were generated")
        self.assertEquals(err['type'], constants.DO_NOTHING_PLAN_ERROR)

    def test_create_plan_no_lock_tasks_list_invalid(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "no-lock-tasks": "false","no-lock-tasks-list": ["svc_cluster"]}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: Invalid value for no-lock-tasks when no-lock-tasks-list specified: 'false'")
        self.assertEquals(err['type'], constants.INVALID_REQUEST_ERROR)

    def test_create_plan_wrong_id(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: '{"id": "some_plan"}'
        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 2)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Create plan failed: Invalid value for argument ID :some_plan' in message_list
        )
        self.assertTrue('Create plan failed: '
            'Must specify type as \'plan\' or \'reboot_plan\'' in message_list)
        self.assertEquals(response['messages'][0]['_links']['self']['href'],
                          '/plans')
        self.assertEquals(
            response['messages'][0]['type'], constants.INVALID_REQUEST_ERROR
        )

    def test_create_plan_no_type(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: '{"id": "plan"}'
        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        self.assertEquals(
            response['messages'][0]['message'],
            'Create plan failed: Must specify type as \'plan\' or \'reboot_plan\''
        )
        self.assertEquals(response['messages'][0]['_links']['self']['href'], '/plans')
        self.assertEquals(
            response['messages'][0]['type'], constants.INVALID_REQUEST_ERROR
        )

    def test_create_plan_wrong_type(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: '{"id": "plan", "type": "pl"}'
        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        self.assertEquals(
            response['messages'][0]['message'],
            'Create plan failed: Must specify type as \'plan\' or \'reboot_plan\''
        )
        self.assertEquals(response['messages'][0]['_links']['self']['href'], '/plans')
        self.assertEquals(
            response['messages'][0]['type'], constants.INVALID_REQUEST_ERROR
        )

    def test_create_plan_with_validation_errors(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        execution_manager = cherrypy.config.get('execution_manager')
        model_manager = cherrypy.config.get('model_manager')
        validation_errors = [{
            'message': 'my error message',
            'item_path': 'some_path',
            'error': constants.INVALID_LOCATION_ERROR
        }]

        execution_manager.create_plan = lambda *args, **kwargs: validation_errors

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create plan failed: my error message')
        self.assertEquals(err['type'], constants.INVALID_LOCATION_ERROR)

    def test_create_plan_with_plan_running(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        execution_manager = cherrypy.config.get('execution_manager')
        model_manager = cherrypy.config.get('model_manager')

        mock_plan = MockPlan()
        execution_manager.plan = mock_plan

        swp_ccp = execution_manager.can_create_plan
        execution_manager.can_create_plan = lambda: False
        execution_manager.is_plan_stopping = lambda: True

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create plan failed: Previous plan is still stopping')
        self.assertEquals(err['type'], constants.INVALID_REQUEST_ERROR)

        execution_manager.can_create_plan = swp_ccp

    def test_create_plan_invalid_request(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create plan failed: no tasks were generated')
        self.assertEquals(err['type'], constants.DO_NOTHING_PLAN_ERROR)

    def test_create_plan_extra_properties(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "properties":{"invalid":"property"}}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: Invalid property 'invalid'")
        self.assertEquals(err['type'], constants.VALIDATION_ERROR)

    def test_create_plan_specify_state(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan", "properties":{"state":"running"}}'
        cherrypy.request.body.fp.read = lambda: params

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], "Create plan failed: Invalid property 'state' for plan create")
        self.assertEquals(err['type'], constants.VALIDATION_ERROR)

    def _add_plugin(self, plugin):
        name = plugin.__class__.__name__
        klass = "%s.%s" % (plugin.__class__.__module__,
            plugin.__class__.__name__)
        version = '1.0.0'

        self.plugin_manager.add_plugin(name, klass, version, plugin)

    def create_plugin(self, config_tasks=None):
        mock_plugin_class = MagicMock()
        mock_plugin_class.__name__ = "MagicMock"
        mock_plugin_class.__module__ = "mock"
        mock_plugin = mock_plugin_class.return_value
        mock_plugin.__class__ = mock_plugin_class
        if config_tasks is not None:
            mock_plugin.create_configuration.return_value = config_tasks
        self._add_plugin(mock_plugin)
        return mock_plugin

    def test_create_plan_when_plan_exists(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        # 0. setup env
        execution_manager = cherrypy.config.get('execution_manager')
        plugin_manager = execution_manager.plugin_manager
        plugin_manager.add_default_model()
        model_manager = execution_manager.model_manager

        # 1. setup model manager with a basic model
        model_manager.create_item( "deployment", "/deployments/dep")
        model_manager.create_item("cluster-base", "/deployments/dep/clusters/clus")
        node = model_manager.create_item(
            'node', "/deployments/dep/clusters/clus/nodes/node", hostname="node"
        )
        node_qa = QueryItem(model_manager, model_manager.query('node')[0])

        # 2. setup exec manager with an existing plan
        self._setup_plan()
        self.assertTrue(execution_manager.plan.is_initial())

        # 3. add a plugin that returns 1 config task for new plan
        tasks = [
            ConfigTask(node_qa,
            QueryItem(model_manager, node),
            "Node Task", "node1", "task1"
            )]
        self.create_plugin(config_tasks = tasks)

        # 4. try and create new plan (should work)
        response = json.loads(self.plan_controller.create_plan())
        self.assertEqual(cherrypy.response.status, 201)

        # 5. check plan created
        self.assertEqual(response['properties']['state'], Plan.INITIAL)
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(response['id'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'phases')
        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')

    def test_create_plan_when_running_plan_exists(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        execution_manager.plan.run()

        response = json.loads(self.plan_controller.create_plan())
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create plan failed: Plan already running')
        self.assertEquals(err['type'], constants.INVALID_REQUEST_ERROR)

    def test_create_plan(self):
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        params = '{"id": "plan", "type": "plan"}'
        cherrypy.request.body.fp.read = lambda: params

        execution_manager = cherrypy.config.get('execution_manager')

        mock_plan = MockPlan()
        execution_manager.create_plan = lambda *args, **kwargs: mock_plan
        execution_manager.plan = mock_plan

        response = json.loads(self.plan_controller.create_plan())
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(response['id'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'phases')
        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')

    def test_create_plan_invalid_properties(self):
        cherrypy.request.body.fp.read = lambda: "saghhs"
        cherrypy.request.path_info = '/'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.method = 'POST'
        response = json.loads(
            self.plan_controller.create_plan()
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/plans/plan")
        self.assertEqual(err["message"],
                         "Create plan failed: Payload is not valid JSON: saghhs")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_delete_plan_wrong_id(self):
        cherrypy.request.method = 'DELETE'
        plan_id = 'some_plan'
        response = json.loads(self.plan_controller.delete_plan(plan_id))
        self.assertEquals(len(response['messages']), 1)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Item not found' in message_list)
        self.assertEquals(response['messages'][0]['_links']['self']['href'], '/plans/some_plan')
        self.assertEquals(
            response['messages'][0]['type'], constants.INVALID_LOCATION_ERROR
        )

    def test_delete_plan_when_no_plan_exists(self):
        cherrypy.request.method = 'DELETE'
        plan_id = 'plan'
        response = json.loads(self.plan_controller.delete_plan(plan_id))
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['_links']['self']['href'], '/plans/')
        self.assertEquals(err['message'], 'Plan does not exist')
        self.assertEquals(err['type'], constants.INVALID_LOCATION_ERROR)

    def test_delete_plan(self):
        cherrypy.request.method = 'DELETE'
        plan_id = 'plan'
        self._setup_plan()
        response = json.loads(self.plan_controller.delete_plan(plan_id))
        self.assertEqual(response['item-type-name'], 'collection-of-plan')
        self.assertEqual(response['id'], 'plans')
        self.assertEqual(response['_links']['self']['href'], '/plans')
        self.assertEqual(response['_links']['collection-of']['href'],
                         '/item-types/plan')

    def test_delete_plan_plan_running(self):
        cherrypy.request.method = 'DELETE'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        execution_manager = cherrypy.config['execution_manager']
        execution_manager.plan = MockPlan()
        execution_manager.plan.valid = False
        execution_manager.plan.running = True
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        response = json.loads(self.plan_controller.delete_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Removing a running/stopping plan is not allowed' in message_list
        )

    def test_update_plan_invalid_id(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'some_plan'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Item not found' in message_list
        )

    def test_update_plan_no_properties(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Properties must be specified for update' in message_list
        )

    def test_update_plan_no_state(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"prop": "my_prop"}}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            "Property 'state' must be specified" in message_list
        )

    def test_update_plan_invalid_state(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "some_state"}}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Invalid state specified' in message_list
        )

    def test_update_plan_invalid_resume_value(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties": {"state": "running", "resume": "False"}}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            "Invalid value for resume specified: 'False'" in message_list
        )

        cherrypy.request.body.fp.read = lambda: '{"properties": {"state": "running", "resume": "True"}}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertTrue(len(response['messages']) > 0)
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            "Invalid value for resume specified: 'True'" in message_list
        )

    def test_update_plan_execution_manager_plan_invalid(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        plan_id = 'plan'
        execution_manager = cherrypy.config['execution_manager']
        model_manager = cherrypy.config['model_manager']
        self._setup_plan()
        execution_manager.plan.run()
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        response = json.loads(self.plan_controller.update_plan(plan_id))
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Plan is currently running or stopping' in message_list
        )

    def test_update_plan_execution_manager_plan_running(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = 'plan'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        execution_manager = cherrypy.config['execution_manager']
        model_manager = cherrypy.config['model_manager']
        self._setup_plan()
        execution_manager.plan.run()
        # execution_manager.plan.running = True
        response = json.loads(self.plan_controller.update_plan(plan_id))
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Plan is currently running or stopping' in message_list
        )

    def test_update_plan_invalid_properties(self):
        cherrypy.request.body.fp.read = lambda: "saghhs"
        cherrypy.request.path_info = '/'
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.plan_controller.update_plan('plan')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/plans/plan")
        self.assertEqual(err["message"],
                         "Payload is not valid JSON: saghhs")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_update_plan_when_no_plan_exists(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = 'plan'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        execution_manager = cherrypy.config['execution_manager']
        model_manager = cherrypy.config['model_manager']
        self._setup_plan()
        execution_manager.plan.run()
        response = json.loads(self.plan_controller.update_plan(plan_id))
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue(
            'Plan is currently running or stopping' in message_list
        )

    def test_update_plan_running(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = 'plan'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "running"}}'
        execution_manager = cherrypy.config['execution_manager']
        model_manager = cherrypy.config['model_manager']
        self._setup_plan()

        # dont do this at home kids
        mock_plan = MockPlan()
        mock_plan.is_active = lambda : False
        mock_plan.is_initial = lambda : True
        mock_plan.is_running = False
        mock_plan.state = 'INITIAL'
        execution_manager.plan = mock_plan

        execution_manager.run_plan_background = MagicMock()
        execution_manager.run_plan_background.return_value = {'success': 'Plan Complete'}

        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'phases')
        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')

    def test_update_plan_stopped(self):
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = 'plan'
        plan_id = 'plan'
        cherrypy.request.body.fp.read = lambda: '{"properties":{"state": "stopped"}}'
        execution_manager = cherrypy.config['execution_manager']
        self._setup_plan()
        execution_manager.plan.run()
        response = json.loads(self.plan_controller.update_plan(plan_id))
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'phases')
        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')

    def test_list_phases_no_plan(self):
        plan_id = 'plan'
        response = json.loads(self.plan_controller.list_phases(plan_id))
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Plan does not exist' in message_list)

    def test_list_phases(self):
        plan_id = 'plan'
        self._setup_plan()
        response = json.loads(self.plan_controller.list_phases(plan_id))
        self.assertEqual(response['_links']['self']['href'],
                         '/plans/plan/phases')
        self.assertEqual(response['id'], 'phases')

    def test_get_phase_no_plan(self):
        plan_id = 'plan'
        phase_id = '1'
        response = json.loads(
            self.plan_controller.get_phase(plan_id, phase_id)
        )
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Plan does not exist' in message_list)

    def test_get_phase_invalid_phase_id(self):
        plan_id = 'plan'
        phase_id = 'some phase id'
        self._setup_plan()
        response = json.loads(
            self.plan_controller.get_phase(plan_id, phase_id)
        )
        self.assertTrue(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Invalid phase id :some phase id')

    def test_get_phase(self):
        plan_id = 'plan'
        phase_id = '1'
        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        execution_manager.plan._phases = [[]]
        response = json.loads(
            self.plan_controller.get_phase(plan_id, phase_id)
        )

        self.assertEqual(
            response['_links']['self']['href'], '/plans/plan/phases/1')

        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases/1/tasks')
        self.assertEqual(response['_embedded']['item'][0]['id'], 'tasks')
        self.assertEqual(response['id'], '1')

    def test_list_tasks_no_plan(self):
        plan_id = 'plan'
        phase_id = '1'
        response = json.loads(
            self.plan_controller.list_tasks(plan_id, phase_id)
        )
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Plan does not exist' in message_list)

    def test_list_tasks_invalid_phase_id(self):
        plan_id = 'plan'
        phase_id = 'some phase id'
        self._setup_plan()
        response = json.loads(
            self.plan_controller.list_tasks(plan_id, phase_id)
        )
        self.assertTrue(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Invalid phase id :some phase id')

    def test_list_tasks(self):
        plan_id = 'plan'
        phase_id = '1'
        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        mock_task = MockTask()
        execution_manager.plan._phases = [[mock_task]]
        with patch('litp.service.controllers.mixins.LitpControllerMixin.data_manager', new_callable=PropertyMock) as mock_data_manager:
            mock_data_manager.return_value.get_task.return_value = mock_task
            response = json.loads(
                self.plan_controller.list_tasks(plan_id, phase_id)
            )
        self.assertEqual(response['_links']['self']['href'],
                         '/plans/plan/phases/1/tasks')
        self.assertEqual(
            response['_embedded']['item'][0]['_links']['self']['href'],
            '/plans/plan/phases/1/tasks/task_id')
        self.assertEqual(response['id'], 'tasks')


    def test_plan_with_recurse_depth(self):
        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        mock_task = MockTask()
        execution_manager.plan._phases = [[mock_task]]
        with patch('litp.service.controllers.mixins.LitpControllerMixin.data_manager', new_callable=PropertyMock) as mock_data_manager:
            mock_data_manager.return_value.get_task.return_value = mock_task
            response = json.loads(
                self.plan_controller.list_plans(recurse_depth=100)
            )
        # plans
        self.assertEqual(response['_links']['self']['href'], '/plans')
        self.assertEqual(
            response['_links']['collection-of']['href'], '/item-types/plan')
        self.assertEqual(response['item-type-name'], 'collection-of-plan')
        self.assertEqual(response['id'], 'plans')
        # plans/plan
        response = response['_embedded']['item'][0]
        self.assertEqual(response['_links']['self']['href'], '/plans/plan')
        self.assertEqual(response['_links']['item-type']['href'],
                         '/item-types/plan')
        self.assertEqual(response['item-type-name'], 'plan')
        self.assertEqual(response['id'], 'plan')
        # plans/plan/phases
        response = response['_embedded']['item'][0]
        self.assertEqual(
            response['_links']['self']['href'], '/plans/plan/phases')
        self.assertEqual(
            response['_links']['collection-of']['href'], '/item-types/phase')
        self.assertEqual(response['item-type-name'], 'collection-of-phase')
        self.assertEqual(response['id'], 'phases')
        # plans/plan/phases/phase
        response = response['_embedded']['item'][0]
        self.assertEqual(
            response['_links']['self']['href'], '/plans/plan/phases/1')
        self.assertEqual(
            response['_links']['item-type']['href'], '/item-types/phase')
        self.assertEqual(response['item-type-name'], 'phase')
        self.assertEqual(response['id'], 1)
        # plans/plan/phases/phase/tasks
        response = response['_embedded']['item'][0]
        self.assertEqual(
            response['_links']['self']['href'], '/plans/plan/phases/1/tasks')
        self.assertEqual(
            response['_links']['collection-of']['href'], '/item-types/task')
        self.assertEqual(response['item-type-name'], 'collection-of-task')
        self.assertEqual(response['id'], 'tasks')
        # plans/plan/phases/phase/tasks/task
        response = response['_embedded']['item'][0]
        self.assertEqual(
            response['_links']['self']['href'],
            '/plans/plan/phases/1/tasks/task_id')
        self.assertEqual(
            response['_links']['item-type']['href'], '/item-types/task')
        self.assertEqual(response['item-type-name'], 'task')
        self.assertEqual(response['id'], 'task_id')

    def test_get_task_no_plan(self):
        plan_id = 'plan'
        phase_id = '1'
        task_id = 'my_unique_id'
        with patch('litp.service.controllers.mixins.LitpControllerMixin.data_manager', new_callable=PropertyMock) as mock_data_manager:
            mock_data_manager.return_value.get_task.return_value = None
            response = json.loads(
                self.plan_controller.get_task(plan_id, phase_id, task_id)
            )
        message_list = [err['message'] for err in response['messages']]
        self.assertTrue('Plan does not exist' in message_list)

    def get_task_invalid_phase_id(self):
        plan_id = 'plan'
        phase_id = 'some phase id'
        task_id = 'my_unique_id'
        self._setup_plan()
        response = json.loads(
            self.plan_controller.get_task(plan_id, phase_id, task_id)
        )
        self.assertTrue(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Invalid phase id :some phase id')

    def test_get_task_invalid_task_id(self):
        plan_id = 'plan'
        phase_id = '1'
        task_id = 'some_string_id'
        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        execution_manager.plan._phases = [[MockTask()]]
        with patch('litp.service.controllers.mixins.LitpControllerMixin.data_manager', new_callable=PropertyMock) as mock_data_manager:
            mock_data_manager.return_value.get_task.return_value = None
            response = json.loads(
                self.plan_controller.get_task(plan_id, phase_id, task_id)
            )
        self.assertTrue(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Invalid task id :some_string_id')

    def test_get_task(self):
        plan_id = 'plan'
        phase_id = '1'
        task_id = 'task_id'
        execution_manager = cherrypy.config.get('execution_manager')
        self._setup_plan()
        mock_task = MockTask()
        execution_manager.plan._phases = [[mock_task]]
        with patch('litp.service.controllers.mixins.LitpControllerMixin.data_manager', new_callable=PropertyMock) as mock_data_manager:
            mock_data_manager.return_value.get_task.return_value = mock_task
            response = json.loads(
                self.plan_controller.get_task(plan_id, phase_id, task_id)
            )
        self.assertEqual(response['_links']['self']['href'],
                         '/plans/plan/phases/1/tasks/task_id')
        self.assertEqual(response['id'], 'task_id')

    @patch('litp.core.plan.BasePlan._get_task_cluster')
    @patch('litp.core.execution_manager.current_jobs')
    def test_outage_during_plan_execution(self, mock_jobs, mock_get_task_cluster):
        orig_exec_mgr = cherrypy.config.get('execution_manager')
        mm = orig_exec_mgr.model_manager
        pm = orig_exec_mgr.puppet_manager
        plm = orig_exec_mgr.plugin_manager

        mock_get_task_cluster.return_value = None

        with patch('litp.core.execution_manager.ExecutionManagerNextGen.data_manager', new_callable=PropertyMock) as mock_data_manager:
            execution_manager = ExecutionManagerNextGen(
                mm, pm, plm
            )
            cherrypy.config.update({
                'execution_manager': execution_manager,
            })

            self._setup_plan()
            mock_task = MockTask()
            mock_task.all_model_items = set()
            mock_task.group = None
            execution_manager.plan._phases = [[mock_task]]
            execution_manager.plan.run()
            original_plan = execution_manager.plan

            mock_job = Mock()
            mock_job.processing = True
            mock_job.result = None
            mock_jobs.return_value = [mock_job]

            mock_task.state=constants.TASK_RUNNING
            mock_data_manager.return_value.get_task.return_value = mock_task

            self.assertEquals(True, cherrypy.config['db_available'])
            self.assertEquals(constants.NO_OUTAGE, execution_manager._outage_status)

            # SQLAlchemy has detected that a connection in the pool had to
            # be invalidated
            set_db_availability(False)

            self.assertEquals(False, cherrypy.config['db_available'])
            self.assertEquals(constants.OUTAGE_DETECTED, execution_manager._outage_status)

            # The execution thread has died. Subsequently, we're dealing with a
            # separate thread that doesn't yet have a plan in its scope
            mock_job.processing = False
            mock_job.result = {'error': 'An exception occurred'}
            del mock_data_manager.plan

            mock_data_manager.return_value.get_plan.return_value = None

            # SQLAlchemy has managed to reconnect to Postgres
            set_db_availability(True)
            mock_data_manager.return_value.get_plan.return_value = original_plan

            # The plan's state isn't fixed until the next access
            self.assertEquals(True, cherrypy.config['db_available'])
            # Accessing plan here causes the outage to move from detected to handled!
            self.assertEquals(Plan.FAILED, execution_manager.plan.state)
            self.assertEquals(constants.OUTAGE_HANDLED, execution_manager._outage_status)
            self.assertEquals(constants.TASK_FAILED, mock_task.state)

        cherrypy.config.update({
            'execution_manager': orig_exec_mgr,
        })
