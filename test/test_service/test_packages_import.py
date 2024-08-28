import cherrypy
import unittest

from litp.service.controllers import PackagesImportController
from mock import MagicMock, patch
from litp.plugins.core.core_plugin import CorePlugin
from litp.core.model_manager import ModelManager
from litp.core.model_type import PropertyType, Property, ItemType, Child, \
    Reference, RefCollection, Collection
from litp.core.validators import ValidationError
from litp.core.constants import INTERNAL_SERVER_ERROR
from litp.core.plugin_context_api import PluginApiContext
from litp.core.packages_import import (
    ModelProxy,
    SourcePath,
    DestinationPath,
    PackagesImport
)
from litp.core.rpc_commands import BaseRpcCommandProcessor,\
                                   reduce_errs

class MockPackagesImportController(object):
    def load(self, item_path, body_data, **kwargs):
        return []


class TestUpgradeController(unittest.TestCase):

    def setUp(self):
        self.import_controller = PackagesImportController()
        self.swp = cherrypy.request
        cherrypy.request = MagicMock()
        cherrypy.request.body = MagicMock()
        cherrypy.request.body.fp = MagicMock()
        cherrypy.request.body.fp.read = lambda: '{"source_path": "/trololo", "destination_path": "/trololo"}'
        cherrypy.request.path_info = ''
        cherrypy.request.method = 'PUT'
        cherrypy.request.headers = {'Content-Type': 'application/json'}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''

        self.plugin = CorePlugin()
        self.model = ModelManager()
        self.execution_manager = object()
        self.plugin_api_context = PluginApiContext(self.model)
        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_property_type(PropertyType("basic_list"))
        self.model.register_item_type(
            ItemType(
                "root",
                nodes=Collection("node"),
                ms=Child("ms"),
                cluster1=Child("cluster"),
                networks=Collection("network"),
             )
        )
        self.model.register_item_type(
            ItemType(
                "node",
                hostname=Property("basic_string"),
           )
        )
        self.model.register_item_type(
            ItemType(
                "ms",
                hostname=Property("basic_string"),
           )
        )
        self.model.register_item_type(
            ItemType(
                "network",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "model-item",
                name=Property("basic_string"),
            )
        )
        self.model.register_item_type(
            ItemType(
                "cluster",
                nodes=Collection('node'),
                services=Collection('clustered-service'),
            )
        )
        self.model.register_item_type(
            ItemType(
                "clustered-service",
                node_list=Property('basic_list'),
                dependency_list=Property('basic_list'),
            )
        )
        self.model.create_root_item("root")
        self.model.create_item("ms", "/ms", hostname="ms1")
        self.model.create_item("cluster", "/cluster1")
        self.model.create_item("node", "/cluster1/nodes/node1",
                hostname="foo")

    def tearDown(self):
        cherrypy.request = self.swp

    def test_import_with_running_plan(self):
        em = MagicMock()
        em.is_plan_running.return_value = True
        cherrypy.config = {
            'model_manager': MagicMock(),
            'execution_manager': em,
            'import_loader': PackagesImportController()
        }
        self.assertEqual('{"messages": [{"type": "InvalidRequestError", "message": "Operation not allowed while plan is running/stopping", "_links": {"self": {"href": ""}}}], "_links": {"self": {"href": ""}}}',
                         self.import_controller.handle_import())
        self.assertEqual(422, cherrypy.response.status)

    @patch('litp.core.packages_import.PackagesImport')
    def test_import_with_not_running_plan(self, mock_import):
        em = MagicMock()
        em.is_plan_running.return_value = False
        cherrypy.config = {
            'model_manager': MagicMock(),
            'execution_manager': em,
            'import_loader': PackagesImportController()
        }
        mock_import.run_import = MagicMock()
        self.import_controller.handle_import()
        mock_import.run_import.called_once_with(None)

    def test_rsync_packages_without_errors(self):

        packages_import = self._create_package_import_object()
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.return_value = \
        {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 0,
                            'err': ''
                            },
                   'errors': ''
                   },
        }, []
        packages_import._rsync_packages(packages_import.model_manager.get_ms_node())

    def test_rsync_packages_with_errors(self):

        packages_import = self._create_package_import_object()
        outputs = [
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : ['error 1']}),
        # Std error
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : [""], '2' : ["Non-determined error"]})
        ]
        # Abnormal error (from internal layers)
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.side_effect = \
            outputs
        outputs[1][1]["1"] = packages_import._add_default_msg_to_errors(outputs[1][1]["1"])
        self.assertEqual([ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="rsync failed with message: error 1")],
        packages_import._rsync_packages(packages_import.model_manager.get_ms_node()))

    def test_clean_yum_cache_without_errors(self):

        packages_import = self._create_package_import_object()
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result = MagicMock()
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.return_value = \
        {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 0,
                            'err': ''
                            },
                   'errors': ''
                   },
        }, []
        packages_import._clean_yum_cache(packages_import.model_manager.get_all_nodes())

    def test_clean_yum_cache_with_errors(self):

        packages_import = self._create_package_import_object()
        outputs = [
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : ['error 1']}),
# Std error
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : [""], '2' : ["Non-determined error"]})
        ]
# Abnormal error (from internal layers)
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.side_effect = \
            outputs
        self.assertEqual([ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="clean cache failed with message: %s" %
                        outputs[0][1]["1"][0])],
        packages_import._clean_yum_cache(packages_import.model_manager.get_all_nodes()))
        outputs[1][1]["1"] = packages_import._add_default_msg_to_errors(outputs[1][1]["1"])
        self.assertEqual([ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="clean cache failed with message: %s" %
                        error) for error in reduce_errs(outputs[1][1])],
        packages_import._clean_yum_cache(packages_import.model_manager.get_all_nodes()))

    def test_create_repo_without_errors(self):

        packages_import = self._create_package_import_object()
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.return_value = \
        {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 0,
                            'err': ''
                            },
                   'errors': ''
                   },
        }, []
        packages_import._create_repo(packages_import.model_manager.get_ms_node())

    def test_create_repo_with_errors(self):

        packages_import = self._create_package_import_object()
        outputs = [
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : ['error 1']}),
# Std error
        (
            {"node1": {'data': {'out': "/dev/vg_root/lv_test1 10g owi-aos--\n" +
                                   "/dev/vg_root/lv_test2 20g owi-aos--",
                            'status': 1,
                            'err': 'error'
                            },
                   'errors': 'error 1'
                   },
        }, {'1' : [""], '2' : ["Non-determined error"]})
        ]
# Abnormal error (from internal layersear
        
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result.side_effect = \
            outputs
        self.assertEqual([ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="createrepo failed with message: %s" %
                        outputs[0][1]["1"][0])],
        packages_import._create_repo(packages_import.model_manager.get_ms_node()))
        outputs[1][1]["1"] = packages_import._add_default_msg_to_errors(outputs[1][1]["1"])
        self.assertEqual([ValidationError(error_type=INTERNAL_SERVER_ERROR,
                        item_path='/import',
                        error_message="createrepo failed with message: %s" %
                        error) for error in reduce_errs(outputs[1][1])],
        packages_import._create_repo(packages_import.model_manager.get_ms_node()))

    def _create_package_import_object(self):
        self.execution_manager = MagicMock()
        self.execution_manager.model_manager = self.model
        source_path = SourcePath("/tmp/")
        destination_path = DestinationPath("os")

        packages_import = PackagesImport(
            source_path,
            destination_path,
            self.execution_manager)

        packages_import.base_rpc_command_proc = MagicMock()
        packages_import.base_rpc_command_proc.execute_rpc_and_process_result = MagicMock()
        return packages_import
