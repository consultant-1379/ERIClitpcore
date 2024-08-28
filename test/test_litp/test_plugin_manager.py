##############################################################################
# COPYRIGHT Ericsson AB 2013
#
# The copyright to the computer program(s) herein is the property of
# Ericsson AB. The programs may be used and/or copied only with written
# permission from Ericsson AB. or in accordance with the terms and
# conditions stipulated in the agreement/contract under which the
# program(s) have been supplied.
##############################################################################

import os
import sys
from unittest import TestCase
from ConfigParser import NoOptionError

from litp.core.model_manager import ModelManager
from litp.core.model_type import ItemType, Property, PropertyType
from litp.core.exceptions import DuplicatedPropertyTypeException
from litp.core.exceptions import DuplicatedItemTypeException
from litp.core.plugin_manager import PluginManager
from litp.core.exceptions import RegistryException


def get_submodule_paths(module_paths):
    '''
    Given a list of Python module paths, returns a generator of their
    component subpaths. Can be used when removing modules from sys.modules.

    Example:
    >>> print list(get_submodule_paths(['tools.text.stemmer', 'math.sigma']))
        ['tools', 'tools.text', 'tools.text.stemmer', 'math', 'math.sigma']
    '''
    for module_path in module_paths:
        module_path_parts = module_path.split('.')
        for i in range(len(module_path_parts)):
            yield '.'.join(module_path_parts[0: i + 1])


class MockModelManager(ModelManager):
    def register_item_type(self, item_type):
        self.item_types[item_type.item_type_id] = item_type


