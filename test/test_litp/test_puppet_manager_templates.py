import unittest
import mock

from litp.core.puppet_manager_templates import PuppetManagerTemplates, \
    clean_hostname
from litp.core.model_manager import ModelManager, QueryItem
from litp.core.puppet_manager import PuppetManager
from litp.core.model_type import PropertyType
from litp.core.model_type import ItemType
from litp.core.model_type import Property


class PuppetManagerTemplatesTest(unittest.TestCase):
    def setUp(self):
        self.model = ModelManager()
        self.manager = PuppetManager(self.model)
        self.templates = PuppetManagerTemplates(self.manager)
        self._setup_model_items()

    def _setup_model_items(self):
        self.model.register_property_type(PropertyType("basic_string"))
        self.model.register_item_type(ItemType("root",
            name=Property("basic_string",
                updatable_rest=True,
                updatable_plugin=True)
        ))
        self.model.create_root_item("root", "/root")
        self.root_query_item = QueryItem(self.model, self.model.query("root")[0])
        self.root_query_item._model_item.set_property('name', "MyTestName")

    def test_format_dict(self):
        self.assertEquals(
            'name => {\n        k2 => "val2",'
            '\n        key => "value"\n        }',
            self.templates._format_dict('name',
                                        {'key': 'value', 'k2': 'val2'})
        )
        self.assertEquals(
            '{\n        k2 => "val2",'
            '\n        key => "value"\n        }',
            self.templates._format_param(None,
                                         {'key': 'value', 'k2': 'val2'})
        )
        self.assertEquals(
            'name => {\n        k2 => "val2",'
            '\n        \'eth3.3\' => "value"\n        }',
            self.templates._format_dict('name',
                                        {'eth3.3': 'value', 'k2': 'val2'})
        )
        test_dict = {'interfaces':
                        {'bond0.835':
                            {'dns_name': 'node2',
                             'ip_address': '10.44.86.96'}}}

        self.assertEquals(
            'name => {\ninterfaces => {\n\'bond0.835\' => {'
            '\n        dns_name => "node2",\n        ip_address '
            '=> "10.44.86.96"\n        }\n        }\n        }',
            self.templates._format_dict('name',
                                        test_dict)
        )

    def test_format_list(self):
        list_values = ['value1', 'value2', 'value3', 'value4']
        self.assertEquals(
            'name => [\n        "value1",\n        "value2",'
            '\n        "value3",\n        "value4"\n        ]\n',
            self.templates._format_list('name', list_values)
        )
        self.assertEquals(
            '[\n        "value1",\n        "value2",'
            '\n        "value3",\n        "value4"\n        ]\n',
            self.templates._format_param(None, list_values)
        )
        self.assertEquals(
            'name => [\n        "value1",\n        "value2",'
            '\n        "value3",\n        "value4"\n        ]\n',
            self.templates._format_list('name', list_values)
        )

    def test_clean_host_name(self):
        self.assertEquals(
            '127_0_0_1',
            clean_hostname('127.0.0.1')
        )

    def test_format_param_name(self):
        self.assertEquals("'eth3.3'",
            self.templates._format_param_name("eth3.3")
        )
        self.assertEquals("eth0",
            self.templates._format_param_name("eth0")
        )

    def test_format_param_value(self):
        self.assertEquals("\"\"", self.templates._format_param_value(""))
        self.assertEquals("\"abc123\"", self.templates._format_param_value("abc123"))
        self.assertEquals("\"\\\"\"", self.templates._format_param_value("\""))

    def test_require_not_added_until_dependency_available(self):
        node = mock.Mock()
        node.item_type.item_type_id = 'node'
        task1 = mock.Mock()
        task1.unique_id = 'task1'
        task1._requires = set()
        task1._redundant_requires = set()
        task1.kwargs = dict()
        task2 = mock.Mock()
        task2.unique_id = 'task2'
        task2._requires = set(['task1'])
        task2._redundant_requires = set()
        task2.kwargs = dict()
        output = self.templates.create_node_pp(node, [task2],
                                               'ms1', 'vcs')
        for l in output.splitlines():
            if "require => [Class[\"task_task1\"]]" in l:
                self.fail()
        #  now it should be there
        output = self.templates.create_node_pp(node, [task2, task1], 'ms1', 'vcs')
        for l in output.splitlines():
            if "require => [Class[\"task_task1\"]]" in l:
                break
        else:
            self.fail()

    def test_no_redundant_requires_added(self):
        node = mock.Mock()
        node.item_type.item_type_id = 'node'
        task1 = mock.Mock()
        task1.unique_id = 'task1'
        task1._requires = set()
        task1._redundant_requires = set()
        task1.kwargs = dict()
        task2 = mock.Mock()
        task2.unique_id = 'task2'
        task2._requires = set(['task1'])
        task2._redundant_requires = set()
        task2.kwargs = dict()
        task3 = mock.Mock()
        task3.unique_id = 'task3'
        task3._requires = set(['task1','task2'])
        task3._redundant_requires = set()
        task3.kwargs = dict()
        output = self.templates.create_node_pp(node, [task3], 'ms1', 'vcs')
        for l in output.splitlines():
            if "require => [Class[\"task_task1\"]]" in l:
                self.fail()
        #  now it should be there
        output = self.templates.create_node_pp(node, [task3, task2, task1],
                                               'ms1', 'vcs')
        for l in output.splitlines():
            if "require => [Class[\"task_task1\"]]" in l:
                break
        else:
            self.fail()
