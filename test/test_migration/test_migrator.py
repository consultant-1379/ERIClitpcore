import unittest
from litp.migration.migrator import Migrator
from litp.migration import BaseMigration
from litp.migration.operations import AddCollection, AddRefCollection
import os
import logging
import logging.config
import argparse
import cherrypy
import platform
import sys
import shutil
from mock import Mock, call
from time import gmtime, strftime
from litp.core.model_manager import ModelManager
from litp.core.model_container import ModelItemContainer
from litp.core.model_type import Child, Collection, RefCollection
from litp.core.model_type import PropertyType, ItemType, Property, Reference
from litp.core.model_item import ModelItem, CollectionItem, RefCollectionItem
from litp.core.plugin_manager import PluginManager
from litp.core.extension_info import ExtensionInfo

class MockModelManager(ModelManager):
    def update_properties(self, item, properties):
        item.properties.update(properties)

    def query(self, *args, **kwargs):
        return []

    def find_modelitems(self, *args, **kwargs):
        return []


class MockMigration(BaseMigration):
    version = '1.2.4'
    operations = [
        AddCollection('software', 'test_items', 'test_item_type'),
        AddRefCollection('software', 'test_ref_items', 'test_ref_item_type'),
    ]


class MockModelItem(object):
    properties = {}

    def set_property(self, name, value):
        self.properties[name] = value

    def get_vpath(self):
        return "/model/item/path"

    def update_properties(self, properties):
        self.properties.update(properties)