class PluginManagerTest(TestCase):
    def setUp(self):
        self.model_mgr = MockModelManager()
        self.plugin_mgr = PluginManager(self.model_mgr)

        self.base_path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)), 'plugin_manager')
        self.modules_path = os.path.join(self.base_path,
                'modules')
        self.modules_alt_path = os.path.join(self.base_path,
                'modules_alt')
        self.plugins_config_path = os.path.join(self.base_path,
                'conf', 'plugins')
        self.extensions_config_path = os.path.join(self.base_path,
                'conf', 'extensions')
        sys.path.append(self.modules_path)

    def tearDown(self):
        if self.modules_path in sys.path:
            sys.path.remove(self.modules_path)

        # Unload the plugin/extension modules in order to keep a fresh
        # version of sys.modules for PluginManager
        module_paths = ['plugins.a.b.c', 'plugins.d.e.f', 'plugins.g.h.i',
                'extensions.a.b.c', 'extensions.d.e.f', 'extensions.g.h.i']
        for submodule_path in get_submodule_paths(module_paths):
            if submodule_path in sys.modules:
                del sys.modules[submodule_path]

    def test_add_plugins(self):
        """
        Test importing multiple plugins from:
          conf/plugins/correct
          |-a.conf  --  TestAPlugin v1.0, class=plugins.a.b.c.APlugin
          |-b.conf  --  TestBPlugin v1.0, class=plugins.d.e.f.BPlugin
          |-c.conf  --  TestCPlugin v1.0, class=plugins.g.h.i.CPlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'correct')

        self.plugin_mgr.add_plugins(config_path)

        from plugins.a.b.c import APlugin
        from plugins.d.e.f import BPlugin
        from plugins.g.h.i import CPlugin
        self.assertEquals([('TestBPlugin', BPlugin()),
                           ('TestCPlugin', CPlugin()),
                           ('TestAPlugin', APlugin())],
                          [x for x in self.plugin_mgr.iter_plugins()])
        self.assertEquals([{'name': 'TestBPlugin',
                            'class': 'plugins.d.e.f.BPlugin',
                            'version': '1.0',
                            'cls': BPlugin},
                           {'name': 'TestCPlugin',
                            'class': 'plugins.g.h.i.CPlugin',
                            'version': '1.0',
                            'cls': CPlugin},
                           {'name': 'TestAPlugin',
                            'class': 'plugins.a.b.c.APlugin',
                            'version': '1.0',
                            'cls': APlugin}],
                          self.plugin_mgr.get_plugins())

    def test_add_plugins_duplicate_names(self):
        """
        Test importing multiple plugins with the same name from:
          conf/plugins/duplicate_names
          |-a.conf  --  TestAPlugin v1.0, class=plugins.a.b.c.APlugin
          |-b.conf  --  TestBPlugin v1.0, class=plugins.d.e.f.BPlugin
          |-c.conf  --  TestAPlugin v1.0, class=plugins.g.h.i.CPlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'duplicate_names')

        self.assertRaises(RegistryException,
                self.plugin_mgr.add_plugins, config_path)

    def test_add_plugins_duplicate_classes(self):
        """
        Test importing multiple plugins with the same class from:
          conf/plugins/duplicate_classes
          |-a.conf  --  TestAPlugin v1.0, class=plugins.a.b.c.APlugin
          |-b.conf  --  TestBPlugin v1.0, class=plugins.d.e.f.BPlugin
          |-c.conf  --  TestCPlugin v1.0, class=plugins.a.b.c.APlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'duplicate_classes')

        self.assertRaises(RegistryException,
                self.plugin_mgr.add_plugins, config_path)

    def test_add_plugins_no_conf_file(self):
        """
        Test if files different than *.conf are ommitted:
          conf/plugins/no_conf_file
          |-a.cnf     --  TestAPlugin v1.0, class=plugins.a.b.c.APlugin
          |-b.config  --  TestBPlugin v1.0, class=plugins.d.e.f.BPlugin
          |-c.cfg     --  TestCPlugin v1.0, class=plugins.g.h.i.CPlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'no_conf_file')

        self.plugin_mgr.add_plugins(config_path)
        # No module should be imported -> mgr._plugins should be an empty dict.
        self.assertEqual([], [x for x in self.plugin_mgr.iter_plugins()])

    def test_add_plugins_no_inheritance(self):
        """
        Test if plugin classes that do not inherit from Plugin are ommited:
          conf/plugins/no_inheritance
          |-a.conf  --  TestNoInheritancePlugin v1.0,
                        class=plugins.a.b.c.NoInheritancePlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'no_inheritance')

        self.plugin_mgr.add_plugins(config_path)
        self.assertEqual([], [x for x in self.plugin_mgr.iter_plugins()])

    def test_add_plugins_import_error(self):
        """
        Verify that ImportError is raised when importing a module from a
        non-existent path:
          conf/plugins/import_error
          |-a.conf  --  TestAPlugin v1.0,
                        class=plugins.non.existent.path.APlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'import_error')

        self.assertRaises(ImportError,
                          self.plugin_mgr.add_plugins,
                          config_path)

    def test_add_plugins_attribute_error(self):
        """
        Verify that AttributeError is raised when importing a class from a
        non-existent path:
          conf/plugins/attribute_error
          |-a.conf  --  TestAPlugin v1.0,
                        class=plugins.a.b.c.NonExistentPlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'attribute_error')

        self.assertRaises(AttributeError,
                          self.plugin_mgr.add_plugins,
                          config_path)

    def test_add_plugins_no_option_in_config(self):
        """
        Verify if NoOptionError is raised when reading a plugin config
        file with missing properties:
          conf/plugins/no_option_in_config
          |-a.conf  --  <name property not present> v1.0,
                        class=plugins.a.b.c.APlugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'no_option_in_config')

        self.assertRaises(NoOptionError,
                          self.plugin_mgr.add_plugins,
                          config_path)

    def test_add_plugins_reloading_module(self):
        """
        Verify that modules are reloaded when needed while adding plugins:
          conf/plugins/reloading_module_1
          |-a.conf  --  TestAPlugin v1.0,
                        class=plugins.a.b.c.Aplugin

          conf/plugins/reloading_module_2
          |-a.conf  --  TestAPlugin v1.0,
                        class=plugins.a.b.c.Bplugin
        """

        config_path = os.path.join(
                self.plugins_config_path, 'reloading_module_1')

        self.plugin_mgr.add_plugins(config_path)

        from plugins.a.b.c import APlugin
        self.assertEquals([('TestAPlugin', APlugin())],
                          [x for x in self.plugin_mgr.iter_plugins()])
        self.assertEquals([{'name': 'TestAPlugin',
                            'class': 'plugins.a.b.c.APlugin',
                            'version': '1.0',
                            'cls': APlugin}],
                          self.plugin_mgr.get_plugins())

        # Replace the contents of plugins.a.b.c so that it defines BPlugin
        for submodule_path in get_submodule_paths(['plugins.a.b.c']):
            del sys.modules[submodule_path]
        sys.path.remove(self.modules_path)
        sys.path.append(self.modules_alt_path)
        import plugins.a.b.c
        sys.path.remove(self.modules_alt_path)

        config_path = os.path.join(
                self.plugins_config_path, 'reloading_module_2')

        self.plugin_mgr.add_plugins(config_path)

        from plugins.a.b.c import BPlugin
        self.assertEquals([('TestBPlugin', BPlugin()),
                           ('TestAPlugin', APlugin())],
                          [x for x in self.plugin_mgr.iter_plugins()])
        self.assertEquals([{'name': 'TestBPlugin',
                            'class': 'plugins.a.b.c.BPlugin',
                            'version': '1.0',
                            'cls': BPlugin},
                           {'name': 'TestAPlugin',
                            'class': 'plugins.a.b.c.APlugin',
                            'version': '1.0',
                            'cls': APlugin}],
                          self.plugin_mgr.get_plugins())

    def test_ensure_unique_properties(self):
        '''
        Confirm that a DuplicatedPropertyTypeException is raised when
        ensuring that non unique properties are unique.
        '''
        property_types_by_id = {'first_prop': PropertyType("prop",
                                                           regex="^[a-z]")
                                }
        extension_property_types = [PropertyType("prop", regex="^[A-Z]")]
        try:
            self.plugin_mgr.ensure_unique_properties(
                "mock_extension",
                property_types_by_id, extension_property_types)
        except Exception as e:
            self.fail(e)
        self.assertRaises(DuplicatedPropertyTypeException,
                          self.plugin_mgr.ensure_unique_properties,
                          "mock_extension_numero_due",
                          property_types_by_id,
                          extension_property_types)

    def test_ensure_unique_item_types(self):
        '''
        Confirm that a DuplicatedItemTypeException is raised when
        ensuring that non unique item types are unique.
        '''
        self.model_mgr.register_property_type(PropertyType("basic_string"))
        item_1 = ItemType("test_item1", name=Property("basic_string"))
        item_2 = ItemType("test_item2", name=Property("basic_string"),
                          value=Property("basic_boolean"))
        self.model_mgr.register_item_type(item_1)
        self.model_mgr.register_item_type(item_2)

        item_types_by_id = {"test_item1": (item_1, "mock_extension"),
                            "test_item2": (item_2, "mock_extension")}
        extension_item_type = ItemType(
            "test_item3",
            name=Property("basic_string"),
            value=Property("basic_boolean"))
        try:
            self.plugin_mgr.ensure_unique_item_types(
                "test_extension",
                item_types_by_id, [extension_item_type])
        except Exception as e:
            self.fail(e)
        extension_item_type = ItemType(
            "test_item2",
            name=Property("basic_string"),
            value=Property("basic_boolean"))

        self.assertRaises(DuplicatedItemTypeException,
                          self.plugin_mgr.ensure_unique_item_types,
                          "mock_extension",
                          item_types_by_id,
                          [extension_item_type])

    def test_get_sorted_item_types(self):
        '''
        Test if item types are correctly sorted.
        '''
        self.model_mgr.register_property_type(PropertyType("basic_string"))
        item_3 = ItemType("test_item3",
                          extend_item="test_item1",
                          name=Property("basic_string"),
                          value=Property("basic_boolean"))
        item_1 = ItemType("test_item1", name=Property("basic_string"))
        item_2 = ItemType("test_item2", name=Property("basic_string"),
                          value=Property("basic_boolean"))
        item_types_by_id = {
            "test_item3": (item_3, "mock_extension"),
            "test_item1": (item_1, "mock_extension"),
            "test_item2": (item_2, "mock_extension")}

        self.assertEquals(
            [item_1, item_2, item_3],
            self.plugin_mgr.get_sorted_item_types(item_types_by_id))

    def test_add_extensions(self):
        """
        Test importing multiple extensions from:
          conf/extensions/correct
          |-a.conf  --  TestAExtension v1.0, class=extensions.a.b.c.AExtension
          |-b.conf  --  TestBExtension v1.0, class=extensions.d.e.f.BExtension
          |-c.conf  --  TestCExtension v1.0, class=extensions.g.h.i.CExtension
        """

        config_path = os.path.join(
                self.extensions_config_path, 'correct')

        self.plugin_mgr.add_extensions(config_path)

        self.assertTrue("TestAExtension" in
                        self.plugin_mgr._extensions._by_name)
        self.assertTrue("TestBExtension" in
                        self.plugin_mgr._extensions._by_name)
        self.assertTrue("TestCExtension" in
                        self.plugin_mgr._extensions._by_name)
