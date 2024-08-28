import cherrypy
import json
import unittest

import litp.core.constants as constants
from litp.core.model_manager import ModelManager
from litp.core import execution_manager
from litp.core.puppet_manager import PuppetManager
from litp.core.plugin_manager import PluginManager
from litp.core.plan import Plan
from litp.service.controllers import LitpServiceController
from litp.service.controllers import ItemController
from litp.core.model_type import ItemType, PropertyType
from litp.core.model_type import Collection, Property, Reference
from litp.extensions.core_extension import CoreExtension
from litp.core.maintenance import StateFile

from base import Mock, MockPlan
import mock


class TestLitpServiceController(unittest.TestCase):

    def setUp(self):
        self.litp_service_controller = LitpServiceController()
        self.item_controller = ItemController()
        self.swp = cherrypy.request
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.body = Mock()
        cherrypy.request.body.fp = Mock()

        self.model = model_manager = ModelManager()
        core_extension = CoreExtension()
        self.model.register_property_types(core_extension.define_property_types())
        self.model.register_item_types(core_extension.define_item_types())

        model_manager.register_item_type(
            ItemType("non_updatable", force_debug=Property("basic_boolean"), extend_item='litp-service-base')
        )
        model_manager.register_item_type(
            ItemType(
                "child",
                dependent_ref=Reference("dependant", require=True),
                name=Property("basic_string", required=True))
        )
        model_manager.register_item_type(
            ItemType("dependant", name=Property("basic_string", required=True))
        )
        model_manager.create_root_item("root")
        model_manager.create_item("logging", "/litp/updatable_service")
        model_manager.create_item("prepare-restore", "/litp/prepare-restore")
        model_manager.create_item("import-iso", "/litp/import-iso")
        model_manager.create_item("restore", "/litp/restore_model")
        model_manager.create_item("restore", "/litp/triggerable_service")
        model_manager.create_item("non_updatable", "/litp/non_updatable_service")
        plugin_manager = PluginManager(self.model)

        litp_root = cherrypy.config.get("litp_root", "/opt/ericsson/nms/litp")

        puppet_manager = mock.Mock()
        puppet_manager.remove_certs = mock.Mock(return_value='')
        puppet_manager.remove_manifests_clean_tasks = mock.Mock(return_value='')

        puppet_manager.all_tasks = mock.Mock(return_value=[])
        puppet_manager.cleanup = mock.Mock(return_value=True)
        puppet_manager.node_tasks = {}  # is OK because all_tasks() returns  []

        self.execution_manager = execution_manager.ExecutionManager(model_manager, puppet_manager, plugin_manager)

        cherrypy.config = {'model_manager': model_manager,
                           'execution_manager': self.execution_manager,
                           'puppet_manager': puppet_manager,
                           'dbase_root': "/var/lib/litp/core/model/",
                           'litp_root': "/opt/ericsson/nms/litp",
                           'last_successful_plan_model': "LAST_SUCCESSFUL_PLAN_MODEL"
                           }

    def tearDown(self):
        cherrypy.request = self.swp

    def test_allows_maintenance(self):
        cherrypy.request.path_info = '/litp/not-maintenance'
        self.assertFalse(self.litp_service_controller.allows_maintenance_method())
        cherrypy.request.path_info = '/litp/maintenance'
        self.assertTrue(self.litp_service_controller.allows_maintenance_method())

    def test_list_services(self):
        service_result = self.litp_service_controller.list_services()

        expected_result = {'_embedded': {'item': [{u'_links': {u'item-type': {u'href': u'/item-types/restore'},
                                                               u'self': {u'href': u'/litp/restore_model'}},
                                                   u'applied_properties_determinable': True,
                                                   u'id': u'restore_model',
                                                   u'item-type-name': u'restore',
                                                   u'properties': {u'update_trigger': u'updatable'}},
                                                  {'_links': {'item-type': {'href': '/item-types/restore'},
                                                              'self': {'href': '/litp/triggerable_service'}},
                                                   'applied_properties_determinable': True,
                                                   'id': 'triggerable_service',
                                                   'item-type-name': 'restore',
                                                   'properties': {'update_trigger': 'updatable'}},
                                                  {'_links': {'item-type': {'href': '/item-types/import-iso'},
                                                              'self': {'href': '/litp/import-iso'}},
                                                   'applied_properties_determinable': True,
                                                   'id': 'import-iso',
                                                   'item-type-name': 'import-iso',
                                                   'properties': {'source_path': '/'}},
                                                  {'_links': {'item-type': {'href': '/item-types/non_updatable'},
                                                              'self': {'href': '/litp/non_updatable_service'}},
                                                   'applied_properties_determinable': True,
                                                   'id': 'non_updatable_service',
                                                   'item-type-name': 'non_updatable'},
                                                  {'_links': {'item-type': {'href': '/item-types/prepare-restore'},
                                                              'self': {'href': '/litp/prepare-restore'}},
                                                   'applied_properties_determinable': True,
                                                   'id': 'prepare-restore',
                                                   'item-type-name': 'prepare-restore',
                                                   'properties': {'actions': 'all', 'path': '/',
                                                                  'force_remove_snapshot': 'false'}},
                                                  {'_links': {'item-type': {'href': '/item-types/logging'},
                                                              'self': {'href': '/litp/updatable_service'}},
                                                   'applied_properties_determinable': True,
                                                   'id': 'updatable_service',
                                                   'item-type-name': 'logging',
                                                   'properties': {'force_debug': 'false',
                                                                  'force_postgres_debug': 'false'}
                                                   }]},
                           '_links': {'collection-of': {'href': '/item-types/litp-service-base'},
                                      'self': {'href': '/litp'}},
                           'applied_properties_determinable': True,
                           'id': 'litp',
                           'item-type-name': 'collection-of-litp-service-base'}

        actual_result = json.loads(service_result)
        sort_key = lambda item: item["_links"]["self"]
        actual_result["_embedded"]["item"].sort(key=sort_key)
        expected_result["_embedded"]["item"].sort(key=sort_key)
        self.assertEquals(actual_result, expected_result)

    def test_list_invalid_services(self):
        cherrypy.config['model_manager'] = ModelManager()
        cherrypy.request.path_info = '/litp'
        service_result = self.litp_service_controller.list_services()

        expected_result = json.loads('''
            {
                "_links": {
                    "self": {
                        "href": "/litp"
                    }
                },
                "messages": [
                    {
                        "_links": {
                            "self": {
                                "href": "/litp"
                            }
                        },
                        "message": "Not found",
                        "type": "InvalidLocationError"
                    }
                ]
            }
            ''')
        self.assertEquals(json.loads(service_result), expected_result)

    def test_get_service(self):
        service_id = 'updatable_service'
        service_result = self.litp_service_controller.get_service(service_id)
        expected_result = json.loads('''
            {
                "_links": {
                    "item-type": {
                        "href": "/item-types/logging"
                    },
                    "self": {
                        "href": "/litp/updatable_service"
                    }
                },
                "properties": {
                    "force_debug": "false",
                    "force_postgres_debug": "false"
                },
                "id": "updatable_service",
                "item-type-name": "logging",
                "applied_properties_determinable":true
            }
        ''')
        self.assertEqual(json.loads(service_result), expected_result)
        service_id = '/litp/updatable_service'
        service_result = self.litp_service_controller.get_service(service_id)
        expected_result = json.loads('''
            {
                "_links": {
                    "item-type": {
                        "href": "/item-types/logging"
                    },
                    "self": {
                        "href": "/litp/updatable_service"
                    }
                },
                "properties": {
                    "force_debug": "false",
                    "force_postgres_debug": "false"
                },
                "id": "updatable_service",
                "item-type-name": "logging",
                "applied_properties_determinable":true
            }
        ''')
        self.assertEqual(json.loads(service_result), expected_result)

    def test_get_invalid_service(self):
        service_id = 'nologging'
        service_result = self.litp_service_controller.get_service(service_id)
        expected_result = json.loads('''
            {
                "_links": {
                    "self": {
                        "href": "/litp/nologging"
                    }
                },
                "messages": [
                    {
                        "_links": {
                            "self": {
                                "href": "/litp/nologging"
                            }
                        },
                        "message": "Not found",
                        "type": "InvalidLocationError"
                    }
                ]
            }
        ''')
        self.assertEqual(json.loads(service_result), expected_result)

    @mock.patch('litp.core.model_manager.SafeConfigParser')
    def test_update_service_true(self, MockParser):
        parser_instance = MockParser.return_value
        parser_instance.get.return_value = "INFO"
        service_id = 'updatable_service'
        new_data = {'properties': {'force_debug': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['properties']['force_debug'], 'true')
        self.assertEqual(cherrypy.response.status, 200)
        # Set force_debug back to false
        new_data = {'properties': {'force_debug': 'false'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['properties']['force_debug'], 'false')

    @mock.patch('ConfigParser.SafeConfigParser.has_option')
    @mock.patch('ConfigParser.SafeConfigParser.get')
    @mock.patch('ConfigParser.SafeConfigParser.read')
    @mock.patch('ConfigParser.SafeConfigParser.sections')
    @mock.patch('ConfigParser.SafeConfigParser.has_section')
    def test_update_item_false(
            self, mock_parser_has_section, mock_parser_sections,
            mock_parser_read, mock_parser_get, mock_has_option):
        service_id = 'updatable_service'
        new_data = {'properties': {'force_debug': 'false'}}
        mock_has_option.return_value = True
        mock_parser_has_section.return_value = True
        mock_parser_sections.return_value = ["non", "empty", "list"]
        mock_parser_read.return_value = ["mock log file"]
        mock_parser_get.return_value = "INFO"
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['properties']['force_debug'], 'false')
        self.assertEqual(cherrypy.response.status, 200)

    def test_update_service_invalid_payload(self):
        service_id = 'updatable_service'
        new_data = {'properties': {'force_debug': 'invalid'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['messages'][0],
            {'type': 'ValidationError',
             'message': "Invalid value 'invalid'.",
             'property_name': 'force_debug'}
        )
        self.assertEqual(cherrypy.response.status, 422)

    def test_update_service_empty(self):
        service_id = 'updatable_service'
        new_data = {'properties': {'force_debug': ''}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['messages'][0],
            {'type': 'ValidationError',
             'message': "Invalid value ''.",
             'property_name': 'force_debug'}
        )

    def test_update_non_updatable_service(self):
        service_id = 'non_updatable_service'
        new_data = {'properties': {'property': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        expected_response = json.loads('''
            {
                "_links": {
                    "self": {
                        "href": "/litp/non_updatable_service"
                    }
                },
                "messages": [
                    {
                        "_links": {
                            "self": {
                                "href": "/litp/non_updatable_service"
                            }
                        },
                        "message": "This service cannot be updated",
                        "type": "InvalidRequestError"
                    }
                ]
            }
        ''')

        self.assertEquals(response, expected_response)
        self.assertEqual(cherrypy.response.status, constants.UNPROCESSABLE)

    def test_update_service_invalid(self):
        service_id = 'non_existant_service'
        new_data = {'properties': {'force_debug': ''}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response['messages'][0],
            {"_links": {
                "self": {
                    "href": "/litp/non_existant_service"
                }
             },
             'type': 'InvalidLocationError',
             'message': 'Not found'
             }
        )

    def test_prepare_restore_updated_fs(self):
        fs1 = self.model.create_item("file-system-base", "/infrastructure/storage/nfs_mounts/fs1")
        fs1.set_updated()
        service_id = 'prepare-restore'
        new_data = {'properties': {'path': '/', 'actions':'all'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'

        with mock.patch.object(self.litp_service_controller,
                               '_restore_model') as m:
            m.return_value = [], None, None
            result = self.litp_service_controller.update_service(service_id)
            self.assertTrue(m.called)
        response = json.loads(result)
        self.assertEquals(response['id'], 'prepare-restore')
        self.assertEquals(response['state'], 'Initial')

    def test_prepare_restore_plan_fail(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", "/deployments/dep1/clusters/cluster1")
        self.model.create_item("snapshot-base", "/snapshots/snapshot")
        self.model.create_item("node", "/deployments/dep1/clusters/cluster1/nodes/node1",
                               hostname="node1")
        plan_state_old = self.execution_manager.plan_state
        self.execution_manager.plan_state = lambda: Plan.FAILED
        result = self.litp_service_controller._remove_snapshot(force_remove_snapshot='true')
        res = result[0]
        self.execution_manager.plan_state = plan_state_old

        self.assertEquals(res['error'], 'InternalServerError')
        self.assertEquals(res['message'], 'Remove snapshot plan failed')
        self.assertEquals(res['uri'], '/snapshots/snapshot')
        self.assertEquals(self.model.get_item('/snapshots/snapshot').properties['force'],
                          'true')

    def test_prepare_restore_locked_node(self):
        self.model.create_item("deployment", "/deployments")
        self.model.create_item("deployment", "/deployments/dep1")
        self.model.create_item("cluster", "/deployments/dep1/clusters/cluster1")
        self.model.create_item("node", "/deployments/dep1/clusters/cluster1/nodes/node1",
                               hostname="node1")
        self.model._update_item("/deployments/dep1/clusters/cluster1/nodes/node1",
                                {'is_locked':'true'},
                               validate_readonly=False)
        self.assertEquals('true', self.model.query('node').pop().is_locked)
        self.litp_service_controller._execute_prepare_restore_actions('all', '/', [], False)
        self.assertEquals('false', self.model.query('node').pop().is_locked)

    def test_prepare_restore_existing_plan(self):
        cherrypy.config['execution_manager'].plan = MockPlan()
        self.assertTrue(self.execution_manager.plan_exists())
        self.assertTrue(self.execution_manager.plan is not None)

        service_id = 'prepare-restore'
        new_data = {'properties': {'path': '/', 'actions':'all'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        with mock.patch.object(self.litp_service_controller,
                               '_restore_model') as m:
            m.return_value = [], None, None
            response = json.loads(
                self.litp_service_controller.update_service(service_id)
            )
            self.assertTrue(m.called)
        self.assertFalse(self.execution_manager.plan_exists())
        self.assertTrue(self.execution_manager.plan is None)

    def test_prepare_restore(self):
        service_id = 'prepare-restore'
        new_data = {'properties': {'path': '/', 'actions':'all'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        with mock.patch.object(self.litp_service_controller,
                               '_restore_model') as m:
            m.return_value = [], None, None
            response = json.loads(
                self.litp_service_controller.update_service(service_id)
            )
            self.assertTrue(m.called)
        self.assertEquals(
            response,
            {
                'item-type-name': 'prepare-restore',
                'state': 'Initial',
                '_links': {
                    'self': {
                        'href': '/litp/prepare-restore'
                    },
                    'item-type': {
                        'href': '/item-types/prepare-restore'
                    }
                },
                'id': 'prepare-restore',
                'applied_properties_determinable': True,
                'properties': {
                    'path': '/',
                    'actions': 'all',
                    'force_remove_snapshot': 'false'
                }
            }
        )

    def _get_request_response(self, service_id):
        cherrypy.request.method = 'GET'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        path = cherrypy.request.path_info = '/litp/' + service_id
        response = json.loads(
            self.item_controller.get_item(path)
        )
        return response

    def test_prepare_restore_unsupported_actions(self):
        service_id = 'prepare-restore'
        response_orig = self._get_request_response("prepare-restore")
        new_data = {'properties': {'path': '/', 'actions':'unsupported'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        with mock.patch.object(self.litp_service_controller,
                               '_restore_model') as m:
            m.return_value = [], None, None
            response = json.loads(
                self.litp_service_controller.update_service(service_id)
            )
            self.assertTrue(m.called)
        self.assertEquals(
            response,
            {
                '_links': {
                    'self': {
                        'href': '/litp/prepare-restore'
                    }
                },
                'messages': [
                    {
                        'message': "Invalid value 'unsupported'.",
                        'type': 'ValidationError',
                        'property_name': 'actions'
                    }
                ]
            }
        )
        response_updated = self._get_request_response("prepare-restore")
        self.assertEquals(response_orig['properties'],
                                            response_updated['properties'])

    def test_create_litp_neg(self):
        service_id = 'litp'
        new_data = {'item-type': 'litp-service-base',
                    'properties': {'force_debug': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.create_item(service_id)
        )
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create method on path not allowed'
        )
        self.assertEqual(cherrypy.response.status, 405)

    def test_create_litp_logging(self):
        service_id = 'updatable_service'
        new_data = {'item-type':'litp-service-base',
                    'properties': {'force_debug': 'true'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp/updatable_service'
        response = json.loads(
            self.litp_service_controller.create_item(service_id)
        )
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Create method on path not allowed'
        )
        self.assertEqual(cherrypy.response.status, 405)

    def test_remove_litp(self):
        service_id = 'litp'
        cherrypy.request.method = 'DELETE'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.delete_item(service_id)
        )
        err = response['messages'][0]
        self.assertEquals(err['message'], 'Remove method on path not allowed')

    def test_remove_litp_logging(self):
        service_id = 'updatable_service'
        cherrypy.request.method = 'DELETE'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp/updatable_service'
        response = json.loads(
            self.litp_service_controller.delete_item(service_id)
        )
        err = response['messages'][0]
        self.assertEquals(
            err['message'], 'Remove method on path not allowed')
        self.assertEqual(cherrypy.response.status, 405)

    def test_set_maintenance_error_if_not_found(self):
        self.litp_service_controller._get_statefile_value = mock.MagicMock()
        self.assertEqual('{"messages": [{"message": "Maintenance item not found", "type": "InternalServerError"}], "_links": {"self": {"href": "/litp"}}}',
                         self.litp_service_controller._set_maintenance_props())

    def test_set_maintenance_initiator(self):
        self.model.create_item("maintenance", "/litp/maintenance", enabled="false")
        service_id = 'maintenance'
        new_data = {'properties': {'enabled': 'true'}}
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.path_info = '/litp/maintenance'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response,
            {
                'item-type-name': 'maintenance',
                'state': 'Initial',
                '_links': {
                    'self': {
                        'href': '/litp/maintenance'
                    },
                    'item-type': {
                        'href': '/item-types/maintenance'
                    }
                },
                'id': 'maintenance',
                'applied_properties_determinable': True,
                'properties': {
                    'enabled': 'true',
                    'initiator': 'user',
                    'status': 'None',
                }
            }
        )

    def test_set_maintenance_initiator2(self):
        self.model.create_item("maintenance", "/litp/maintenance", enabled="false")
        service_id = 'maintenance'
        new_data = {'properties': {'initiator': 'test'}}
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.path_info = '/litp/maintenance'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response,
            {
                '_links': {
                    'self': {
                        'href': '/litp/maintenance'
                    }
                },
                'messages': [{
                    'type': 'InvalidRequestError',
                    'message': 'Unable to modify readonly property: initiator',
                    '_links': {
                        'self': {
                            'href': '/litp/maintenance'
                            }
                        },
                    'property_name': 'initiator'
                    }]
            }
        )

    def test_set_maintenance_status(self):
        self.model.create_item("maintenance", "/litp/maintenance", enabled="false")
        service_id = 'maintenance'
        new_data = {'properties': {'status': 'test'}}
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.path_info = '/litp/maintenance'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )
        self.assertEquals(
            response,
            {
                '_links': {
                    'self': {
                        'href': '/litp/maintenance'
                    }
                },
                'messages': [{
                    'type': 'InvalidRequestError',
                    'message': 'Unable to modify readonly property: status',
                    '_links': {
                        'self': {
                            'href': '/litp/maintenance'
                            }
                        },
                    'property_name': 'status'
                    }]
            }
        )

    def test_no_initiator_is_none(self):
        self.model.create_item("maintenance", "/litp/maintenance")
        self.model = mock.MagicMock()
        self.model.get_item.get_property = None
        self.litp_service_controller._read_statefile = mock.MagicMock(return_value='None')
        self.assertEqual('None', self.litp_service_controller._get_statefile_value())

    def test_initiator_and_done_is_done(self):
        self.model.create_item("maintenance", "/litp/maintenance", initiator='perico')
        self.model = mock.MagicMock()
        self.model.get_item.get_property = mock.MagicMock()
        self.litp_service_controller._read_statefile = mock.MagicMock(return_value='None')
        self.assertEqual('Done', self.litp_service_controller._get_statefile_value())

    def test_updated_properties(self):
        item1 = mock.Mock()
        item1._manager = mock.Mock()
        item1.applied_properties = {'prop1': 'value1',
                                    'prop3': 'value3'}
        item1.properties = {'prop1': 'value4',
                            'prop2': 'value2'}
        data = self.litp_service_controller._check_updated_properties(item1)
        self.assertTrue(("prop1","value1") in data['updated'])
        self.assertTrue(("prop3","value3") in data['updated'])
        self.assertTrue("prop2" in data['new'])

    def test_create_updated_error_message_updated(self):
        msg1 = self.litp_service_controller.\
            _create_updated_error_message({'new': None, 'updated': [('p1', 'v1')]})
        self.assertTrue('"p1" to "v1"' in msg1)

    def test_create_updated_error_message_new(self):
        msg1 = self.litp_service_controller.\
            _create_updated_error_message({'new': ['p2'], 'updated': None})
        self.assertTrue("'p2'" in msg1)

    def test_create_updated_error_message_new(self):
        msg1 = self.litp_service_controller.\
            _create_updated_error_message({'new': ['new_property'], 'updated':
                [('size','5G'),('snap_size','1G'),('cache_name','my_cache')]})
        self.assertEquals("Remove additional properties:"
                          " \"new_property\";"
                          " revert updated properties: \"size\""
                          " to \"5G\", \"snap_size\" to \"1G\" and"
                          " \"cache_name\" to \"my_cache\""
                          " and rerun prepare_restore", msg1)

    def test_create_updated_error_message_short(self):
        msg1 = self.litp_service_controller.\
            _create_updated_error_message({'new': [], 'updated':
                [('size','5G'),('snap_size','1G')]})
        self.assertEquals("Revert updated properties: \"size\""
                          " to \"5G\" and \"snap_size\" to \"1G\""
                          " and rerun prepare_restore", msg1)

    def test_create_updated_error_message_short2(self):
        msg1 = self.litp_service_controller.\
            _create_updated_error_message({'new': [], 'updated':
                [('snap_size','1G')]})
        self.assertEquals("Revert updated properties: \"snap_size\" to \"1G\""
                          " and rerun prepare_restore", msg1)

    def test_import_iso(self):
        service_id = 'import-iso'
        response_orig = self._get_request_response("import-iso")
        data = {'properties': {'source_path': '/unsupported'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/litp'
        response = json.loads(
            self.litp_service_controller.update_service(service_id)
        )

        self.assertEquals(
            response,
            {
                '_links': {
                    'self': {
                        'href': '/litp/import-iso'
                    }
                },
                'messages': [
                    {
                        '_links': {'self': {'href': '/litp/import-iso'}},
                        'message': 'Source directory "/unsupported" does not exist.',
                        'type': 'ValidationError'
                    }
                ]
            }
        )
        response_updated = self._get_request_response("import-iso")
        self.assertEquals(response_orig['properties'],
                                            response_updated['properties'])
