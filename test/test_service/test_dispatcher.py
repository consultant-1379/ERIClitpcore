import cherrypy
import unittest
from litp.service.dispatcher import TrailingSlashRoutesDispatcher
from litp.service.dispatcher import wrap_handler
from litp.service.controllers import LitpControllerMixin
from mock import MagicMock, patch


class MaintenanceController(LitpControllerMixin):
    @staticmethod
    def allows_maintenance():
        return True

    def random_handler(self):
        pass


class LitpMaintenanceMethodsController(LitpControllerMixin):
    def allows_maintenance_exceptions(self):
        return {self.handler_maintenance: self.allows_maintenance_method}

    def allows_maintenance_method(self):
        return True

    def handler_no_maintenance(self):
        pass

    def handler_maintenance(self):
        pass


class TestDispatcher(unittest.TestCase):

    def setUp(self):
        self.dispatcher = TrailingSlashRoutesDispatcher('/test')
        self.litp_controller = LitpControllerMixin()
        self.maintenance_controller = MaintenanceController()
        self.maintenance_method_controller = LitpMaintenanceMethodsController()

    def test_maintenance_mode(self):
        # all old controllers will use this
        with patch.object(cherrypy.dispatch.RoutesDispatcher, 'find_handler') as fh:
            fh.return_value = self.litp_controller.plan_is_running
            self.assertEqual(self.litp_controller.plan_is_running.func_name,
                             self.dispatcher.find_handler('/test').func_name)
            self.dispatcher._maintenance_on = MagicMock(return_value=True)
            self.assertEqual(self.dispatcher.return_503,
                             self.dispatcher.find_handler('/test'))

    def test_class_with_maintenance_allowed(self):
        # all methods in that controller work under maintenance
        with patch.object(cherrypy.dispatch.RoutesDispatcher, 'find_handler') as fh:
            self.dispatcher._maintenance_on = MagicMock(return_value=True)
            fh.return_value = self.maintenance_controller.random_handler
            self.assertEqual(self.maintenance_controller.random_handler.func_name,
                             self.dispatcher.find_handler('/test').func_name)

    def test_class_with_maintenance_method_allowed(self):
        # one method works under maintenance the other does not
        with patch.object(cherrypy.dispatch.RoutesDispatcher, 'find_handler') as fh:
            self.dispatcher._maintenance_on = MagicMock(return_value=True)
            fh.return_value = self.maintenance_method_controller.handler_maintenance
            self.assertEqual(self.maintenance_method_controller.handler_maintenance.func_name,
                             self.dispatcher.find_handler('/test').func_name)
            fh.return_value = self.maintenance_method_controller.handler_no_maintenance
            self.assertEqual(self.dispatcher.return_503,
                             self.dispatcher.find_handler('/test'))

    def test_handler_allows_maintenance(self):
        def foo():
            pass

        # try strange handlers
        self.assertFalse(self.dispatcher._handler_allows_maintenance(None))
        # function object, which has no __self__ method
        self.assertFalse(self.dispatcher._handler_allows_maintenance(foo))
        # C class, does not have im_class
        self.assertFalse(self.dispatcher._handler_allows_maintenance(''.count))

    def test_return_503(self):
        self.dispatcher._maintenance_on = MagicMock(return_value=True)
        message = {'messages': [{'message': 'Create plan failed: Cannot restore a Deployment Snapshot if a Named Backup Snapshot exists.', 'type': 'ValidationError'}], '_links': {'self': {'href': 'snapshot'}}}
        self.assertEqual(self.dispatcher.return_503(self.dispatcher),
        '{"messages": [{"message"'\
        ': "LITP is in maintenance mode", "type": '\
        '"ServerUnavailableError"}]}')
        self.assertNotEqual(self.dispatcher.return_503(self.dispatcher),
        '{"messages": [{"_links": {"self": {"href": "%s"}}, "message"'\
        ': "LITP is in maintenance mode", "type": '\
        '"ServerUnavailableError"}], "_links": {"self": {"href": "%s"'\
        '}}}' % (cherrypy.url(), cherrypy.url()))
