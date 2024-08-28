import cherrypy
import json
import unittest

import litp.core.constants as constants
from litp.core.model_manager import ModelManager
from litp.core.execution_manager import ExecutionManager
from litp.core.plan import Plan
from litp.service.controllers import ItemController
from litp.core.model_type import ItemType, PropertyType
from litp.core.model_type import Child, Collection, RefCollection, Property, Reference

from mock import MagicMock, patch, PropertyMock
from base import Mock
import yum
import rpm

def _mock_run_command_negative(self, cmd, args, timeout):
    return 1, "", 'ERROR'

mock_get_litp_packages = (0,
                          '''ERIClitpbmcapi_CXP9030611
ERIClitpbootmgrapi_CXP9030523
ERIClitpbootmgr_CXP9030515
ERIClitpcbaapi_CXP9030830
ERIClitpcfg_CXP9030421
ERIClitpcli_CXP9030420
ERIClitpcore_CXP9030418
ERIClitpdocs_CXP9030557''',
                          '')
mock_yum_info_ret = (0, """Loaded plugins: post-transaction-actions, product-id, versionlock
3PP                                                                                                                                                                                                                  | 2.9 kB     00:00
LITP                                                                                                                                                                                                                 | 3.6 kB     00:00
OS                                                                                                                                                                                                                   | 2.9 kB     00:00
UPDATES                                                                                                                                                                                                              | 2.9 kB     00:00
Installed Packages
Name        : ERIClitpbmcapi_CXP9030611
Arch        : noarch
Version     : 1.8.1
Release     : 1
Size        : 4.2 k
Repo        : installed
From repo   : LITP
Summary     : litpbmcapi_CXP9030611
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP BMC plugin api

Name        : ERIClitpbootmgrapi_CXP9030523
Arch        : noarch
Version     : 1.10.1
Release     : 1
Size        : 6.5 k
Repo        : installed
From repo   : LITP
Summary     : litpbootmgrapi_CXP9030523
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP bootmgr plugin

Name        : ERIClitpbootmgr_CXP9030515
Arch        : noarch
Version     : 1.13.1
Release     : 1
Size        : 255 k
Repo        : installed
From repo   : LITP
Summary     : litpbootmgr_CXP9030515
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP bootmgr plugin

Name        : ERIClitpcbaapi_CXP9030830
Arch        : noarch
Version     : 1.9.3
Release     : 1
Size        : 16 k
Repo        : installed
From repo   : LITP
Summary     : litpcbaapi_CXP9030830
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP cba extension

Name        : ERIClitpcfg_CXP9030421
Arch        : noarch
Version     : 1.11.1
Release     : 1
Size        : 654
Repo        : installed
Summary     : litpcfg_CXP9030421
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description :

Name        : ERIClitpcli_CXP9030420
Arch        : noarch
Version     : 1.14.5
Release     : SNAPSHOT20141125143827
Size        : 78 k
Repo        : installed
From repo   : /ERIClitpcli_CXP9030420-1.14.5-SNAPSHOT
Summary     : litpcli_CXP9030420
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP client

Name        : ERIClitpcore_CXP9030418
Arch        : noarch
Version     : 1.14.27
Release     : SNAPSHOT20141125143002
Size        : 712 k
Repo        : installed
From repo   : /ERIClitpcore_CXP9030418-1.14.27-SNAPSHOT
Summary     : litpcore_CXP9030418
URL         : www.ericsson.com
License     : 2012 Ericsson AB All rights reserved
Description : LITP core modules

Name        : ERIClitpdocs_second_CXP9030557
Arch        : noarch
Version     : 1.13.173

Name        : ERIClitpdocs_CXP9030557
Arch        : noarch
Version     : 1.13.173
Release     : 1
Size        : 19 M
Repo        : installed
From repo   : LITP
Summary     : litpdocs_CXP9030557
URL         : www.ericsson.com
License     : 2013, Ericsson
Description :


""", '')

def mock_system_side_effects(*cmd):
    command = cmd[0][0]

    if 'yum --disablerepo=' in command:
        return mock_get_litp_packages
    elif 'yum info' in command:
        return mock_yum_info_ret

