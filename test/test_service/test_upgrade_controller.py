import cherrypy
import unittest

from litp.service.controllers import UpgradeController
from litp.core.model_manager import ModelManagerException
from litp.core.validators import ValidationError
from litp.core.constants import CARDINALITY_ERROR
from mock import MagicMock


class MockUpgradeLoader(object):
    def load(self, item_path, body_data, **kwargs):
        return []


class TestUpgradeController(unittest.TestCase):

    def setUp(self):
        self.model = MagicMock()
        self.execution_manager = MagicMock()
        self.execution_manager.is_plan_running.return_value = False
        self.execution_manager.is_plan_stopping.return_value = False
        cherrypy.config = {
            'model_manager': self.model,
            'execution_manager': self.execution_manager,
            'upgrade_loader': MockUpgradeLoader()
        }
        self.upgrade_controller = UpgradeController()
        self.swp = cherrypy.request
        cherrypy.request = MagicMock()
        cherrypy.request.body = MagicMock()
        cherrypy.request.body.fp = MagicMock()
        cherrypy.request.body.fp.read = lambda: '{"path": "/trololo"}'
        cherrypy.request.path_info = ''
        cherrypy.request.method = 'POST'
        cherrypy.request.headers = {'Content-Type': 'application/json'}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''

    def tearDown(self):
        cherrypy.request = self.swp

    def test_upgrade_no_errors(self):
        self.model.handle_upgrade_item = MagicMock(return_value=[])
        self.assertEqual('{}', self.upgrade_controller.upgrade('/trololo'))
        self.assertEqual(201, cherrypy.response.status)

    def test_upgrade_on_nonexisting_item(self):
        self.model.handle_upgrade_item = MagicMock(side_effect=ModelManagerException)
        self.assertEqual('{"messages": [{"type": "InvalidLocationError", "message": "Upgrade can only be run on deployments, clusters or nodes", "_links": {"self": {"href": "/trololo"}}}], "_links": {"self": {"href": "/trololo"}}}',
                         self.upgrade_controller.upgrade('/trololo'))
        self.assertEqual(404, cherrypy.response.status)

    def test_upgrade_with_errors(self):
        error = ValidationError(
                       item_path='/trololo',
                       error_message='Muerte por kiki',
                       error_type=CARDINALITY_ERROR)
        self.model.handle_upgrade_item = MagicMock(return_value=error)
        self.assertEqual('{"messages": [{"_links": {"self": {"href": "/trololo"}}, "message": "Muerte por kiki", "type": "CardinalityError"}], "_links": {"self": {"href": "/trololo"}}}',
                         self.upgrade_controller.upgrade('/trololo'))
        self.assertEqual(422, cherrypy.response.status)