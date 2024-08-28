import unittest
import sys
import platform
import cherrypy
from mock import Mock, call, patch, MagicMock

from collections import namedtuple
from litp.core.plugin_info import PluginInfo
from litp.core.extension_info import ExtensionInfo
from litp.core.exceptions import DataIntegrityException
from litp.core.service import (
    update_plugins, check_model_item_types, OwnedWatchedFileHandler,
    check_python_and_linux_versions, setup_logging,
    cleanup_model_snapshot_datasets, _get_celery_conf
)
from litp.core.litp_logging import LitpLogger
from litp.core.constants import CELERY_USER, CELERY_GROUP
from litp.core.worker.celery_app import CELERY_DEFAULTS


log = LitpLogger()


def info_to_tuple(info):
    return (info.name, info.classpath, info.version)


def dict_to_tuple(d):
    return (d["name"], d["class"], d["version"])


class TestService(unittest.TestCase):
    def test_update_plugins(self):
        saved_plugins = [
            PluginInfo("p1", "litp.p1", "1"),
            PluginInfo("p2", "litp.p2", "1"),
            PluginInfo("p3", "litp.p3", "1")
        ]
        saved_extensions = [
            ExtensionInfo("e1", "litp.e1", "1"),
            ExtensionInfo("e2", "litp.e2", "1"),
            ExtensionInfo("e3", "litp.e3", "1")
        ]

        installed_plugins = [
            {
                "name": "p2",
                "class": "litp.p2",
                "version": "1"
            },
            {
                "name": "p3",
                "class": "litp.p3",
                "version": "2"
            },
            {
                "name": "p4",
                "class": "litp.p4",
                "version": "1"
            }
        ]

        installed_extensions = [
            {
                "name": "e2",
                "class": "litp.e2",
                "version": "1"
            },
            {
                "name": "e3",
                "class": "litp.e3",
                "version": "2"
            },
            {
                "name": "e4",
                "class": "litp.e4",
                "version": "1"
            }
        ]

        data_manager = Mock()
        data_manager.get_plugins = Mock(return_value=saved_plugins)
        data_manager.get_extensions = Mock(return_value=saved_extensions)
        data_manager.add_plugin = Mock()
        data_manager.add_extension = Mock()
        data_manager.delete_plugin = Mock()
        data_manager.delete_extension = Mock()

        plugin_manager = Mock()
        plugin_manager.get_plugin_info = Mock(return_value=installed_plugins)
        plugin_manager.get_extension_info = Mock(return_value=installed_extensions)

        update_plugins(data_manager, plugin_manager)

        # deleted plugin
        self.assertEquals(1, data_manager.delete_plugin.call_count)
        saved_plugin = info_to_tuple(saved_plugins[0])
        args, kwargs = data_manager.delete_plugin.call_args
        deleted_plugin = info_to_tuple(args[0])
        self.assertEquals(deleted_plugin, saved_plugin)

        # deleted extension
        self.assertEquals(1, data_manager.delete_extension.call_count)
        saved_extension = info_to_tuple(saved_extensions[0])
        args, kwargs = data_manager.delete_extension.call_args
        deleted_extension = info_to_tuple(args[0])
        self.assertEquals(deleted_extension, saved_extension)

        # added plugin
        self.assertEquals(1, data_manager.add_plugin.call_count)
        args, kwargs = data_manager.add_plugin.call_args
        added_plugin = info_to_tuple(args[0])
        installed_plugin = dict_to_tuple(installed_plugins[2])
        self.assertEquals(added_plugin, installed_plugin)

        # added extension
        self.assertEquals(1, data_manager.add_extension.call_count)
        args, kwargs = data_manager.add_extension.call_args
        added_extension = info_to_tuple(args[0])
        installed_extension = dict_to_tuple(installed_extensions[2])
        self.assertEquals(added_extension, installed_extension)

        # updated plugin
        saved_plugin = saved_plugins[2]
        installed_plugin = installed_plugins[1]
        self.assertEquals(saved_plugin.name, installed_plugin["name"])
        self.assertEquals(saved_plugin.classpath, installed_plugin["class"])
        self.assertEquals(saved_plugin.version, installed_plugin["version"])

        # updated extension
        saved_extension = saved_extensions[2]
        installed_extension = installed_extensions[1]
        self.assertEquals(saved_extension.name, installed_extension["name"])
        self.assertEquals(saved_extension.classpath, installed_extension["class"])
        self.assertEquals(saved_extension.version, installed_extension["version"])

        # non-updated plugin
        saved_plugin = saved_plugins[1]
        installed_plugin = installed_plugins[0]
        self.assertEquals(saved_plugin.name, installed_plugin["name"])
        self.assertEquals(saved_plugin.classpath, installed_plugin["class"])
        self.assertEquals(saved_plugin.version, installed_plugin["version"])

        # non-updated extension
        saved_extension = saved_extensions[1]
        installed_extension = installed_extensions[0]
        self.assertEquals(saved_extension.name, installed_extension["name"])
        self.assertEquals(saved_extension.classpath, installed_extension["class"])
        self.assertEquals(saved_extension.version, installed_extension["version"])

    def test_check_model_item_types(self):
        data_manager = Mock()
        model_manager = Mock()

        data_manager.get_model_item_type_ids = Mock(return_value=["a"])
        model_manager.item_types = {"a": None}

        try:
            check_model_item_types(data_manager, model_manager)
        except DataIntegrityException:
            self.fail()

        model_manager.item_types = {}
        self.assertRaises(DataIntegrityException, check_model_item_types, data_manager, model_manager)

    @patch('platform.dist', MagicMock())
    def test_check_python_and_linux_versions(self):
        log.trace.warn = MagicMock()

        # Positive RHEL case #1
        platform.dist.return_value = ('redhat', '6.6', 'Santiago')
        check_python_and_linux_versions()
        assert not log.trace.warn.called

        # Positive RHEL case #2
        platform.dist.return_value = ('redhat', '6.10', 'Santiago')
        check_python_and_linux_versions()
        assert not log.trace.warn.called

        # Positive RHEL case #3
        platform.dist.return_value = ('redhat', '7.9', 'Maipo')
        check_python_and_linux_versions()
        assert not log.trace.warn.called

        # Positive RHEL case #4
        platform.dist.return_value = ('centos', '7.9', 'Core')
        check_python_and_linux_versions()
        assert not log.trace.warn.called

        #Positive python case #1
        with patch.object(sys, 'version_info') as v_info:
            v_info = namedtuple('v_info', ['major', 'minor', 'micro', 'release', 'serial'])
            sys.version_info = (2, 7, 5, 'final', 0)
            check_python_and_linux_versions()
            assert not log.trace.warn.called

        #Positive python case #2
        with patch.object(sys, 'version_info') as v_info:
            v_info = namedtuple('v_info', ['major', 'minor', 'micro', 'release', 'serial'])
            sys.version_info = (2, 6, 6, 'final', 0)
            check_python_and_linux_versions()
            assert not log.trace.warn.called

        # Negative RHEL case
        platform.dist.return_value = ('redhat', '7.0', 'Santiago')
        check_python_and_linux_versions()
        log.trace.warn.assert_called_once_with("LITP is validated for RedHat versions 6.6, 6.10, 7.9. Your linux is redhat 7.0 Santiago")

        # Negative python case
        with patch.object(sys, 'version_info') as v_info:
            v_info = namedtuple('v_info', ['major', 'minor', 'micro', 'release', 'serial'])
            sys.version_info = (2, 5, 6, 'final', 0)
            check_python_and_linux_versions()
            log.trace.warn.assert_called_with("LITP is validated for python 2.6.x and python 2.7.x. Your version is 2.5.6")

    @patch('litp.core.service.getgrnam', Mock(return_value=Mock(gr_gid=0)))
    @patch('litp.core.service.getpwnam', Mock(return_value=Mock(pw_uid=1)))
    @patch('litp.core.service.OwnedWatchedFileHandler._open', MagicMock(return_value=MagicMock()))
    def test_setup_logging(self):
        setup_logging(MagicMock())
        expected_error_handler_attrs = { 'file_name' :
                                              '/var/log/litp/litpd_error.log',
                                          'uid' : 1,
                                          'gid' : 0, }
        expected_access_handler_attrs = { 'file_name' :
                                            '/var/log/litp/litpd_access.log',
                                         'uid' : 1,
                                         'gid' : 0, }

        def get_file_handler_from_logger(logger):
            for handler in logger.handlers:
                if isinstance(handler, OwnedWatchedFileHandler):
                    file_handler_attrs = {'file_name': handler.baseFilename,
                                          'uid': handler.owner_id,
                                          'gid': handler.group_id}

                    return handler, file_handler_attrs
            return None, None

        access_handler, access_handler_attrs = get_file_handler_from_logger(cherrypy.log.access_log)
        error_handler, error_handler_attrs = get_file_handler_from_logger(cherrypy.log.error_log)

        self.assertTrue(isinstance(access_handler, OwnedWatchedFileHandler))
        self.assertEquals(expected_access_handler_attrs, access_handler_attrs)
        self.assertTrue(isinstance(error_handler, OwnedWatchedFileHandler))
        self.assertEquals(expected_error_handler_attrs, error_handler_attrs)

    @patch('litp.core.service.getgrnam', Mock(return_value=Mock(gr_gid=0)))
    @patch('litp.core.service.getpwnam')
    @patch('litp.core.service.OwnedWatchedFileHandler._open',
           MagicMock(return_value=MagicMock()))
    @patch('litp.core.service.log')
    def test_setup_logging_exception(self, mock_log, mock_getpwnam):

        expected_error = KeyError("User doesnt exist")
        mock_getpwnam.side_effect = expected_error
        mock_log.trace.warning = MagicMock()
        try:
            setup_logging(MagicMock())
        except KeyError as e:
            self.assertEquals(expected_error, e)
            mock_log.trace.warning.assert_called_once_with(
                "Could not get group id for group {0} "
                "or user id for user {1}. {2}".
                    format(CELERY_GROUP, CELERY_USER, str(e)))

    def test_cleanup_model_snapshot_datasets(self):
        data_manager = Mock()
        model_manager = Mock()
        data_manager.model =  Mock()

        cleanup_model_snapshot_datasets(model_manager, data_manager)
        model_manager.assert_has_calls([call.query('snapshot-base')])
        self.assertEquals(1, data_manager.model.delete_snapshot_sets.call_count)


    def test_get_celery_conf(self):
        cherrypy_config = {'celery': {'BROKER_URL': 'amqp://litp:ptil@localhost:5672/%%2flitp',
                                                         'CELERY_RESULT_BACKEND': "db+postgresql+psycopg2://litp@'ms1':'5432'/litpcelery?sslmode=verify-full"}}
        celery = {'BROKER_URL': 'amqp://litp:ptil@localhost:5672/%%2flitp',
                  'CELERY_RESULT_BACKEND': "db+postgresql+psycopg2://litp@ms1:5432/litpcelery?sslmode=verify-full"}
        expected_conf = {}
        expected_conf.update(CELERY_DEFAULTS)
        expected_conf.update(celery)
        with patch.dict(cherrypy.config, cherrypy_config, clear=True):
            conf = _get_celery_conf()
        self.assertEquals(expected_conf, conf)