installed_packages = [
        {'name': 'ERIClitpbmcapi_CXP9030611', 'version': '1.8.1'},
        {'name': 'ERIClitpbootmgrapi_CXP9030523', 'version': '1.10.1'},
        {'version': '1.13.1', 'name': 'ERIClitpbootmgr_CXP9030515'},
        {'version': '1.9.3', 'name': 'ERIClitpcbaapi_CXP9030830'},
        {'version': '1.11.1', 'name': 'ERIClitpcfg_CXP9030421'},
        {'version': '1.14.5', 'name': 'ERIClitpcli_CXP9030420'},
        {'version': '1.14.27', 'name': 'ERIClitpcore_CXP9030418'},
        {'version': '1.13.173', 'name': 'ERIClitpdocs_second_CXP9030557'},
        {'version': '1.13.173', 'name': 'ERIClitpdocs_CXP9030557'}
]

class TestItemController(unittest.TestCase):

    def setUp(self):
        self.item_controller = ItemController()
        self.swp = cherrypy.request
        cherrypy.request.method = 'GET'
        cherrypy.request.headers = {}
        cherrypy.request.base = ''
        cherrypy.request.script_name = ''
        cherrypy.request.body = Mock()
        cherrypy.request.body.fp = Mock()

        model_manager = ModelManager()
        model_manager.register_property_type(PropertyType("basic_string"))
        model_manager.register_item_type(
            ItemType("item", name=Property("basic_string"))
        )
        model_manager.register_item_type(
            ItemType("system", name=Property("basic_string"))
        )
        model_manager.register_item_type(
            ItemType("infra", systems=Collection("system"),
                     item=Child("item"),
                     link=Reference("item"),
                     refs=RefCollection("item"))
        )
        model_manager.register_item_type(
            ItemType("root", infra=Child("infra", required=True),
                     my_child=Child("child"),
                     my_dependant=Child("dependant"))
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
        exec_manager = ExecutionManager(model_manager, None, None)

        cherrypy.config = {'model_manager': model_manager,
                           'execution_manager': exec_manager}

    def tearDown(self):
        cherrypy.request = self.swp

    def _createMockPackage(self, name, version, packager=''):
        pkg = {}
        pkg[rpm.RPMTAG_NAME] = name
        pkg[rpm.RPMTAG_VERSION] = version
        pkg[rpm.RPMTAG_PACKAGER] = packager
        return pkg

    def get_package_list_negative(self):
        packages = []
        pkg = self._createMockPackage("Boguspackage", '12.13.14')
        packages.append(pkg)
        return packages


    def get_package_list(self, return_list=installed_packages):
        packages = []
        for pkg in return_list:
            pkg = self._createMockPackage(pkg['name'], pkg['version'])
            packages.append(pkg)
        return packages

    def _create_json_item(self):
        data = {
            'id': "sys1",
            'type': 'system',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/infra/systems'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        #self.assertEquals(cherrypy.response.status, 201)
        return response

    def test_get_item(self):
        response = json.loads(self.item_controller.get_item('/'))
        self.assertEqual('root', response['item-type-name'])
        self.assertEqual('/', response['_links']['self']['href'])
        self.assertEqual(2, len(response['_links']))
        self.assertEqual('infra',
                            response['_embedded']['item'][0]['item-type-name'])
        self.assertEqual({'href': '/infra'},
                            response['_embedded']['item'][0]['_links']['self'])
        self.assertEqual('infra', response['_embedded']['item'][0]['id'])

    def _setup_ts(self, get_list_callable):
        tsmock = MagicMock()
        tsmock.dbMatch = MagicMock()
        tsmock.dbMatch.side_effect = get_list_callable
        rpm.TransactionSet = MagicMock(return_value=tsmock)

    def test_get_item_version_info(self):
        self._setup_ts(self.get_package_list)
        response = json.loads(self.item_controller.get_item('/'))

        self.assertEqual('1.14.27 CXP9030418 R1T27', response['version'])
        self.assertEqual([{'cxp': 'CXP9030611', 'packager': 'R1J01', 'version': '1.8.1', 'name': 'ERIClitpbmcapi'},
                          {'cxp': 'CXP9030523', 'packager': 'R1L01', 'version': '1.10.1', 'name': 'ERIClitpbootmgrapi'},
                          {'cxp': 'CXP9030515', 'packager': 'R1S01', 'version': '1.13.1', 'name': 'ERIClitpbootmgr'},
                          {'cxp': 'CXP9030830', 'packager': 'R1K03', 'version': '1.9.3', 'name': 'ERIClitpcbaapi'},
                          {'cxp': 'CXP9030421', 'packager': 'R1M01', 'version': '1.11.1', 'name': 'ERIClitpcfg'},
                          {'cxp': 'CXP9030420', 'packager': 'R1T05', 'version': '1.14.5', 'name': 'ERIClitpcli'},
                          {'cxp': 'CXP9030418', 'packager': 'R1T27', 'version': '1.14.27', 'name': 'ERIClitpcore'},
                          {'cxp': 'CXP9030557', 'packager': 'R1S173', 'version': '1.13.173', 'name': 'ERIClitpdocs_second'},
                          {'cxp': 'CXP9030557', 'packager': 'R1S173', 'version': '1.13.173', 'name': 'ERIClitpdocs'}],
                         response['litp-packages'])

    def test_get_item_version_info_negative(self):
        self._setup_ts(self.get_package_list_negative)
        response = json.loads(self.item_controller.get_item('/'))
        self.assertEqual('No version found', response['version'])
        self.assertEqual([], response['litp-packages'])

    def test_get_collection_item(self):
        response = json.loads(self.item_controller.get_item('/infra/systems'))
        self.assertEqual(response['item-type-name'], 'collection-of-system')
        self.assertEqual(response['id'], 'systems')
        self.assertEqual(
            response['_links']['collection-of']['href'], '/item-types/system')
        self.assertEqual(
            response['_links']['self']['href'], '/infra/systems')

    def test_get_refcollection_item(self):
        response = json.loads(self.item_controller.get_item('/infra/refs'))
        self.assertEqual(response['item-type-name'], 'ref-collection-of-item')
        self.assertEqual(response['id'], 'refs')
        self.assertEqual(
            response['_links']['ref-collection-of']['href'], '/item-types/item')
        self.assertEqual(
            response['_links']['self']['href'], '/infra/refs')

    def test_get_child_is_collection(self):
        response = json.loads(self.item_controller.get_item('/infra'))
        self.assertEquals(response['item-type-name'], 'infra')
        self.assertEquals(
            response['_embedded']['item'][1]['_links']['collection-of'],
            {'href': '/item-types/system'})
        self.assertEquals(response['_embedded']['item'][1]['id'], 'systems')

    def test_get_item_invalid_id(self):
        cherrypy.request.path_info = '/some_item'
        response = json.loads(self.item_controller.get_item('/some_item'))
        self.assertTrue('data' not in response)
        self.assertTrue('messages' in response)
        self.assertEquals(len(response['messages']), 1)
        err = response['messages'][0]
        self.assertEquals(
            err['message'], "Not found"
        )
        self.assertEquals(err["_links"]["self"]["href"],
                          cherrypy.request.path_info)
        self.assertEquals(err['type'], constants.INVALID_LOCATION_ERROR)

    def test_create_item(self):
        response = self._create_json_item()
        self.assertEquals(cherrypy.response.status, 201)
        self.assertEqual(response['item-type-name'], 'system')
        self.assertEqual(response['state'], 'Initial')
        self.assertEqual(response['id'], 'sys1')
        self.assertEqual(response['_links']['self']['href'],
                         '/infra/systems/sys1')
        self.assertEqual(response['properties'], {'name': 'SYS1'})

    def test_create_item_already_exists(self):
        self._create_json_item()
        data = {
            'id': "sys1",
            'type': 'system',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/infra/systems'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 409)
        self.assertEqual(response['item-type-name'], 'system')
        self.assertEqual(response['state'], 'Initial')
        self.assertEqual(response['id'], 'sys1')
        self.assertEqual(response['_links']['self']['href'],
                         '/infra/systems/sys1')
        self.assertEqual(response['properties'], {'name': 'SYS1'})
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems/sys1")
        self.assertEqual(err["message"],
                         "Item already exists in model: sys1")
        self.assertEqual(err["type"], constants.ITEM_EXISTS_ERROR)

    def test_create_item_invalid_properties(self):
        cherrypy.request.body.fp.read = lambda: "saghhs"
        cherrypy.request.path_info = '/'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.method = 'POST'
        response = json.loads(
            self.item_controller.create_json_item('/infra/systems')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                         "Payload is not valid JSON: saghhs")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_create_item_on_root(self):
        data = {
            'id': "sys1",
            'type': 'system',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        self.assertEqual(response["_links"]["self"]["href"], "/sys1")
        self.assertEqual(response["messages"][0]["message"],
            "'sys1' (type: 'system') is not an allowed child of /")
        self.assertEqual(response["messages"][0]["type"],
            constants.CHILD_NOT_ALLOWED_ERROR)

    def test_create_json_inherit(self):
        self._create_json_item()
        model_manager = cherrypy.config.get('model_manager')
        model_manager.create_item("item", "/infra/item", name="myitem")
        data = {
            'id': "link",
            'inherit': '/infra/item',
            'properties': {'name': 'mynewname'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/infra'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 201)
        self.assertEqual(response['item-type-name'], 'reference-to-item')
        self.assertEqual(response['state'], 'Initial')
        self.assertEqual(response['id'], 'link')
        self.assertEqual(response['_links']['self']['href'], '/infra/link')
        self.assertEqual(response['_links']['inherited-from']['href'], '/infra/item')
        self.assertEqual(response['_links']['item-type']['href'], '/item-types/item')
        self.assertEqual(response['properties'], {'name': 'mynewname'})
        self.assertEqual(response['properties-overwritten'], ['name'])

    def test_create_json_inherit_reference(self):
        model_manager = cherrypy.config.get('model_manager')
        model_manager.create_item("child", "/my_child", name="child")
        model_manager.create_item("dependant", "/my_dependant", name="depend1")
        data = {
            'id': "dependent_ref",
            'inherit': '/my_dependant',
            'properties': {}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/my_child'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 201)
        self.assertEqual(response['item-type-name'], 'reference-to-dependant')
        self.assertEqual(response['state'], 'Initial')
        self.assertEqual(response['id'], 'dependent_ref')
        self.assertEqual(response['_links']['self']['href'], '/my_child/dependent_ref')
        self.assertEqual(response['_links']['inherited-from']['href'], '/my_dependant')
        self.assertEqual(response['properties'], {'name': 'depend1'})

    def test_update_modelitem(self):
        self._create_json_item()

        new_data = {'properties': {'name': 'updated_SYS1'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems/sys1')
        )
        self.assertEquals(
            response['properties']['name'], 'updated_SYS1')
        self.assertEqual(cherrypy.response.status, 200)

    def test_update_item_collection(self):
        self._create_json_item()

        new_data = {'properties': {'name': 'updated_SYS1'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                         "Properties cannot be set on collections")
        self.assertEqual(err["type"], constants.PROP_NOT_ALLOWED_ERROR)

    def test_update_item_invalid_properties(self):
        self._create_json_item()

        cherrypy.request.body.fp.read = lambda: "saghhs"
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                         "Payload is not valid JSON: saghhs")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_update_item_no_properties(self):
        self._create_json_item()

        new_data = {}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                         "Properties must be specified for update")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_update_item_doesnt_exist(self):
        self._create_json_item()

        new_data = {'properties': {'name': 'updated_SYS1'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/sys')
        )
        self.assertEqual(cherrypy.response.status, 404)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/sys")
        self.assertEqual(err["message"],
                         "Not found")
        self.assertEqual(err["type"], constants.INVALID_LOCATION_ERROR)

    def test_update_item_fails(self):
        self._create_json_item()
        new_data = {'properties': {'hostname': "$$^&*$%"}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems/sys1')
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["message"],
                         '"hostname" is not an allowed property of system')
        self.assertEqual(err["type"], constants.PROP_NOT_ALLOWED_ERROR)
        self.assertEquals(
            response['properties']['name'], 'SYS1')

    def test_delete_item(self):
        self._create_json_item()
        cherrypy.request.path_info = '/infra/systems/sys1'
        cherrypy.request.method = 'DELETE'
        self.item_controller.delete_item(cherrypy.request.path_info)
        self.assertEqual(cherrypy.response.status, 200)

        cherrypy.request.method = 'GET'
        self.item_controller.get_item(cherrypy.request.path_info)
        self.assertEqual(cherrypy.response.status, 404)

    def test_delete_item_fails(self):
        self._create_json_item()
        cherrypy.request.path_info = '/infra/systems/sys2'
        cherrypy.request.method = 'DELETE'
        response = json.loads(self.item_controller.delete_item(
                                            cherrypy.request.path_info))
        self.assertEqual(cherrypy.response.status, 404)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems/sys2")
        self.assertEqual(err["message"], "Path not found")
        self.assertEqual(err["type"], constants.INVALID_LOCATION_ERROR)

    def test_create_json_item_instead_of_json_link(self):
        data = {
            'id': "link",
            'type': 'item',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        cherrypy.request.path_info = '/infra'
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEqual(cherrypy.response.status, 422)
        self.assertEqual(len(response["messages"]), 1)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra")
        self.assertEqual(err["message"], "'link' must be an inherited item")
        self.assertEqual(err["type"], constants.CHILD_NOT_ALLOWED_ERROR)

    def mock_is_plan_running(self):
        return True

    def mock_is_plan_stopping(self):
        return True

    def test_create_json_item_with_plan_running(self):

        exec_mngr = cherrypy.config["execution_manager"]
        exec_mngr.is_plan_running = self.mock_is_plan_running
        exec_mngr.is_plan_stopping = self.mock_is_plan_stopping
        data = {
            'id': "sys1",
            'type': 'system',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/infra/systems'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 422)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                 "Operation not allowed while plan is running/stopping")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_create_json_link_with_plan_running(self):

        exec_mngr = cherrypy.config["execution_manager"]
        exec_mngr.plan = Plan([], [])
        exec_mngr.plan.set_ready()
        exec_mngr.plan.run()
        data = {
            'id': "link",
            'link': 'item',
            'properties': {'name': 'SYS1'}
        }
        cherrypy.request.body.fp.read = lambda: json.dumps(data)
        cherrypy.request.path_info = '/infra/systems'
        cherrypy.request.method = 'POST'
        cherrypy.request.headers['Content-Type'] = 'application/json'
        response = json.loads(
            self.item_controller.create_json_item(cherrypy.request.path_info)
        )
        self.assertEquals(cherrypy.response.status, 422)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                 "Operation not allowed while plan is running/stopping")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_update_item_with_plan_running(self):
        exec_mngr = cherrypy.config["execution_manager"]

        self._create_json_item()

        exec_mngr.plan = Plan([], [])
        exec_mngr.plan.set_ready()
        exec_mngr.plan.run()

        new_data = {'properties': {'name': 'updated_SYS1'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'
        response = json.loads(
            self.item_controller.update_item('/infra/systems/sys1')
        )
        self.assertEquals(cherrypy.response.status, 422)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems")
        self.assertEqual(err["message"],
                 "Operation not allowed while plan is running/stopping")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_delete_item_with_plan_running(self):
        exec_mngr = cherrypy.config["execution_manager"]

        exec_mngr.plan = Plan([], [])
        exec_mngr.plan.set_ready()
        exec_mngr.plan.run()

        cherrypy.request.path_info = '/infra/systems/sys1'
        cherrypy.request.method = 'DELETE'
        response = json.loads(self.item_controller.delete_item(
                                                cherrypy.request.path_info))
        self.assertEquals(cherrypy.response.status, 422)
        err = response['messages'][0]
        self.assertEqual(err["_links"]["self"]["href"], "/infra/systems/sys1")
        self.assertEqual(err["message"],
                 "Operation not allowed while plan is running/stopping")
        self.assertEqual(err["type"], constants.INVALID_REQUEST_ERROR)

    def test_get_item_with_plan_running(self):
        exec_mngr = cherrypy.config["execution_manager"]
        exec_mngr.plan = Plan([], [])
        exec_mngr.plan.set_ready()
        exec_mngr.plan.run()

        response = json.loads(self.item_controller.get_item('/'))
        self.assertEqual(response['item-type-name'], 'root')
        self.assertEqual(response['_links']['self']['href'], '/')
        self.assertEqual(len(response['_links']), 2)
        self.assertEqual(response['_embedded']['item'][0]['item-type-name'],
                         'infra')
        self.assertEqual(response['_embedded']['item'][0]['_links']['self'],
                         {'href': '/infra'})
        self.assertEqual(response['_embedded']['item'][0]['id'], 'infra')

    def test_parse_recurse_depth(self):
        cherrypy.request.path_info = '/infra/refs'

        response_sz_zero = self.item_controller._parse_recurse_depth("0")
        response_sz_one = self.item_controller._parse_recurse_depth("1")
        response_sz_ten = self.item_controller._parse_recurse_depth("10")
        response_n_zero = self.item_controller._parse_recurse_depth(0)
        response_n_one = self.item_controller._parse_recurse_depth(1)
        response_n_ten = self.item_controller._parse_recurse_depth(10)
        response_sz_bad = self.item_controller._parse_recurse_depth("bad")
        response_o_none = self.item_controller._parse_recurse_depth(None)
        response_sz_none = self.item_controller._parse_recurse_depth("None")

        self.assertEqual(response_sz_zero, 0)
        self.assertEqual(response_sz_one, 1)
        self.assertEqual(response_sz_ten, 10)
        self.assertEqual(response_n_zero, 0)
        self.assertEqual(response_n_one, 1)
        self.assertEqual(response_n_ten, 10)
        self.assertEqual(response_sz_bad.to_dict(),
            {'message': 'Invalid value for recurse_depth',
             'uri': '/infra/refs',
             'error': 'InvalidRequestError'})
        self.assertEqual(response_o_none, 1)
        self.assertEqual(response_sz_none.to_dict(),
            {'message': 'Invalid value for recurse_depth',
             'uri': '/infra/refs',
             'error': 'InvalidRequestError'})

    def test_get_item_exception(self):
        # This will raise an exception when GETting /infra
        with patch('litp.core.model_item.ModelItem.get_state', side_effect=KeyError):
            response = None
            exception_seen = False
            try:
                exception_json = self.item_controller.get_item('/infra')
                response = json.loads(exception_json)
            except Exception as caught:
                exception_seen = True
            finally:
                self.assertFalse(exception_seen)
                self.assertTrue(isinstance(exception_json, str))
                self.assertTrue(0 < len(exception_json))

                self.assertEquals(cherrypy.response.status, 500)
                self.assertTrue('messages' in response)
                self.assertEqual(1, len(response['messages']))
                self.assertEqual("InternalServerError", response['messages'][0]['type'])
                self.assertEqual("An exception occurred while reading this item.", response['messages'][0]['message'])
                self.assertEqual({'href': '/infra'}, response['messages'][0]['_links']['self'])

    def test_post_item_exception(self):
        # This will raise an exception when POSTing the item
        with patch('litp.core.model_manager.ModelManager.create_item', side_effect=Exception):
            exception_seen = False
            try:
                response = self._create_json_item()
            except Exception as caught:
                exception_seen = True
            finally:
                self.assertFalse(exception_seen)
                self.assertEquals(cherrypy.response.status, 500)
                self.assertTrue('messages' in response)
                self.assertEqual(1, len(response['messages']))
                self.assertEqual("InternalServerError", response['messages'][0]['type'])
                self.assertEqual("An exception occurred while creating this item.", response['messages'][0]['message'])
                self.assertEqual({'href': '/infra/systems/sys1'}, response['messages'][0]['_links']['self'])

    def test_put_item_exception(self):
        self._create_json_item()

        new_data = {'properties': {'name': 'updated_SYS1'}}
        cherrypy.request.body.fp.read = lambda: json.dumps(new_data)
        cherrypy.request.method = 'PUT'

        # This will raise an exception when PUTting the item
        with patch('litp.core.model_manager.ModelManager.update_item', side_effect=Exception):
            exception_seen = False
            try:
                response = json.loads(
                    self.item_controller.update_item('/infra/systems/sys1')
                )
            except Exception as caught:
                exception_seen = True
            finally:
                self.assertFalse(exception_seen)
                self.assertEquals(cherrypy.response.status, 500)
                self.assertTrue('messages' in response)
                self.assertEqual(1, len(response['messages']))
                self.assertEqual("InternalServerError", response['messages'][0]['type'])
                self.assertEqual("An exception occurred while updating this item.", response['messages'][0]['message'])
                self.assertEqual({'href': '/infra/systems/sys1'}, response['messages'][0]['_links']['self'])

    def test_delete_item_exception(self):
        self._create_json_item()

        cherrypy.request.path_info = '/infra/systems/sys1'
        cherrypy.request.method = 'DELETE'

        # This will raise an exception when DELETing the item
        with patch('litp.core.model_item.ModelItem.get_state', side_effect=Exception):
            exception_seen = False
            try:
                response = json.loads(
                    self.item_controller.delete_item(cherrypy.request.path_info)
                )
            except Exception as caught:
                exception_seen = True
            finally:
                self.assertFalse(exception_seen)
                self.assertEquals(cherrypy.response.status, 500)
                self.assertTrue('messages' in response)
                self.assertEqual(1, len(response['messages']))
                self.assertEqual("InternalServerError", response['messages'][0]['type'])
                self.assertEqual("An exception occurred while deleting this item.", response['messages'][0]['message'])
                self.assertEqual({'href': '/infra/systems/sys1'}, response['messages'][0]['_links']['self'])