class TestMigrator(unittest.TestCase):
    def setUp(self):
        self.model_manager = self._model_manager(
            MockModelManager, self._get_item_types())
        self.data_manager = self.model_manager.data_manager
        self._reload_data_with_one_package()

        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: [("mock_extension",
                        "test_migration.MockPlugin",
                        "1.2.3"),
                       ("mock_extension_no_migration",
                        "test_litp.MockPlugin",
                        "1.2.3"),
                       ]

        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)

    def _reload_data_with_one_package(self, mm=None):
        if mm is None:
            mm = self.model_manager

        mm.data_manager.session.query(ExtensionInfo).delete()
        mm.data_manager.session.query(ModelItem).delete()

        extension_info = ExtensionInfo(
            "mock_extension", "test_migration.mock_ext.MockExtension", "1.2.4")
        mm.data_manager.add_extension(extension_info)

        it = mm.item_types

        items = []

        item = ModelItem(mm, it["root"], "", None)
        items.append(item)

        item = ModelItem(mm, it["software"], "software", "/")
        items.append(item)

        item = CollectionItem(mm, it["software-item"], "items", "/software")
        items.append(item)

        item = ModelItem(mm, it["package"], "pkg1", "/software/items", {
            "version": "1.2.3",
            "ensure": "installed",
            "name": "vim"
        })
        items.append(item)

        item = ModelItem(mm, it["software"], "software_reference", "/")
        item._source_vpath = "/software"
        items.append(item)

        item = CollectionItem(mm, it["software-item"], "items", "/software_reference")
        item._source_vpath = "/software/items"
        items.append(item)

        item = ModelItem(mm, it["package"], "pkg1", "/software_reference/items", {
            "version": "666"
        })
        item._source_vpath = "/software/items/pkg1"
        items.append(item)

        for item in items:
            mm.data_manager.model.add(item)

    def _reload_data_with_multiple_packages(self, mm=None):
        if mm is None:
            mm = self.model_manager

        mm.data_manager.session.query(ExtensionInfo).delete()
        mm.data_manager.session.query(ModelItem).delete()

        extension_info = ExtensionInfo(
            "mock_extension", "test_migration.mock_ext.MockExtension", "1.2.2")
        mm.data_manager.add_extension(extension_info)

        it = mm.item_types

        items = []

        item = ModelItem(mm, it["root"], "", None)
        items.append(item)

        item = ModelItem(mm, it["software"], "software", "/")
        items.append(item)

        item = CollectionItem(mm, it["software-item"], "items", "/software")
        items.append(item)

        item = ModelItem(mm, it["package"], "pkg1", "/software/items", {
            "version": "1.2.3",
            "ensure": "installed",
            "name": "vim1"
        })
        items.append(item)

        item = ModelItem(mm, it["package"], "pkg2", "/software/items", {
            "version": "1.2.3",
            "ensure": "installed",
            "name": "vim2"
        })
        items.append(item)

        item = ModelItem(mm, it["package"], "pkg3", "/software/items", {
            "version": "1.2.3",
            "ensure": "installed",
            "name": "vim3"
        })
        items.append(item)

        for item in items:
            mm.data_manager.session.add(item)

    def _get_items(self, model_manager):
        items = {}
        for item in model_manager.data_manager.model.query():
            items[item._vpath] = {
                "__type__": item.__class__.__name__,
                "item_id": item._item_id,
                "item_type_id": item._item_type_id,
                "parent": item._parent_vpath,
                "source": item._source_vpath,
                "properties": item._properties
            }
        return items

    def test_collections_migration(self):
        old_model_manager = self._model_manager(
            ModelManager, self._get_item_types())
        self._reload_data_with_one_package(old_model_manager)
        old_items = self._get_items(old_model_manager)

        new_model_manager = self._model_manager(
            ModelManager, self._get_new_item_types())
        self._reload_data_with_one_package(new_model_manager)
        new_items = self._get_items(new_model_manager)

        self.assertEquals(old_items, new_items)

        migration = MockMigration()
        migration.forwards(new_model_manager)

        new_items = self._get_items(new_model_manager)
        migration.forwards(new_model_manager)

        self.assertNotEqual(old_items, new_items)

        parent = new_model_manager.get_item("/software")
        coll_child = parent.test_items
        refColl_child = parent.test_ref_items
        self.assertTrue(isinstance(coll_child, CollectionItem))
        self.assertTrue(isinstance(refColl_child, RefCollectionItem))

        model_manager_after = new_model_manager

        self.assertTrue(model_manager_after.has_item('/software/test_items'))
        self.assertTrue(model_manager_after.has_item('/software/test_ref_items'))
        self.assertTrue(model_manager_after.has_item('/software_reference/test_items'))
        self.assertTrue(model_manager_after.has_item('/software_reference/test_ref_items'))
        self.assertTrue(model_manager_after.has_item('/software_reference/test_items'))
        self.assertTrue(model_manager_after.has_item('/software_reference/test_ref_items'))
        coll = model_manager_after.get_item("/software/test_items")
        ref = model_manager_after.get_item("/software/test_ref_items")
        source_coll = model_manager_after.get_item(
            model_manager_after.get_item("/software_reference/test_items").source_vpath)
        source_ref = model_manager_after.get_item(
            model_manager_after.get_item("/software_reference/test_ref_items").source_vpath)
        self.assertEquals(source_coll, coll)
        self.assertEquals(source_ref, ref)

    def _get_item_types(self):
        item_types = [
            ItemType(
                "root",
                item_description="root item for /.",
                software=Child("software", required=True),
                software_reference=Reference("software")
            ),
            ItemType(
                "software",
                item_description="/software root item contains software.",
                items=Collection("software-item"),
            ),
            ItemType(
                "software-item",
                item_description="Base software item.",
            ),
            ItemType(
                "package",
                extend_item="software-item",
                item_description="Package item.",
                name=Property(
                    "basic_string",
                    prop_description="name"),
                version=Property("basic_string",
                    prop_description="version"),
                ensure=Property("basic_string",
                    prop_description="ensure"),
            )
        ]
        return item_types

    def _get_new_item_types(self):
        """Return 'item_types' list with new ItemTypes added."""
        old_item_types = self._get_item_types()
        new_items = [
            ItemType(
                "software",
                item_description="/software root item contains software.",
                items=Collection("software-item"),
                test_items=Collection("test_item_type"),
                test_ref_items=RefCollection("test_ref_item_type")
            ),
            ItemType(
                "test_item_type",
                item_description="Test item type"
            ),
            ItemType(
                "test_ref_item_type",
                item_description="Test item type"
            ),
            ItemType(
                "has_reference_item_type",
                item_description="Test item type",
                test_reference=Reference("test_ref_item_type")
            )
        ]
        for item in old_item_types:
            if item.item_type_id == "software":
                old_item_types.remove(item)
        new_item_types = old_item_types + new_items
        return new_item_types

    def _model_manager(self, cls, item_types):
        property_types= [
            PropertyType("basic_string"),
        ]
        model_manager = cls()
        for property_type in property_types:
            model_manager.register_property_type(property_type)
        for item_type in item_types:
            model_manager.register_item_type(item_type)
        return model_manager

    def test_get_current_extensions(self):
        current_extensions = self.migrator.current_extensions
        self.assertEquals(dict, type(current_extensions))
        self.assertTrue('mock_extension' in current_extensions.keys())
        self.assertEquals([1, 2, 4, 0, ''],
                        current_extensions['mock_extension']['version'])
        self.assertEquals('test_migration.mock_ext.MockExtension',
                        current_extensions['mock_extension']['classpath'])

    def test_get_current_extensions_when_no_save_file(self):
        self.data_manager.session.query(ExtensionInfo).delete()
        current_extensions = self.migrator.get_persisted_extensions()
        self.assertEquals(dict, type(current_extensions))
        self.assertTrue('mock_extension' in current_extensions.keys())
        self.assertEquals([1, 2, 3, 0, ''],
                        current_extensions['mock_extension']['version'])
        self.assertEquals('test_migration.MockPlugin',
                        current_extensions['mock_extension']['classpath'])

    def test_get_current_extensions_when_no_save_file_or_new_extensions(self):
        self.data_manager.session.query(ExtensionInfo).delete()
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: []
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        current_extensions = self.migrator.get_persisted_extensions()
        self.assertEquals({}, current_extensions)

    def test_get_current_version_for_ext(self):
        self.assertEquals([1, 2, 4, 0, ''],
                          self.migrator.get_current_version_for_ext(
                                                    'mock_extension'))

    def test_get_current_version_for_an_invalid_ext(self):
        self.assertEquals(None,
                          self.migrator.get_current_version_for_ext(
                                                    'not_an_extension'))

    def test_new_extensions(self):
        new_extensions = self.migrator.new_extensions
        self.assertTrue('mock_extension' in new_extensions.keys())
        self.assertEquals([1, 2, 3, 0, ''],
                        new_extensions['mock_extension']['version'])
        self.assertEquals('test_migration.MockPlugin',
                        new_extensions['mock_extension']['classpath'])

    def test_get_current_extensions_when_no_extensions(self):
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: []
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        new_extensions = self.migrator.get_installed_extensions()
        self.assertEquals({}, new_extensions)

    def test_get_new_version_for_ext(self):
        self.assertEquals([1, 2, 3, 0, ''],
             self.migrator.get_new_version_for_ext('mock_extension'))

    def test_get_new_version_for_an_invalid_ext(self):
        self.assertEquals(None,
                          self.migrator.get_new_version_for_ext(
                                                    'not_an_extension'))

    def test_migration_required_negative(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], [1, 2, 4], [1, 2, 2])
        self.assertEquals(None, direction)

    def test_migration_required_negative_equal_versions(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], [1, 2, 3], [1, 2, 3])
        self.assertEquals(None, direction)

    def test_migration_required_negative_equal_to_versions(self):
        direction = self.migrator.migration_required(
            [1, 2, 4], [1, 2, 3], [1, 2, 3])
        self.assertEquals(None, direction)

    def test_migration_required_negative_equal_from_versions(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], [1, 2, 4], [1, 2, 3])
        self.assertEquals(None, direction)

    def test_migration_required_forwards(self):
        direction = self.migrator.migration_required(
            [1, 2, 1], [1, 2, 3], [1, 2, 2])
        self.assertEquals('forwards', direction)

    def test_migration_required_forwards_matching_to_version(self):
        direction = self.migrator.migration_required(
            [1, 2, 1], [1, 2, 3], [1, 2, 3])
        self.assertEquals('forwards', direction)

    def test_migration_required_backwards(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], [1, 2, 1], [1, 2, 2])
        self.assertEquals('backwards', direction)

    def test_migration_required_backwards_matching_from_version(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], [1, 2, 1], [1, 2, 3])
        self.assertEquals('backwards', direction)

    def test_migration_required_is_none_when_from_version_is_none(self):
        direction = self.migrator.migration_required(
            None, [1, 2, 3], [1, 2, 3])
        self.assertEquals(None, direction)

    def test_migration_required_is_none_when_to_version_is_none(self):
        direction = self.migrator.migration_required(
            [1, 2, 3], None, [1, 2, 3])
        self.assertEquals(None, direction)

    def test_load_migrations(self):
        self.migrator.load_migrations()
        self.assertTrue('mock_extension' in self.migrator.migrations.keys())
        self.assertEquals(2, len(self.migrator.migrations['mock_extension']))
        self.assertTrue(isinstance(
            self.migrator.migrations['mock_extension'][0], BaseMigration))

    def test_load_migrations_when_no_new_extensions(self):
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: []
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        self.migrator.current_extensions = \
            self.migrator.get_persisted_extensions()
        self.migrator.new_extensions = self.migrator.get_installed_extensions()
        self.migrator.load_migrations()
        self.assertEquals({}, self.migrator.migrations)

    def test_apply_migrations_backwards_no_operations(self):
        self.migrator.model_manager.item_types = dict()
        for it in self._get_item_types():
            self.migrator.model_manager.item_types[it.item_type_id] = it

        self.assertEquals({}, self.migrator.migrations)
        self.assertEquals(None, self.migrator.apply_migrations())
        self.assertTrue('mock_extension' in self.migrator.migrations.keys())

    def test_apply_migrations_no_migrations_required(self):
        self.migrator.model_manager.item_types = dict()
        for it in self._get_item_types():
            self.migrator.model_manager.item_types[it.item_type_id] = it

        self.assertEquals({}, self.migrator.migrations)
        self.assertEquals(None, self.migrator.apply_migrations())
        self.assertTrue('mock_extension' in self.migrator.migrations.keys())

    def test_apply_migrations_forwards_multiple_migrations(self):
        self._reload_data_with_multiple_packages()
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: [("mock_extension",
                        "test_migration.MockPlugin",
                        "1.2.5"),
                       ("mock_extension_no_migration",
                        "test_litp.MockPlugin",
                        "1.3.2"),
                       ]
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        mock_model_item1 = MockModelItem()
        mock_model_item2 = MockModelItem()
        self.model_manager.find_modelitems = lambda x: \
            [mock_model_item1, mock_model_item2]
        self.assertEquals({}, self.migrator.migrations)
        self.assertEquals(None, self.migrator.apply_migrations())
        self.assertTrue('mock_extension' in self.migrator.migrations.keys())
        self.assertEqual('abc', mock_model_item1.properties['prop1'])
        self.assertEqual('def', mock_model_item1.properties['prop2'])
        self.assertEqual('ghi', mock_model_item1.properties['prop3'])
        self.assertEqual('abc', mock_model_item2.properties['prop1'])
        self.assertEqual('def', mock_model_item2.properties['prop2'])
        self.assertEqual('ghi', mock_model_item2.properties['prop3'])

    def test_apply_migrations_exception_in_migration_operation(self):
        self._reload_data_with_multiple_packages()
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: [("mock_extension",
                        "test_migration.MockPlugin",
                        "1.2.5"),
                       ("mock_extension_no_migration",
                        "test_litp.MockPlugin",
                        "1.3.2"),
                       ]
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        mock_model_item1 = MockModelItem()

        def raise_exp(x, y):
            raise Exception("error...")

        mock_model_item1.update_properties = raise_exp
        self.model_manager.find_modelitems = lambda x: \
                    [mock_model_item1]
        self.assertEquals({}, self.migrator.migrations)
        self.assertRaises(Exception, self.migrator.apply_migrations)

    def test_apply_migrations_exception_in_migration_init(self):
        self._reload_data_with_multiple_packages()
        self.plugin_manager = PluginManager(self.model_manager)
        self.plugin_manager.read_ext_config = \
            lambda x: [("mock_extension2",
                        "test_migration.MockPlugin",
                        "1.2.5"),
                       ("mock_extension_no_migration",
                        "test_litp.MockPlugin",
                        "1.3.2"),
                       ]
        self.migrator = Migrator(
            os.path.dirname(__file__), self.model_manager, self.plugin_manager)
        self.assertEquals({}, self.migrator.migrations)
        self.assertRaises(Exception, self.migrator.apply_migrations)

    def test_upgrade_backup_snapshots(self):
        model_manager = ModelManager()
        data_manager = model_manager.data_manager

        model_manager.register_property_type(
                PropertyType("basic_string"))

        model_manager.register_item_type(
            ItemType("root",
                    snapshots=Collection("snapshot-base", max_count=1000),
                     name=Property("basic_string")))

        model_manager.register_item_type(
            ItemType(
                "snapshot-base",
                item_description="Blah",
                timestamp=Property('basic_string',
                            prop_description='Snapshot creation timestamp.',
                            required=False,
                            updatable_rest=False),
                active=Property('basic_string',
                            prop_description='Whether this is the active '\
                            'snapshot.',
                            required=False,
                            updatable_rest=False,
                            default='true')
            ))
        model_manager.create_root_item('root')
        model_manager.create_snapshot_item('snapshot')
        migrator = Migrator(
            os.path.dirname(__file__), model_manager, self.plugin_manager)

        data_manager.model.create_backup = Mock()
        migrator._upgrade_backup_snapshots()
        expected_calls = [
            call("snapshot")
        ]
        self.assertEquals(data_manager.model.create_backup.call_count, 1)
        self.assertEquals(data_manager.model.create_backup.call_args_list,
                expected_calls)

        data_manager.model.create_backup = Mock()
        self.assertFalse(data_manager.model.create_backup.called)
