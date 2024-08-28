import cherrypy
import json
import mock
import unittest

from litp.core.model_manager import ModelManager
from litp.core.model_container import ModelItemContainer
from litp.service.controllers import MiscController

from base import Mock, MockExecutionManager


class TestMiscController(unittest.TestCase):

    def setUp(self):
        self.misc_controller = MiscController()
        self.swp = cherrypy.request
        cherrypy.request = Mock()
        cherrypy.request.body = Mock()
        cherrypy.request.body.fp = Mock()
        cherrypy.request.body.fp.read = lambda: '{}'
        cherrypy.request.path_info = '/litp/logging'
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        execution_manager = MockExecutionManager()
        self.model_manager = ModelManager()
        plugin_manager = Mock()
        plugin_manager.get_plugins = lambda arg: []
        plugin_manager.get_extensions = lambda arg: []
        model_container = ModelItemContainer(
            self.model_manager, plugin_manager, execution_manager)
        cherrypy.config = {
            'execution_manager': execution_manager,
            'model_manager': self.model_manager,
            'model_container': model_container
        }

        _mm_setdebug = {"error": "missing logger_litptrace section"}
        self.model_manager.set_debug = mock.Mock(return_value=_mm_setdebug)

    def tearDown(self):
        cherrypy.request = self.swp
        execution_manager = cherrypy.config.get('execution_manager')
        execution_manager.plan = None

    def test_default_route(self):
        path_info = "my/path/info"
        response = json.loads(self.misc_controller.default_route(path_info))
        self.assertEquals(len(response['messages']), 1)
        self.assertEquals(
            response['messages'][0]['message'],
            'Not found'
        )
