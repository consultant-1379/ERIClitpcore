import cherrypy
import json
import unittest

from litp.core import constants
from litp.core.model_manager import ModelManager
from litp.core.execution_manager import ExecutionManager
from litp.service.controllers import XmlController
from litp.service.controllers.xml import clean_xml_error_message
from litp.core.model_type import ItemType, PropertyType, Property, Collection
from litp.core.plan import Plan
from litp.xml.xml_exporter import XmlExporter
from litp.core.scope_utils import setup_threadlocal_scope
from litp.core import scope

from base import Mock
from mock import MagicMock


class MockXmlLoader(object):
    def load(self, item_path, body_data, **kwargs):
        return []

class MockErrorXmlLoader(object):
    def load(self, item_path, body_data, **kwargs):
        return [{'error': constants.CARDINALITY_ERROR}]


class UtilsTestCase(unittest.TestCase):

    def test_clean_xml_error_message(self):
        # LITPCDS-10807
        message = (
            "Element '{http://www.ericsson.com/litp}volume-group-physical_"
            "devices-collection-inherit', attribute 'id': [facet 'pattern']"
            " The value 'physical_devices_madeup' is not accepted by the"
            " pattern 'physical_devices'., line 9"
        )
        expected = (
            "The value 'physical_devices_madeup' is not accepted by the"
            " pattern 'physical_devices'., line 9"
        )
        self.assertEquals(expected, clean_xml_error_message(message))


class TestXmlController(unittest.TestCase):

    def setUp(self):
        model_manager = self._setup_model_manager()
        execution_manager = ExecutionManager(model_manager, None, None)
        execution_manager.plan = Plan([], [])
        execution_manager.plan.set_ready()
        cherrypy.config = {
            'model_manager': model_manager,
            'execution_manager': execution_manager,
            'xml_loader': MockXmlLoader(),
            'xml_exporter': XmlExporter(model_manager)
        }
        scope.data_manager = model_manager.data_manager
        self.xml_controller = XmlController()
        self.swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.body = Mock()
        cherrypy.request.body.fp = Mock()
        cherrypy.request.body.fp.read = lambda: ''
        cherrypy.request.path_info = ''
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''

    def tearDown(self):
        scope.data_manager.rollback()
        scope.data_manager.close()
        del scope.data_manager
        cherrypy.request = self.swp

    def _setup_model_manager(self):
        model_manager = ModelManager()
        model_manager.register_property_type(PropertyType("basic_string"))

        model_manager.register_item_type(
            ItemType("dummy", item_description="some description")
        )
        dummy_prop = Property('basic_string',
                           prop_description='A dummy property',
                           required=True)

        model_manager.register_item_type(ItemType(
                "collection",
                item_description="collection item."
        ))
        model_manager.register_item_type(
            ItemType('bigger_dummy',
                    item_description='More of a dummy item type',
                    extend_item='dummy',
                    dummy_property=dummy_prop,
                    collective=Collection('collection'))
        )
        model_manager.create_root_item("dummy")
        return model_manager

    def mock_is_plan_running(self):
        return True

    def mock_is_plan_stopping(self):
        return True

    def test_export_xml_item(self):
        item_path = "/plans"
        response = json.loads(
            self.xml_controller.export_xml_item(item_path)
        )
        self.assertEquals(
            cherrypy.response.status, constants.METHOD_NOT_ALLOWED)
        self.assertEqual(len(response["messages"]), 1)
        self.assertEqual(response["messages"][0]["message"],
            constants.ERROR_MESSAGE_CODES.get(
                    constants.METHOD_NOT_ALLOWED_ERROR))
        self.assertEqual(response["messages"][0]["type"],
            constants.METHOD_NOT_ALLOWED_ERROR)

    def test_xml_export_with_plan_running(self):
        exec_mngr = cherrypy.config["execution_manager"]
        exec_mngr.is_plan_running = self.mock_is_plan_running
        exec_mngr.is_plan_stopping = self.mock_is_plan_stopping
        response = json.loads(self.xml_controller.export_xml_item('/'))
        self.assertEquals(cherrypy.response.status, 422)
        err = response['messages'][0]
        self.assertEqual(err["message"],
                 "Operation not allowed while plan is running/stopping")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_export_item_2(self):
        item_path = "/zzz"
        response = json.loads(
            self.xml_controller.export_xml_item(item_path)
        )
        self.assertEquals(
            cherrypy.response.status, constants.NOT_FOUND)
        self.assertEqual(len(response["messages"]), 1)
        self.assertEqual(response["messages"][0]["message"],
            "Not Found")
        self.assertEqual(response["messages"][0]["type"],
            constants.INVALID_LOCATION_ERROR)

    def test_export_item_3(self):
        expected = ("<?xml version='1.0' encoding='utf-8'?>\n" +
                   '<litp:dummy ' +
                   'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" ' +
                   'xmlns:litp="http://www.ericsson.com/litp" ' +
                   'xsi:schemaLocation=' +
                   '"http://www.ericsson.com/litp ' +
                   'litp-xml-schema/litp.xsd"/>' +
                   '\n')
        item_path = "/"

        response = self.xml_controller.export_xml_item(item_path)
        self.assertEquals(
            cherrypy.response.status, constants.OK)
        self.assertEqual(expected, response)

    def test_export_xml_item_if_not_xml_doc(self):
        expected = constants.NOT_FOUND
        response = None
        msg = "JL DEBUG"
        item_path = "GARBADAGE"
        response = self.xml_controller.export_xml_item(item_path)
        self.assertEqual(expected, constants.NOT_FOUND)

    def test_if_plan_reject(self):
        item_path = "/plans"
        plan_structure = ["/plans"]
        result_structure = self.xml_controller._inspect_plan_structure()
        data = "<test><plans><plan><item /></plan></plans></test>"
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/xml'
        cherrypy.request.body.fp.read = lambda: data

        response = json.loads(
            self.xml_controller.import_xml_item(item_path)
        )
        expected = [{u'_links': {u'self': {u'href': u''}}, u'message': \
        u'Operation not permitted', u'type': u'MethodNotAllowedError'}]
        errs = response.get('messages')
        self.assertEqual(expected, errs)

    def test_inspect_if_no_plan(self):
        plan_structure = ['/plans']
        execution_manager = cherrypy.config.get("execution_manager")
        execution_manager.plan = None
        result_structure = self.xml_controller._inspect_plan_structure()
        self.assertEqual(plan_structure, result_structure)

    def test_inspect_if_plan(self):
        plan_structure = ['/plans',
                          '/plans/plan',
                          '/plans/plan/phases',
                          '/plans/plan/phases/1',
                          '/plans/plan/phases/1/tasks',
                          '/plans/plan/phases/1/tasks/task_id',
                          '/plans/plan/phases/1/tasks/task_id',
                          '/plans/plan/phases/2',
                          '/plans/plan/phases/2/tasks',
                          '/plans/plan/phases/2/tasks/task_id',
                          '/plans/plan/phases/2/tasks/task_id']
        execution_manager = cherrypy.config.get("execution_manager")
        execution_manager.plan = MagicMock()
        task = MagicMock()
        task.task_id = "task_id"
        tasks = [task, task]
        execution_manager.plan.phases = [tasks, tasks]

        execution_manager.plan.get_phase = MagicMock(return_value=tasks)
        result_structure = self.xml_controller._inspect_plan_structure()
        self.assertEqual(plan_structure, result_structure)

    def test_if_ValidationError_thrown(self):
        ## TODO increase coverage on src/litp/service/controllers/xml
        pass

    def test_if_DocumentInvalid_Exception_thrown(self):
        ## TODO increase coverage on src/litp/service/controllers/xml
        pass

    def test_if_XMLSyntax_Exception_thrown(self):
        ## TODO increase coverage on src/litp/service/controllers/xml
        pass

    def test_import_invalidates_plan(self):
        self._setup_model_manager()
        exec_mngr = cherrypy.config["execution_manager"]
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/xml'
        cherrypy.request.body.fp.read = lambda: '<data></data>'
        self.xml_controller.import_xml_item('/')
        self.assertEquals(Plan.INVALID, exec_mngr.plan.state)

    def test_import_wont_invalidates_plan_on_error(self):
        cherrypy.config['xml_loader'] = MockErrorXmlLoader()
        exec_mngr = cherrypy.config["execution_manager"]
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/xml'
        self.xml_controller.import_xml_item('/')
        self.assertEquals(Plan.INITIAL, exec_mngr.plan.state)

#     def test_import_xml_item_fails(self):
#         item_path = "/"
#         data = "<test><item /></test"
#         cherrypy.request.method = 'POST'
#         cherrypy.request.headers['Content-Type'] = 'application/xml'
#         cherrypy.request.body.fp.read = lambda: data
#
#         response = json.loads(
#             self.xml_controller.import_xml_item(item_path)
#         )
#         self.assertEquals(
#             cherrypy.response.status, constants.UNPROCESSABLE)
#         self.assertEqual(len(response["message"]), 1)
#         self.assertEqual(response["messages"][0]["message"],
#             "expected '>', line 1, column 16")
#         self.assertEqual(response["messages"][0]["type"],
#             constants.INVALID_REQUEST_ERROR)
